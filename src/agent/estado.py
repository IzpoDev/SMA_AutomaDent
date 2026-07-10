# src/agent/estado.py — Estado del Grafo y Gestión de Herramientas MCP
# ==============================================================================
# Migrado de bot/agents.py (líneas 36-68, 150-156, 436-440).
# Define el estado mutable del grafo LangGraph y la distribución de
# herramientas MCP a cada subagente por rol.
# ==============================================================================

from typing import Annotated, Literal
from typing_extensions import TypedDict
from langgraph.graph import END
from langgraph.graph.message import add_messages


# ==============================================================================
#  ESTADO DEL GRAFO LANGGRAPH
# ==============================================================================

class AgentState(TypedDict):
    """Estado mutable del grafo LangGraph.

    Atributos:
        messages: Historial de mensajes (acumulativo via add_messages).
        next_agent: Subagente al que debe delegar el supervisor.
        telegram_chat_id: ID del chat de Telegram del usuario activo.
        user_role: Rol resuelto del usuario en Supabase.
    """
    messages: Annotated[list, add_messages]
    next_agent: str
    telegram_chat_id: str
    user_role: Literal[
        "paciente",
        "odontologo",
        "recepcionista",
        "administrador",
        "paciente_no_registrado",
    ]


# ==============================================================================
#  DISTRIBUCIÓN DE HERRAMIENTAS MCP POR AGENTE (RBAC)
# ==============================================================================

# Nombres de las herramientas que cada agente tiene permitido usar
_TOOLS_RECEPCION_NAMES: set[str] = {
    "crear_paciente_y_historia",
    "consultar_disponibilidad_agenda",
    "agendar_cita",
    "consultar_historial_paciente",
    "obtener_mis_citas",
    "listar_citas",
    "listar_pacientes",
    "exportar_citas_excel",
}
_TOOLS_MEDICO_NAMES: set[str] = {
    "actualizar_estado_cita",
    "registrar_evolucion_medica",
    "listar_citas",
    "listar_pacientes",
    "consultar_historial_paciente",
}
_TOOLS_FACTURACION_NAMES: set[str] = {
    "registrar_pago",
}

# Listas de herramientas activas (pobladas al conectar al servidor MCP)
_tools_recepcion: list = []
_tools_medico: list = []
_tools_facturacion: list = []


def set_mcp_tools(all_tools: list) -> None:
    """Distribuye las herramientas MCP a cada agente según sus nombres permitidos.

    Llamado por el bot (telegram/bot.py) tras conectar al servidor MCP.

    Args:
        all_tools: Lista completa de herramientas obtenidas del servidor MCP.
    """
    global _tools_recepcion, _tools_medico, _tools_facturacion
    _tools_recepcion = [t for t in all_tools if t.name in _TOOLS_RECEPCION_NAMES]
    _tools_medico = [t for t in all_tools if t.name in _TOOLS_MEDICO_NAMES]
    _tools_facturacion = [t for t in all_tools if t.name in _TOOLS_FACTURACION_NAMES]


def get_tools_recepcion() -> list:
    """Retorna las herramientas del agente de recepción."""
    return _tools_recepcion


def get_tools_medico() -> list:
    """Retorna las herramientas del agente médico."""
    return _tools_medico


def get_tools_facturacion() -> list:
    """Retorna las herramientas del agente de facturación."""
    return _tools_facturacion


# ==============================================================================
#  FUNCIÓN DE ROUTING DEL GRAFO
# ==============================================================================

def router(state: AgentState) -> str:
    """Determina el siguiente nodo del grafo basándose en next_agent.

    Retorna END si el agente supervisor resolvió la consulta directamente,
    o el nombre del subagente al que delegar.

    Args:
        state: Estado actual del grafo.

    Returns:
        Nombre del siguiente nodo o END.
    """
    next_agent = state.get("next_agent", "FINISH")
    if next_agent == "FINISH":
        return END
    return next_agent
