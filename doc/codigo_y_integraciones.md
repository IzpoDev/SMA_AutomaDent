# 📖 Documentación del Código e Integraciones

Esta guía describe en detalle la organización modular de los componentes clave del repositorio del **Sistema Multiagente AutomaDent**, bajo la nueva estructura centralizada en `src/`.

---

## 1. Archivos de Configuración y Entorno

### `1.1. .env`
Contiene las variables de entorno sensibles y de configuración clínica.
- `TELEGRAM_BOT_TOKEN`: Token otorgado por BotFather para la interfaz del usuario.
- `SUPABASE_URL` / `SUPABASE_SERVICE_KEY`: Credenciales para Supabase.
- `GEMINI_API_KEY`: Clave para invocar los modelos de Google Gemini.
- `CLINIC_TIMEZONE`: Zona horaria oficial de la clínica (default `America/Lima`).

### `1.2. requirements.txt`
Consolida todas las dependencias del proyecto de forma ordenada por categorías (FastAPI, Streamlit, LangGraph, Telegram, Google API) para evitar la fragmentación de requisitos que existía anteriormente.

---

## 2. Puntos de Entrada de la Aplicación

El sistema unifica los subprocesos de ejecución en un punto de entrada centralizado:

### `2.1. src/main.py` (CLI de Control General)
Es el script que actúa como CLI para arrancar cualquiera de los servicios:
- `bot`: Lanza el bot de Telegram (`src/telegram/bot.py`). Arranca de forma automática el servidor MCP como subproceso.
- `api`: Inicia el servidor de API REST FastAPI (`src/api/app.py`).
- `mcp`: Ejecuta únicamente el backend de herramientas FastMCP (`src/tools/servidor_mcp.py`).
- `dashboard`: Ejecuta el panel interactivo Streamlit (`src/dashboard/app.py`).
- `notifier`: Corre el script de notificaciones proactivas programadas (`src/notifier/notifier.py`).

---

## 3. El Cerebro (IA) y Agentes

### `3.1. src/agent/` (Capa de LangGraph)
- **`agente.py`**: Define los nodos y compila el grafo supervisor-especialistas (`StateGraph`).
- **`ejecutor.py`**: Es el pipeline de procesamiento de mensajes. Realiza búsquedas semánticas vectoriales (RAG) en base a la entrada, inyecta resúmenes históricos e invoca el grafo.
- **`estado.py`**: Contiene la definición del estado de ejecución `AgentState` y distribuye el mapeo de herramientas de red MCP permitidas a cada subagente según RBAC.
- **`memoria.py`**: Genera resúmenes automáticos asíncronos en background cuando el número de mensajes excede el umbral para evitar la saturación de tokens del contexto.

### `3.2. src/prompts/` (Prompt Engineering)
Contiene las plantillas de prompts desvinculadas del código lógico:
- **`sistema_prompts.py`**: Prompts de enrutamiento del supervisor y generación de resúmenes.
- **`agente_prompts.py`**: Prompts específicos de Recepción, Asistente Médico y Facturación con restricciones de rol embebidas.

---

## 4. Herramientas MCP y Lógica de Negocio

### `4.1. src/tools/` (Capa de Herramientas)
Contiene la lógica de negocio expuesta vía protocolo MCP:
- **`recepcion.py`**: Gestión de agenda, disponibilidad horaria (`consultar_disponibilidad_agenda`) y registro de pacientes.
- **`medico.py`**: Actualización de citas y registro de atenciones.
- **`facturacion.py`**: Registro de pagos en la base de datos.
- **`exportacion.py`**: Integración con Google Sheets para generar informes.
- **`servidor_mcp.py`**: Expone las funciones como herramientas a través del servidor FastMCP.

---

## 5. Capa Web y Tareas de Background

### `5.1. src/api/` (FastAPI REST)
Expone la API REST que consume el frontend Angular de la clínica. Centraliza autenticación JWT y CRUD clínico completo en `src/api/rutas/`.

### `5.2. src/dashboard/` (Streamlit)
Panel web visual e independiente para la gestión del personal dental y visualización de gráficos Plotly.

### `5.3. src/notifier/` (Recordatorios Autónomos)
Script asíncrono para enviar de forma programada recordatorios automáticos de citas a los pacientes y la agenda del día a los doctores.
