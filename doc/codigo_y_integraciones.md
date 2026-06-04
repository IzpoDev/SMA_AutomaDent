# 📖 Documentación del Código e Integraciones

Esta guía describe en detalle cada archivo clave del repositorio del **Sistema Multiagente AutomaDent**, explicando su propósito, cómo se integra con el resto del sistema, y la reciente adopción de **MCP (Model Context Protocol)**.

---

## 1. Archivos de Configuración y Entorno

### `1.1. .env`
Contiene las variables de entorno sensibles y configuración de la aplicación.
- `TELEGRAM_BOT_TOKEN`: Token otorgado por BotFather para la interfaz del usuario.
- `SUPABASE_URL` / `SUPABASE_SERVICE_KEY`: Credenciales de la base de datos PostgreSQL alojada en Supabase.
- `GOOGLE_API_KEY`: Clave principal para instanciar el modelo LLM de Google Gemini.
- `MCP_SERVER_URL`: URL en la cual escucha el servidor FastMCP (por defecto `http://localhost:8001/sse`).
- `WEBHOOK_URL`: (Opcional) Si se establece, cambia el comportamiento del bot de `polling` a `webhook` para producción.

### `1.2. .gitignore`
Archivos y carpetas excluidos del control de versiones (git). Esto evita que secretos, como `.env` y `credentials.json`, y archivos de entorno virtual (`.venv/`, `__pycache__/`) se suban al repositorio público.

### `1.3. requirements.txt`
Listado de todas las dependencias de Python necesarias. Entre las más importantes:
- `langchain`, `langgraph`, `langchain-google-genai`: Construcción del sistema multiagente.
- `python-telegram-bot`: Framework asíncrono para el bot de Telegram.
- `supabase`: Cliente oficial para operaciones en la base de datos.
- `mcp`, `langchain-mcp-adapters`: Bibliotecas para levantar el servidor y consumir herramientas mediante el Model Context Protocol.
- `streamlit`: Framework para el dashboard administrativo.

---

## 2. Puntos de Entrada de la Aplicación

El sistema requiere dos procesos ejecutándose de manera simultánea:

### `2.1. mcp_server.py` (Capa Backend de Datos)
Es un servidor **FastMCP** independiente que expone todas las funciones críticas de negocio a través de la red (puerto `8001`).
- **¿Qué hace?** Expone métodos CRUD en Supabase y los registra como herramientas de IA (`@mcp.tool()`).
- **Integraciones:** Conecta directamente con Supabase (`create_client`) usando la `SUPABASE_SERVICE_KEY` para saltarse restricciones RLS y operar como administrador backend. También incluye notificaciones a través de Telegram (`requests.post`).
- **Herramientas Expuestas:** `crear_paciente_y_historia`, `consultar_disponibilidad_agenda`, `agendar_cita`, `consultar_historial_paciente`, `actualizar_estado_cita`, `registrar_pago`, etc.
- **Seguridad:** Recibe el parámetro `user_role` desde el bot en cada llamada. Si el rol no tiene permisos, el servidor deniega la acción antes de consultar la BD.

### `2.2. main.py` (Capa de Presentación e IA)
Es el script principal del bot de Telegram que orquesta la conexión entre el usuario, el LLM y el servidor MCP.
- **Arranque Asíncrono:** La función `run()` primero inicializa una conexión **SSE (Server-Sent Events)** con el servidor MCP en `http://localhost:8001/sse` mediante `MultiServerMCPClient`.
- **Carga de herramientas:** Extrae dinámicamente las herramientas proporcionadas por el servidor MCP (`mcp_client.get_tools()`) y las inyecta al grafo mediante `set_mcp_tools()` en `agents.py`.
- **RBAC Inicial:** La función `obtener_rol_usuario()` hace la primera verificación en Supabase para obtener el rol del usuario conectado mediante su ID de Telegram.
- **Ciclo:** Recibe el mensaje, pasa el `texto`, `chat_id` y `rol` a `procesar_mensaje` y responde al usuario parseando a HTML.

---

## 3. El Cerebro (IA)

### `3.1. agents.py`
Contiene toda la lógica del **Sistema Multiagente (SMA)** usando **LangGraph**.
- **Distribución MCP:** Recibe todas las herramientas cargadas desde el servidor MCP en `main.py` y las divide en grupos: `_tools_recepcion`, `_tools_medico`, `_tools_facturacion`.
- **Nodos del Grafo:** Existen 4 agentes (nodos):
  1. `supervisor_node`: Es un clasificador. Revisa el mensaje y responde **solo** con el nombre del departamento al que corresponde (ej. `recepcion`), dictando el enrutamiento.
  2. `recepcion_node`, `medico_node`, `facturacion_node`: Agentes especialistas. A estos nodos se les bindean (atan) las herramientas de red MCP correspondientes (`llm.bind_tools(_tools_recepcion)`).
- **Memoria Persistente:** Se comunica con `database.py` para inyectar un buffer de mensajes (historial) en cada turno y guardar la nueva interacción en Supabase para que el bot no pierda el contexto de la conversación.

---

## 4. Archivos Auxiliares y Lógica de Negocio

### `4.1. database.py`
Inicializa el cliente de conexión a Supabase usado por las herramientas directas.
Sus responsabilidades actuales son el manejo de la tabla `mensajes_chat` para proporcionar memoria a largo plazo al bot, permitiendo a los agentes leer el historial reciente usando `obtener_historial_mensajes()`.

### `4.2. tools.py`
Archivo de herramientas heredado (Legacy).
Gran parte de su funcionalidad (operaciones de Supabase) fue reescrita en `mcp_server.py`. Sin embargo, conserva integraciones locales importantes como la **Exportación de Reportes a Google Sheets** (`exportar_citas_excel`), la cual requiere los tokens estáticos cargados desde `credentials.json` (credenciales de Service Account de Google Cloud).

### `4.3. schema.sql`
El script de Base de Datos.
Contiene el modelo Entidad-Relación exacto en sintaxis PostgreSQL. Define enums (`rol_personal`, `estado_cita`), y la arquitectura relacional (pacientes ↔ citas ↔ atenciones_medicas). Sirve de referencia documental e inicializador para Supabase.

### `4.4. dashboard.py`
Aplicación web construida con **Streamlit**.
Se conecta de manera independiente a Supabase usando `.env` y permite a los dueños de la clínica gestionar al personal (`odontologos`, `recepcionistas`), ver métricas en tiempo real con gráficos Plotly y gestionar pacientes en una GUI tradicional, sin requerir la intervención del bot de IA.

### `4.5. notifier.py`
Script planificado (Cron Job).
Está diseñado para ejecutarse diariamente de forma aislada. Consulta la base de datos de Supabase y utiliza la API de Telegram para mandar proactivamente a los pacientes alertas de confirmación ("Recuerda tu cita de mañana a las 3PM").

---

## 5. Notas de Despliegue

La nueva arquitectura con **MCP** implica que el despliegue a producción requiere ejecutar dos servicios:
1. `mcp_server.py`: Para que los Endpoints locales/remotos expongan la manipulación de la Base de Datos.
2. `main.py`: Como el intermediario (cliente de IA) que consume el servidor y conecta a Telegram.

Esto abre la puerta a que el backend de AutomaDent (el servidor MCP) sea consumido por otras interfaces en el futuro (ej. Claude Desktop, asistentes de voz, entre otros) utilizando el mismo puerto `8001`.
