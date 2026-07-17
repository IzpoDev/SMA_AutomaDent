# src/agent/ejecutor.py — Punto de Entrada al Sistema Multiagente
# ==============================================================================
# Migrado de bot/agents.py (líneas 508-572).
# Orquesta el ciclo completo: recuperar historial → inyectar RAG →
# invocar el grafo → guardar respuesta.
# ==============================================================================

import asyncio

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from src.agent.agente import app
from src.agent.memoria import intentar_resumir_si_es_necesario
from src.utils.database import (
    guardar_mensaje,
    obtener_historial_con_resumen,
    buscar_soporte_rag,
)
from src.utils.helpers import get_text_content
from src.utils.logger import get_logger
from langsmith import traceable

logger = get_logger(__name__)

_RESPUESTA_ERROR = (
    "🤖 Lo siento, ocurrió un inconveniente. ¿Podrías indicarme de nuevo tu consulta?"
)


@traceable(
    name="AutomaDent::procesar_mensaje",
    run_type="chain",
)
async def procesar_mensaje(
    telegram_chat_id: str,
    user_role: str,
    mensaje: str,
) -> str:
    """Punto de entrada público al SMA. Orquesta el ciclo completo de procesamiento.

    Flujo:
        1. Recupera historial con soporte de resúmenes compactos.
        2. Dispara resumen en background si se supera el umbral.
        3. Construye la lista de mensajes LangChain.
        4. Inyecta contexto RAG si hay coincidencias relevantes.
        5. Invoca el grafo multiagente.
        6. Extrae y persiste la respuesta del bot.

    Args:
        telegram_chat_id: ID del chat de Telegram del usuario.
        user_role: Rol resuelto del usuario en Supabase.
        mensaje: Texto del mensaje enviado por el usuario.

    Returns:
        Texto de la respuesta generada por el agente.
    """
    # 1. Recuperar historial con soporte de resúmenes compactos
    historial_data = obtener_historial_con_resumen(telegram_chat_id, limite_mensajes=8)
    resumen = historial_data["resumen"]
    mensajes_recientes = historial_data["mensajes"]

    # 2. Disparar resumen en background (sin bloquear)
    asyncio.create_task(
        intentar_resumir_si_es_necesario(telegram_chat_id, mensajes_recientes)
    )

    # 3. Reconstruir lista de mensajes para LangChain
    messages_list: list = []

    # Inyectar resumen como contexto inicial si existe
    if resumen:
        messages_list.append(
            SystemMessage(content=f"[RESUMEN DE CONVERSACIÓN PREVIA]\n{resumen}")
        )

    # Agregar mensajes recientes
    for msg in mensajes_recientes:
        if msg["sender"] == "user":
            messages_list.append(HumanMessage(content=msg["content"]))
        elif msg["sender"] == "bot":
            messages_list.append(AIMessage(content=msg["content"]))

    # 4. Búsqueda RAG vectorial — inyectar contexto si hay coincidencias
    contexto_rag = buscar_soporte_rag(mensaje)
    if contexto_rag:
        messages_list.append(
            SystemMessage(
                content=(
                    f"[INFORMACIÓN DE SOPORTE RAG DE LA CLÍNICA]\n{contexto_rag}\n\n"
                    "Usa esta información para responder con datos precisos sobre la clínica."
                )
            )
        )
        logger.debug(f"[RAG] ✅ Contexto inyectado para: '{mensaje[:60]}...'")

    # Agregar el mensaje actual del usuario
    messages_list.append(HumanMessage(content=mensaje))

    # 5. Invocar al grafo multiagente con todo el contexto
    try:
        result = await app.ainvoke(
            {
                "messages": messages_list,
                "next_agent": "supervisor",
                "telegram_chat_id": telegram_chat_id,
                "user_role": user_role,
            },
            config={
                "metadata": {
                    "telegram_chat_id": telegram_chat_id,
                    "user_role": user_role,
                },
                "tags": [f"role:{user_role}", "sma:automadent"],
            },
        )
    except Exception as e:
        logger.error(f"Error invocando el grafo SMA: {e}", exc_info=True)
        guardar_mensaje(telegram_chat_id, "user", mensaje)
        guardar_mensaje(telegram_chat_id, "bot", _RESPUESTA_ERROR)
        return _RESPUESTA_ERROR

    # 6. Extraer la respuesta del bot (último AIMessage con contenido)
    respuesta = _RESPUESTA_ERROR
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            texto = get_text_content(msg.content)
            if texto:
                respuesta = texto
                break

    # 7. Persistir el intercambio en Supabase
    guardar_mensaje(telegram_chat_id, "user", mensaje)
    guardar_mensaje(telegram_chat_id, "bot", respuesta)

    return respuesta
