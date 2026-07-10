# src/utils/notificaciones.py — Servicio Centralizado de Notificaciones Telegram
# ==============================================================================
# DEDUPLICACIÓN: _notificar_paciente() y _notificar_odontologo() existían en
# 3 archivos diferentes (tools.py, mcp_server.py, api/routes/citas.py).
# Esta es la única fuente de verdad.
# ==============================================================================

import requests

from src.utils.config import TELEGRAM_TOKEN
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _enviar_mensaje_telegram(chat_id: str, mensaje: str) -> bool:
    """Envía un mensaje directo vía API HTTP de Telegram.

    Args:
        chat_id: ID del chat de Telegram del destinatario.
        mensaje: Texto del mensaje (soporta HTML con parse_mode HTML).

    Returns:
        True si se envió exitosamente, False en caso contrario.
    """
    if not TELEGRAM_TOKEN:
        logger.error("[NOTIF] TELEGRAM_BOT_TOKEN no configurado.")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": mensaje, "parse_mode": "HTML"},
            timeout=5,
        )
        if resp.status_code == 200:
            return True
        else:
            logger.error(f"[NOTIF] Telegram respondió {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"[NOTIF] Excepción enviando a {chat_id}: {e}")
        return False


def notificar_paciente(supabase_client, paciente_id: int, mensaje: str) -> None:
    """Envía un mensaje directo al paciente en Telegram.

    Busca el chat_id del paciente en la tabla `pacientes` usando el campo
    `telefono` (que almacena el Telegram chat_id).

    Args:
        supabase_client: Cliente Supabase activo.
        paciente_id: ID del paciente en la base de datos.
        mensaje: Texto del mensaje a enviar.
    """
    try:
        pac = (
            supabase_client.table("pacientes")
            .select("telefono")
            .eq("id", paciente_id)
            .limit(1)
            .execute()
        )
        if not pac.data:
            logger.warning(f"[NOTIF PACIENTE] Paciente ID {paciente_id} no encontrado en BD.")
            return
        chat_id = pac.data[0]["telefono"]
        if _enviar_mensaje_telegram(chat_id, mensaje):
            logger.info(f"[NOTIF PACIENTE] ✅ Mensaje enviado al chat_id {chat_id}.")
        else:
            logger.error(f"[NOTIF PACIENTE] ❌ No se pudo enviar al chat_id {chat_id}.")
    except Exception as e:
        logger.error(f"[NOTIF PACIENTE] ❌ Excepción: {e}")


def notificar_odontologo(supabase_client, odontologo_id: int, mensaje: str) -> None:
    """Envía un mensaje directo al odontólogo en Telegram cuando se le asigna una cita.

    Busca el chat_id del odontólogo en la tabla `personal` usando el campo
    `telefono` (que almacena el Telegram chat_id).

    Args:
        supabase_client: Cliente Supabase activo.
        odontologo_id: ID del odontólogo en la base de datos.
        mensaje: Texto del mensaje a enviar.
    """
    try:
        doc = (
            supabase_client.table("personal")
            .select("telefono")
            .eq("id", odontologo_id)
            .limit(1)
            .execute()
        )
        if not doc.data or not doc.data[0].get("telefono"):
            logger.warning(
                f"[NOTIF ODONTÓLOGO] Odontólogo ID {odontologo_id} sin chat_id en BD."
            )
            return
        chat_id = doc.data[0]["telefono"]
        if _enviar_mensaje_telegram(chat_id, mensaje):
            logger.info(f"[NOTIF ODONTÓLOGO] ✅ Mensaje enviado al chat_id {chat_id}.")
        else:
            logger.error(f"[NOTIF ODONTÓLOGO] ❌ No se pudo enviar al chat_id {chat_id}.")
    except Exception as e:
        logger.error(f"[NOTIF ODONTÓLOGO] ❌ Excepción: {e}")


def notificar_cambio_estado_cita(
    supabase_client, cita_id: int, paciente_id: int, nuevo_estado: str
) -> None:
    """Envía notificación automática al paciente cuando cambia el estado de su cita.

    Args:
        supabase_client: Cliente Supabase activo.
        cita_id: ID de la cita.
        paciente_id: ID del paciente.
        nuevo_estado: Nuevo estado de la cita.
    """
    mensajes = {
        "confirmada": (
            f"✅ <b>Tu cita #{cita_id} ha sido confirmada.</b>\n¡Te esperamos en AutomaDent!"
        ),
        "cancelada": (
            f"❌ <b>Tu cita #{cita_id} ha sido cancelada.</b>\nPor favor contáctanos para reagendar."
        ),
        "no_show": (
            f"⚠️ <b>Tu cita #{cita_id} fue registrada como no asistida.</b>\n"
            "Si hubo un error, comunícate con nosotros."
        ),
        "asistida": (
            f"✅ <b>Gracias por tu visita.</b>\nTu cita #{cita_id} quedó registrada como completada."
        ),
    }
    if nuevo_estado in mensajes:
        notificar_paciente(supabase_client, paciente_id, mensajes[nuevo_estado])
