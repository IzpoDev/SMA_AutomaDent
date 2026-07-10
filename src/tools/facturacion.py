# src/tools/facturacion.py — Herramientas del Agente de Facturación
# ==============================================================================
# Migrado de bot/mcp_server.py (herramientas de facturación).
# Gestiona: registro de pagos de citas atendidas.
# ==============================================================================

from datetime import datetime

from src.utils.config import TIMEZONE
from src.utils.database import supabase
from src.utils.logger import get_logger

logger = get_logger(__name__)

_METODOS_PAGO_VALIDOS = {"efectivo", "tarjeta", "yape", "plin"}


def registrar_pago(
    telegram_chat_id: str,
    user_role: str,
    cita_id: int,
    monto: float,
    metodo_pago: str,
) -> str:
    """Registra el pago de una cita. Solo para administradores y recepcionistas.

    Args:
        telegram_chat_id: ID de Telegram.
        user_role: Rol del usuario.
        cita_id: ID de la cita.
        monto: Monto en Soles (S/).
        metodo_pago: 'efectivo', 'tarjeta', 'yape' o 'plin'.

    Returns:
        Confirmación del registro de pago.
    """
    if user_role not in ["administrador", "recepcionista", "odontologo"]:
        return "❌ Solo el personal administrativo puede registrar pagos."

    if metodo_pago not in _METODOS_PAGO_VALIDOS:
        return f"❌ Método de pago inválido. Usa: {', '.join(_METODOS_PAGO_VALIDOS)}."

    cita = (
        supabase.table("citas")
        .select("id, estado")
        .eq("id", cita_id)
        .limit(1)
        .execute()
    )
    if not cita.data:
        return f"❌ Cita #{cita_id} no encontrada."
    if cita.data[0]["estado"] != "asistida":
        return "❌ Solo se pueden cobrar citas en estado 'asistida'."

    supabase.table("pagos").insert({
        "cita_id": cita_id,
        "monto": monto,
        "metodo_pago": metodo_pago,
        "estado_pago": "pagado",
        "fecha_pago": datetime.now(TIMEZONE).isoformat(),
    }).execute()

    return f"✅ Pago de S/ {monto:.2f} con '{metodo_pago}' registrado para la cita #{cita_id}."
