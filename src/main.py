# src/main.py — Punto de entrada unificado para AutomaDent
# ==============================================================================
# CLI unificado para iniciar cualquiera de los servicios del sistema:
#   python -m src.main bot        # Arranca Bot Telegram (inicia MCP en background)
#   python -m src.main api        # Arranca API REST FastAPI
#   python -m src.main mcp        # Arranca solo el servidor MCP
#   python -m src.main dashboard  # Arranca el Dashboard Streamlit
#   python -m src.main notifier   # Envía notificaciones (cron/task scheduler)
# ==============================================================================

import sys
import argparse
import subprocess
from src.utils.logger import get_logger

logger = get_logger(__name__)

def start_bot():
    """Arranca el bot de Telegram."""
    logger.info("Arrancando Bot de Telegram...")
    from src.telegram.bot import main as bot_main
    bot_main()

def start_api():
    """Arranca la API REST FastAPI."""
    logger.info("Arrancando API REST FastAPI...")
    import uvicorn
    from src.utils.config import MCP_SERVER_PORT # Puerto de referencia si fuera necesario
    # uvicorn src.api.app:app --reload --port 8000
    uvicorn.run("src.api.app:app", host="0.0.0.0", port=8000, reload=True)

def start_mcp():
    """Arranca el servidor MCP."""
    logger.info("Arrancando Servidor MCP...")
    from src.tools.servidor_mcp import run_mcp_server
    run_mcp_server()

def start_dashboard():
    """Arranca el dashboard de Streamlit."""
    logger.info("Arrancando Dashboard Streamlit...")
    try:
        import os
        env = os.environ.copy()
        # Aseguramos que la raíz del proyecto está en el PYTHONPATH
        env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        subprocess.run(["streamlit", "run", "src/dashboard/app.py", "--server.port", "8502"], env=env)
    except KeyboardInterrupt:
        logger.info("Dashboard detenido.")


def run_notifier(args):
    """Ejecuta el notifier standalone."""
    logger.info("Ejecutando Notificaciones Proactivas...")
    import asyncio
    from src.notifier.notifier import alertar_doctores_citas_dia, recordar_pacientes_citas
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        if args.doctores:
            loop.run_until_complete(alertar_doctores_citas_dia())
        elif args.recordatorios:
            loop.run_until_complete(recordar_pacientes_citas())
        else:
            loop.run_until_complete(alertar_doctores_citas_dia())
            loop.run_until_complete(recordar_pacientes_citas())
    finally:
        loop.close()

def main():
    parser = argparse.ArgumentParser(description="CLI de Control para AutomaDent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcomando bot
    subparsers.add_parser("bot", help="Iniciar el Bot de Telegram + Servidor MCP en background")

    # Subcomando api
    subparsers.add_parser("api", help="Iniciar la API REST FastAPI")

    # Subcomando mcp
    subparsers.add_parser("mcp", help="Iniciar únicamente el Servidor MCP HTTP")

    # Subcomando dashboard
    subparsers.add_parser("dashboard", help="Iniciar el Dashboard Streamlit")

    # Subcomando notifier
    notifier_parser = subparsers.add_parser("notifier", help="Ejecutar el despachador de notificaciones proactivas")
    notifier_parser.add_argument("--doctores", action="store_true", help="Solo alertar agenda a doctores")
    notifier_parser.add_argument("--recordatorios", action="store_true", help="Solo enviar recordatorios a pacientes")

    args = parser.parse_args()

    try:
        if args.command == "bot":
            start_bot()
        elif args.command == "api":
            start_api()
        elif args.command == "mcp":
            start_mcp()
        elif args.command == "dashboard":
            start_dashboard()
        elif args.command == "notifier":
            run_notifier(args)
    except KeyboardInterrupt:
        logger.info("Servicio detenido por el usuario.")
        sys.exit(0)

if __name__ == "__main__":
    main()
