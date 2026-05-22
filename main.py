# main.py — Punto de entrada del Bot de Telegram
# ==============================================================================
# Arranca automáticamente el servidor MCP (mcp_server.py) como subproceso,
# espera que esté listo, carga las herramientas y lanza el bot de Telegram.
#
# Solo necesitas correr: python main.py
# ==============================================================================

import os
import sys
import asyncio
import logging
import subprocess
import httpx

# Bypass de proxy del sistema para conexiones locales (fix Windows)
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from langchain_mcp_adapters.client import MultiServerMCPClient
from database import supabase
from agents import procesar_mensaje, set_mcp_tools

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8001/mcp")
MCP_SERVER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")


# ==============================================================================
#  GESTIÓN DEL SERVIDOR MCP (subproceso automático)
# ==============================================================================

_mcp_process: subprocess.Popen | None = None


def _start_mcp_server() -> subprocess.Popen:
    """Arranca mcp_server.py como subproceso en background."""
    logger.info("Iniciando servidor MCP como subproceso...")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"  # Fix emojis en consola Windows
    proc = subprocess.Popen(
        [sys.executable, MCP_SERVER_SCRIPT],
        stdout=sys.stdout,
        stderr=sys.stderr,
        env=env,
    )
    return proc


async def _wait_for_mcp_server(url: str, timeout: int = 20) -> None:
    """Espera hasta que el servidor MCP responda (con retry).
    Un GET a /mcp devuelve 405 Method Not Allowed, lo que confirma que el servidor está activo."""
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
                # Cualquier código HTTP (incluido 405) confirma que el servidor está vivo
                logger.info("✅ Servidor MCP listo.")
                return

    raise RuntimeError(
        f"❌ El servidor MCP no respondió en {timeout}s ({url}).\n"
        "Revisa que mcp_server.py arranca sin errores de configuración."
    )


# ==============================================================================
#  LÓGICA DE ROLES (RBAC)
# ==============================================================================

async def obtener_rol_usuario(chat_id: str) -> str:
    """Determina el rol del usuario buscando su chat_id en personal y pacientes."""
    try:
        personal_res = (
            supabase.table("personal")
            .select("rol")
            .eq("telefono", chat_id)
            .maybe_single()
            .execute()
        )
        if personal_res.data:
            return personal_res.data["rol"]

        pacientes_res = (
            supabase.table("pacientes")
            .select("id")
            .eq("telefono", chat_id)
            .maybe_single()
            .execute()
        )
        if pacientes_res.data:
            return "paciente"

        return "paciente_no_registrado"

    except Exception as e:
        logger.error(f"Error obteniendo rol del usuario {chat_id}: {e}")
        return "paciente_no_registrado"


# ==============================================================================
#  HANDLERS DE TELEGRAM
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    rol = await obtener_rol_usuario(chat_id)

    if rol in ["odontologo", "recepcionista", "administrador"]:
        await update.message.reply_text(
            f"🔑 <b>Sesión Administrativa Iniciada</b>\n\n"
            f"Bienvenido(a) al bot interno de AutomaDent.\n"
            f"👤 Rol detectado: <b>{rol.upper()}</b>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "🦷 <b>¡Bienvenido a la Clínica Dental AutomaDent!</b>\n\n"
            "Soy tu asistente virtual. ¿En qué puedo ayudarte?\n\n"
            "📋 <b>Registro</b> — Si eres nuevo paciente\n"
            "📅 <b>Citas</b> — Consultar disponibilidad y agendar\n"
            "📂 <b>Historial</b> — Consultar tu evolución clínica",
            parse_mode="HTML",
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    texto = update.message.text

    rol = await obtener_rol_usuario(chat_id)
    logger.info(f"📩 {chat_id} | Rol: {rol} | '{texto[:40]}...'")

    await update.effective_chat.send_action("typing")

    try:
        respuesta = await procesar_mensaje(
            telegram_chat_id=chat_id,
            user_role=rol,
            mensaje=texto,
        )
        await update.message.reply_text(respuesta, parse_mode="HTML")
        logger.info(f"✅ Respuesta enviada a {chat_id}")

    except Exception as e:
        logger.error(f"❌ Error procesando mensaje de {chat_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ Ocurrió un inconveniente. Por favor intenta de nuevo."
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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


# ==============================================================================
#  INICIO ASYNC (MCP + BOT)
# ==============================================================================

async def run() -> None:
    """Arranca el servidor MCP, conecta, carga las herramientas y lanza el bot."""
    global _mcp_process

    # 1. Arrancar el servidor MCP como subproceso
    _mcp_process = _start_mcp_server()

    try:
        # 2. Esperar a que el servidor esté listo
        await _wait_for_mcp_server(MCP_SERVER_URL)

        # 3. Cargar herramientas MCP (proxies={} fuerza bypass del proxy del sistema)
        logger.info(f"🔌 Cargando herramientas desde {MCP_SERVER_URL} ...")
        mcp_client = MultiServerMCPClient(
            {
                "automadent": {
                    "url": MCP_SERVER_URL,
                    "transport": "streamable-http",
                }
            }
        )

        tools = await mcp_client.get_tools()
        set_mcp_tools(tools)
        logger.info(f"✅ {len(tools)} herramientas MCP cargadas: {[t.name for t in tools]}")

        # 4. Arrancar el bot de Telegram
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
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
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("🛑 Bot detenido.")
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
