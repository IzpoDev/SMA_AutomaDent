# database.py — Cliente Supabase centralizado (Singleton)
# Incluye funciones de historial, memoria compacta (resúmenes) y búsqueda RAG vectorial.

import os
from google import genai
from google.genai import types as genai_types
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str = os.environ["SUPABASE_SERVICE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configurar cliente de Google GenAI para embeddings
_genai_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# ─── Constantes ───────────────────────────────────────────────────────────────
_EMBEDDING_MODEL = "gemini-embedding-001"
_RAG_THRESHOLD = 0.65
_RAG_TOP_K = 3


# ==============================================================================
#  HISTORIAL DE MENSAJES
# ==============================================================================

def guardar_mensaje(chat_id: str, sender: str, content: str) -> None:
    """Guarda un mensaje en la tabla mensajes_chat."""
    try:
        supabase.table("mensajes_chat").insert({
            "chat_id": str(chat_id),
            "sender": sender,
            "content": content
        }).execute()
    except Exception as e:
        print(f"Error guardando mensaje en la base de datos: {e}")

def obtener_historial_mensajes(chat_id: str, limite: int = 20) -> list:
    """Obtiene los últimos N mensajes del historial del chat en orden cronológico."""
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
        print(f"Error obteniendo historial de mensajes: {e}")
        return []


# ==============================================================================
#  MEMORIA COMPACTA — RESÚMENES
# ==============================================================================

def guardar_resumen(chat_id: str, summary_content: str) -> None:
    """Guarda un resumen comprimido del historial con sender='summary'."""
    try:
        supabase.table("mensajes_chat").insert({
            "chat_id": str(chat_id),
            "sender": "summary",
            "content": summary_content
        }).execute()
    except Exception as e:
        print(f"Error guardando resumen: {e}")


def obtener_historial_con_resumen(chat_id: str, limite_mensajes: int = 8) -> dict:
    """
    Recupera el último resumen disponible y los mensajes más recientes posteriores a él.

    Returns:
        dict con claves:
            - 'resumen': str | None  → texto del resumen (si existe)
            - 'mensajes': list       → mensajes recientes (user/bot)
    """
    try:
        # 1. Buscar el resumen más reciente
        res_summary = (
            supabase.table("mensajes_chat")
            .select("id, content, created_at")
            .eq("chat_id", str(chat_id))
            .eq("sender", "summary")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        resumen = None
        resumen_id = None
        resumen_ts = None
        if res_summary.data:
            resumen = res_summary.data[0]["content"]
            resumen_id = res_summary.data[0]["id"]
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
        print(f"Error obteniendo historial con resumen: {e}")
        return {"resumen": None, "mensajes": []}


def contar_turnos_desde_ultimo_resumen(chat_id: str) -> int:
    """Cuenta cuántos pares user/bot hay desde el último resumen guardado."""
    try:
        res_summary = (
            supabase.table("mensajes_chat")
            .select("created_at")
            .eq("chat_id", str(chat_id))
            .eq("sender", "summary")
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
        print(f"Error contando turnos: {e}")
        return 0


# ==============================================================================
#  RAG — BÚSQUEDA VECTORIAL EN SUPABASE (pgvector)
# ==============================================================================

def buscar_soporte_rag(query_text: str) -> str | None:
    """
    Genera el embedding del texto, busca documentos similares en Supabase
    usando la función RPC `buscar_documentos` (pgvector cosine similarity)
    y retorna un bloque de contexto listo para inyectar en el prompt del agente.

    Returns:
        str con el bloque de contexto RAG, o None si no hay resultados relevantes.
    """
    try:
        # 1. Generar embedding con gemini-embedding-001 (truncado a 768 dims para el schema SQL)
        result = _genai_client.models.embed_content(
            model=_EMBEDDING_MODEL,
            contents=query_text,
            config=genai_types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=768,
            ),
        )
        embedding = list(result.embeddings[0].values)

        # 2. Llamar a la función RPC de Supabase (pgvector)
        rpc_result = supabase.rpc(
            "buscar_documentos",
            {
                "query_embedding": embedding,
                "match_threshold": _RAG_THRESHOLD,
                "match_count": _RAG_TOP_K,
            },
        ).execute()

        if not rpc_result.data:
            return None

        # 3. Construir bloque de contexto
        bloques = []
        for doc in rpc_result.data:
            bloques.append(
                f"[{doc['titulo'].upper()}]\n{doc['contenido']}"
            )
        return "\n\n".join(bloques)

    except Exception as e:
        print(f"[RAG] Error en búsqueda vectorial: {e}")
        return None
