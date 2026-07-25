"""Implementación de su agente.

Completen `register_tool` y `run` para el Milestone 1.
En el Milestone 2 amplíen `MyAgent` para que sea estatal y respete
`max_history_messages`.

Los tests de conformidad en `tests/conformance/test_m1.py` y
`test_m2.py` describen con precisión qué comportamientos deben funcionar
— léanlos antes de empezar.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from mia_agents.protocols import LLMClient
from mia_agents.tool_schema import FINAL_RESULT_TOOL_NAME, final_result_tool_schema
from mia_agents.types import AgentResult, AgentStep, ToolSchema


class MyAgent:
    def __init__(
        self,
        llm_client: LLMClient,
        system_prompt: str = "Sos un agente muy eficiente hincha de River",
        max_iterations: int = 20,
        max_history_messages: int = 100,
    ) -> None:
        """Inicializa el agente."""
        self._llm = llm_client
        self._system = system_prompt
        self._max_iterations = max_iterations
        self._max_history_messages = max_history_messages

        self._tools: dict[str, Callable[..., str]] = {}
        self._schemas: dict[str, ToolSchema] = {}
        self._conversation_history: list[dict[str, Any]] = []

    def _trim_history(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._max_history_messages is None or self._max_history_messages <= 0:
            return []
        return messages[-self._max_history_messages :]

    def _append_history(self, message: dict[str, Any]) -> None:
        self._conversation_history.append(message)
        self._conversation_history = self._trim_history(self._conversation_history)

    def register_tool(
        self,
        tool: Callable[..., str],
        schema: ToolSchema,
    ) -> None:
        """Registra una herramienta callable junto a su esquema."""
        self._tools[schema.name] = tool
        self._schemas[schema.name] = schema

    def run(self, user_message: str) -> AgentResult:
        self._append_history({"role": "user", "content": user_message})
        steps: list[AgentStep] = []
        total_input_tokens: int | None = None
        total_output_tokens: int | None = None

        for _ in range(self._max_iterations):
            messages = self._trim_history(self._conversation_history)
            response = self._llm.chat(
                messages=messages,
                tools=list(self._schemas.values()),
                system=self._system,
            )

            if response.input_tokens is not None:
                total_input_tokens = (
                    response.input_tokens
                    if total_input_tokens is None
                    else total_input_tokens + response.input_tokens
                )
            if response.output_tokens is not None:
                total_output_tokens = (
                    response.output_tokens
                    if total_output_tokens is None
                    else total_output_tokens + response.output_tokens
                )

            if not response.tool_calls:
                self._append_history({"role": "assistant", "content": response.content or ""})
                return AgentResult(
                    answer=response.content or "",
                    steps=steps,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                )

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": response.content or "",
            }
            if response.tool_calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": tool_call.id,
                        "function": {
                            "name": tool_call.name,
                            "arguments": tool_call.arguments,
                        },
                    }
                    for tool_call in response.tool_calls
                ]
            self._append_history(assistant_message)

            for tool_call in response.tool_calls:
                if tool_call.name not in self._tools:
                    step = AgentStep(
                        tool_name=tool_call.name,
                        tool_input=tool_call.arguments,
                        tool_output=None,
                        error=f"Herramienta no encontrada: {tool_call.name}",
                    )
                    steps.append(step)
                    self._append_history(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": step.error or "",
                        }
                    )
                    continue

                try:
                    kwargs = json.loads(tool_call.arguments or "{}")
                except json.JSONDecodeError:
                    kwargs = {}

                if not isinstance(kwargs, dict):
                    kwargs = {}

                tool_output = self._tools[tool_call.name](**kwargs)
                step = AgentStep(
                    tool_name=tool_call.name,
                    tool_input=tool_call.arguments,
                    tool_output=tool_output,
                    error=None,
                )
                steps.append(step)
                self._append_history(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_output,
                    }
                )

        return AgentResult(
            answer=response.content or "Se alcanzó el límite de iteraciones.",
            steps=steps,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
        )

    def structured_call(
        self,
        prompt: str,
        schema: Any,
        max_repair_attempts: int = 2,
    ) -> Any:
        """Pide al LLM una respuesta validada contra `schema` (M2)."""
        from pydantic import ValidationError

        tools = [final_result_tool_schema(schema)]
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

        for attempt in range(max_repair_attempts + 1):
            response = self._llm.chat(
                messages=messages,
                tools=tools,
                system=self._system,
            )

            final_result_calls = [
                tool_call for tool_call in response.tool_calls if tool_call.name == FINAL_RESULT_TOOL_NAME
            ]
            if final_result_calls:
                tool_call = final_result_calls[0]
                try:
                    arguments = json.loads(tool_call.arguments or "{}")
                    if hasattr(schema, "model_validate"):
                        return schema.model_validate(arguments)
                    return schema(**arguments)
                except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as exc:
                    if attempt >= max_repair_attempts:
                        raise RuntimeError("No se pudo obtener una respuesta estructurada válida.") from exc
                    messages.append({"role": "assistant", "content": response.content or ""})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": f"Argumentos inválidos: {exc}",
                        }
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Los argumentos de final_result no validan contra el schema. "
                                f"Reintenta con un objeto válido. Error: {exc}"
                            ),
                        }
                    )
                    continue

            if attempt >= max_repair_attempts:
                raise RuntimeError("No se pudo obtener una respuesta estructurada válida.")

            messages.append({"role": "assistant", "content": response.content or ""})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Debes responder usando la herramienta final_result con argumentos "
                        "que validen contra el schema proporcionado."
                    ),
                }
            )

        raise RuntimeError("No se pudo obtener una respuesta estructurada válida.")
