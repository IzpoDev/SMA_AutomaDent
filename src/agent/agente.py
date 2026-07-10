# src/agent/agente.py — Grafo LangGraph: Nodos y Ensamblaje del SMA
# ==============================================================================
# Migrado de bot/agents.py (líneas 264-471).
# Define los nodos del grafo (supervisor, recepcion, medico, facturacion)
# y ensambla el StateGraph compilado.
# ==============================================================================

from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, START, END

from src.agent.estado import (
    AgentState,
    router,
    get_tools_recepcion,
    get_tools_medico,
    get_tools_facturacion,
)
from src.utils.config import TIMEZONE
from src.utils.helpers import get_text_content
from src.utils.logger import get_logger
from src.modelos.cliente_llm import invocar_llm_con_fallback, invocar_llm_con_fallback_async
from src.prompts.sistema_prompts import PROMPT_SUPERVISOR
from src.prompts.agente_prompts import (
    PROMPT_RECEPCION,
    PROMPT_ASISTENTE_MEDICO,
    PROMPT_FACTURACION,
)

logger = get_logger(__name__)


# ==============================================================================
#  NODOS DEL GRAFO
# ==============================================================================

def supervisor_node(state: AgentState) -> dict:
    """Nodo Supervisor: clasifica la intención y delega al subagente correcto.

    Analiza el mensaje del usuario y decide si responde directamente (consultas
    generales) o redirige a recepcion, asistente_medico, o facturacion.

    Args:
        state: Estado actual del grafo.

    Returns:
        Actualización del estado con next_agent y posible respuesta directa.
    """
    messages = state["messages"]
    chat_id = state["telegram_chat_id"]
    role = state["user_role"]

    prompt = PROMPT_SUPERVISOR.format(telegram_chat_id=chat_id, user_role=role)

    response = invocar_llm_con_fallback([
        SystemMessage(content=prompt),
        *messages,
    ])

    response_text = get_text_content(response.content).strip().lower()

    if "recepcion" in response_text and len(response_text) < 30:
        return {"messages": [], "next_agent": "recepcion"}
    elif "asistente_medico" in response_text and len(response_text) < 30:
        return {"messages": [], "next_agent": "asistente_medico"}
    elif "facturacion" in response_text and len(response_text) < 30:
        return {"messages": [], "next_agent": "facturacion"}
    else:
        return {
            "messages": [AIMessage(content=get_text_content(response.content))],
            "next_agent": "FINISH",
        }


async def recepcion_node(state: AgentState) -> dict:
    """Nodo Recepción: gestiona registro, disponibilidad, agendamiento e historial.

    Args:
        state: Estado actual del grafo.

    Returns:
        Respuesta del agente con el resultado de las herramientas ejecutadas.
    """
    messages = state["messages"]
    chat_id = state["telegram_chat_id"]
    role = state["user_role"]
    fecha_hoy = datetime.now(TIMEZONE).strftime("%Y-%m-%d")

    prompt = PROMPT_RECEPCION.format(
        user_role=role, telegram_chat_id=chat_id, fecha_hoy=fecha_hoy
    )
    tools = get_tools_recepcion()

    response = await invocar_llm_con_fallback_async(
        [SystemMessage(content=prompt), *messages],
        tools=tools,
    )

    if response.tool_calls:
        tool_results = []
        for tool_call in response.tool_calls:
            tool_call["args"]["telegram_chat_id"] = chat_id
            tool_call["args"]["user_role"] = role

            tool_fn = _get_tool_by_name(tool_call["name"], tools)
            if tool_fn:
                result = await tool_fn.ainvoke(tool_call["args"])
                tool_results.append(str(result))

        context_msg = "\n\n".join(tool_results)
        final_response = await invocar_llm_con_fallback_async([
            SystemMessage(content=prompt),
            *messages,
            AIMessage(content=f"[Resultado de herramientas]:\n{context_msg}"),
            HumanMessage(
                content="Basándote en el resultado de la herramienta, dale una respuesta amable y clara al usuario."
            ),
        ])
        return {
            "messages": [AIMessage(content=get_text_content(final_response.content))],
            "next_agent": "FINISH",
        }

    return {"messages": [response], "next_agent": "FINISH"}


async def medico_node(state: AgentState) -> dict:
    """Nodo Asistente Médico: gestiona citas, evoluciones e historial clínico.

    Args:
        state: Estado actual del grafo.

    Returns:
        Respuesta del agente con el resultado de las herramientas ejecutadas.
    """
    messages = state["messages"]
    chat_id = state["telegram_chat_id"]
    role = state["user_role"]

    prompt = PROMPT_ASISTENTE_MEDICO.format(user_role=role)
    tools = get_tools_medico()

    response = await invocar_llm_con_fallback_async(
        [SystemMessage(content=prompt), *messages],
        tools=tools,
    )

    if response.tool_calls:
        tool_results = []
        for tool_call in response.tool_calls:
            tool_call["args"]["telegram_chat_id"] = chat_id
            tool_call["args"]["user_role"] = role

            tool_fn = _get_tool_by_name(tool_call["name"], tools)
            if tool_fn:
                result = await tool_fn.ainvoke(tool_call["args"])
                tool_results.append(str(result))

        context_msg = "\n\n".join(tool_results)
        final_response = await invocar_llm_con_fallback_async([
            SystemMessage(content=prompt),
            *messages,
            AIMessage(content=f"[Resultado de herramientas]:\n{context_msg}"),
            HumanMessage(
                content="Genera una respuesta clara para el doctor basándote en el resultado anterior."
            ),
        ])
        return {
            "messages": [AIMessage(content=get_text_content(final_response.content))],
            "next_agent": "FINISH",
        }

    return {"messages": [response], "next_agent": "FINISH"}


async def facturacion_node(state: AgentState) -> dict:
    """Nodo Facturación: gestiona el registro de pagos.

    Args:
        state: Estado actual del grafo.

    Returns:
        Respuesta del agente con el resultado de las herramientas ejecutadas.
    """
    messages = state["messages"]
    chat_id = state["telegram_chat_id"]
    role = state["user_role"]

    prompt = PROMPT_FACTURACION.format(user_role=role)
    tools = get_tools_facturacion()

    response = await invocar_llm_con_fallback_async(
        [SystemMessage(content=prompt), *messages],
        tools=tools,
    )

    if response.tool_calls:
        tool_results = []
        for tool_call in response.tool_calls:
            tool_call["args"]["telegram_chat_id"] = chat_id
            tool_call["args"]["user_role"] = role

            tool_fn = _get_tool_by_name(tool_call["name"], tools)
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
            "messages": [AIMessage(content=get_text_content(final_response.content))],
            "next_agent": "FINISH",
        }

    return {"messages": [response], "next_agent": "FINISH"}


# ==============================================================================
#  UTILIDAD INTERNA
# ==============================================================================

def _get_tool_by_name(name: str, tool_list: list):
    """Busca una herramienta por nombre en la lista proporcionada."""
    for t in tool_list:
        if t.name == name:
            return t
    return None


# ==============================================================================
#  ENSAMBLAJE DEL GRAFO LANGGRAPH
# ==============================================================================

def build_graph():
    """Construye y compila el StateGraph del Sistema Multiagente.

    Returns:
        Grafo compilado listo para invocar con ainvoke().
    """
    graph = StateGraph(AgentState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("recepcion", recepcion_node)
    graph.add_node("asistente_medico", medico_node)
    graph.add_node("facturacion", facturacion_node)

    graph.add_edge(START, "supervisor")

    graph.add_conditional_edges(
        "supervisor",
        router,
        {
            "recepcion": "recepcion",
            "asistente_medico": "asistente_medico",
            "facturacion": "facturacion",
            END: END,
        },
    )

    graph.add_edge("recepcion", END)
    graph.add_edge("asistente_medico", END)
    graph.add_edge("facturacion", END)

    return graph.compile()


# Instancia compilada del grafo (singleton)
app = build_graph()
