# src/utils/database.py — Cliente Supabase Centralizado (Singleton)
# ==============================================================================
# Migrado de shared/database.py.
# Incluye:
#   - Cliente Supabase singleton
#   - Funciones de historial de mensajes
#   - Memoria compacta (resúmenes automáticos)
#   - Búsqueda RAG vectorial (pgvector)
# ==============================================================================

import os
from google import genai
from google.genai import types as genai_types
from supabase import create_client, Client

from src.utils.config import (
    SUPABASE_URL,
    SUPABASE_KEY,
    GEMINI_API_KEY,
    EMBEDDING_MODEL,
    EMBEDDING_DIMS,
    RAG_THRESHOLD,
    RAG_TOP_K,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ─── Singleton Supabase ───────────────────────────────────────────────────────
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─── Cliente Google GenAI para embeddings ────────────────────────────────────
_genai_client = genai.Client(api_key=GEMINI_API_KEY)


# ==============================================================================
#  HISTORIAL DE MENSAJES
# ==============================================================================

def guardar_mensaje(chat_id: str, sender: str, content: str) -> None:
    """Guarda un mensaje en la tabla mensajes_chat.

    Args:
        chat_id: ID del chat de Telegram.
        sender: Emisor del mensaje ('user', 'bot').
        content: Contenido del mensaje.
    """
    try:
        supabase.table("mensajes_chat").insert({
            "chat_id": str(chat_id),
            "sender": sender,
            "content": content,
        }).execute()
    except Exception as e:
        logger.error(f"Error guardando mensaje en la base de datos: {e}")


def obtener_historial_mensajes(chat_id: str, limite: int = 20) -> list:
    """Obtiene los últimos N mensajes del historial del chat en orden cronológico.

    Args:
        chat_id: ID del chat de Telegram.
        limite: Máximo de mensajes a recuperar.

    Returns:
        Lista de mensajes ordenados del más antiguo al más reciente.
    """
    try:
        res = (
            supabase.table("mensajes_chat")
            .select("sender, content")
            .eq("chat_id", str(chat_id))
            .order("created_at", desc=True)
            .limit(limite)
            .execute()
        )
        return list(reversed(res.data)) if res.data else []
    except Exception as e:
        logger.error(f"Error obteniendo historial de mensajes: {e}")
        return []


# ==============================================================================
#  MEMORIA COMPACTA — RESÚMENES
# ==============================================================================

def guardar_resumen(chat_id: str, summary_content: str) -> None:
    """Guarda un resumen comprimido del historial en la tabla resumenes_chat.

    Args:
        chat_id: ID del chat de Telegram.
        summary_content: Texto del resumen generado por el LLM.
    """
    try:
        supabase.table("resumenes_chat").insert({
            "chat_id": str(chat_id),
            "content": summary_content,
        }).execute()
    except Exception as e:
        logger.error(f"Error guardando resumen: {e}")


def obtener_historial_con_resumen(chat_id: str, limite_mensajes: int = 8) -> dict:
    """Recupera el último resumen disponible (de resumenes_chat) y los mensajes
    más recientes de mensajes_chat posteriores a ese resumen.

    Returns:
        dict con claves:
            - 'resumen': str | None  → texto del resumen (si existe)
            - 'mensajes': list       → mensajes recientes (user/bot)
    """
    try:
        # 1. Buscar el resumen más reciente en la tabla dedicada
        res_summary = (
            supabase.table("resumenes_chat")
            .select("content, created_at")
            .eq("chat_id", str(chat_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        resumen = None
        resumen_ts = None
        if res_summary.data:
            resumen = res_summary.data[0]["content"]
            resumen_ts = res_summary.data[0]["created_at"]

        # 2. Obtener mensajes posteriores al resumen (solo user/bot)
        query = (
            supabase.table("mensajes_chat")
            .select("sender, content")
            .eq("chat_id", str(chat_id))
            .in_("sender", ["user", "bot"])
            .order("created_at", desc=True)
            .limit(limite_mensajes)
        )
        if resumen_ts:
            query = query.gt("created_at", resumen_ts)

        res_msgs = query.execute()
        mensajes = list(reversed(res_msgs.data)) if res_msgs.data else []

        return {"resumen": resumen, "mensajes": mensajes}

    except Exception as e:
        logger.error(f"Error obteniendo historial con resumen: {e}")
        return {"resumen": None, "mensajes": []}


def contar_turnos_desde_ultimo_resumen(chat_id: str) -> int:
    """Cuenta cuántos mensajes user/bot hay desde el último resumen guardado.

    Consulta la tabla dedicada resumenes_chat para obtener el timestamp
    del último resumen.

    Args:
        chat_id: ID del chat de Telegram.

    Returns:
        Número de mensajes desde el último resumen (0 si no hay resumen).
    """
    try:
        res_summary = (
            supabase.table("resumenes_chat")
            .select("created_at")
            .eq("chat_id", str(chat_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        query = (
            supabase.table("mensajes_chat")
            .select("id", count="exact")
            .eq("chat_id", str(chat_id))
            .in_("sender", ["user", "bot"])
        )
        if res_summary.data:
            query = query.gt("created_at", res_summary.data[0]["created_at"])
        res = query.execute()
        return res.count or 0
    except Exception as e:
        logger.error(f"Error contando turnos: {e}")
        return 0


# ==============================================================================
#  RAG — BÚSQUEDA VECTORIAL EN SUPABASE (pgvector)
# ==============================================================================

def buscar_soporte_rag(query_text: str) -> str | None:
    """Genera el embedding del texto y busca documentos similares en Supabase.

    Usa la función RPC `buscar_documentos` (pgvector cosine similarity) y
    retorna un bloque de contexto listo para inyectar en el prompt del agente.

    Args:
        query_text: Texto de consulta del usuario.

    Returns:
        Bloque de contexto RAG formateado, o None si no hay resultados relevantes.
    """
    try:
        # 1. Generar embedding (truncado a 768 dims para el schema SQL)
        result = _genai_client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=query_text,
            config=genai_types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=EMBEDDING_DIMS,
            ),
        )
        embedding = list(result.embeddings[0].values)

        # 2. Llamar a la función RPC de Supabase (pgvector)
        rpc_result = supabase.rpc(
            "buscar_documentos",
            {
                "query_embedding": embedding,
                "match_threshold": RAG_THRESHOLD,
                "match_count": RAG_TOP_K,
            },
        ).execute()

        if not rpc_result.data:
            return None

        # 3. Construir bloque de contexto
        bloques = [
            f"[{doc['titulo'].upper()}]\n{doc['contenido']}"
            for doc in rpc_result.data
        ]
        return "\n\n".join(bloques)

    except Exception as e:
        logger.error(f"[RAG] Error en búsqueda vectorial: {e}")
        return None
