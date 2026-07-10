# src/tools/administrativas.py — Herramientas Administrativas y de Consulta
# ==============================================================================
# Migrado de bot/mcp_server.py (herramientas administrativas).
# Gestiona: listados de citas, pacientes y consulta de citas propias.
# ==============================================================================

from datetime import datetime
from typing import Optional

from src.utils.config import TIMEZONE
from src.utils.database import supabase
from src.utils.logger import get_logger

logger = get_logger(__name__)


def listar_pacientes(
    telegram_chat_id: str,
    user_role: str,
    limite: int = 50,
) -> str:
    """Lista los pacientes registrados. Solo para personal clínico.

    Args:
        telegram_chat_id: ID de Telegram del usuario que consulta.
        user_role: Rol del usuario.
        limite: Número máximo de registros a devolver.

    Returns:
        Listado de pacientes formateado.
    """
    if user_role not in ["odontologo", "recepcionista", "administrador"]:
        return "❌ Acceso denegado. Esta función es exclusiva para el personal de la clínica."

    pacientes = (
        supabase.table("pacientes")
        .select("id, nombre, apellido, telefono, email")
        .limit(limite)
        .order("id", desc=True)
        .execute()
    )
    if not pacientes.data:
        return "📭 No hay pacientes registrados."

    lineas = [f"👥 Pacientes registrados ({len(pacientes.data)}):"]
    for p in pacientes.data:
        lineas.append(
            f"  #{p['id']} — {p['nombre']} {p['apellido']} | "
            f"Tel/ChatID: {p['telefono']} | Email: {p.get('email') or '—'}"
        )
    return "\n".join(lineas)


def listar_citas(
    telegram_chat_id: str,
    user_role: str,
    fecha: str = "",
    estado: str = "",
    limite: int = 30,
) -> str:
    """Lista citas con filtros opcionales y control de acceso por rol.

    Los odontólogos solo ven sus propias citas.
    Recepcionistas y administradores ven todas.

    Args:
        telegram_chat_id: ID de Telegram del usuario que consulta.
        user_role: Rol del usuario.
        fecha: Filtrar por fecha YYYY-MM-DD (opcional).
        estado: Filtrar por estado (opcional).
        limite: Máximo de registros.

    Returns:
        Listado de citas formateado.
    """
    if user_role in ["paciente", "paciente_no_registrado"]:
        return "❌ Acceso denegado. Esta función es exclusiva para el personal de la clínica."

    query = supabase.table("citas").select(
        "id, fecha_hora, estado, motivo_consulta, paciente_id, odontologo_id"
    )

    # RBAC: los odontólogos solo ven sus propias citas
    if user_role == "odontologo":
        doc = (
            supabase.table("personal")
            .select("id")
            .eq("telefono", telegram_chat_id)
            .eq("rol", "odontologo")
            .limit(1)
            .execute()
        )
        if not doc.data:
            return (
                "❌ No se encontró tu perfil de odontólogo en la base de datos. "
                "Verifica que tu Telegram Chat ID esté registrado."
            )
        query = query.eq("odontologo_id", doc.data[0]["id"])

    if fecha:
        try:
            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
            inicio = datetime(
                fecha_obj.year, fecha_obj.month, fecha_obj.day, 0, 0, 0, tzinfo=TIMEZONE
            ).isoformat()
            fin = datetime(
                fecha_obj.year, fecha_obj.month, fecha_obj.day, 23, 59, 59, tzinfo=TIMEZONE
            ).isoformat()
            query = query.gte("fecha_hora", inicio).lte("fecha_hora", fin)
        except ValueError:
            return "❌ Formato de fecha inválido. Usa YYYY-MM-DD."

    if estado:
        if estado == "atendida":
            estado = "asistida"
        query = query.eq("estado", estado)

    citas = query.order("fecha_hora", desc=False).limit(limite).execute()

    if not citas.data:
        return "📭 No se encontraron citas con esos filtros."

    pac_map = {
        p["id"]: f"{p['nombre']} {p['apellido']}"
        for p in (supabase.table("pacientes").select("id, nombre, apellido").execute().data or [])
    }
    doc_map = {
        d["id"]: f"{d['nombre']} {d['apellido']}"
        for d in (supabase.table("personal").select("id, nombre, apellido").execute().data or [])
    }

    lineas = [f"📅 Citas encontradas ({len(citas.data)}) para {user_role}:"]
    for c in citas.data:
        dt = datetime.fromisoformat(c["fecha_hora"])
        lineas.append(
            f"  #{c['id']} | {dt.strftime('%d/%m/%Y %H:%M')} | {c['estado'].upper()}\n"
            f"        Paciente: {pac_map.get(c['paciente_id'], '—')} | "
            f"Dr: {doc_map.get(c['odontologo_id'], '—')}\n"
            f"        Motivo: {c.get('motivo_consulta') or '—'}"
        )
    return "\n".join(lineas)


def obtener_mis_citas(telegram_chat_id: str, user_role: str) -> str:
    """Muestra las citas próximas del paciente que hace la consulta.

    Args:
        telegram_chat_id: ID de Telegram del paciente.
        user_role: Rol del usuario.

    Returns:
        Listado de citas próximas del paciente.
    """
    pac = (
        supabase.table("pacientes")
        .select("id, nombre, apellido")
        .eq("telefono", telegram_chat_id)
        .limit(1)
        .execute()
    )
    if not pac.data:
        return "❌ No estás registrado en la clínica."

    ahora = datetime.now(TIMEZONE).isoformat()
    citas = (
        supabase.table("citas")
        .select("id, fecha_hora, estado, motivo_consulta, odontologo_id")
        .eq("paciente_id", pac.data[0]["id"])
        .gte("fecha_hora", ahora)
        .in_("estado", ["programada", "confirmada"])
        .order("fecha_hora")
        .execute()
    )

    if not citas.data:
        return "📭 No tienes citas próximas programadas."

    doc_map = {
        d["id"]: f"Dr(a). {d['nombre']} {d['apellido']}"
        for d in (supabase.table("personal").select("id, nombre, apellido").execute().data or [])
    }

    lineas = [f"📅 Tus próximas citas, {pac.data[0]['nombre']}:"]
    for c in citas.data:
        dt = datetime.fromisoformat(c["fecha_hora"])
        lineas.append(
            f"  🦷 Cita #{c['id']} — {dt.strftime('%d/%m/%Y a las %H:%M')}\n"
            f"     Estado: {c['estado']} | {doc_map.get(c['odontologo_id'], '—')}\n"
            f"     Motivo: {c.get('motivo_consulta') or '—'}"
        )
    return "\n".join(lineas)
