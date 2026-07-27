"""Implementación del agente — M1 + M2.

M1: bucle registrar/ejecutar herramientas hasta respuesta de texto libre.
M2 agrega, sobre la misma fachada (`build_agent`, `register_tool`, `run`):
  - Estado conversacional entre llamadas a `run`.
  - Ventana deslizante de historial (`max_history_messages`).
  - `structured_call` con la tool sintética `final_result` + reparación.
  - Reintentos ante fallos transitorios del cliente LLM.
  - Acumulación de tokens en `AgentResult`.

Ver ENUNCIADO_M2.md / README.md para el contrato completo.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from mia_agents.protocols import LLMClient
from mia_agents.tool_schema import FINAL_RESULT_TOOL_NAME, final_result_tool_schema
from mia_agents.types import AgentResult, AgentStep, LLMResponse, ToolSchema

_TSchema = TypeVar("_TSchema", bound=BaseModel)


class TransientLLMError(Exception):
    """Marca un fallo de `chat()` como transitorio (reintentable)."""


class StructuredOutputError(RuntimeError):
    """Se agotaron los reintentos de reparación en `structured_call`."""


def _accumulate(total: int | None, value: int | None) -> int | None:
    """Suma tokens tratando None-por-respuesta como 0, una vez que
    algún LLMResponse reportó un valor no-None."""
    if value is None:
        return total
    return (total or 0) + value


class MyAgent:
    # -- resiliencia: llamadas al LLM -------------------------------------
    _LLM_MAX_ATTEMPTS = 3
    _LLM_RETRY_BASE_DELAY = 0.05  # segundos; backoff exponencial simple

    def __init__(
        self,
        llm_client: LLMClient,
        system_prompt: str = "Sos un agente muy eficiente hincha de River",
        max_iterations: int = 20,
        max_history_messages: int = 100,
    ) -> None:
        """Inicializa el agente.

        Parameters
        ----------
        llm_client : LLMClient
            Cliente LLM (real o mock) que el agente utilizará.
        system_prompt : str
            System prompt por defecto.
        max_iterations : int
            Tope de iteraciones del bucle del agente por cada `run`.
        max_history_messages : int
            Tope de mensajes que se envían a `self._llm.chat(...)` en
            cada llamada. Se aplica sobre `self._history` (el registro
            persistente de la conversación) mediante una ventana
            deslizante "atómica": ver `_windowed_messages`.
        """
        self._llm = llm_client
        self._system = system_prompt
        self._max_iterations = max_iterations
        self._max_history_messages = max_history_messages

        self._tools: dict[str, Callable[..., str]] = {}
        self._schemas: dict[str, ToolSchema] = {}

        # Estado conversacional (M2): se acumula entre llamadas a `run`.
        self._history: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Registro de herramientas (M1, sin cambios de contrato en M2)
    # ------------------------------------------------------------------
    def register_tool(
        self,
        tool: Callable[..., str],
        schema: ToolSchema,
    ) -> None:
        """Registra una herramienta callable junto a su esquema."""
        self._tools[schema.name] = tool
        self._schemas[schema.name] = schema

    # ------------------------------------------------------------------
    # Resiliencia: wrapper de reintentos para `self._llm.chat(...)`
    # ------------------------------------------------------------------
    def _chat_with_retries(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[ToolSchema] | None,
        system: str | None,
    ) -> LLMResponse:
        """Reintenta `chat()` ante cualquier excepción del cliente LLM
        (timeouts, 5xx, rate limits, errores de red, etc.).

        No distinguimos tipos de excepción del proveedor porque el
        protocolo `LLMClient` no los estandariza; tratamos cualquier
        excepción levantada por `chat()` como potencialmente transitoria
        y la reintentamos con backoff exponencial corto. Si se agotan
        los intentos, la excepción original se re-levanta tal cual (la
        capa que llama a este método decide cómo fallar limpiamente).
        """
        last_exc: Exception | None = None
        for attempt in range(self._LLM_MAX_ATTEMPTS):
            try:
                return self._llm.chat(messages=messages, tools=tools, system=system)
            except Exception as exc:  # noqa: BLE001 — reintento deliberadamente amplio
                last_exc = exc
                if attempt < self._LLM_MAX_ATTEMPTS - 1:
                    time.sleep(self._LLM_RETRY_BASE_DELAY * (2**attempt))
                    continue
        assert last_exc is not None
        raise last_exc

    # ------------------------------------------------------------------
    # Gestión de contexto / memoria (M2): sliding window "atómica"
    # ------------------------------------------------------------------
    def _windowed_messages(self) -> list[dict[str, Any]]:
        """Recorta `self._history` para respetar `max_history_messages`.

        Estrategia: **sliding window por unidades atómicas**. Un mensaje
        `assistant` con `tool_calls` no puede separarse de los mensajes
        `tool` que le siguen inmediatamente (son una sola "jugada":
        pedido de herramienta + resultado); si se cortaran por separado,
        el historial quedaría inconsistente para providers reales
        (Bedrock exige que todo `toolUse` tenga su `toolResult`
        inmediatamente después). El resto de los mensajes (`user`,
        `assistant` de cierre sin tools) son unidades de a uno.

        Se recorren las unidades desde la más reciente hacia atrás y se
        van acumulando mientras quepan en el presupuesto. Como el
        mensaje de usuario más reciente es siempre la última unidad
        agregada a `self._history` antes de llamar a este método, la
        invariante de recencia queda garantizada mientras el presupuesto
        alcance para al menos una unidad.

        Caso límite (documentado, no crítico para los tests): si una
        única unidad (p. ej. un tramo largo de tool-calls) excede sola
        el presupuesto, se trunca esa unidad conservando sus mensajes
        más recientes para no exceder el límite; en ese caso puede
        perderse la correlación toolUse/toolResult más antigua dentro
        de esa unidad. Ver informe, sección "modos de fallo fuera de
        alcance".
        """
        budget = self._max_history_messages
        history = self._history

        # 1) Agrupar en unidades atómicas.
        units: list[list[dict[str, Any]]] = []
        i = 0
        while i < len(history):
            msg = history[i]
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                unit = [msg]
                i += 1
                while i < len(history) and history[i].get("role") == "tool":
                    unit.append(history[i])
                    i += 1
                units.append(unit)
            else:
                units.append([msg])
                i += 1

        # 2) Tomar unidades desde la más nueva mientras quepan.
        kept: list[list[dict[str, Any]]] = []
        total = 0
        for unit in reversed(units):
            if total + len(unit) > budget:
                break
            kept.append(unit)
            total += len(unit)

        if not kept and units:
            # Ni siquiera la unidad más reciente entra completa: la
            # truncamos conservando su cola (caso límite, ver docstring).
            last_unit = units[-1]
            kept = [last_unit[-budget:]] if budget > 0 else [[]]

        kept.reverse()
        return [msg for unit in kept for msg in unit]

    # ------------------------------------------------------------------
    # Bucle principal (M1 + estado/memoria/tokens/resiliencia de M2)
    # ------------------------------------------------------------------
    def run(self, user_message: str) -> AgentResult:
        """Ejecuta un turno de conversación.

        M2: `self._history` persiste entre llamadas (statefulness).
        Antes de cada `chat()` se recorta la vista enviada al LLM con
        `_windowed_messages()`, respetando `max_history_messages`.
        """
        self._history.append({"role": "user", "content": user_message})
        steps: list[AgentStep] = []
        input_tokens: int | None = None
        output_tokens: int | None = None

        last_response: LLMResponse | None = None

        for _ in range(self._max_iterations):
            windowed = self._windowed_messages()
            try:
                response = self._chat_with_retries(
                    messages=windowed,
                    tools=list(self._schemas.values()),
                    system=self._system,
                )
            except Exception as exc:  # fallo persistente del LLM tras reintentos
                answer = (
                    "No se pudo completar la solicitud: el cliente LLM falló "
                    f"de forma persistente tras varios reintentos ({exc})."
                )
                return AgentResult(
                    answer=answer,
                    steps=steps,
                    error=str(exc),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

            last_response = response
            input_tokens = _accumulate(input_tokens, response.input_tokens)
            output_tokens = _accumulate(output_tokens, response.output_tokens)

            if not response.tool_calls:
                answer = response.content or ""
                self._history.append({"role": "assistant", "content": answer})
                return AgentResult(
                    answer=answer,
                    steps=steps,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

            for tool_call in response.tool_calls:
                self._history.append(
                    {
                        "role": "assistant",
                        "content": response.content,
                        "tool_calls": [
                            {
                                "id": tool_call.id,
                                "function": {
                                    "name": tool_call.name,
                                    "arguments": tool_call.arguments,
                                },
                            }
                        ],
                    }
                )

                tool_output, error = self._invoke_tool(tool_call.name, tool_call.arguments)
                steps.append(
                    AgentStep(
                        tool_name=tool_call.name,
                        tool_input=tool_call.arguments,
                        tool_output=tool_output,
                        error=error,
                    )
                )
                self._history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_output if tool_output is not None else error,
                    }
                )

        answer = (last_response.content if last_response else None) or (
            "Se alcanzó el límite de iteraciones sin una respuesta final."
        )
        return AgentResult(
            answer=answer,
            steps=steps,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def _invoke_tool(self, name: str, raw_arguments: str) -> tuple[str | None, str | None]:
        """Ejecuta una herramienta registrada de forma resiliente.

        Devuelve `(tool_output, error)`. `tool_output` es siempre lo que
        la herramienta devuelve (incluidos sus propios mensajes de error
        recuperables — la calculadora y el lector de archivos ya
        devuelven strings accionables ante argumentos inválidos; eso NO
        pasa por acá como excepción).

        Este método sólo captura fallos *inesperados* de la herramienta
        (bugs, excepciones no manejadas): si la herramienta no está
        registrada, o si el callable revienta con una excepción, se
        registra un error accionable en el `AgentStep` y se le devuelve
        al LLM un mensaje de "tool" describiendo el problema — así el
        bucle nunca se cae por un fallo de una herramienta.
        """
        if name not in self._tools:
            available = ", ".join(sorted(self._tools)) or "(ninguna registrada)"
            error = (
                f"Herramienta no encontrada: '{name}'. "
                f"Herramientas disponibles: {available}."
            )
            return None, error

        try:
            kwargs = json.loads(raw_arguments) if raw_arguments else {}
        except json.JSONDecodeError as exc:
            error = (
                f"Argumentos inválidos para '{name}': no es JSON válido "
                f"({exc}). Se recibió: {raw_arguments!r}."
            )
            return None, error

        if not isinstance(kwargs, dict):
            error = (
                f"Argumentos inválidos para '{name}': se esperaba un objeto "
                f"JSON con los parámetros, se recibió {type(kwargs).__name__}."
            )
            return None, error

        try:
            output = self._tools[name](**kwargs)
        except TypeError as exc:
            # Argumentos con nombres/tipos incompatibles con la firma:
            # recuperable — el LLM puede corregir y reintentar.
            error = (
                f"Llamada inválida a '{name}' con argumentos {kwargs!r}: {exc}. "
                "Revisá los nombres y tipos de parámetros esperados por la herramienta."
            )
            return None, error
        except Exception as exc:  # bug inesperado dentro de la herramienta
            error = f"La herramienta '{name}' falló inesperadamente: {exc}."
            return None, error

        return output, None

    # ------------------------------------------------------------------
    # Salida estructurada (M2): tool sintética `final_result` + reparación
    # ------------------------------------------------------------------
    def structured_call(
        self,
        prompt: str,
        schema: type[_TSchema],
        max_repair_attempts: int = 2,
    ) -> _TSchema:
        """Pide al LLM una instancia de `schema`, validada, vía `final_result`.

        No comparte estado con `self._history` (es una sub-conversación
        acotada y de un solo objetivo); esto evita que intentos de
        reparación fallidos contaminen la memoria de la conversación
        principal.
        """
        final_tool = final_result_tool_schema(schema)
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

        last_error: str | None = None
        total_attempts = max_repair_attempts + 1

        for attempt in range(total_attempts):
            response = self._chat_with_retries(
                messages=messages,
                tools=[final_tool],
                system=self._system,
            )

            final_call = next(
                (tc for tc in response.tool_calls if tc.name == FINAL_RESULT_TOOL_NAME),
                None,
            )

            if final_call is None:
                # El modelo respondió con texto libre (o llamó otra tool):
                # no aceptado. Preparamos un prompt de reparación.
                last_error = (
                    "No invocaste la herramienta obligatoria "
                    f"'{FINAL_RESULT_TOOL_NAME}'. Debés responder ÚNICAMENTE "
                    f"invocando '{FINAL_RESULT_TOOL_NAME}' con los argumentos "
                    "requeridos; no respondas con texto libre."
                )
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": last_error})
                continue

            try:
                parsed_args = json.loads(final_call.arguments)
            except json.JSONDecodeError as exc:
                last_error = (
                    f"Los argumentos de '{FINAL_RESULT_TOOL_NAME}' no son JSON "
                    f"válido ({exc}). Recibido: {final_call.arguments!r}. "
                    "Reintentá con un objeto JSON válido que respete el schema."
                )
                self._append_repair_turn(messages, response, final_call, last_error)
                continue

            try:
                return schema.model_validate(parsed_args)
            except ValidationError as exc:
                last_error = (
                    f"Los argumentos de '{FINAL_RESULT_TOOL_NAME}' no cumplen el "
                    f"schema esperado: {exc}. Corregí los campos señalados y "
                    "volvé a invocar la herramienta con valores válidos."
                )
                self._append_repair_turn(messages, response, final_call, last_error)
                continue

        raise StructuredOutputError(
            f"No se pudo obtener una salida estructurada válida para el schema "
            f"{schema.__name__} tras {total_attempts} intentos "
            f"(1 inicial + {max_repair_attempts} reparaciones). "
            f"Último error: {last_error}"
        )

    @staticmethod
    def _append_repair_turn(
        messages: list[dict[str, Any]],
        response: LLMResponse,
        final_call: Any,
        error_message: str,
    ) -> None:
        """Agrega el turno assistant(tool_call) + tool(error) de reparación."""
        messages.append(
            {
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {
                        "id": final_call.id,
                        "function": {
                            "name": final_call.name,
                            "arguments": final_call.arguments,
                        },
                    }
                ],
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": final_call.id,
                "content": error_message,
            }
        )