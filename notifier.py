# notifier.py — Sistema de Notificaciones Proactivas (Standalone)
# ================================================================
# Script independiente para ejecutarse vía Cron/Task Scheduler.
# NO depende del bot de Telegram corriendo.
# Usa la API HTTP de Telegram directamente con httpx.
#
# Ejecución:
#   python notifier.py                    → Ejecuta ambas alertas
#   python notifier.py --doctores         → Solo alerta a doctores
#   python notifier.py --recordatorios    → Solo recordatorios a pacientes
#
# Cron (Linux) ejemplo:
#   0 7 * * * cd /ruta/proyecto && python notifier.py --doctores
#   0 19 * * * cd /ruta/proyecto && python notifier.py --recordatorios
#
# Task Scheduler (Windows):
#   Trigger: Daily at 7:00 AM
#   Action: python C:\ruta\proyecto\notifier.py --doctores
# ================================================================

import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
import httpx

from database import supabase

load_dotenv()

# ─── Configuración ───────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
TIMEZONE = ZoneInfo("America/Lima")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("notifier")


# ==================================================================
#  UTILIDADES
# ==================================================================

async def enviar_mensaje_telegram(chat_id: str, texto: str) -> bool:
    """Envía un mensaje directo vía API HTTP de Telegram.

    Args:
        chat_id: ID del chat de Telegram del destinatario.
        texto: Texto del mensaje (soporta Markdown).

    Returns:
        True si se envió exitosamente, False en caso contrario.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{TELEGRAM_API}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": texto,
                    "parse_mode": "Markdown",
                },
            )
            if response.status_code == 200:
                logger.info(f"✅ Mensaje enviado a {chat_id}")
                return True
            else:
                logger.error(f"❌ Error enviando a {chat_id}: {response.text}")
                return False
    except Exception as e:
        logger.error(f"❌ Excepción enviando a {chat_id}: {e}")
        return False


# ==================================================================
#  ALERTAS A DOCTORES (Citas del día)
# ==================================================================

async def alertar_doctores_citas_dia() -> None:
    """Lee las citas de hoy y envía a cada odontólogo su agenda del día.
    Diseñado para ejecutarse cada mañana (ej: 7:00 AM).
    """
    hoy = datetime.now(TIMEZONE).date()
    inicio_dia = datetime(hoy.year, hoy.month, hoy.day, 0, 0, 0, tzinfo=TIMEZONE).isoformat()
    fin_dia = datetime(hoy.year, hoy.month, hoy.day, 23, 59, 59, tzinfo=TIMEZONE).isoformat()

    logger.info(f"📅 Consultando citas para hoy: {hoy}")

    # Obtener citas del día con datos del paciente y doctor
    citas = (
        supabase.table("citas")
        .select("id, fecha_hora, motivo_consulta, estado, odontologo_id, paciente_id")
        .gte("fecha_hora", inicio_dia)
        .lte("fecha_hora", fin_dia)
        .in_("estado", ["programada", "confirmada"])
        .order("fecha_hora")
        .execute()
    )

    if not citas.data:
        logger.info("📭 No hay citas programadas para hoy.")
        return

    # Obtener información de los doctores
    doctor_ids = list(set(c["odontologo_id"] for c in citas.data))
    doctores = (
        supabase.table("personal")
        .select("id, nombre, apellido, telefono")
        .in_("id", doctor_ids)
        .execute()
    )
    doctores_map = {d["id"]: d for d in (doctores.data or [])}

    # Obtener información de los pacientes
    paciente_ids = list(set(c["paciente_id"] for c in citas.data))
    pacientes = (
        supabase.table("pacientes")
        .select("id, nombre, apellido")
        .in_("id", paciente_ids)
        .execute()
    )
    pacientes_map = {p["id"]: p for p in (pacientes.data or [])}

    # Agrupar citas por doctor
    citas_por_doctor = {}
    for cita in citas.data:
        doc_id = cita["odontologo_id"]
        if doc_id not in citas_por_doctor:
            citas_por_doctor[doc_id] = []
        citas_por_doctor[doc_id].append(cita)

    # Enviar alerta a cada doctor
    enviados = 0
    for doc_id, citas_doc in citas_por_doctor.items():
        doctor = doctores_map.get(doc_id)
        if not doctor or not doctor.get("telefono"):
            logger.warning(f"⚠️ Doctor ID {doc_id} sin teléfono de Telegram registrado.")
            continue

        # Construir mensaje
        lineas = [f"🦷 *Buenos días, Dr(a). {doctor['nombre']}!*\n"]
        lineas.append(f"📅 Tienes *{len(citas_doc)} cita(s)* para hoy ({hoy.strftime('%d/%m/%Y')}):\n")

        for i, cita in enumerate(citas_doc, 1):
            hora = datetime.fromisoformat(cita["fecha_hora"]).strftime("%H:%M")
            paciente = pacientes_map.get(cita["paciente_id"], {})
            pac_nombre = f"{paciente.get('nombre', '?')} {paciente.get('apellido', '?')}"
            motivo = cita.get("motivo_consulta") or "No especificado"

            lineas.append(
                f"*{i}.* 🕐 {hora}\n"
                f"   👤 {pac_nombre}\n"
                f"   📝 {motivo}\n"
                f"   📌 Estado: {cita['estado']}\n"
            )

        lineas.append("¡Que tengas un excelente día! 💪")
        mensaje = "\n".join(lineas)

        if await enviar_mensaje_telegram(doctor["telefono"], mensaje):
            enviados += 1

    logger.info(f"📤 Alertas enviadas a {enviados}/{len(citas_por_doctor)} doctores.")


# ==================================================================
#  RECORDATORIOS A PACIENTES (Citas de mañana)
# ==================================================================

async def recordar_pacientes_citas() -> None:
    """Envía recordatorios a pacientes que tienen cita mañana.
    Diseñado para ejecutarse cada tarde/noche (ej: 7:00 PM).
    """
    manana = (datetime.now(TIMEZONE) + timedelta(days=1)).date()
    inicio_dia = datetime(manana.year, manana.month, manana.day, 0, 0, 0, tzinfo=TIMEZONE).isoformat()
    fin_dia = datetime(manana.year, manana.month, manana.day, 23, 59, 59, tzinfo=TIMEZONE).isoformat()

    logger.info(f"📅 Consultando citas para mañana: {manana}")

    citas = (
        supabase.table("citas")
        .select("id, fecha_hora, motivo_consulta, paciente_id, odontologo_id")
        .gte("fecha_hora", inicio_dia)
        .lte("fecha_hora", fin_dia)
        .in_("estado", ["programada", "confirmada"])
        .order("fecha_hora")
        .execute()
    )

    if not citas.data:
        logger.info("📭 No hay citas programadas para mañana.")
        return

    # Obtener datos de pacientes y doctores
    paciente_ids = list(set(c["paciente_id"] for c in citas.data))
    pacientes = (
        supabase.table("pacientes")
        .select("id, nombre, telefono")
        .in_("id", paciente_ids)
        .execute()
    )
    pacientes_map = {p["id"]: p for p in (pacientes.data or [])}

    doctor_ids = list(set(c["odontologo_id"] for c in citas.data))
    doctores = (
        supabase.table("personal")
        .select("id, nombre, apellido")
        .in_("id", doctor_ids)
        .execute()
    )
    doctores_map = {d["id"]: d for d in (doctores.data or [])}

    # Enviar recordatorio a cada paciente
    enviados = 0
    for cita in citas.data:
        paciente = pacientes_map.get(cita["paciente_id"])
        if not paciente or not paciente.get("telefono"):
            continue

        doctor = doctores_map.get(cita["odontologo_id"], {})
        hora = datetime.fromisoformat(cita["fecha_hora"]).strftime("%H:%M")
        doc_nombre = f"Dr(a). {doctor.get('nombre', '?')} {doctor.get('apellido', '?')}"

        mensaje = (
            f"🦷 *Recordatorio de Cita — Clínica AutomaDent*\n\n"
            f"Hola *{paciente['nombre']}*, te recordamos que tienes una cita mañana:\n\n"
            f"📅 Fecha: *{manana.strftime('%d/%m/%Y')}*\n"
            f"🕐 Hora: *{hora}*\n"
            f"🦷 Doctor: *{doc_nombre}*\n"
            f"📝 Motivo: {cita.get('motivo_consulta') or 'No especificado'}\n\n"
            f"Si necesitas reprogramar, escríbenos por este chat. 😊\n"
            f"¡Te esperamos!"
        )

        if await enviar_mensaje_telegram(paciente["telefono"], mensaje):
            enviados += 1

    logger.info(f"📤 Recordatorios enviados a {enviados}/{len(citas.data)} pacientes.")


# ==================================================================
#  PUNTO DE ENTRADA
# ==================================================================

async def main():
    """Ejecuta las alertas según los argumentos de línea de comando."""
    args = sys.argv[1:] if len(sys.argv) > 1 else []

    if "--doctores" in args:
        await alertar_doctores_citas_dia()
    elif "--recordatorios" in args:
        await recordar_pacientes_citas()
    else:
        # Sin argumentos: ejecutar ambas
        await alertar_doctores_citas_dia()
        await recordar_pacientes_citas()


if __name__ == "__main__":
    asyncio.run(main())