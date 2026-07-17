# src/telegram/rbac.py — Resolución de Roles de Usuario (RBAC)
# ==============================================================================
# Migrado de bot/main.py (líneas 103-131).
# Determina el rol de un usuario buscando su chat_id en Supabase.
# ==============================================================================

from src.utils.database import supabase
from src.utils.logger import get_logger

logger = get_logger(__name__)

_ROL_DEFAULT = "paciente_no_registrado"


async def obtener_rol_usuario(chat_id: str) -> str:
    """Determina el rol del usuario buscando su chat_id en personal y pacientes.

    Orden de búsqueda:
        1. Tabla `personal` (odontologo, recepcionista, administrador)
        2. Tabla `pacientes` → retorna 'paciente'
        3. Si no está en ninguna → 'paciente_no_registrado'

    Args:
        chat_id: ID del chat de Telegram del usuario.

    Returns:
        Rol del usuario como string.
    """
    try:
        personal_res = (
            supabase.table("personal")
            .select("rol")
            .eq("telefono", chat_id)
            .limit(1)
            .execute()
        )
        if hasattr(personal_res, 'data') and len(personal_res.data) > 0:
            return personal_res.data[0]["rol"]

        pacientes_res = (
            supabase.table("pacientes")
            .select("id")
            .eq("telefono", chat_id)
            .limit(1)
            .execute()
        )
        if hasattr(pacientes_res, 'data') and len(pacientes_res.data) > 0:
            return "paciente"

        return _ROL_DEFAULT

    except Exception as e:
        logger.error(f"Error obteniendo rol del usuario {chat_id}: {e}")
        return _ROL_DEFAULT
