# 🦷 Arquitectura del Proyecto: Sistema Multiagente AutomaDent

Este documento detalla la arquitectura del software, los flujos de comunicación, el modelo de datos y los componentes tecnológicos que integran el **Sistema Multiagente para la Clínica Dental AutomaDent**, bajo la nueva estructura limpia, modular y centralizada en `src/`.

---

## 🗺️ 1. Arquitectura General (Hub-and-Spoke + MCP)

El sistema se basa en un patrón de diseño **Hub-and-Spoke (Orquestador y Especialistas)** implementado mediante **LangGraph** y **LangChain**. La lógica de negocio y las integraciones de base de datos están desacopladas en herramientas MCP que corre en un servidor interno expuesto vía HTTP y consumido dinámicamente por el agente principal.

```mermaid
graph TD
    %% Interfaces
    Telegram[📱 Bot de Telegram - src.telegram.bot]
    Dashboard[💻 Dashboard Web - src.dashboard.app]
    Cron[⏰ Tareas - src.notifier.notifier]

    %% Capa de Orquestación e IA
    SMA[🧠 LangGraph - src.agent.agente]
    Supervisor[👤 Orquestador Central]
    Recepcion[👩‍💼 Agente Recepción]
    Medico[🩺 Agente Médico]
    Facturacion[💰 Agente Facturación]

    %% Capa de Datos (MCP)
    MCPServer[🔌 Servidor MCP - src.tools.servidor_mcp]
    DB[(🗄️ Supabase)]

    %% Flujos Principales
    Telegram -->|Mensaje + Rol| SMA
    SMA --> Supervisor
    Supervisor -->|Ruta intenciones| Recepcion
    Supervisor -->|Ruta intenciones| Medico
    Supervisor -->|Ruta intenciones| Facturacion

    %% Conexión de herramientas MCP
    Recepcion -- "Client SSE/HTTP" --> MCPServer
    Medico -- "Client SSE/HTTP" --> MCPServer
    Facturacion -- "Client SSE/HTTP" --> MCPServer
    
    %% Base de Datos
    MCPServer --> DB
    Dashboard --> DB
    Cron --> DB
    Cron -->|Notificaciones| Telegram
```

---

## 📦 2. Estructura de Componentes en `src/`

La estructura modular del sistema se distribuye de la siguiente manera:

### `src/utils/`
- **`config.py`**: Centraliza todas las variables de entorno, constantes clínicas (`TIMEZONE`, `HORARIO_INICIO`, etc.) y configuraciones de modelos.
- **`database.py`**: Inicialización del cliente Supabase singleton y utilidades de almacenamiento de historial de chat, memorias y resúmenes.
- **`notificaciones.py`**: Centraliza el envío de notificaciones automáticas y alertas a pacientes u odontólogos vía API de Telegram.
- **`logger.py`**: Setup global para logs rotativos y de consola.
- **`helpers.py`**: Funciones utilitarias como sanitización de HTML y extracción de contenidos de mensajes de texto.

### `src/modelos/`
- **`cliente_llm.py`**: Construye el cliente Gemini y administra la lógica de cascada de fallback ante límites de cuota (429).
- **`embeddings.py`**: Generación de vectores de embeddings de documentos y queries para RAG.

### `src/prompts/`
- **`sistema_prompts.py`**: Contiene las plantillas de prompts para el Supervisor central y la compresión del historial.
- **`agente_prompts.py`**: Definiciones de personalidad y reglas RBAC para los agentes de Recepción, Asistente Médico y Facturación.

### `src/agent/`
- **`estado.py`**: Estructura `AgentState` de LangGraph y mapeo de herramientas permitidas por rol.
- **`agente.py`**: Construcción del grafo de LangGraph y definición de nodos.
- **`ejecutor.py`**: Orquestación del flujo del mensaje: búsqueda RAG, carga de memoria compacta, ejecución del grafo y almacenamiento del historial.
- **`memoria.py`**: Lógica de generación automática de resúmenes asíncronos en segundo plano.

### `src/tools/`
Módulos que contienen la lógica de negocio registrada como herramientas MCP (`@mcp.tool()`):
- **`recepcion.py`**: Registro de pacientes, citas e historial.
- **`medico.py`**: Evoluciones médicas y estados de citas.
- **`facturacion.py`**: Registro de pagos.
- **`administrativas.py`**: Listados de citas y personal.
- **`exportacion.py`**: Reportes en Google Sheets.
- **`servidor_mcp.py`**: Servidor FastMCP que inicializa y expone las herramientas.

### `src/telegram/`
- **`bot.py`**: Lógica principal de ejecución de Telegram, polling, handlers `/start` e inicio del subproceso del servidor MCP.
- **`rbac.py`**: Resolución de roles basada en el chat ID.

### `src/api/`
- **`app.py`**: Aplicación FastAPI principal.
- **`auth.py`**: Gestión de tokens JWT y hashing de contraseñas de personal.
- **`rutas/`**: Controladores de endpoints REST para la gestión web (`citas.py`, `pacientes.py`, `personal.py`, etc.).

---

## 🚦 3. Flujo de un Mensaje (Secuencia)

```mermaid
sequenceDiagram
    autonumber
    actor Usuario as 📱 Usuario
    participant Main as 🔌 src.telegram.bot (CLI)
    participant MCP as 🌐 src.tools.servidor_mcp
    participant DB as 🗄️ Supabase
    participant SMA as 🧠 src.agent.ejecutor
    
    Main->>MCP: Levanta el servidor MCP (puerto 8001)
    Main->>MCP: Se conecta y obtiene lista de herramientas
    Main->>SMA: Inyecta herramientas a los agentes
    Usuario->>Main: Envía mensaje (ej: "Agendar cita")
    Main->>DB: Consulta rol asignado al Chat ID (rbac.py)
    DB-->>Main: Retorna rol
    Main->>SMA: procesar_mensaje()
    SMA->>SMA: Inyecta RAG y Memoria Reciente
    SMA->>MCP: Invoca herramienta MCP (agendar_cita)
    MCP->>DB: Realiza inserción
    DB-->>MCP: Retorna OK
    MCP-->>SMA: Retorna resultado
    SMA-->>Main: Respuesta final en HTML
    Main->>Usuario: "✅ Cita agendada"
```
