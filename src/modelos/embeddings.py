# src/modelos/embeddings.py — Cliente de Embeddings con Google GenAI
# ==============================================================================
# Migrado de shared/database.py (cliente GenAI) y shared/sembrar_rag.py.
# Encapsula la generación de embeddings para búsqueda RAG y sembrado de datos.
# ==============================================================================

from google import genai
from google.genai import types as genai_types

from src.utils.config import GEMINI_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIMS
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ─── Singleton del cliente GenAI ──────────────────────────────────────────────
_genai_client = genai.Client(api_key=GEMINI_API_KEY)


def generar_embedding_query(texto: str) -> list[float]:
    """Genera un embedding optimizado para consultas de recuperación (RETRIEVAL_QUERY).

    Usar al buscar documentos similares en la base de conocimiento RAG.

    Args:
        texto: Texto de la consulta del usuario.

    Returns:
        Lista de flotantes representando el embedding ({EMBEDDING_DIMS} dimensiones).

    Raises:
        Exception: Si la API de Google GenAI falla.
    """
    result = _genai_client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texto,
        config=genai_types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=EMBEDDING_DIMS,
        ),
    )
    return list(result.embeddings[0].values)


def generar_embedding_documento(texto: str) -> list[float]:
    """Genera un embedding optimizado para documentos a indexar (RETRIEVAL_DOCUMENT).

    Usar al sembrar/indexar documentos en la base de conocimiento RAG.

    Args:
        texto: Texto del documento a indexar.

    Returns:
        Lista de flotantes representando el embedding ({EMBEDDING_DIMS} dimensiones).

    Raises:
        Exception: Si la API de Google GenAI falla.
    """
    result = _genai_client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texto,
        config=genai_types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=EMBEDDING_DIMS,
        ),
    )
    return list(result.embeddings[0].values)
