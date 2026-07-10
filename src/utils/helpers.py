# src/utils/helpers.py — Funciones Auxiliares Compartidas
# ==============================================================================
# Utilidades de propósito general reutilizables en toda la aplicación.
# ==============================================================================

import re
from typing import Any


# ==============================================================================
#  PROCESAMIENTO DE TEXTO
# ==============================================================================

def sanitize_html(text: str) -> str:
    """Convierte HTML al subconjunto que acepta Telegram.

    Elimina etiquetas no soportadas (ul, ol, li, h1-h6, p, br) y las convierte
    a equivalentes de texto plano o etiquetas HTML válidas en Telegram.

    Args:
        text: Texto con posibles etiquetas HTML.

    Returns:
        Texto con HTML sanitizado para Telegram.
    """
    text = re.sub(r"<li>", "• ", text)
    text = re.sub(r"</li>", "\n", text)
    text = re.sub(r"</?ul>|</?ol>", "", text)
    text = re.sub(
        r"<h[1-6][^>]*>(.*?)</h[1-6]>",
        r"<b>\1</b>\n",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_text_content(content: Any) -> str:
    """Extrae el texto de un objeto de contenido de LangChain.

    Maneja los diferentes formatos que puede devolver el LLM:
    str, list de str, o list de dicts con clave 'text'.

    Args:
        content: Contenido de un mensaje de LangChain.

    Returns:
        Texto plano extraído.
    """
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and "text" in part:
                text_parts.append(part["text"])
        return " ".join(text_parts)
    return str(content)


# ==============================================================================
#  UTILIDADES DE HERRAMIENTAS MCP
# ==============================================================================

def get_tool_by_name(name: str, tool_list: list) -> Any | None:
    """Busca una herramienta por nombre dentro de una lista de herramientas MCP.

    Args:
        name: Nombre de la herramienta a buscar.
        tool_list: Lista de objetos herramienta.

    Returns:
        La herramienta encontrada o None si no existe.
    """
    for tool in tool_list:
        if tool.name == name:
            return tool
    return None
