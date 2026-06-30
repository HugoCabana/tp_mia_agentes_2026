# Informe — Milestone 1: Bucle del agente y herramientas

**Maestría en Inteligencia Artificial — Universidad de San Andrés**  
**Integrantes:** Hugo Cabaña · Oscar Carrizo  
**Proveedor LLM utilizado:** Ollama (`llama3.1`, local)

---

## 1. Diagrama de arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                        student_framework                        │
│                                                                 │
│   build_agent(config)                                           │
│        │                                                        │
│        ▼                                                        │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │                        MyAgent                           │  │
│   │                                                          │  │
│   │  _tools:   { nombre → callable }                        │  │
│   │  _schemas: { nombre → ToolSchema }                      │  │
│   │                                                          │  │
│   │  register_tool(fn, schema) ──────────────────────────►  │  │
│   │                                         guarda en dicts  │  │
│   │                                                          │  │
│   │  run(user_message)                                       │  │
│   │    │                                                     │  │
│   │    │  arma messages = [{"role":"user", ...}]             │  │
│   │    │                                                     │  │
│   │    │◄──────────────────────────────────────────────────┐ │  │
│   │    │           bucle (hasta max_iterations)            │ │  │
│   │    │                                                   │ │  │
│   │    ▼                                                   │ │  │
│   │  llm.chat(messages, tools=schemas, system=...)         │ │  │
│   │    │                                                   │ │  │
│   │    ▼                                                   │ │  │
│   │  LLMResponse                                           │ │  │
│   │    ├── tool_calls = []  →  devuelve AgentResult        │ │  │
│   │    └── tool_calls = [ToolCall, ...]                    │ │  │
│   │              │                                         │ │  │
│   │              ▼                                         │ │  │
│   │        json.loads(arguments)                           │ │  │
│   │        callable(**kwargs) → str                        │ │  │
│   │        AgentStep registrado                            │ │  │
│   │        mensaje role:"tool" agregado a messages ────────┘ │  │
│   └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ llm.chat(...)
                              ▼
             ┌────────────────────────────────┐
             │          LLMClient             │
             │   (wrapper sobre proveedor)    │
             │                                │
             │  from_env() → OllamaProvider   │
             │            → BedrockProvider   │
             └────────────────────────────────┘
                              │
                              ▼
             ┌────────────────────────────────┐
             │        OllamaProvider          │
             │  ollama.Client.chat(...)       │
             │  modelo: llama3.1              │
             │  host:   localhost:11434       │
             └────────────────────────────────┘
```

**Flujo de datos resumido:**

1. `build_agent` instancia `MyAgent` y registra las tres herramientas.
2. El usuario llama a `agent.run(mensaje)`.
3. El agente envía el historial al LLM con los esquemas de herramientas.
4. Si el LLM solicita una herramienta, el agente la ejecuta y agrega el resultado al historial.
5. El bucle continúa hasta que el LLM devuelve texto sin `tool_calls` (respuesta final) o se alcanza `max_iterations`.

---

## 2. Diseño de la interfaz de herramientas

### 2.1 Definición: de callable a ToolSchema

Cada herramienta es una función Python tipada con `Annotated` + `Field` de Pydantic y un docstring descriptivo. El método `ToolSchema.from_callable(fn)` (en `mia_agents/tool_schema.py`) automatiza la generación del esquema en tres pasos:

**Paso 1 — Modelo Pydantic intermedio** (`_input_model_from_callable`):  
Recorre los parámetros de la firma con `inspect.signature` y `get_type_hints`. Cada parámetro con `Annotated[tipo, Field(description="...")]` se convierte en un campo del modelo, preservando tipo y descripción.

**Paso 2 — JSON Schema** (`parameters_json_schema`):  
Llama a `model.model_json_schema()` sobre el modelo generado. El resultado es un dict con `type`, `properties` y `required` compatible con la especificación de herramientas de los LLM.

**Paso 3 — ToolSchema**:  
Se construye el dataclass `ToolSchema(name, description, parameters)` donde `name` viene de `fn.__name__`, `description` del docstring limpio y `parameters` del JSON Schema del paso anterior.

Ejemplo con `calculadora`:

```python
# Firma de la herramienta
def calculadora(
    a: Annotated[float, Field(description="Primer operando numérico.")],
    b: Annotated[float, Field(description="Segundo operando numérico.")],
    operador: Annotated[Literal["+","-","*","%"], Field(description="Operador.")],
) -> str: ...

# ToolSchema generado
ToolSchema(
    name="calculadora",
    description="Realiza una operación aritmética entre dos números...",
    parameters={
        "type": "object",
        "properties": {
            "a":        {"type": "number", "description": "Primer operando numérico."},
            "b":        {"type": "number", "description": "Segundo operando numérico."},
            "operador": {"enum": ["+","-","*","%"], "description": "Operador."}
        },
        "required": ["a", "b", "operador"]
    }
)
```

### 2.2 Registro en el agente

`register_tool(fn, schema)` guarda en dos diccionarios internos de `MyAgent`:

```
_tools:   { "calculadora" → <callable> }
_schemas: { "calculadora" → ToolSchema }
```

La separación entre callable y schema es intencional: el LLM solo recibe el schema (descripción + parámetros), nunca el código.

### 2.3 Lo que se pasa a chat(tools=...)

En cada iteración del bucle, el agente pasa `tools=list(self._schemas.values())` a `llm.chat(...)`. La lista contiene objetos `ToolSchema`, no callables ni dicts.

### 2.4 Lo que hace LLMClient con cada ToolSchema

`LLMClient` delega en el proveedor activo. En ambos casos, el método `_format_tools` recorre la lista y llama a `schema.to_llm_spec()` sobre cada elemento, que devuelve:

```python
{"name": ..., "description": ..., "parameters": ...}
```

Luego cada proveedor envuelve ese dict en su formato nativo:

**OllamaProvider** — el spec se pasa directamente como entrada de la API de Ollama:
```python
{
    "type": "function",
    "function": {
        "name": "calculadora",
        "description": "...",
        "parameters": { "type": "object", "properties": {...}, "required": [...] }
    }
}
```

**BedrockProvider** — el spec se envuelve en el formato Converse de AWS:
```python
{
    "toolSpec": {
        "name": "calculadora",
        "description": "...",
        "inputSchema": { "json": { "type": "object", "properties": {...} } }
    }
}
```

### 2.5 Respuesta del LLM y ejecución

Cuando el LLM decide usar una herramienta, devuelve un `ToolCall` con:

```python
ToolCall(id="c1", name="calculadora", arguments='{"a": 10, "b": 3, "operador": "+"}')
```

`arguments` es siempre un **string JSON**. El agente lo parsea con `json.loads` antes de invocar el callable:

```python
kwargs = json.loads(tool_call.arguments)   # {"a": 10, "b": 3, "operador": "+"}
resultado = self._tools[tool_call.name](**kwargs)  # "13.0"
```

El resultado (string) se agrega al historial como mensaje `role: "tool"` y el bucle continúa.

---

## 3. Terminación del bucle y límite de iteraciones

El bucle de `run` itera como máximo `max_iterations` veces (defecto: 20). En cada iteración:

1. Se llama a `llm.chat(...)`.
2. Si la respuesta **no** trae `tool_calls`, el bucle corta inmediatamente y devuelve `AgentResult(answer=response.content, steps=steps)`. Esta es la condición de parada normal.
3. Si la respuesta trae `tool_calls`, se ejecutan, se registran como `AgentStep` y se agregan al historial como mensajes `role: "tool"`. El bucle continúa a la siguiente iteración.

**Si se alcanza `max_iterations` sin que el LLM devuelva una respuesta final** (por ejemplo, porque queda invocando herramientas indefinidamente), el `for` termina sin haber hecho `return` dentro del cuerpo, y se ejecuta el bloque final:

```python
return AgentResult(
    answer=response.content or "Se alcanzó el límite de iteraciones.",
    steps=steps,
)
```

Es decir: el agente **nunca lanza una excepción ni queda colgado** — siempre devuelve un `AgentResult` válido, con todos los `AgentStep` acumulados hasta ese punto. Si la última respuesta del LLM tenía contenido de texto además de `tool_calls`, ese texto se usa como respuesta; si no, se devuelve un mensaje genérico indicando que se cortó por límite.

Este mecanismo es la única protección contra bucles infinitos en M1: no hay detección de ciclos repetidos ni timeout por tiempo real, solo el tope de iteraciones.

---

## 4. Limitaciones conocidas

**Sin estado entre llamadas a `run`.**  
En M1 cada llamada a `run` es independiente. Si el mismo usuario hace dos preguntas relacionadas en dos llamadas distintas, el agente no recuerda el contexto anterior. La memoria persistente se implementa en M2.

**`max_iterations` como único mecanismo de corte.**  
Si el LLM entra en un bucle de tool calls que nunca termina en texto libre, el agente solo se detiene al agotar las iteraciones (defecto: 20). No hay detección de ciclos ni timeout.

**Dependencia de `llama3.1` para tool calling.**  
No todos los modelos de Ollama soportan tool calling correctamente. `llama3.1` lo soporta, pero si se cambia el modelo vía `OLLAMA_MODEL` a uno incompatible, el agente puede no recibir `tool_calls` aunque el LLM decida usarlas.

**`structured_call` no implementado.**  
El método existe como stub y lanza `NotImplementedError`. Es un requisito de M2.

**Acumulación de tokens no reportada.**  
Ollama en su configuración estándar no siempre reporta `input_tokens` / `output_tokens` por respuesta. En ese caso `AgentResult.input_tokens` y `output_tokens` quedan en `None`.

**Mensaje `assistant` duplicado con múltiples `tool_calls` en un mismo turno.**  
Si el LLM solicita más de una herramienta en la misma respuesta, la implementación actual agrega un mensaje `role: "assistant"` por cada `tool_call` procesado (en vez de uno solo agrupando todos los `tool_calls`). Esto duplica el texto de `response.content` en el historial cuando hay 2+ herramientas en un turno. No afecta los tests de conformidad de M1 (que usan un solo `tool_call` por respuesta), pero es una mejora pendiente para mantener el historial limpio frente al LLM.

**Seguridad de `lector_archivo`.**  
La herramienta restringe el acceso al directorio de trabajo del proceso en el momento de importación (`os.getcwd()`). Si el proceso cambia de directorio después de iniciar, la restricción podría no funcionar como se espera.
