# src/tools/servidor_mcp.py — Servidor MCP de AutomaDent
# ==============================================================================
# Refactorizado de bot/mcp_server.py.
# Registra todas las herramientas de los submódulos en el servidor FastMCP
# y lo expone via streamable-http en el puerto configurado.
#
# Ejecución directa:
#   python -m src.tools.servidor_mcp
# O via src/main.py:
#   python -m src.main mcp
# ==============================================================================

from mcp.server.fastmcp import FastMCP

from src.utils.config import MCP_SERVER_HOST, MCP_SERVER_PORT
from src.utils.logger import get_logger
from src.tools.recepcion import (
    crear_paciente_y_historia,
    consultar_disponibilidad_agenda,
    agendar_cita,
    consultar_historial_paciente,
)
from src.tools.medico import (
    actualizar_estado_cita,
    registrar_evolucion_medica,
)
from src.tools.facturacion import registrar_pago
from src.tools.administrativas import (
    listar_pacientes,
    listar_citas,
    obtener_mis_citas,
)
from src.tools.exportacion import exportar_citas_excel

logger = get_logger(__name__)

# ─── Instancia del servidor MCP ───────────────────────────────────────────────
mcp = FastMCP(
    "AutomaDent MCP Server",
    host=MCP_SERVER_HOST,
    port=MCP_SERVER_PORT,
)

# ─── Registro de herramientas ─────────────────────────────────────────────────
# Herramientas de Recepción
mcp.tool()(crear_paciente_y_historia)
mcp.tool()(consultar_disponibilidad_agenda)
mcp.tool()(agendar_cita)
mcp.tool()(consultar_historial_paciente)

# Herramientas Médicas
mcp.tool()(actualizar_estado_cita)
mcp.tool()(registrar_evolucion_medica)

# Herramientas de Facturación
mcp.tool()(registrar_pago)

# Herramientas Administrativas
mcp.tool()(listar_pacientes)
mcp.tool()(listar_citas)
mcp.tool()(obtener_mis_citas)

# Herramientas de Exportación
mcp.tool()(exportar_citas_excel)


def run_mcp_server() -> None:
    """Arranca el servidor MCP en modo streamable-http."""
    logger.info(
        f"AutomaDent MCP Server iniciando en "
        f"http://{MCP_SERVER_HOST}:{MCP_SERVER_PORT}/mcp ..."
    )
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    run_mcp_server()
