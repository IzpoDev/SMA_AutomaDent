# main.py — Punto de entrada del Bot de Telegram
# ==============================================================================
# 1. Conecta al servidor MCP (mcp_server.py debe estar corriendo en puerto 8001)
# 2. Carga las herramientas MCP y las pasa a agents.py
# 3. Inicia el bot de Telegram en modo polling
#
# Para ejecutar:
#   Ventana 1: python mcp_server.py
#   Ventana 2: python main.py
# ==============================================================================

import os
import asyncio
import logging
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
    """Inicializa el cliente MCP, carga las herramientas y arranca el bot."""

    logger.info(f"🔌 Conectando al servidor MCP en {MCP_SERVER_URL} ...")

    # En langchain-mcp-adapters 0.2.x no necesita async with:
    # cada llamada a una tool abre su propia sesión HTTP.
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


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("🛑 Bot detenido.")


if __name__ == "__main__":
    main()
