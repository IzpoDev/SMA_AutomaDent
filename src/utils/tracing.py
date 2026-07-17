# src/utils/tracing.py — Configuración de LangSmith Tracing
# ==============================================================================
# Inicializa LangSmith como plataforma de observabilidad para el SMA.
# Se activa automáticamente si LANGSMITH_TRACING=true en el .env.
# ==============================================================================

import os
from src.utils.config import (
    LANGSMITH_API_KEY,
    LANGSMITH_PROJECT,
    LANGSMITH_ENDPOINT,
    LANGSMITH_TRACING,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


def init_tracing() -> None:
    """Inicializa LangSmith tracing si está habilitado en la configuración.

    Configura las variables de entorno requeridas por LangChain/LangGraph
    para enviar trazas automáticamente al servidor de LangSmith.

    Debe llamarse UNA VEZ al inicio de la aplicación (antes de cualquier
    invocación del grafo o del LLM).
    """
    if not LANGSMITH_TRACING:
        logger.info("[TRACING] ⏭️  LangSmith deshabilitado (LANGSMITH_TRACING=false)")
        return

    if not LANGSMITH_API_KEY:
        logger.warning(
            "[TRACING] ⚠️  LANGSMITH_TRACING=true pero LANGSMITH_API_KEY está vacía. "
            "Tracing no se activará."
        )
        return

    # Configurar variables de entorno que LangChain/LangGraph detectan
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = LANGSMITH_PROJECT
    os.environ["LANGCHAIN_ENDPOINT"] = LANGSMITH_ENDPOINT

    logger.info(
        f"[TRACING] ✅ LangSmith habilitado — Proyecto: '{LANGSMITH_PROJECT}' "
        f"| Endpoint: {LANGSMITH_ENDPOINT}"
    )
