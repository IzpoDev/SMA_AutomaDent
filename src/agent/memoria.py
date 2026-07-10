# src/agent/memoria.py — Gestión de Memoria Compacta (Resúmenes Automáticos)
# ==============================================================================
# Migrado de bot/agents.py (líneas 478-501).
# Gestiona la compresión automática del historial cuando supera el umbral.
# ==============================================================================

import asyncio

from langchain_core.messages import SystemMessage, HumanMessage

from src.utils.config import TURNOS_PARA_RESUMIR
from src.utils.database import contar_turnos_desde_ultimo_resumen, guardar_resumen
from src.utils.helpers import get_text_content
from src.utils.logger import get_logger
from src.modelos.cliente_llm import invocar_llm_con_fallback
from src.prompts.sistema_prompts import PROMPT_RESUMEN

logger = get_logger(__name__)


async def intentar_resumir_si_es_necesario(
    chat_id: str, messages_list: list
) -> None:
    """Genera y guarda un resumen comprimido si el historial supera el umbral.

    Esta función corre en background (asyncio.create_task) sin bloquear
    el flujo principal de respuesta al usuario.

    Args:
        chat_id: ID del chat de Telegram.
        messages_list: Lista de mensajes recientes del historial.
    """
    try:
        turnos = contar_turnos_desde_ultimo_resumen(chat_id)
        if turnos < TURNOS_PARA_RESUMIR:
            return

        # Construir bloque de texto para resumir
        bloque = "\n".join(
            f"{'Usuario' if m['sender'] == 'user' else 'Bot'}: {m['content']}"
            for m in messages_list
        )

        resumen_response = invocar_llm_con_fallback(
            [
                SystemMessage(content=PROMPT_RESUMEN),
                HumanMessage(content=bloque),
            ],
            temperature=0.1,
        )
        resumen_texto = get_text_content(resumen_response.content).strip()

        if resumen_texto:
            guardar_resumen(chat_id, resumen_texto)
            logger.info(
                f"[RESUMEN] ✅ Resumen generado para chat {chat_id} ({turnos} turnos)."
            )

    except Exception as e:
        logger.error(f"[RESUMEN] ❌ Error generando resumen: {e}")
