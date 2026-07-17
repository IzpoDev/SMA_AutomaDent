# src/telegram/bot.py — Bot de Telegram: Handlers y Ciclo de Vida
# ==============================================================================
# Refactorizado de bot/main.py.
# Gestiona: handlers de comandos (/start, /help), handler de mensajes,
# arranque del servidor MCP como subproceso y el polling del bot.
# ==============================================================================

import os
import sys
import asyncio
import subprocess

import httpx
from telegram import Update
# pyrefly: ignore [missing-import]
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
# pyrefly: ignore [missing-import]
from langchain_mcp_adapters.client import MultiServerMCPClient

from src.agent.estado import set_mcp_tools
from src.agent.ejecutor import procesar_mensaje
from src.telegram.rbac import obtener_rol_usuario
from src.telegram.panel_personal import (
    start_personal,
    handle_panel_callback,
    handle_panel_texto,
    ROLES_PERSONAL,
)
from src.utils.config import TELEGRAM_TOKEN, MCP_SERVER_URL
from src.utils.database import supabase
from src.utils.helpers import sanitize_html
from src.utils.logger import get_logger
from src.utils.tracing import init_tracing

logger = get_logger(__name__)

# Path absoluto al servidor MCP
_MCP_SERVER_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "src", "tools", "servidor_mcp.py",
)
_mcp_process: subprocess.Popen | None = None


# ==============================================================================
#  GESTIÓN DEL SERVIDOR MCP (subproceso automático)
# ==============================================================================

def _start_mcp_server() -> subprocess.Popen:
    """Arranca servidor_mcp.py como subproceso en background."""
    logger.info("Iniciando servidor MCP como subproceso...")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.path.join(os.path.dirname(__file__), "..", "..")
    proc = subprocess.Popen(
        [sys.executable, "-m", "src.tools.servidor_mcp"],
        stdout=sys.stdout,
        stderr=sys.stderr,
        env=env,
    )
    return proc


async def _wait_for_mcp_server(url: str, timeout: int = 20) -> None:
    """Espera hasta que el servidor MCP responda (con reintentos).

    Un GET a /mcp devuelve 405, lo que confirma que el servidor está activo.
    """
    async with httpx.AsyncClient(trust_env=False) as client:
        for intento in range(timeout):
            try:
                await client.get(url, timeout=2.0)
                logger.info("✅ Servidor MCP listo.")
                return
            except (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadError,
                httpx.ReadTimeout,
                httpx.RemoteProtocolError,
                httpx.TimeoutException,
            ):
                if intento == 0:
                    logger.info("⏳ Esperando que el servidor MCP arranque...")
                await asyncio.sleep(1)
            except httpx.HTTPStatusError:
                logger.info("✅ Servidor MCP listo.")
                return

    raise RuntimeError(
        f"❌ El servidor MCP no respondió en {timeout}s ({url}).\n"
        "Revisa que servidor_mcp.py arranca sin errores de configuración."
    )


# ==============================================================================
#  HANDLERS DE TELEGRAM
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler del comando /start. Muestra el panel o el saludo según el rol del usuario."""
    chat_id = str(update.effective_chat.id)
    rol = await obtener_rol_usuario(chat_id)

    if rol in ["odontologo", "recepcionista", "administrador"]:
        # Cargar nombre del personal y guardarlo en user_data para el panel
        try:
            personal_res = (
                supabase.table("personal")
                .select("nombre, apellido")
                .eq("telefono", chat_id)
                .limit(1)
                .execute()
            )
            if personal_res.data:
                p = personal_res.data[0]
                context.user_data["nombre_personal"] = f"{p['nombre']} {p['apellido']}"
            else:
                context.user_data["nombre_personal"] = ""
        except Exception:
            context.user_data["nombre_personal"] = ""

        context.user_data["rol"] = rol
        await start_personal(update, context)
    else:
        await update.message.reply_text(
            "🦷 <b>¡Bienvenido a la Clínica Dental AutomaDent!</b>\n\n"
            "Soy tu asistente virtual. ¿En qué puedo ayudarte?\n\n"
            "📋 <b>Registro</b> — Si eres nuevo paciente\n"
            "📅 <b>Citas</b> — Consultar disponibilidad y agendar\n"
            "📂 <b>Historial</b> — Consultar tu evolución clínica",
            parse_mode="HTML",
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler del comando /help. Muestra ejemplos según el rol del usuario."""
    chat_id = str(update.effective_chat.id)
    rol = await obtener_rol_usuario(chat_id)

    ayuda = "🆘 <b>Ayuda — Clínica Dental AutomaDent</b>\n\nEjemplos de uso:\n\n"

    if rol == "odontologo":
        ayuda += (
            "• <i>\"Actualizar estado de cita 10 a asistida\"</i>\n"
            "• <i>\"Registrar evolución de cita 15\"</i>\n"
            "• <i>\"Ver historial clínico de paciente 3\"</i>"
        )
    elif rol in ["recepcionista", "administrador"]:
        ayuda += (
            "• <i>\"Registrar pago de la cita 5\"</i>\n"
            "• <i>\"Ver disponibilidad para el viernes\"</i>\n"
            "• <i>\"Agendar cita para el odontólogo 1\"</i>"
        )
    else:
        ayuda += (
            "• <i>\"Quiero registrarme\"</i>\n"
            "• <i>\"¿Qué horarios hay para mañana?\"</i>\n"
            "• <i>\"Agendar una cita\"</i>\n"
            "• <i>\"Ver mis citas\"</i>"
        )

    await update.message.reply_text(ayuda, parse_mode="HTML")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler de mensajes de texto.

    Si el personal está en medio de un flujo del panel (panel_step activo),
    el texto se redirige al panel en lugar del agente LLM.
    Para todos los demás casos, delega al SMA.
    """
    chat_id = str(update.effective_chat.id)
    texto = update.message.text

    # Obtener rol: usar user_data si ya está cacheado para evitar una query extra
    rol = context.user_data.get("rol") or await obtener_rol_usuario(chat_id)

    # ── Panel de personal: interceptar texto si hay un flujo activo ──────────
    if rol in ROLES_PERSONAL and context.user_data.get("panel_step"):
        logger.info(f"📥 [PANEL] {chat_id} | step={context.user_data['panel_step']} | '{texto[:30]}'")
        await handle_panel_texto(update, context)
        return

    # ── Flujo normal: agente LLM ─────────────────────────────────────────────
    logger.info(f"📩 {chat_id} | Rol: {rol} | '{texto[:40]}...'")
    await update.effective_chat.send_action("typing")

    try:
        respuesta = await procesar_mensaje(
            telegram_chat_id=chat_id,
            user_role=rol,
            mensaje=texto,
        )
        await update.message.reply_text(sanitize_html(respuesta), parse_mode="HTML")
        logger.info(f"✅ Respuesta enviada a {chat_id}")

    except Exception as e:
        logger.error(f"❌ Error procesando mensaje de {chat_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ Ocurrió un inconveniente. Por favor intenta de nuevo."
        )


# ==============================================================================
#  CICLO DE VIDA DEL BOT
# ==============================================================================

async def run_bot() -> None:
    """Arranca el servidor MCP, conecta, carga herramientas y lanza el bot."""
    global _mcp_process

    # 0. Inicializar LangSmith tracing (observabilidad)
    init_tracing()

    # 1. Arrancar el servidor MCP como subproceso
    _mcp_process = _start_mcp_server()

    try:
        # 2. Esperar a que el servidor esté listo
        await _wait_for_mcp_server(MCP_SERVER_URL)

        # 3. Cargar herramientas MCP
        logger.info(f"🔌 Cargando herramientas desde {MCP_SERVER_URL} ...")
        mcp_client = MultiServerMCPClient({
            "automadent": {
                "url": MCP_SERVER_URL,
                "transport": "streamable-http",
            }
        })

        tools = await mcp_client.get_tools()
        set_mcp_tools(tools)
        logger.info(f"✅ {len(tools)} herramientas MCP cargadas: {[t.name for t in tools]}")

        # 4. Arrancar el bot de Telegram
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

        # Panel interactivo: CallbackQueryHandler directo (sin ConversationHandler)
        # Captura botones: panel_*, estado_*, metodo_*
        application.add_handler(
            CallbackQueryHandler(
                handle_panel_callback,
                pattern=r"^(panel_|estado_|metodo_)",
            )
        )

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        )

        async with application:
            await application.updater.start_polling()
            await application.start()
            logger.info("🤖 Bot AutomaDent iniciado en modo POLLING.")

            try:
                await asyncio.Event().wait()  # Corre hasta Ctrl+C
            finally:
                await application.updater.stop()
                await application.stop()

    finally:
        # 5. Terminar el servidor MCP al apagar el bot
        if _mcp_process and _mcp_process.poll() is None:
            logger.info("🛑 Deteniendo servidor MCP...")
            _mcp_process.terminate()
            _mcp_process.wait(timeout=5)


def main() -> None:
    """Punto de entrada para el bot de Telegram."""
    # Bypass de proxy del sistema para conexiones locales (fix Windows)
    os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
    os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("🛑 Bot detenido.")
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
