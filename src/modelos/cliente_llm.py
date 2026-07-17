# src/modelos/cliente_llm.py — Cliente LLM con Cascada de Fallback
# ==============================================================================
# Migrado y refactorizado desde bot/agents.py (líneas 71-148).
# Encapsula la lógica de construcción del LLM y el manejo de cuotas (429).
# ==============================================================================

import asyncio
import time

from langchain_google_genai import ChatGoogleGenerativeAI

from src.utils.config import GEMINI_API_KEY, MODEL_CASCADE, MODEL_TEMPERATURE
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _build_llm(model_name: str, temperature: float = MODEL_TEMPERATURE) -> ChatGoogleGenerativeAI:
    """Construye una instancia del LLM de Google Generative AI.

    Args:
        model_name: Nombre del modelo Gemini a usar.
        temperature: Temperatura de generación (0.0 a 1.0).

    Returns:
        Instancia configurada de ChatGoogleGenerativeAI.
    """
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=GEMINI_API_KEY,
        temperature=temperature,
        convert_system_message_to_human=False,
        max_retries=0,
    )


def invocar_llm_con_fallback(
    messages: list,
    tools: list = None,
    temperature: float = MODEL_TEMPERATURE,
):
    """Invoca el LLM con cascada de modelos.

    Intenta cada modelo de MODEL_CASCADE en orden. Si recibe cualquier excepción
    (cuota 429, no disponible 503, error de red, etc.), registra el aviso y
    pasa al siguiente modelo de forma inmediata.
    """
    last_exc = None
    for model_name in MODEL_CASCADE:
        try:
            candidate = _build_llm(model_name, temperature)
            if tools:
                candidate = candidate.bind_tools(tools)
            response = candidate.invoke(messages)
            if model_name != MODEL_CASCADE[0]:
                logger.info(f"[FALLBACK] Respondió exitosamente con modelo: {model_name}")
            return response
        except Exception as e:
            logger.warning(
                f"[FALLBACK] Falló modelo '{model_name}': {e}. Probando el siguiente..."
            )
            last_exc = e
            time.sleep(0.5)  # Breve pausa antes de reintentar con el siguiente
    raise last_exc or Exception("Todos los modelos del cascade fallaron.")


async def invocar_llm_con_fallback_async(
    messages: list,
    tools: list = None,
    temperature: float = MODEL_TEMPERATURE,
):
    """Versión asíncrona de invocar_llm_con_fallback."""
    last_exc = None
    for model_name in MODEL_CASCADE:
        try:
            candidate = _build_llm(model_name, temperature)
            if tools:
                candidate = candidate.bind_tools(tools)
            response = await candidate.ainvoke(messages)
            if model_name != MODEL_CASCADE[0]:
                logger.info(f"[FALLBACK] Respondió exitosamente con modelo: {model_name}")
            return response
        except Exception as e:
            logger.warning(
                f"[FALLBACK] Falló modelo '{model_name}': {e}. Probando el siguiente..."
            )
            last_exc = e
            await asyncio.sleep(0.5)
    raise last_exc or Exception("Todos los modelos del cascade fallaron.")
