"""Provider de Anthropic para student_framework.

Implementa el protocolo LLMClient usando la API de Anthropic directamente.
No modifica mia_agents/ — se instancia en build_agent() vía config["llm_client"].

Uso:
    from student_framework.anthropic_provider import AnthropicClient
    agent = build_agent({"llm_client": AnthropicClient()})

Variable de entorno requerida:
    ANTHROPIC_API_KEY: tu API key de Anthropic (sk-ant-...)
"""

from __future__ import annotations

import json
import os
from typing import Any

import anthropic

from mia_agents.types import LLMResponse, ToolCall, ToolSchema


class AnthropicClient:
    """Cliente LLM que usa la API de Anthropic directamente.

    Satisface el protocolo mia_agents.protocols.LLMClient:
    tiene un único método chat(...) -> LLMResponse.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        api_key: str | None = None,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSchema] | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        # Normalizar mensajes al formato de Anthropic
        normalized = self._normalize_messages(messages)

        # Normalizar tools al formato de Anthropic
        anthropic_tools = None
        if tools:
            anthropic_tools = []
            for tool in tools:
                if isinstance(tool, ToolSchema):
                    spec = tool.to_llm_spec()
                else:
                    spec = tool
                anthropic_tools.append({
                    "name": spec["name"],
                    "description": spec.get("description", ""),
                    "input_schema": spec.get("parameters", {
                        "type": "object",
                        "properties": {}
                    }),
                })

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": normalized,
        }
        if system:
            kwargs["system"] = system
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        resp = self._client.messages.create(**kwargs)
        return self._to_llm_response(resp)

    @staticmethod
    def _normalize_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Traduce el historial interno al formato de Anthropic.

        Mapeo:
          user                     -> {role: user, content: str}
          assistant (texto)        -> {role: assistant, content: str}
          assistant (+ tool_calls) -> {role: assistant, content: [text, tool_use]}
          tool (resultado)         -> {role: user, content: [tool_result]}
        """
        out: list[dict[str, Any]] = []
        i = 0
        while i < len(messages):
            m = messages[i]
            role = m.get("role")

            if role == "system":
                i += 1
                continue

            if role == "user":
                out.append({
                    "role": "user",
                    "content": m.get("content") or ""
                })
                i += 1
                continue

            if role == "assistant":
                content: list[dict[str, Any]] = []
                text = m.get("content") or ""
                if text:
                    content.append({"type": "text", "text": text})

                for tc in m.get("tool_calls") or []:
                    fn = tc.get("function", {})
                    args = fn.get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            args_dict = json.loads(args)
                        except json.JSONDecodeError:
                            args_dict = {}
                    else:
                        args_dict = args or {}

                    content.append({
                        "type": "tool_use",
                        "id": tc.get("id", f"toolu_{i}"),
                        "name": fn.get("name", ""),
                        "input": args_dict,
                    })

                if content:
                    out.append({"role": "assistant", "content": content})
                i += 1

                # Agrupar tool results consecutivos en un único user message
                tool_results: list[dict[str, Any]] = []
                while i < len(messages) and messages[i].get("role") == "tool":
                    tm = messages[i]
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tm.get("tool_call_id", ""),
                        "content": str(tm.get("content", "")),
                    })
                    i += 1
                if tool_results:
                    out.append({"role": "user", "content": tool_results})
                continue

            if role == "tool":
                # tool huérfano
                out.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.get("tool_call_id", ""),
                        "content": str(m.get("content", "")),
                    }]
                })
                i += 1
                continue

            # default
            out.append({"role": "user", "content": m.get("content") or ""})
            i += 1

        return out

    @staticmethod
    def _to_llm_response(resp: Any) -> LLMResponse:
        """Convierte la respuesta de Anthropic al formato LLMResponse del framework."""
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=json.dumps(block.input, ensure_ascii=False),
                ))

        return LLMResponse(
            content="".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            input_tokens=resp.usage.input_tokens if resp.usage else None,
            output_tokens=resp.usage.output_tokens if resp.usage else None,
        )