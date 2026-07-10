# src/utils/logger.py — Configuración Centralizada de Logging
# ==============================================================================
# Reemplaza las llamadas dispersas a logging.basicConfig() en cada módulo.
# Usar: from src.utils.logger import get_logger
#       logger = get_logger(__name__)
# ==============================================================================

import logging
import logging.handlers
import os
from pathlib import Path

from src.utils.config import LOG_LEVEL, LOG_DIR


def setup_logging() -> None:
    """Configura el sistema de logging global de la aplicación.

    Crea el directorio de logs si no existe y configura handlers
    para consola y archivo rotativo.
    """
    log_dir = Path(LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Handler de consola
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    # Handler de archivo rotativo (10 MB, 5 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "automadent.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    # Configuración del logger raíz
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Silenciar loggers de terceros muy verbosos
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Retorna un logger nombrado para el módulo que lo solicite.

    Args:
        name: Nombre del logger (usar __name__ del módulo).

    Returns:
        Logger configurado.
    """
    return logging.getLogger(name)


# Configurar logging al importar el módulo
setup_logging()
