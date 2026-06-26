# agents.py — Cerebro del Sistema Multiagente (SMA)
# ==============================================================================
# Orquesta el flujo de interacción Hub-and-Spoke.
# Incorpora:
#   - Cascada de fallbacks para manejar límites de cuota (RPM/RPD)
#   - Inyección RAG vectorial desde Supabase (pgvector)
#   - Resúmenes automáticos de historial (memoria compacta)
#   - RBAC por rol de usuario
# ==============================================================================

import os
import time
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Literal, Annotated
from typing_extensions import TypedDict

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

TIMEZONE = ZoneInfo("America/Lima")

from database import (
    guardar_mensaje,
    obtener_historial_con_resumen,
    guardar_resumen,
    contar_turnos_desde_ultimo_resumen,
    buscar_soporte_rag,
)

# ─── Herramientas MCP (pobladas por main.py al iniciar) ──────────────────────
_TOOLS_RECEPCION_NAMES = {
    "crear_paciente_y_historia",
    "consultar_disponibilidad_agenda",
    "agendar_cita",
    "consultar_historial_paciente",
    "obtener_mis_citas",
    "listar_citas",
    "listar_pacientes",
}
_TOOLS_MEDICO_NAMES = {
    "actualizar_estado_cita",
    "registrar_evolucion_medica",
    "listar_citas",
    "listar_pacientes",
    "consultar_historial_paciente",
}
_TOOLS_FACTURACION_NAMES = {
    "registrar_pago",
}

_tools_recepcion: list = []
_tools_medico: list = []
_tools_facturacion: list = []


def set_mcp_tools(all_tools: list) -> None:
    """Llamado por main.py después de conectar al servidor MCP.
    Distribuye las herramientas MCP a cada agente según su nombre."""
    global _tools_recepcion, _tools_medico, _tools_facturacion
    _tools_recepcion = [t for t in all_tools if t.name in _TOOLS_RECEPCION_NAMES]
    _tools_medico = [t for t in all_tools if t.name in _TOOLS_MEDICO_NAMES]
    _tools_facturacion = [t for t in all_tools if t.name in _TOOLS_FACTURACION_NAMES]

load_dotenv()

# ─── Cascada de Modelos (Principal → Fallback 1 → Fallback 2) ─────────────────
_MODEL_CASCADE = [
    "gemini-2.0-flash-lite",   # Principal — Mayor cuota diaria
    "gemini-2.5-flash-lite-preview-06-17",   # Fallback 1
    "gemini-2.5-flash",         # Fallback 2
]

def _build_llm(model_name: str, temperature: float = 0.3) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=os.environ["GEMINI_API_KEY"],
        temperature=temperature,
        convert_system_message_to_human=False,
    )

# LLM principal (reutilizado en los nodos para evitar re-instanciar en cada llamada)
llm = _build_llm(_MODEL_CASCADE[0])


def invocar_llm_con_fallback(messages: list, tools: list = None, temperature: float = 0.3):
    """
    Intenta invocar el LLM con la cascada de modelos definida en _MODEL_CASCADE.
    Si recibe un error 429 (cuota), espera brevemente y pasa al siguiente modelo.

    Args:
        messages: Lista de mensajes LangChain (SystemMessage, HumanMessage, AIMessage).
        tools: Lista de tools a vincular (opcional).
        temperature: Temperatura de generación.

    Returns:
        Respuesta AIMessage del primer modelo que responda exitosamente.

    Raises:
        Exception: Si todos los modelos del cascade fallan.
    """
    last_exc = None
    for model_name in _MODEL_CASCADE:
        try:
            candidate = _build_llm(model_name, temperature)
            if tools:
                candidate = candidate.bind_tools(tools)
            response = candidate.invoke(messages)
            if model_name != _MODEL_CASCADE[0]:
                print(f"[FALLBACK] Respondió con modelo: {model_name}")
            return response
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
                print(f"[FALLBACK] Cuota agotada en {model_name}, probando siguiente...")
                time.sleep(1)
                last_exc = e
            else:
                raise  # Error no relacionado a cuota → relanzar
    raise last_exc or Exception("Todos los modelos del cascade fallaron.")


async def invocar_llm_con_fallback_async(messages: list, tools: list = None, temperature: float = 0.3):
    """Versión asíncrona de invocar_llm_con_fallback."""
    last_exc = None
    for model_name in _MODEL_CASCADE:
        try:
            candidate = _build_llm(model_name, temperature)
            if tools:
                candidate = candidate.bind_tools(tools)
            response = await candidate.ainvoke(messages)
            if model_name != _MODEL_CASCADE[0]:
                print(f"[FALLBACK] Respondió con modelo: {model_name}")
            return response
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
                print(f"[FALLBACK] Cuota agotada en {model_name}, probando siguiente...")
                await asyncio.sleep(1)
                last_exc = e
            else:
                raise
    raise last_exc or Exception("Todos los modelos del cascade fallaron.")


# ─── Estado del grafo ────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    next_agent: str
    telegram_chat_id: str
    user_role: str  # 'paciente', 'odontologo', 'recepcionista', 'administrador', 'paciente_no_registrado'


# ==============================================================================
#  SYSTEM PROMPTS CON REGLAS DE ROLES (RBAC)
# ==============================================================================

PROMPT_SUPERVISOR = """Eres el Orquestador Central de la Clínica Dental AutomaDent.

Tu única función es clasificar la intención del mensaje del usuario y delegarlo al subagente correcto.

## INFORMACIÓN DE SESIÓN DE ESTE CHAT:
- ID del Chat: {telegram_chat_id}
- Rol del Usuario: {user_role}

## INSTRUCCIÓN CRÍTICA DE RUTEO:
Si decides delegar la intención a un subagente ("recepcion", "asistente_medico", "facturacion"), DEBES responder Única Y EXCLUSIVAMENTE con la palabra clave del subagente. No incluyas ningún otro texto, ni explicaciones, ni confirmaciones. Solo la palabra exacta en minúsculas.

## FORMATO DE RESPUESTA (Solo si NO delegas):
Si la intención es "general", o debes denegar acceso por seguridad, responde directamente usando EXCLUSIVAMENTE formato HTML (ej: <b>texto</b>, <i>texto</i>). NUNCA uses Markdown como ** o *.

## REGLAS DE SEGURIDAD IMPORTANTES:
1. Si el rol es "paciente" o "paciente_no_registrado", NUNCA le permitas acceder a herramientas de "asistente_medico" (diagnósticos, listados clínicos) ni "facturacion" (registro de pagos). Si intenta realizar estas acciones, deniégale el acceso educadamente (formato HTML).
2. Si el rol es "paciente_no_registrado", y el usuario quiere agendar, registrarse, presentarse, proporcionar su nombre o responder a preguntas de registro, la intención es "recepcion". Responde SOLO con la palabra: recepcion
3. Si el rol es "odontologo", "recepcionista" o "administrador", tiene acceso COMPLETO a TODOS los subagentes: "recepcion", "asistente_medico" y "facturacion".

## Clasificación de intenciones (Palabras Clave):
- recepcion: Registrarse, dar datos personales, consultar disponibilidad, agendar citas, historial clínico, reportes Excel, registrar nuevo paciente, listar pacientes.
- asistente_medico: Listar citas, ver agenda, registrar evoluciones, diagnósticos, tratamientos, marcar citas como atendidas/asistidas/no_show, listar pacientes, consultar historial de pacientes.
- facturacion: Registrar cobros, pagos.
- general: Saludos, despedidas y preguntas genéricas de la clínica. (Responde conversando en HTML).
"""

PROMPT_RECEPCION = """Eres la Recepcionista Virtual de AutomaDent.
- ID del Chat de Telegram actual: {telegram_chat_id}
- Rol del Usuario actual: {user_role}
- Fecha de hoy: {fecha_hoy} (usa esta fecha para resolver referencias como "mañana", "el lunes", "la próxima semana")

## FORMATO DE RESPUESTA:
Usa EXCLUSIVAMENTE formato HTML para resaltar texto (ej: <b>negrita</b>, <i>cursiva</i>). NUNCA uses Markdown como ** o *. Sé informativa, amable y clara.

## Tus capacidades:
1. **Registro**: Recopila datos (Nombre, Apellido, opcionalmente Correo y Fecha de Nacimiento YYYY-MM-DD) para nuevos pacientes y regístralos usando `crear_paciente_y_historia`. Note que el número de teléfono del paciente se asocia de forma automática utilizando su ID de Telegram ({telegram_chat_id}), por lo que NUNCA debes solicitar su número de teléfono.
2. **Disponibilidad**: Muestra slots vacíos usando `consultar_disponibilidad_agenda`.
3. **Agendar**: Reserva citas con `agendar_cita`.
4. **Historial clínico**: Muestra el historial clínico.
5. **Exportación a Sheets**: Puedes exportar reportes de citas usando `exportar_citas_excel` si el rol es 'recepcionista', 'administrador' o 'odontologo'.
6. **Listar pacientes**: Muestra la lista de pacientes registrados usando `listar_pacientes` si el rol es 'recepcionista', 'administrador' o 'odontologo'.

## REGLAS DE SEGURIDAD Y CONTROL DE ROLES (RBAC):
- **Confianza Absoluta en el Rol del Sistema:** Debes confiar ciegamente en el "Rol del Usuario actual" ({user_role}) proporcionado.
- **Si el rol es 'odontologo', 'recepcionista' o 'administrador':**
  * Tiene acceso total a todas las funciones de recepción. Puede registrar pacientes, agendar citas para cualquier paciente, exportar reportes y listar pacientes.
- **Si el rol es 'paciente_no_registrado':**
  * Significa que este chat NO está registrado en la base de datos de la clínica.
  * ¡NO PUEDE AGENDAR CITAS! Si intenta agendar, explícale que primero debe registrarse.
  * **Flujo de Registro:** Para registrarse, DEBES informarle claramente que necesitas su Nombre y Apellido (el correo y fecha de nacimiento son opcionales). Si el usuario no ha proporcionado esos datos, solícitalos educadamente en tu respuesta.
  * Tan pronto como el usuario proporcione su Nombre y Apellido (ej: "Fabricio Ruiz Ponce"), DEBES llamar inmediatamente a la herramienta `crear_paciente_y_historia` para darlo de alta en Supabase.
- **Si el rol es 'paciente':**
  * Ya está registrado. Para agendar una cita, usa `agendar_cita`.
"""

PROMPT_ASISTENTE_MEDICO = """Eres el Asistente Médico de AutomaDent.
- Rol del Usuario actual: {user_role}

## FORMATO DE RESPUESTA:
Usa EXCLUSIVAMENTE formato HTML para resaltar texto (ej: <b>negrita</b>, <i>cursiva</i>). NUNCA uses Markdown como ** o *.

## Tus capacidades (para odontólogos y personal autorizado):
1. **Listar citas**: Muestra la agenda de citas usando `listar_citas`. Si el rol es 'odontologo', filtra automáticamente sus propias citas.
2. **Estado de cita**: Cambia el estado usando `actualizar_estado_cita`. Estados válidos: 'confirmada', 'asistida' (o 'atendida' como alias), 'cancelada', 'no_show'.
3. **Evoluciones**: Registra diagnóstico y tratamiento clínico con `registrar_evolucion_medica` (la cita debe estar en estado 'asistida' primero).
4. **Listar pacientes**: Muestra la lista de pacientes registrados usando `listar_pacientes` (siempre disponible para odontólogos).
5. **Historial clínico de paciente**: Muestra la historia clínica completa de cualquier paciente usando `consultar_historial_paciente` (especificando `paciente_id`).

## Reglas:
- Todos los roles de personal (odontologo, recepcionista, administrador) pueden usar estas funciones.
- Si el odontólogo pide "la lista de citas", "mis citas" o "mi agenda", usa `listar_citas`.
- Si pide "lista de pacientes" o "pacientes registrados", usa `listar_pacientes`.
- Para registrar una evolución, solicita el ID de la cita si no fue proporcionado.
- El odontólogo puede decir "marcar cita X como atendida" — esto equivale a 'asistida' en el sistema.
"""

PROMPT_FACTURACION = """Eres el Agente Financiero de AutomaDent.
- Rol del Usuario actual: {user_role}

## FORMATO DE RESPUESTA:
Usa EXCLUSIVAMENTE formato HTML para resaltar texto (ej: <b>negrita</b>, <i>cursiva</i>). NUNCA uses Markdown como ** o *.

## Tus capacidades:
1. **Pagos**: Registrar pagos con `registrar_pago` (monto y método: efectivo, tarjeta, yape, plin).

## Reglas:
- Los roles 'odontologo', 'administrador' y 'recepcionista' pueden registrar pagos.
- Si el usuario es un paciente y quiere pagar, indícale amablemente que debe realizar el pago en caja con la recepcionista para que ella lo registre.
"""

PROMPT_RESUMEN = """Eres un asistente de compresión de contexto. Se te proporcionará un historial de conversación entre un usuario y el bot de AutomaDent (clínica dental).

Tu tarea es generar un resumen compacto y estructurado en español que capture:
- La identidad del usuario (si se mencionó nombre o rol).
- Acciones ya realizadas (registros, citas agendadas, consultas, pagos).
- Preferencias o solicitudes pendientes.
- Información importante para el contexto futuro.

Responde SOLO con el resumen, sin explicaciones adicionales. Máximo 200 palabras. Usa formato de lista si hay múltiples puntos.
"""


# ==============================================================================
#  NODOS DEL GRAFO
# ==============================================================================

def _get_text_content(content) -> str:
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and "text" in part:
                text_parts.append(part["text"])
        return " ".join(text_parts)
    return str(content)

def supervisor_node(state: AgentState) -> dict:
    messages = state["messages"]
    chat_id = state["telegram_chat_id"]
    role = state["user_role"]

    prompt = PROMPT_SUPERVISOR.format(telegram_chat_id=chat_id, user_role=role)

    response = invocar_llm_con_fallback([
        SystemMessage(content=prompt),
        *messages,
    ])

    response_text = _get_text_content(response.content).strip().lower()

    if "recepcion" in response_text and len(response_text) < 30:
        return {"messages": [], "next_agent": "recepcion"}
    elif "asistente_medico" in response_text and len(response_text) < 30:
        return {"messages": [], "next_agent": "asistente_medico"}
    elif "facturacion" in response_text and len(response_text) < 30:
        return {"messages": [], "next_agent": "facturacion"}
    else:
        return {
            "messages": [AIMessage(content=_get_text_content(response.content))],
            "next_agent": "FINISH",
        }


async def recepcion_node(state: AgentState) -> dict:
    messages = state["messages"]
    chat_id = state["telegram_chat_id"]
    role = state["user_role"]

    fecha_hoy = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    prompt = PROMPT_RECEPCION.format(user_role=role, telegram_chat_id=chat_id, fecha_hoy=fecha_hoy)

    response = await invocar_llm_con_fallback_async(
        [SystemMessage(content=prompt), *messages],
        tools=_tools_recepcion,
    )

    if response.tool_calls:
        tool_results = []
        for tool_call in response.tool_calls:
            tool_call["args"]["telegram_chat_id"] = chat_id
            tool_call["args"]["user_role"] = role

            tool_fn = _get_tool_by_name(tool_call["name"], _tools_recepcion)
            if tool_fn:
                result = await tool_fn.ainvoke(tool_call["args"])
                tool_results.append(str(result))

        context_msg = "\n\n".join(tool_results)
        final_response = await invocar_llm_con_fallback_async([
            SystemMessage(content=prompt),
            *messages,
            AIMessage(content=f"[Resultado de herramientas]:\n{context_msg}"),
            HumanMessage(content="Basándote en el resultado de la herramienta, dale una respuesta amable y clara al usuario."),
        ])

        return {
            "messages": [AIMessage(content=_get_text_content(final_response.content))],
            "next_agent": "FINISH",
        }

    return {"messages": [response], "next_agent": "FINISH"}


async def medico_node(state: AgentState) -> dict:
    messages = state["messages"]
    chat_id = state["telegram_chat_id"]
    role = state["user_role"]

    prompt = PROMPT_ASISTENTE_MEDICO.format(user_role=role)

    response = await invocar_llm_con_fallback_async(
        [SystemMessage(content=prompt), *messages],
        tools=_tools_medico,
    )

    if response.tool_calls:
        tool_results = []
        for tool_call in response.tool_calls:
            tool_call["args"]["telegram_chat_id"] = chat_id
            tool_call["args"]["user_role"] = role

            tool_fn = _get_tool_by_name(tool_call["name"], _tools_medico)
            if tool_fn:
                result = await tool_fn.ainvoke(tool_call["args"])
                tool_results.append(str(result))

        context_msg = "\n\n".join(tool_results)
        final_response = await invocar_llm_con_fallback_async([
            SystemMessage(content=prompt),
            *messages,
            AIMessage(content=f"[Resultado de herramientas]:\n{context_msg}"),
            HumanMessage(content="Genera una respuesta clara para el doctor basándote en el resultado anterior."),
        ])

        return {
            "messages": [AIMessage(content=_get_text_content(final_response.content))],
            "next_agent": "FINISH",
        }

    return {"messages": [response], "next_agent": "FINISH"}


async def facturacion_node(state: AgentState) -> dict:
    messages = state["messages"]
    chat_id = state["telegram_chat_id"]
    role = state["user_role"]

    prompt = PROMPT_FACTURACION.format(user_role=role)

    response = await invocar_llm_con_fallback_async(
        [SystemMessage(content=prompt), *messages],
        tools=_tools_facturacion,
    )

    if response.tool_calls:
        tool_results = []
        for tool_call in response.tool_calls:
            tool_call["args"]["telegram_chat_id"] = chat_id
            tool_call["args"]["user_role"] = role

            tool_fn = _get_tool_by_name(tool_call["name"], _tools_facturacion)
            if tool_fn:
                result = await tool_fn.ainvoke(tool_call["args"])
                tool_results.append(str(result))

        context_msg = "\n\n".join(tool_results)
        final_response = await invocar_llm_con_fallback_async([
            SystemMessage(content=prompt),
            *messages,
            AIMessage(content=f"[Resultado de herramientas]:\n{context_msg}"),
            HumanMessage(content="Genera una respuesta clara para el usuario."),
        ])

        return {
            "messages": [AIMessage(content=_get_text_content(final_response.content))],
            "next_agent": "FINISH",
        }

    return {"messages": [response], "next_agent": "FINISH"}


# ==============================================================================
#  UTILIDADES INTERNAS Y RUTEO
# ==============================================================================

def _get_tool_by_name(name: str, tool_list: list):
    for t in tool_list:
        if t.name == name:
            return t
    return None

def _router(state: AgentState) -> str:
    next_agent = state.get("next_agent", "FINISH")
    if next_agent == "FINISH":
        return END
    return next_agent


# ==============================================================================
#  ENSAMBLAJE DE LANGGRAPH
# ==============================================================================

graph = StateGraph(AgentState)

graph.add_node("supervisor", supervisor_node)
graph.add_node("recepcion", recepcion_node)
graph.add_node("asistente_medico", medico_node)
graph.add_node("facturacion", facturacion_node)

graph.add_edge(START, "supervisor")

graph.add_conditional_edges(
    "supervisor",
    _router,
    {
        "recepcion": "recepcion",
        "asistente_medico": "asistente_medico",
        "facturacion": "facturacion",
        END: END
    }
)

graph.add_edge("recepcion", END)
graph.add_edge("asistente_medico", END)
graph.add_edge("facturacion", END)

app = graph.compile()


# ==============================================================================
#  RESUMEN AUTOMÁTICO DE HISTORIAL
# ==============================================================================

_TURNOS_PARA_RESUMIR = 10  # Resumir cada 10 mensajes (5 intercambios)

async def _intentar_resumir_si_es_necesario(chat_id: str, messages_list: list) -> None:
    """Si el historial supera el umbral, genera y guarda un resumen comprimido."""
    try:
        turnos = contar_turnos_desde_ultimo_resumen(chat_id)
        if turnos < _TURNOS_PARA_RESUMIR:
            return

        # Tomar los últimos mensajes para resumir
        bloque = "\n".join(
            f"{'Usuario' if m['sender'] == 'user' else 'Bot'}: {m['content']}"
            for m in messages_list
        )
        resumen_response = invocar_llm_con_fallback([
            SystemMessage(content=PROMPT_RESUMEN),
            HumanMessage(content=bloque),
        ], temperature=0.1)
        resumen_texto = _get_text_content(resumen_response.content).strip()
        if resumen_texto:
            guardar_resumen(chat_id, resumen_texto)
            print(f"[RESUMEN] ✅ Resumen generado para chat {chat_id} ({turnos} turnos).")
    except Exception as e:
        print(f"[RESUMEN] ❌ Error generando resumen: {e}")


# ==============================================================================
#  FUNCIÓN PÚBLICA DE PROCESAMIENTO
# ==============================================================================

async def procesar_mensaje(telegram_chat_id: str, user_role: str, mensaje: str) -> str:
    """Punto de entrada al SMA.

    Args:
        telegram_chat_id: ID del chat de Telegram.
        user_role: Rol resuelto del usuario en Supabase ('paciente', 'odontologo', etc.).
        mensaje: El mensaje de texto.
    """
    # 1. Obtener historial con soporte de resúmenes compactos
    historial_data = obtener_historial_con_resumen(telegram_chat_id, limite_mensajes=8)
    resumen = historial_data["resumen"]
    mensajes_recientes = historial_data["mensajes"]

    # 2. Disparar resumen en background si se supera el umbral (sin bloquear)
    asyncio.create_task(_intentar_resumir_si_es_necesario(telegram_chat_id, mensajes_recientes))

    # 3. Reconstruir lista de mensajes para LangChain
    messages_list = []

    # Inyectar resumen como contexto inicial si existe
    if resumen:
        messages_list.append(SystemMessage(
            content=f"[RESUMEN DE CONVERSACIÓN PREVIA]\n{resumen}"
        ))

    # Agregar mensajes recientes
    for msg in mensajes_recientes:
        if msg["sender"] == "user":
            messages_list.append(HumanMessage(content=msg["content"]))
        elif msg["sender"] == "bot":
            messages_list.append(AIMessage(content=msg["content"]))

    # 4. Búsqueda RAG vectorial — inyectar contexto de soporte si hay coincidencias
    contexto_rag = buscar_soporte_rag(mensaje)
    if contexto_rag:
        messages_list.append(SystemMessage(
            content=f"[INFORMACIÓN DE SOPORTE RAG DE LA CLÍNICA]\n{contexto_rag}\n\nUsa esta información para responder con datos precisos sobre la clínica."
        ))
        print(f"[RAG] ✅ Contexto inyectado para: '{mensaje[:60]}...'")

    # Agregar el mensaje actual del usuario
    messages_list.append(HumanMessage(content=mensaje))

    # 5. Invocar al agente con todo el contexto
    result = await app.ainvoke({
        "messages": messages_list,
        "next_agent": "supervisor",
        "telegram_chat_id": telegram_chat_id,
        "user_role": user_role
    })

    # 6. Obtener la respuesta del bot
    respuesta = "🤖 Lo siento, ocurrió un inconveniente. ¿Podrías indicarme de nuevo tu consulta?"
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            respuesta = _get_text_content(msg.content)
            if respuesta:
                break

    # 7. Guardar el nuevo mensaje del usuario y la respuesta del bot en Supabase
    guardar_mensaje(telegram_chat_id, "user", mensaje)
    guardar_mensaje(telegram_chat_id, "bot", respuesta)

    return respuesta
