# src/notifier/notifier.py — Notificaciones Proactivas (Standalone)
# ==============================================================================
# Refactorizado de bot/notifier.py.
# Script independiente que NO depende del bot corriendo.
#
# Ejecución:
#   python -m src.notifier.notifier                  → Ambas alertas
#   python -m src.notifier.notifier --doctores        → Solo alertas a doctores
#   python -m src.notifier.notifier --recordatorios   → Solo recordatorios a pacientes
#
# Vía src/main.py:
#   python -m src.main notifier --doctores
# ==============================================================================

import sys
import asyncio
from datetime import datetime, timedelta

import httpx

from src.utils.config import TELEGRAM_TOKEN, TIMEZONE
from src.utils.database import supabase
from src.utils.logger import get_logger

logger = get_logger(__name__)

_TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


# ==============================================================================
#  ENVÍO ASYNC DE MENSAJES
# ==============================================================================

async def _enviar_telegram_async(chat_id: str, texto: str) -> bool:
    """Envía un mensaje a Telegram usando httpx async.

    Args:
        chat_id: Chat ID de Telegram del destinatario.
        texto: Texto del mensaje (soporta Markdown).

    Returns:
        True si fue enviado correctamente.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_TELEGRAM_API}/sendMessage",
                json={"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"},
            )
            if resp.status_code == 200:
                logger.info(f"✅ Mensaje enviado a {chat_id}")
                return True
            else:
                logger.error(f"❌ Error enviando a {chat_id}: {resp.text}")
                return False
    except Exception as e:
        logger.error(f"❌ Excepción enviando a {chat_id}: {e}")
        return False


# ==============================================================================
#  ALERTAS A DOCTORES (Citas del día — ejecutar a las 7:00 AM)
# ==============================================================================

async def alertar_doctores_citas_dia() -> None:
    """Envía a cada odontólogo su agenda del día actual.

    Consulta las citas programadas/confirmadas de hoy y agrupa por doctor.
    Diseñado para ejecutarse cada mañana (Task Scheduler / Cron).
    """
    hoy = datetime.now(TIMEZONE).date()
    inicio = datetime(hoy.year, hoy.month, hoy.day, 0, 0, 0, tzinfo=TIMEZONE).isoformat()
    fin = datetime(hoy.year, hoy.month, hoy.day, 23, 59, 59, tzinfo=TIMEZONE).isoformat()

    logger.info(f"📅 Alertas para hoy: {hoy}")

    citas = (
        supabase.table("citas")
        .select("id, fecha_hora, motivo_consulta, estado, odontologo_id, paciente_id")
        .gte("fecha_hora", inicio).lte("fecha_hora", fin)
        .in_("estado", ["programada", "confirmada"])
        .order("fecha_hora").execute()
    )
    if not citas.data:
        logger.info("📭 Sin citas para hoy.")
        return

    doctor_ids = list({c["odontologo_id"] for c in citas.data})
    paciente_ids = list({c["paciente_id"] for c in citas.data})

    doctores = {
        d["id"]: d for d in
        (supabase.table("personal").select("id, nombre, apellido, telefono").in_("id", doctor_ids).execute().data or [])
    }
    pacientes = {
        p["id"]: p for p in
        (supabase.table("pacientes").select("id, nombre, apellido").in_("id", paciente_ids).execute().data or [])
    }

    citas_por_doctor: dict = {}
    for c in citas.data:
        citas_por_doctor.setdefault(c["odontologo_id"], []).append(c)

    enviados = 0
    for doc_id, citas_doc in citas_por_doctor.items():
        doctor = doctores.get(doc_id)
        if not doctor or not doctor.get("telefono"):
            logger.warning(f"⚠️ Doctor ID {doc_id} sin Telegram registrado.")
            continue

        lineas = [
            f"🦷 *Buenos días, Dr(a). {doctor['nombre']}!*\n",
            f"📅 Tienes *{len(citas_doc)} cita(s)* para hoy ({hoy.strftime('%d/%m/%Y')}):\n",
        ]
        for i, c in enumerate(citas_doc, 1):
            hora = datetime.fromisoformat(c["fecha_hora"]).strftime("%H:%M")
            pac = pacientes.get(c["paciente_id"], {})
            lineas.append(
                f"*{i}.* 🕐 {hora}\n"
                f"   👤 {pac.get('nombre', '?')} {pac.get('apellido', '?')}\n"
                f"   📝 {c.get('motivo_consulta') or 'Sin motivo'}\n"
            )
        lineas.append("¡Que tengas un excelente día! 💪")

        if await _enviar_telegram_async(doctor["telefono"], "\n".join(lineas)):
            enviados += 1

    logger.info(f"📤 Alertas enviadas a {enviados}/{len(citas_por_doctor)} doctores.")


# ==============================================================================
#  RECORDATORIOS A PACIENTES (Citas de mañana — ejecutar a las 7:00 PM)
# ==============================================================================

async def recordar_pacientes_citas() -> None:
    """Envía recordatorios a pacientes con citas programadas para mañana.

    Diseñado para ejecutarse cada tarde/noche (Task Scheduler / Cron).
    """
    manana = (datetime.now(TIMEZONE) + timedelta(days=1)).date()
    inicio = datetime(manana.year, manana.month, manana.day, 0, 0, 0, tzinfo=TIMEZONE).isoformat()
    fin = datetime(manana.year, manana.month, manana.day, 23, 59, 59, tzinfo=TIMEZONE).isoformat()

    logger.info(f"📅 Recordatorios para mañana: {manana}")

    citas = (
        supabase.table("citas")
        .select("id, fecha_hora, motivo_consulta, paciente_id, odontologo_id")
        .gte("fecha_hora", inicio).lte("fecha_hora", fin)
        .in_("estado", ["programada", "confirmada"])
        .order("fecha_hora").execute()
    )
    if not citas.data:
        logger.info("📭 Sin citas para mañana.")
        return

    paciente_ids = list({c["paciente_id"] for c in citas.data})
    doctor_ids = list({c["odontologo_id"] for c in citas.data})

    pacientes = {
        p["id"]: p for p in
        (supabase.table("pacientes").select("id, nombre, telefono").in_("id", paciente_ids).execute().data or [])
    }
    doctores = {
        d["id"]: d for d in
        (supabase.table("personal").select("id, nombre, apellido").in_("id", doctor_ids).execute().data or [])
    }

    enviados = 0
    for c in citas.data:
        pac = pacientes.get(c["paciente_id"])
        if not pac or not pac.get("telefono"):
            continue
        doc = doctores.get(c["odontologo_id"], {})
        hora = datetime.fromisoformat(c["fecha_hora"]).strftime("%H:%M")
        doc_nombre = f"Dr(a). {doc.get('nombre', '?')} {doc.get('apellido', '?')}"

        mensaje = (
            f"🦷 *Recordatorio — Clínica AutomaDent*\n\n"
            f"Hola *{pac['nombre']}*, tienes cita mañana:\n\n"
            f"📅 *{manana.strftime('%d/%m/%Y')}* a las *{hora}*\n"
            f"🦷 {doc_nombre}\n"
            f"📝 {c.get('motivo_consulta') or 'Sin motivo'}\n\n"
            f"Si necesitas reprogramar, escríbenos. 😊"
        )
        if await _enviar_telegram_async(pac["telefono"], mensaje):
            enviados += 1

    logger.info(f"📤 Recordatorios enviados a {enviados}/{len(citas.data)} pacientes.")


# ==============================================================================
#  PUNTO DE ENTRADA
# ==============================================================================

async def _main() -> None:
    """Ejecuta las alertas según los argumentos de línea de comando."""
    args = set(sys.argv[1:])
    if "--doctores" in args:
        await alertar_doctores_citas_dia()
    elif "--recordatorios" in args:
        await recordar_pacientes_citas()
    else:
        await alertar_doctores_citas_dia()
        await recordar_pacientes_citas()


if __name__ == "__main__":
    asyncio.run(_main())
