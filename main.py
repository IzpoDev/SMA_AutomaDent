# main.py — Punto de entrada del Bot de Telegram (Polling)
# ==============================================================================
# Determina el rol del usuario en Supabase mediante su chat_id.
# Pasa la información y el mensaje al Sistema Multiagente (SMA).
# ==============================================================================

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
from database import supabase
from agents import procesar_mensaje

load_dotenv()

# ─── Configuración de Logging ────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]


# ==============================================================================
#  LÓGICA DE ROLES (RBAC)
# ==============================================================================

async def obtener_rol_usuario(chat_id: str) -> str:
    """Busca el chat_id en las tablas personal y pacientes para determinar su rol.

    Args:
        chat_id: ID del chat de Telegram del usuario.

    Returns:
        El rol del usuario: 'odontologo', 'recepcionista', 'administrador',
        'paciente', o 'paciente_no_registrado'.
    """
    try:
        # 1. Buscar en tabla 'personal'
        personal_res = (
            supabase.table("personal")
            .select("rol")
            .eq("telefono", chat_id)
            .maybe_single()
            .execute()
        )
        if personal_res.data:
            return personal_res.data["rol"]

        # 2. Buscar en tabla 'pacientes'
        pacientes_res = (
            supabase.table("pacientes")
            .select("id")
            .eq("telefono", chat_id)
            .maybe_single()
            .execute()
        )
        if pacientes_res.data:
            return "paciente"

        # 3. No registrado
        return "paciente_no_registrado"

    except Exception as e:
        logger.error(f"Error obteniendo rol del usuario {chat_id}: {e}")
        return "paciente_no_registrado"


# ==============================================================================
#  HANDLERS DE TELEGRAM
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para el comando /start. Personaliza la bienvenida según el rol."""
    chat_id = str(update.effective_chat.id)
    rol = await obtener_rol_usuario(chat_id)

    if rol in ["odontologo", "recepcionista", "administrador"]:
        rol_txt = rol.upper()
        await update.message.reply_text(
            f"🔑 <b>Sesión Administrativa Iniciada</b>\n\n"
            f"Bienvenido(a) al bot interno de AutomaDent.\n"
            f"👤 Rol detectado: <b>{rol_txt}</b>\n\n"
            f"Puedes usar tus comandos y herramientas autorizadas directamente.",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            "🦷 <b>¡Bienvenido a la Clínica Dental AutomaDent!</b>\n\n"
            "Soy tu asistente virtual. ¿En qué puedo ayudarte hoy?\n\n"
            "📋 <b>Registro</b> — Si eres un nuevo paciente\n"
            "📅 <b>Citas</b> — Consultar disponibilidad y agendar citas\n"
            "📂 <b>Historial</b> — Consultar tu evolución clínica",
            parse_mode="HTML"
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler principal para procesar mensajes de texto."""
    chat_id = str(update.effective_chat.id)
    texto = update.message.text

    # Determinar el rol del usuario
    rol = await obtener_rol_usuario(chat_id)
    logger.info(f"📩 Mensaje recibido de {chat_id} | Rol: {rol} | Texto: {texto[:40]}...")

    # Activar indicador de "escribiendo..." en Telegram
    await update.effective_chat.send_action("typing")

    try:
        # Enviar el mensaje al SMA
        respuesta = await procesar_mensaje(
            telegram_chat_id=chat_id,
            user_role=rol,
            mensaje=texto
        )

        await update.message.reply_text(respuesta, parse_mode="HTML")
        logger.info(f"✅ Respuesta enviada a {chat_id}")

    except Exception as e:
        logger.error(f"❌ Error al procesar mensaje de {chat_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ Ocurrió un inconveniente al procesar tu solicitud. "
            "Por favor intenta de nuevo en unos momentos."
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para el comando /help."""
    chat_id = str(update.effective_chat.id)
    rol = await obtener_rol_usuario(chat_id)

    ayuda_texto = (
        "🆘 <b>Ayuda — Clínica Dental AutomaDent</b>\n\n"
        "Puedes escribirme en lenguaje natural. Ejemplos de uso:\n\n"
    )

    if rol == "odontologo":
        ayuda_texto += (
            "• <i>\"Finalizar cita 15 y registrar evolución\"</i>\n"
            "• <i>\"Actualizar estado de cita 10 a asistida\"</i>\n"
            "• <i>\"Ver historial clínico de paciente 3\"</i>"
        )
    elif rol in ["recepcionista", "administrador"]:
        ayuda_texto += (
            "• <i>\"Registrar pago de la cita 5\"</i>\n"
            "• <i>\"Ver disponibilidad de horarios para el viernes\"</i>\n"
            "• <i>\"Agendar cita para odontólogo 1\"</i>\n"
            "• <i>\"Exportar citas de hoy a Excel\"</i>"
        )
    else:
        ayuda_texto += (
            "• <i>\"Quiero registrarme\"</i>\n"
            "• <i>\"¿Qué horarios hay disponibles para el viernes?\"</i>\n"
            "• <i>\"Agendar una cita\"</i>\n"
            "• <i>\"Quiero consultar mi historial\"</i>"
        )

    await update.message.reply_text(ayuda_texto, parse_mode="HTML")


# ==============================================================================
#  INICIO DE LA APLICACIÓN
# ==============================================================================

def main() -> None:
    """Inicia el bot de Telegram."""
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    webhook_url = os.environ.get("WEBHOOK_URL")
    port_str = os.environ.get("PORT")
    port = int(port_str) if port_str and port_str.isdigit() else 8000

    if webhook_url:
        logger.info(f"🤖 Bot AutomaDent iniciado en modo WEBHOOK en el puerto {port}...")
        logger.info(f"🔗 URL del Webhook: {webhook_url}/{TELEGRAM_TOKEN}")
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=TELEGRAM_TOKEN,
            webhook_url=f"{webhook_url}/{TELEGRAM_TOKEN}",
            allowed_updates=Update.ALL_TYPES
        )
    else:
        logger.info("🤖 Bot AutomaDent iniciado y escuchando en modo POLLING...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
