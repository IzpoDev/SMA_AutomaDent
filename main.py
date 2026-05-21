# main.py — Punto de entrada de la aplicación
# ================================================================
# Configura el bot de Telegram con Polling.
# Recibe mensajes, extrae chat_id y texto, los pasa al SMA,
# y devuelve la respuesta al usuario.
# ================================================================

import os
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
from agents import procesar_mensaje

load_dotenv()

# ─── Logging ─────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Token ───────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]


# ==================================================================
#  HANDLERS
# ==================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para el comando /start."""
    await update.message.reply_text(
        "🦷 *¡Bienvenido a la Clínica Dental AutomaDent!*\n\n"
        "Soy tu asistente virtual y puedo ayudarte con:\n\n"
        "📋 *Registro* — Registrarte como paciente nuevo\n"
        "📅 *Citas* — Consultar disponibilidad y agendar citas\n"
        "📂 *Historial* — Ver tu historial clínico\n"
        "💰 *Pagos* — Registrar y consultar pagos\n\n"
        "Escríbeme lo que necesites y te guiaré. 😊",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para mensajes de texto. Procesa a través del SMA."""
    chat_id = str(update.effective_chat.id)
    texto = update.message.text

    logger.info(f"📩 Mensaje de {chat_id}: {texto[:50]}...")

    # Indicador de "escribiendo..." mientras el SMA procesa
    await update.effective_chat.send_action("typing")

    try:
        # Procesar el mensaje con el Sistema Multiagente
        respuesta = await procesar_mensaje(
            telegram_chat_id=chat_id,
            mensaje=texto,
        )

        await update.message.reply_text(respuesta)
        logger.info(f"✅ Respuesta enviada a {chat_id}")

    except Exception as e:
        logger.error(f"❌ Error procesando mensaje de {chat_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ Ocurrió un error procesando tu mensaje. "
            "Por favor intenta de nuevo o contacta a recepción directamente."
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para el comando /help."""
    await update.message.reply_text(
        "🆘 *Ayuda — Clínica Dental AutomaDent*\n\n"
        "Puedes escribirme en lenguaje natural. Ejemplos:\n\n"
        "• _\"Quiero registrarme\"_ → Te guío en el registro\n"
        "• _\"¿Qué horarios hay para el viernes?\"_ → Muestro disponibilidad\n"
        "• _\"Quiero agendar una cita\"_ → Te ayudo a reservar\n"
        "• _\"Ver mi historial\"_ → Muestro tus atenciones previas\n"
        "• _\"Quiero pagar mi cita\"_ → Te guío en el pago\n\n"
        "Comandos:\n"
        "/start — Mensaje de bienvenida\n"
        "/help — Esta ayuda",
        parse_mode="Markdown",
    )


# ==================================================================
#  ARRANQUE DE LA APLICACIÓN
# ==================================================================

def main() -> None:
    """Inicia el bot de Telegram con Polling."""
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Registrar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("🤖 Bot AutomaDent iniciado (modo Polling)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
