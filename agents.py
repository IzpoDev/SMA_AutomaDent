# agents.py — Cerebro del Sistema Multiagente (SMA)
# ==============================================================================
# Orquesta el flujo de interacción Hub-and-Spoke.
# Incorpora el rol del usuario (user_role) en el estado y los prompts
# para garantizar el control de acceso (RBAC).
# ==============================================================================

import os
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

from tools import tools_recepcion, tools_medico, tools_facturacion
from database import guardar_mensaje, obtener_historial_mensajes

load_dotenv()

# ─── LLM ─────────────────────────────────────────────────────────────────────
llm = ChatGoogleGenerativeAI(
    model="gemini-3.1-flash-lite",
    google_api_key=os.environ["GEMINI_API_KEY"],
    temperature=0.3,
    convert_system_message_to_human=False,
)

# ─── Estado del grafo ────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    next_agent: str
    telegram_chat_id: str
    user_role: str  # 'paciente', 'odontologo', 'recepcionista', 'administrador', 'paciente_no_registrado'


# ==============================================================================
#  SYSTEM PROMPTS ACTUALIZADOS CON REGLAS DE ROLES (RBAC)
# ==============================================================================

PROMPT_SUPERVISOR = """Eres el Orquestador Central de la Clínica Dental AutomaDent.

Tu única función es clasificar la intención del mensaje del usuario y delegarlo al subagente correcto.

## INFORMACIÓN DE SESIÓN DE ESTE CHAT:
- ID del Chat: {telegram_chat_id}
- Rol del Usuario: {user_role}

## INSTRUCCIÓN CRÍTICA DE RUTEO:
Si decides delegar la intención a un subagente ("recepcion", "asistente_medico", "facturacion"), DEBES responder ÚNICA Y EXCLUSIVAMENTE con la palabra clave del subagente. No incluyas ningún otro texto, ni explicaciones, ni confirmaciones. Solo la palabra exacta en minúsculas.

## FORMATO DE RESPUESTA (Solo si NO delegas):
Si la intención es "general", o debes denegar acceso por seguridad, responde directamente usando EXCLUSIVAMENTE formato HTML (ej: <b>texto</b>, <i>texto</i>). NUNCA uses Markdown como ** o *.

## REGLAS DE SEGURIDAD IMPORTANTES:
1. Si el rol es "paciente" o "paciente_no_registrado", NUNCA le permitas acceder a herramientas de "asistente_medico" (diagnósticos) ni "facturacion" (registro de pagos). Si intenta realizar estas acciones, deniégale el acceso educadamente (formato HTML).
2. Si el rol es "paciente_no_registrado", y el usuario quiere agendar, registrarse, presentarse, proporcionar su nombre o responder a preguntas de registro, la intención es "recepcion". Responde SOLO con la palabra: recepcion
3. Si el rol es "odontologo", su intención principal debe ser "asistente_medico".
4. Si el rol es "recepcionista" o "administrador", tiene acceso tanto a "recepcion" como a "facturacion".

## Clasificación de intenciones (Palabras Clave):
- recepcion: Registrarse, presentarse, dar datos personales, consultar disponibilidad, agendar citas, historial clínico, reportes Excel.
- asistente_medico: Registrar evoluciones, diagnósticos y tratamientos.
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
5. **Exportación a Sheets**: Puedes exportar reportes de citas usando `exportar_citas_excel` si el rol es 'recepcionista' o 'administrador'.

## REGLAS DE SEGURIDAD Y CONTROL DE ROLES (RBAC):
- **Confianza Absoluta en el Rol del Sistema:** Debes confiar ciegamente en el "Rol del Usuario actual" ({user_role}) proporcionado.
- **Si el rol es 'paciente_no_registrado':**
  * Significa que este chat NO está registrado en la base de datos de la clínica.
  * ¡NO PUEDE AGENDAR CITAS! Si intenta agendar, explícale que primero debe registrarse.
  * **Flujo de Registro:** Para registrarse, DEBES informarle claramente que necesitas su Nombre y Apellido (el correo y fecha de nacimiento son opcionales). Si el usuario no ha proporcionado esos datos, solicítalos educadamente en tu respuesta.
  * Tan pronto como el usuario proporcione su Nombre y Apellido (ej: "Fabricio Ruiz Ponce"), DEBES llamar inmediatamente a la herramienta `crear_paciente_y_historia` para darlo de alta en Supabase.
- **Si el rol es 'paciente':**
  * Ya está registrado. Para agendar una cita, usa `agendar_cita`.
"""

PROMPT_ASISTENTE_MEDICO = """Eres el Asistente Médico de AutomaDent.
- Rol del Usuario actual: {user_role}

## FORMATO DE RESPUESTA:
Usa EXCLUSIVAMENTE formato HTML para resaltar texto (ej: <b>negrita</b>, <i>cursiva</i>). NUNCA uses Markdown como ** o *.

## Tus capacidades (SOLO para Odontólogos):
1. **Estado de cita**: Cambiar estado de citas a 'asistida', 'no_show', etc., usando `actualizar_estado_cita`.
2. **Evoluciones**: Registrar diagnóstico y tratamiento clínico con `registrar_evolucion_medica`.

## Reglas:
- Si el usuario NO es un 'odontologo', rechaza la acción amablemente indicando que es una herramienta de uso exclusivo para odontólogos.
- Solicita el ID de la cita para registrar la evolución.
"""

PROMPT_FACTURACION = """Eres el Agente Financiero de AutomaDent.
- Rol del Usuario actual: {user_role}

## FORMATO DE RESPUESTA:
Usa EXCLUSIVAMENTE formato HTML para resaltar texto (ej: <b>negrita</b>, <i>cursiva</i>). NUNCA uses Markdown como ** o *.

## Tus capacidades:
1. **Pagos**: Registrar pagos con `registrar_pago` (monto y método: efectivo, tarjeta, yape, plin).

## Reglas:
- Solo los administradores o recepcionistas pueden registrar pagos.
- Si el usuario es un paciente y quiere pagar, indícale amablemente que debe realizar el pago en caja con la recepcionista para que ella lo registre.
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

    response = llm.invoke([
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


def recepcion_node(state: AgentState) -> dict:
    messages = state["messages"]
    chat_id = state["telegram_chat_id"]
    role = state["user_role"]

    fecha_hoy = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    prompt = PROMPT_RECEPCION.format(user_role=role, telegram_chat_id=chat_id, fecha_hoy=fecha_hoy)
    llm_with_tools = llm.bind_tools(tools_recepcion)

    response = llm_with_tools.invoke([
        SystemMessage(content=prompt),
        *messages,
    ])

    if response.tool_calls:
        tool_results = []
        for tool_call in response.tool_calls:
            # Inyectar argumentos de seguridad
            tool_call["args"]["telegram_chat_id"] = chat_id
            tool_call["args"]["user_role"] = role

            tool_fn = _get_tool_by_name(tool_call["name"], tools_recepcion)
            if tool_fn:
                result = tool_fn.invoke(tool_call["args"])
                tool_results.append(result)

        context_msg = "\n\n".join(tool_results)
        final_response = llm.invoke([
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


def medico_node(state: AgentState) -> dict:
    messages = state["messages"]
    chat_id = state["telegram_chat_id"]
    role = state["user_role"]

    prompt = PROMPT_ASISTENTE_MEDICO.format(user_role=role)
    llm_with_tools = llm.bind_tools(tools_medico)

    response = llm_with_tools.invoke([
        SystemMessage(content=prompt),
        *messages,
    ])

    if response.tool_calls:
        tool_results = []
        for tool_call in response.tool_calls:
            tool_call["args"]["telegram_chat_id"] = chat_id
            tool_call["args"]["user_role"] = role

            tool_fn = _get_tool_by_name(tool_call["name"], tools_medico)
            if tool_fn:
                result = tool_fn.invoke(tool_call["args"])
                tool_results.append(result)

        context_msg = "\n\n".join(tool_results)
        final_response = llm.invoke([
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


def facturacion_node(state: AgentState) -> dict:
    messages = state["messages"]
    chat_id = state["telegram_chat_id"]
    role = state["user_role"]

    prompt = PROMPT_FACTURACION.format(user_role=role)
    llm_with_tools = llm.bind_tools(tools_facturacion)

    response = llm_with_tools.invoke([
        SystemMessage(content=prompt),
        *messages,
    ])

    if response.tool_calls:
        tool_results = []
        for tool_call in response.tool_calls:
            tool_call["args"]["telegram_chat_id"] = chat_id
            tool_call["args"]["user_role"] = role

            tool_fn = _get_tool_by_name(tool_call["name"], tools_facturacion)
            if tool_fn:
                result = tool_fn.invoke(tool_call["args"])
                tool_results.append(result)

        context_msg = "\n\n".join(tool_results)
        final_response = llm.invoke([
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
#  FUNCIÓN PÚBLICA DE PROCESAMIENTO
# ==============================================================================

async def procesar_mensaje(telegram_chat_id: str, user_role: str, mensaje: str) -> str:
    """Punto de entrada al SMA.
    
    Args:
        telegram_chat_id: ID del chat de Telegram.
        user_role: Rol resuelto del usuario en Supabase ('paciente', 'odontologo', etc.).
        mensaje: El mensaje de texto.
    """
    # 1. Obtener historial desde Supabase
    historial = obtener_historial_mensajes(telegram_chat_id, limite=20)
    
    # 2. Reconstruir lista de mensajes para LangChain
    messages_list = []
    for msg in historial:
        if msg["sender"] == "user":
            messages_list.append(HumanMessage(content=msg["content"]))
        elif msg["sender"] == "bot":
            messages_list.append(AIMessage(content=msg["content"]))
            
    # Agregar el mensaje actual del usuario
    messages_list.append(HumanMessage(content=mensaje))
    
    # 3. Invocar al agente con todo el contexto
    result = await app.ainvoke({
        "messages": messages_list,
        "next_agent": "supervisor",
        "telegram_chat_id": telegram_chat_id,
        "user_role": user_role
    })

    # 4. Obtener la respuesta del bot
    respuesta = "🤖 Lo siento, ocurrió un inconveniente. ¿Podrías indicarme de nuevo tu consulta?"
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            respuesta = _get_text_content(msg.content)
            if respuesta:
                break

    # 5. Guardar el nuevo mensaje del usuario y la respuesta del bot en Supabase
    guardar_mensaje(telegram_chat_id, "user", mensaje)
    guardar_mensaje(telegram_chat_id, "bot", respuesta)

    return respuesta
