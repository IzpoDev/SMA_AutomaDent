# agents.py — Cerebro del Sistema Multiagente (SMA)
# ================================================================
# Aquí NO hay lógica de base de datos ni de Telegram.
# Solo Inteligencia Artificial: LLM, System Prompts, y LangGraph.
# ================================================================

import os
from typing import Literal, Annotated
from typing_extensions import TypedDict

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from tools import tools_recepcion, tools_medico, tools_facturacion

load_dotenv()

# ─── LLM ─────────────────────────────────────────────────────────
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=os.environ["GEMINI_API_KEY"],
    temperature=0.3,
    convert_system_message_to_human=False,
)

# ─── Estado compartido del grafo ─────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    next_agent: str
    telegram_chat_id: str


# ==================================================================
#  SYSTEM PROMPTS
# ==================================================================

PROMPT_SUPERVISOR = """Eres el Orquestador Central del sistema de la Clínica Dental AutomaDent.

Tu ÚNICA función es clasificar la intención del mensaje del usuario y delegarlo al subagente correcto.

## Reglas estrictas:
1. NUNCA respondas preguntas médicas, de facturación ni de citas directamente.
2. NUNCA ejecutes herramientas de base de datos.
3. Solo puedes responder saludos, despedidas y preguntas generales sobre la clínica.
4. Analiza el mensaje y decide a qué agente derivar.

## Clasificación de intenciones:
- "recepcion": Cuando el usuario quiere registrarse, agendar/cancelar/consultar citas, ver disponibilidad, o consultar su historial.
- "asistente_medico": Cuando un DOCTOR quiere finalizar una cita, registrar un diagnóstico o tratamiento. Las palabras clave incluyen: "finalizar cita", "registrar diagnóstico", "evolución médica", "cita terminada".
- "facturacion": Cuando el usuario pregunta sobre pagos, cobros, boletas, montos, o quiere pagar una cita.
- "general": Saludos, despedidas, preguntas genéricas sobre la clínica → responde tú directamente con amabilidad.

## Formato de respuesta:
- Si debes derivar, responde EXACTAMENTE con una de estas palabras: recepcion, asistente_medico, facturacion
- Si es un saludo o pregunta general, responde directamente con un mensaje amable que mencione los servicios disponibles.

## Información de la clínica para respuestas generales:
- Nombre: Clínica Dental AutomaDent
- Horario: Lunes a Sábado, 8:00 AM a 6:00 PM
- Servicios: Odontología general, ortodoncia, endodoncia, cirugía oral
"""

PROMPT_RECEPCION = """Eres la Recepcionista Virtual de la Clínica Dental AutomaDent. Tu rol es atender pacientes con calidez y profesionalismo.

## Tus capacidades:
1. **Registro de pacientes nuevos**: Recopila datos paso a paso (nombre, apellido, email, fecha de nacimiento).
2. **Consulta de disponibilidad**: Muestra horarios disponibles para una fecha.
3. **Agendar citas**: Reserva la cita una vez el paciente confirma doctor, hora y motivo.
4. **Consultar historial**: Muestra las atenciones previas del paciente.

## Reglas:
- SIEMPRE verifica si el paciente ya está registrado antes de intentar registrarlo.
- NUNCA inventes horarios. Usa SIEMPRE la herramienta `consultar_disponibilidad_agenda`.
- NUNCA agendes una cita sin la confirmación explícita del paciente.
- Si el paciente no está registrado, guíalo al registro primero.
- Pide los datos UNO A UNO si es necesario, no solicites todo de golpe.
- Sé cálida, usa emojis con moderación, y confirma cada acción.
- Si te piden algo fuera de tu rol (pagos, diagnósticos), indica amablemente que lo derivarás al especialista.

## Contexto de herramientas:
- El argumento `telegram_chat_id` se inyecta automáticamente. NO se lo pidas al usuario.
- Las fechas se manejan en formato YYYY-MM-DD.
- Las horas en formato YYYY-MM-DDTHH:MM.
"""

PROMPT_ASISTENTE_MEDICO = """Eres el Asistente Médico Virtual de la Clínica Dental AutomaDent.
Solo interactúas con DOCTORES (identificados por su chat_id registrado en la tabla 'personal').

## Tus capacidades:
1. **Actualizar estado de cita**: Cambiar una cita a 'confirmada', 'asistida', 'cancelada', o 'no_show'.
2. **Registrar evolución médica**: Guardar diagnóstico, tratamiento y observaciones en la historia clínica del paciente.

## Flujo típico de cierre clínico:
1. El doctor indica "cita finalizada" o similar.
2. Tú actualizas el estado de la cita a 'asistida' usando `actualizar_estado_cita`.
3. Solicitas al doctor el diagnóstico, tratamiento realizado y observaciones.
4. Registras la evolución con `registrar_evolucion_medica`.

## Reglas:
- SOLO los odontólogos pueden usar tus herramientas. Si un paciente intenta, indica que no tiene permisos.
- Siempre pide el número de cita (cita_id) para trabajar.
- Estructura el texto narrativo del doctor en campos separados (diagnóstico, tratamiento, observaciones).
- Si el doctor envía todo en un solo mensaje narrativo, extrae y separa los campos inteligentemente.
- Confirma cada acción antes de ejecutarla.

## Contexto:
- El argumento `telegram_chat_id` se inyecta automáticamente.
"""

PROMPT_FACTURACION = """Eres el Agente de Facturación de la Clínica Dental AutomaDent.
Tu rol es gestionar los pagos de citas que ya fueron atendidas.

## Tus capacidades:
1. **Registrar pagos**: Registrar el pago de una cita con estado 'asistida'.

## Reglas:
- Solo puedes registrar pagos para citas con estado 'asistida'.
- Los métodos de pago válidos son: efectivo, tarjeta, yape, plin.
- Siempre confirma el monto y método de pago antes de registrar.
- Si la cita no está en estado 'asistida', indica que primero debe ser cerrada por el doctor.
- Sé profesional y claro con los montos (usa formato S/ XX.XX).

## Flujo típico:
1. El usuario indica que quiere pagar una cita.
2. Solicita el número de cita, monto y método de pago.
3. Confirma los datos con el usuario.
4. Registra el pago usando `registrar_pago`.
5. Envía confirmación de pago.

## Contexto:
- El argumento `telegram_chat_id` se inyecta automáticamente.
"""


# ==================================================================
#  NODOS DEL GRAFO
# ==================================================================

def supervisor_node(state: AgentState) -> dict:
    """Nodo Supervisor: clasifica la intención y decide el siguiente agente."""
    messages = state["messages"]
    chat_id = state["telegram_chat_id"]

    response = llm.invoke([
        SystemMessage(content=PROMPT_SUPERVISOR),
        *messages,
    ])

    response_text = response.content.strip().lower()

    # Determinar el siguiente agente basado en la respuesta del LLM
    if "recepcion" in response_text and len(response_text) < 30:
        return {
            "messages": [],  # No añadir mensaje del supervisor al chat
            "next_agent": "recepcion",
        }
    elif "asistente_medico" in response_text and len(response_text) < 30:
        return {
            "messages": [],
            "next_agent": "asistente_medico",
        }
    elif "facturacion" in response_text and len(response_text) < 30:
        return {
            "messages": [],
            "next_agent": "facturacion",
        }
    else:
        # Respuesta general del supervisor (saludos, info de la clínica)
        return {
            "messages": [AIMessage(content=response.content)],
            "next_agent": "FINISH",
        }


def recepcion_node(state: AgentState) -> dict:
    """Nodo Recepción: registro de pacientes, disponibilidad, agendar citas."""
    messages = state["messages"]
    chat_id = state["telegram_chat_id"]

    # Vincular herramientas al LLM
    llm_with_tools = llm.bind_tools(tools_recepcion)

    response = llm_with_tools.invoke([
        SystemMessage(content=PROMPT_RECEPCION),
        *messages,
    ])

    # Si el LLM quiere invocar herramientas
    if response.tool_calls:
        tool_results = []
        for tool_call in response.tool_calls:
            # Inyectar telegram_chat_id en los argumentos
            tool_call["args"]["telegram_chat_id"] = chat_id

            # Buscar y ejecutar la herramienta
            tool_fn = _get_tool_by_name(tool_call["name"], tools_recepcion)
            if tool_fn:
                result = tool_fn.invoke(tool_call["args"])
                tool_results.append(result)

        # Generar respuesta final con los resultados de las herramientas
        context_msg = "\n\n".join(tool_results)
        final_response = llm.invoke([
            SystemMessage(content=PROMPT_RECEPCION),
            *messages,
            AIMessage(content=f"[Resultado de herramientas]:\n{context_msg}"),
            HumanMessage(content="Basándote en el resultado anterior, genera una respuesta amable y clara para el paciente."),
        ])

        return {
            "messages": [AIMessage(content=final_response.content)],
            "next_agent": "FINISH",
        }

    return {
        "messages": [response],
        "next_agent": "FINISH",
    }


def medico_node(state: AgentState) -> dict:
    """Nodo Asistente Médico: cierre clínico, evoluciones."""
    messages = state["messages"]
    chat_id = state["telegram_chat_id"]

    llm_with_tools = llm.bind_tools(tools_medico)

    response = llm_with_tools.invoke([
        SystemMessage(content=PROMPT_ASISTENTE_MEDICO),
        *messages,
    ])

    if response.tool_calls:
        tool_results = []
        for tool_call in response.tool_calls:
            tool_call["args"]["telegram_chat_id"] = chat_id

            tool_fn = _get_tool_by_name(tool_call["name"], tools_medico)
            if tool_fn:
                result = tool_fn.invoke(tool_call["args"])
                tool_results.append(result)

        context_msg = "\n\n".join(tool_results)
        final_response = llm.invoke([
            SystemMessage(content=PROMPT_ASISTENTE_MEDICO),
            *messages,
            AIMessage(content=f"[Resultado de herramientas]:\n{context_msg}"),
            HumanMessage(content="Basándote en el resultado anterior, genera una respuesta clara para el doctor."),
        ])

        return {
            "messages": [AIMessage(content=final_response.content)],
            "next_agent": "FINISH",
        }

    return {
        "messages": [response],
        "next_agent": "FINISH",
    }


def facturacion_node(state: AgentState) -> dict:
    """Nodo Facturación: registro de pagos."""
    messages = state["messages"]
    chat_id = state["telegram_chat_id"]

    llm_with_tools = llm.bind_tools(tools_facturacion)

    response = llm_with_tools.invoke([
        SystemMessage(content=PROMPT_FACTURACION),
        *messages,
    ])

    if response.tool_calls:
        tool_results = []
        for tool_call in response.tool_calls:
            tool_call["args"]["telegram_chat_id"] = chat_id

            tool_fn = _get_tool_by_name(tool_call["name"], tools_facturacion)
            if tool_fn:
                result = tool_fn.invoke(tool_call["args"])
                tool_results.append(result)

        context_msg = "\n\n".join(tool_results)
        final_response = llm.invoke([
            SystemMessage(content=PROMPT_FACTURACION),
            *messages,
            AIMessage(content=f"[Resultado de herramientas]:\n{context_msg}"),
            HumanMessage(content="Basándote en el resultado anterior, genera una respuesta clara para el usuario."),
        ])

        return {
            "messages": [AIMessage(content=final_response.content)],
            "next_agent": "FINISH",
        }

    return {
        "messages": [response],
        "next_agent": "FINISH",
    }


# ==================================================================
#  UTILIDADES INTERNAS
# ==================================================================

def _get_tool_by_name(name: str, tool_list: list):
    """Busca una herramienta por su nombre en una lista de tools."""
    for t in tool_list:
        if t.name == name:
            return t
    return None


def _router(state: AgentState) -> str:
    """Función de enrutamiento condicional para el grafo."""
    next_agent = state.get("next_agent", "FINISH")
    if next_agent == "FINISH":
        return END
    return next_agent


# ==================================================================
#  ENSAMBLAJE DEL GRAFO (StateGraph)
# ==================================================================

# 1. Crear el grafo
graph = StateGraph(AgentState)

# 2. Añadir nodos
graph.add_node("supervisor", supervisor_node)
graph.add_node("recepcion", recepcion_node)
graph.add_node("asistente_medico", medico_node)
graph.add_node("facturacion", facturacion_node)

# 3. Definir flujo
graph.add_edge(START, "supervisor")

# 4. Enrutamiento condicional desde el supervisor
graph.add_conditional_edges(
    "supervisor",
    _router,
    {
        "recepcion": "recepcion",
        "asistente_medico": "asistente_medico",
        "facturacion": "facturacion",
        END: END,
    }
)

# 5. Los subagentes siempre terminan después de responder
graph.add_edge("recepcion", END)
graph.add_edge("asistente_medico", END)
graph.add_edge("facturacion", END)

# 6. Compilar
app = graph.compile()


# ==================================================================
#  FUNCIÓN PÚBLICA (usada por main.py)
# ==================================================================

async def procesar_mensaje(telegram_chat_id: str, mensaje: str) -> str:
    """Punto de entrada principal del SMA.
    Recibe el chat_id y el texto del mensaje de Telegram,
    procesa a través del grafo de agentes, y retorna la respuesta.

    Args:
        telegram_chat_id: ID del chat de Telegram del usuario.
        mensaje: Texto del mensaje enviado por el usuario.

    Returns:
        Respuesta del agente correspondiente como string.
    """
    result = await app.ainvoke({
        "messages": [HumanMessage(content=mensaje)],
        "next_agent": "supervisor",
        "telegram_chat_id": telegram_chat_id,
    })

    # Extraer el último mensaje del AI
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content

    return "🤖 Lo siento, no pude procesar tu mensaje. ¿Podrías reformularlo?"
