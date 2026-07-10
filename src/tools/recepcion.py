# src/tools/recepcion.py — Herramientas del Agente de Recepción
# ==============================================================================
# Migrado de bot/mcp_server.py (herramientas de recepción).
# Gestiona: registro de pacientes, disponibilidad, agendamiento, historial.
# ==============================================================================

from datetime import datetime
from typing import Optional

from src.utils.config import (
    TIMEZONE,
    DURACION_CITA_MIN,
    HORARIO_INICIO,
    HORARIO_FIN,
    DIAS_LABORALES,
)
from src.utils.database import supabase
from src.utils.notificaciones import notificar_odontologo
from src.utils.logger import get_logger

logger = get_logger(__name__)


def crear_paciente_y_historia(
    telegram_chat_id: str,
    user_role: str,
    nombre: str,
    apellido: str,
    email: str = "",
    fecha_nacimiento: str = "",
) -> str:
    """Registra un nuevo paciente y crea su historia clínica vacía.

    Args:
        telegram_chat_id: ID de Telegram del usuario (se usa como teléfono).
        user_role: Rol del usuario.
        nombre: Nombre del paciente.
        apellido: Apellido del paciente.
        email: Correo electrónico (opcional).
        fecha_nacimiento: Fecha de nacimiento YYYY-MM-DD (opcional).

    Returns:
        Mensaje de confirmación o error.
    """
    existente = (
        supabase.table("pacientes")
        .select("id, nombre, apellido")
        .eq("telefono", telegram_chat_id)
        .limit(1)
        .execute()
    )
    if existente.data:
        return (
            f"⚠️ Ya estás registrado como "
            f"{existente.data[0]['nombre']} {existente.data[0]['apellido']}."
        )

    datos = {
        "nombre": nombre.strip().title(),
        "apellido": apellido.strip().title(),
        "telefono": telegram_chat_id,
    }
    if email:
        datos["email"] = email.strip().lower()
    if fecha_nacimiento:
        datos["fecha_nacimiento"] = fecha_nacimiento

    resultado = supabase.table("pacientes").insert(datos).execute()
    paciente_id = resultado.data[0]["id"]
    supabase.table("historias_clinicas").insert({"paciente_id": paciente_id}).execute()

    return (
        f"✅ ¡Registro exitoso!\n"
        f"👤 Paciente: {datos['nombre']} {datos['apellido']}\n"
        f"📂 Historia clínica creada."
    )


def consultar_disponibilidad_agenda(
    telegram_chat_id: str,
    user_role: str,
    fecha: str,
    especialidad: str = "",
) -> str:
    """Consulta los horarios disponibles de odontólogos para una fecha.

    Args:
        telegram_chat_id: ID de Telegram del usuario.
        user_role: Rol del usuario.
        fecha: Fecha en formato YYYY-MM-DD.
        especialidad: Filtro opcional (ej: 'ortodoncia').

    Returns:
        Listado de slots disponibles por odontólogo.
    """
    try:
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        return "❌ Formato de fecha inválido. Usa YYYY-MM-DD (ej: 2026-05-23)."

    hoy = datetime.now(TIMEZONE).date()
    if fecha_obj < hoy:
        return "❌ No puedes consultar fechas pasadas."
    if fecha_obj.weekday() not in DIAS_LABORALES:
        return "❌ La clínica no atiende los domingos. Elige Lunes a Sábado."

    query = (
        supabase.table("personal")
        .select("id, nombre, apellido, especialidad")
        .eq("rol", "odontologo")
    )
    if especialidad:
        query = query.ilike("especialidad", f"%{especialidad}%")
    odontologos = query.execute()

    if not odontologos.data:
        return (
            f"❌ No se encontraron odontólogos"
            f"{' con especialidad ' + especialidad if especialidad else ''}."
        )

    inicio_dia = datetime(
        fecha_obj.year, fecha_obj.month, fecha_obj.day, 0, 0, 0, tzinfo=TIMEZONE
    ).isoformat()
    fin_dia = datetime(
        fecha_obj.year, fecha_obj.month, fecha_obj.day, 23, 59, 59, tzinfo=TIMEZONE
    ).isoformat()

    citas_dia = (
        supabase.table("citas")
        .select("odontologo_id, fecha_hora")
        .gte("fecha_hora", inicio_dia)
        .lte("fecha_hora", fin_dia)
        .in_("estado", ["programada", "confirmada"])
        .execute()
    )

    ocupados: dict = {}
    for c in (citas_dia.data or []):
        doc_id = c["odontologo_id"]
        hora = datetime.fromisoformat(c["fecha_hora"]).strftime("%H:%M")
        ocupados.setdefault(doc_id, set()).add(hora)

    hora_actual = datetime.now(TIMEZONE) if fecha_obj == hoy else None
    todos_slots = []

    for doc in odontologos.data:
        slots = []
        for h in range(HORARIO_INICIO, HORARIO_FIN):
            for m in range(0, 60, DURACION_CITA_MIN):
                slot_str = f"{h:02d}:{m:02d}"
                if hora_actual:
                    slot_dt = datetime(
                        fecha_obj.year, fecha_obj.month, fecha_obj.day, h, m, tzinfo=TIMEZONE
                    )
                    if slot_dt <= hora_actual:
                        continue
                if slot_str in ocupados.get(doc["id"], set()):
                    continue
                slots.append(slot_str)
        if slots:
            todos_slots.append(
                f"🦷 Dr(a). {doc['nombre']} {doc['apellido']} ({doc['especialidad']}) [ID: {doc['id']}]\n"
                f"   🕐 {', '.join(slots)}"
            )

    if not todos_slots:
        return f"❌ No hay horarios disponibles para el {fecha}."
    return f"📅 Disponibilidad para el {fecha}:\n\n" + "\n\n".join(todos_slots)


def agendar_cita(
    telegram_chat_id: str,
    user_role: str,
    odontologo_id: int,
    fecha_hora: str,
    motivo_consulta: str,
) -> str:
    """Agenda una nueva cita para el paciente registrado.

    Args:
        telegram_chat_id: ID de Telegram del paciente.
        user_role: Rol del usuario.
        odontologo_id: ID del odontólogo.
        fecha_hora: Fecha y hora ISO YYYY-MM-DDTHH:MM.
        motivo_consulta: Motivo de la consulta.

    Returns:
        Confirmación de la cita agendada.
    """
    paciente = (
        supabase.table("pacientes")
        .select("id, nombre, apellido")
        .eq("telefono", telegram_chat_id)
        .limit(1)
        .execute()
    )
    if not paciente.data:
        return "❌ No estás registrado. Escribe 'Quiero registrarme' primero."

    doctor = (
        supabase.table("personal")
        .select("id, nombre, apellido")
        .eq("id", odontologo_id)
        .eq("rol", "odontologo")
        .limit(1)
        .execute()
    )
    if not doctor.data:
        return f"❌ No se encontró un odontólogo con ID {odontologo_id}."

    try:
        dt = datetime.fromisoformat(fecha_hora).replace(tzinfo=TIMEZONE)
    except ValueError:
        return "❌ Formato inválido. Usa YYYY-MM-DDTHH:MM."

    if dt <= datetime.now(TIMEZONE):
        return "❌ No puedes agendar citas en el pasado."

    nueva_cita = (
        supabase.table("citas")
        .insert({
            "paciente_id": paciente.data[0]["id"],
            "odontologo_id": odontologo_id,
            "fecha_hora": dt.isoformat(),
            "estado": "programada",
            "motivo_consulta": motivo_consulta.strip(),
        })
        .execute()
    )
    cita_id = nueva_cita.data[0]["id"]
    pac_nombre = f"{paciente.data[0]['nombre']} {paciente.data[0]['apellido']}"
    doc_nombre = f"Dr(a). {doctor.data[0]['nombre']} {doctor.data[0]['apellido']}"

    # Notificar al odontólogo
    notificar_odontologo(
        supabase,
        odontologo_id,
        (
            f"🔔 <b>Nueva Cita Asignada</b>\n\n"
            f"📅 Fecha: <b>{dt.strftime('%d/%m/%Y')}</b>\n"
            f"🕐 Hora: <b>{dt.strftime('%H:%M')}</b>\n"
            f"👤 Paciente: <b>{pac_nombre}</b>\n"
            f"📝 Motivo: {motivo_consulta.strip()}\n"
            f"🆔 Cita #{cita_id}\n\n"
            f"¡Revisa tu agenda actualizada!"
        ),
    )

    return (
        f"✅ ¡Cita agendada!\n"
        f"🆔 Cita #{cita_id}\n"
        f"👤 Paciente: {pac_nombre}\n"
        f"🦷 {doc_nombre}\n"
        f"📅 {dt.strftime('%d/%m/%Y')} a las {dt.strftime('%H:%M')}"
    )


def consultar_historial_paciente(
    telegram_chat_id: str,
    user_role: str,
    paciente_id: Optional[int] = None,
) -> str:
    """Consulta el historial clínico. Los pacientes solo ven el suyo propio.

    Args:
        telegram_chat_id: ID de Telegram.
        user_role: Rol del usuario.
        paciente_id: ID del paciente (solo para personal clínico).

    Returns:
        Historial clínico formateado.
    """
    if user_role == "paciente":
        pac = (
            supabase.table("pacientes")
            .select("id, nombre, apellido")
            .eq("telefono", telegram_chat_id)
            .limit(1)
            .execute()
        )
        if not pac.data:
            return "❌ No estás registrado en la clínica."
        target_id = pac.data[0]["id"]
    else:
        if not paciente_id:
            return "❌ Debes especificar un paciente_id."
        target_id = paciente_id

    historia = (
        supabase.table("historias_clinicas")
        .select("id, antecedentes_medicos, fecha_creacion")
        .eq("paciente_id", target_id)
        .limit(1)
        .execute()
    )
    if not historia.data:
        return "❌ No se encontró historia clínica."

    pac_info = (
        supabase.table("pacientes")
        .select("nombre, apellido")
        .eq("id", target_id)
        .limit(1)
        .execute()
    )
    nombre = (
        f"{pac_info.data[0]['nombre']} {pac_info.data[0]['apellido']}"
        if pac_info.data
        else "Desconocido"
    )

    evoluciones = (
        supabase.table("atenciones_medicas")
        .select("diagnostico, tratamiento_realizado, observaciones, fecha_atencion")
        .eq("historia_id", historia.data[0]["id"])
        .order("fecha_atencion", desc=True)
        .execute()
    )

    texto = (
        f"📂 Historia Clínica de {nombre}\n"
        f"📅 Creación: {historia.data[0]['fecha_creacion'][:10]}\n"
        f"🏥 Antecedentes: {historia.data[0].get('antecedentes_medicos') or 'Ninguno registrado.'}\n\n"
    )

    if not evoluciones.data:
        texto += "📝 Sin atenciones clínicas registradas."
    else:
        texto += f"📝 Evolución clínica ({len(evoluciones.data)} atenciones):\n"
        for i, evo in enumerate(evoluciones.data, 1):
            fecha = datetime.fromisoformat(str(evo["fecha_atencion"])).strftime("%d/%m/%Y")
            texto += (
                f"\nAtención #{i} ({fecha})\n"
                f"  🔍 Diagnóstico: {evo['diagnostico']}\n"
                f"  💊 Tratamiento: {evo['tratamiento_realizado']}\n"
                f"  📌 Observaciones: {evo.get('observaciones') or 'Ninguna'}\n"
            )
    return texto
