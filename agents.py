# agents.py — Cerebro del Sistema Multiagente (SMA)
# ==============================================================================
# Orquesta el flujo de interacción Hub-and-Spoke.
# Incorpora el rol del usuario (user_role) en el estado y los prompts
# para garantizar el control de acceso (RBAC).
# ==============================================================================

import os
from typing import Literal, Annotated
from typing_extensions import TypedDict

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from tools import tools_recepcion, tools_medico, tools_facturacion

load_dotenv()

# ─── LLM ─────────────────────────────────────────────────────────────────────
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
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

## REGLAS DE SEGURIDAD IMPORTANTES:
1. Si el rol es "paciente" o "paciente_no_registrado", NUNCA le permitas acceder a herramientas de "asistente_medico" (diagnósticos) ni "facturacion" (registro de pagos). Si intenta realizar estas acciones, responde de forma educada indicando que no cuenta con los permisos necesarios.
2. Si el rol es "odontologo", su intención principal debe ser "asistente_medico" para registrar evoluciones o diagnósticos.
3. Si el rol es "recepcionista" o "administrador", tiene acceso tanto a "recepcion" como a "facturacion", y herramientas administrativas.

## Clasificación de intenciones:
- "recepcion": Registrarse, consultar disponibilidad, agendar citas, ver su propio historial clínico (o cualquier historial si es personal de la clínica), o exportar reportes de citas a Excel (solo recepcionista/administrador).
- "asistente_medico": Registrar evoluciones, diagnósticos y tratamientos de citas finalizadas (SOLO odontólogos).
- "facturacion": Registrar cobros, ver montos de pagos (SOLO administradores o recepcionistas).
- "general": Saludos, despedidas y preguntas genéricas de la clínica → responde tú directamente con cortesía.
"""

PROMPT_RECEPCION = """Eres la Recepcionista Virtual de AutomaDent.
- Rol del Usuario actual: {user_role}

## Tus capacidades:
1. **Registro**: Recopila datos paso a paso para nuevos pacientes.
2. **Disponibilidad**: Muestra slots vacíos usando `consultar_disponibilidad_agenda`.
3. **Agendar**: Reserva citas.
4. **Historial clínico**: Muestra el historial. Si el usuario es un paciente, solo puede ver su propio historial. Si es odontólogo, recepcionista o administrador, puede ver el de cualquier paciente pasando su ID.
5. **Exportación a Sheets**: Puedes exportar reportes de citas a Google Sheets usando `exportar_citas_excel` si el rol es 'recepcionista' o 'administrador'. Pídele su correo Gmail para compartir la hoja.

## Reglas:
- Si el usuario no está registrado (rol='paciente_no_registrado'), invítalo a registrarse antes de agendar.
- Para agendar, pide la confirmación explícita del horario y doctor.
"""

PROMPT_ASISTENTE_MEDICO = """Eres el Asistente Médico de AutomaDent.
- Rol del Usuario actual: {user_role}

## Tus capacidades (SOLO para Odontólogos):
1. **Estado de cita**: Cambiar estado de citas a 'asistida', 'no_show', etc., usando `actualizar_estado_cita`.
2. **Evoluciones**: Registrar diagnóstico y tratamiento clínico con `registrar_evolucion_medica`.

## Reglas:
- Si el usuario NO es un 'odontologo', rechaza la acción amablemente indicando que es una herramienta de uso exclusivo para odontólogos.
- Solicita el ID de la cita para registrar la evolución.
"""

PROMPT_FACTURACION = """Eres el Agente Financiero de AutomaDent.
- Rol del Usuario actual: {user_role}

## Tus capacidades:
1. **Pagos**: Registrar pagos con `registrar_pago` (monto y método: efectivo, tarjeta, yape, plin).

## Reglas:
- Solo los administradores o recepcionistas pueden registrar pagos.
- Si el usuario es un paciente y quiere pagar, indícale amablemente que debe realizar el pago en caja con la recepcionista para que ella lo registre.
"""


# ==============================================================================
#  NODOS DEL GRAFO
# ==============================================================================

def supervisor_node(state: AgentState) -> dict:
    messages = state["messages"]
    chat_id = state["telegram_chat_id"]
    role = state["user_role"]

    prompt = PROMPT_SUPERVISOR.format(telegram_chat_id=chat_id, user_role=role)

    response = llm.invoke([
        SystemMessage(content=prompt),
        *messages,
    ])

    response_text = response.content.strip().lower()

    if "recepcion" in response_text and len(response_text) < 30:
        return {"messages": [], "next_agent": "recepcion"}
    elif "asistente_medico" in response_text and len(response_text) < 30:
        return {"messages": [], "next_agent": "asistente_medico"}
    elif "facturacion" in response_text and len(response_text) < 30:
        return {"messages": [], "next_agent": "facturacion"}
    else:
        return {
            "messages": [AIMessage(content=response.content)],
            "next_agent": "FINISH",
        }


def recepcion_node(state: AgentState) -> dict:
    messages = state["messages"]
    chat_id = state["telegram_chat_id"]
    role = state["user_role"]

    prompt = PROMPT_RECEPCION.format(user_role=role)
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
            "messages": [AIMessage(content=final_response.content)],
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
            "messages": [AIMessage(content=final_response.content)],
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
            "messages": [AIMessage(content=final_response.content)],
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
    result = await app.ainvoke({
        "messages": [HumanMessage(content=mensaje)],
        "next_agent": "supervisor",
        "telegram_chat_id": telegram_chat_id,
        "user_role": user_role
    })

    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content

    return "🤖 Lo siento, ocurrió un inconveniente. ¿Podrías indicarme de nuevo tu consulta?"
