# src/tools/medico.py — Herramientas del Agente Asistente Médico
# ==============================================================================
# Migrado de bot/mcp_server.py (herramientas médicas).
# Gestiona: actualización de estados de citas y evoluciones médicas.
# ==============================================================================

from src.utils.database import supabase
from src.utils.notificaciones import notificar_cambio_estado_cita
from src.utils.logger import get_logger

logger = get_logger(__name__)

_ESTADOS_VALIDOS = {"programada", "confirmada", "asistida", "cancelada", "no_show"}


def actualizar_estado_cita(
    telegram_chat_id: str,
    user_role: str,
    cita_id: int,
    nuevo_estado: str,
) -> str:
    """Actualiza el estado de una cita. Solo para odontólogos, recepcionistas y administradores.

    Args:
        telegram_chat_id: ID de Telegram del usuario.
        user_role: Rol del usuario.
        cita_id: ID de la cita.
        nuevo_estado: Estado destino. Válidos: 'confirmada', 'asistida' (o 'atendida'), 'cancelada', 'no_show'.

    Returns:
        Mensaje de confirmación del cambio de estado.
    """
    if user_role not in ["odontologo", "recepcionista", "administrador"]:
        return "❌ Acceso denegado. Solo el personal de la clínica puede cambiar el estado de las citas."

    # Alias: 'atendida' → 'asistida' (valor correcto en el ENUM de Supabase)
    if nuevo_estado == "atendida":
        nuevo_estado = "asistida"

    if nuevo_estado not in _ESTADOS_VALIDOS:
        return f"❌ Estado inválido '{nuevo_estado}'. Usa: {', '.join(_ESTADOS_VALIDOS)}."

    cita = (
        supabase.table("citas")
        .select("id, estado, paciente_id")
        .eq("id", cita_id)
        .limit(1)
        .execute()
    )
    if not cita.data:
        return f"❌ No se encontró la cita #{cita_id}."

    estado_anterior = cita.data[0]["estado"]
    supabase.table("citas").update({"estado": nuevo_estado}).eq("id", cita_id).execute()

    # Notificar al paciente sobre el cambio de estado
    paciente_id = cita.data[0].get("paciente_id")
    if paciente_id:
        notificar_cambio_estado_cita(supabase, cita_id, paciente_id, nuevo_estado)

    return f"✅ Cita #{cita_id}: '{estado_anterior}' → '{nuevo_estado}'."


def registrar_evolucion_medica(
    telegram_chat_id: str,
    user_role: str,
    cita_id: int,
    diagnostico: str,
    tratamiento_realizado: str,
    observaciones: str = "",
) -> str:
    """Registra la evolución médica de una cita. Solo para odontólogos.

    Args:
        telegram_chat_id: ID de Telegram.
        user_role: Rol del usuario.
        cita_id: ID de la cita (debe estar en estado 'asistida').
        diagnostico: Diagnóstico clínico.
        tratamiento_realizado: Tratamiento realizado.
        observaciones: Notas adicionales.

    Returns:
        Confirmación del registro de la evolución.
    """
    if user_role not in ["odontologo", "administrador"]:
        return "❌ Solo los odontólogos y administradores autorizados pueden registrar evoluciones médicas."

    cita = (
        supabase.table("citas")
        .select("id, estado, paciente_id")
        .eq("id", cita_id)
        .limit(1)
        .execute()
    )
    if not cita.data:
        return f"❌ No se encontró la cita #{cita_id}."
    if cita.data[0]["estado"] != "asistida":
        return f"❌ La cita #{cita_id} debe marcarse primero como 'asistida'."

    historia = (
        supabase.table("historias_clinicas")
        .select("id")
        .eq("paciente_id", cita.data[0]["paciente_id"])
        .limit(1)
        .execute()
    )
    if not historia.data:
        return "❌ El paciente no tiene historia clínica."

    supabase.table("atenciones_medicas").insert({
        "historia_id": historia.data[0]["id"],
        "cita_id": cita_id,
        "diagnostico": diagnostico.strip(),
        "tratamiento_realizado": tratamiento_realizado.strip(),
        "observaciones": observaciones.strip() if observaciones else None,
    }).execute()

    return f"✅ Evolución médica registrada para la cita #{cita_id}."
