# 🦷 Arquitectura del Proyecto: Sistema Multiagente AutomaDent

Este documento detalla la arquitectura del software, los flujos de comunicación, el modelo de datos y los componentes tecnológicos que integran el **Sistema Multiagente para la Clínica Dental AutomaDent**, con especial énfasis en la reciente integración del protocolo **MCP (Model Context Protocol)**.

---

## 🗺️ 1. Arquitectura General (Hub-and-Spoke + MCP)

El sistema se basa en un patrón de diseño **Hub-and-Spoke (Orquestador y Especialistas)** implementado mediante **LangGraph** y **LangChain**. Recientemente, la lógica de negocio y las integraciones de base de datos fueron desacopladas del cliente Telegram a un servidor dedicado usando **FastMCP**, permitiendo un ecosistema escalable donde la IA consume las herramientas a través de Server-Sent Events (SSE).

```mermaid
graph TD
    %% Interfaces
    Telegram[📱 Bot de Telegram - main.py]
    Dashboard[💻 Dashboard Web - Streamlit]
    Cron[⏰ Tareas - notifier.py]

    %% Capa de Orquestación e IA
    SMA[🧠 LangGraph - agents.py]
    Supervisor[👤 Orquestador Central]
    Recepcion[👩‍💼 Agente Recepción]
    Medico[🩺 Agente Médico]
    Facturacion[💰 Agente Facturación]

    %% Capa de Datos (MCP)
    MCPServer[🔌 Servidor MCP - mcp_server.py]
    DB[(🗄️ Supabase)]

    %% Flujos Principales
    Telegram -->|Mensaje + Rol| SMA
    SMA --> Supervisor
    Supervisor -->|Ruta intenciones| Recepcion
    Supervisor -->|Ruta intenciones| Medico
    Supervisor -->|Ruta intenciones| Facturacion

    %% Conexión de herramientas MCP
    Recepcion -- "Client SSE" --> MCPServer
    Medico -- "Client SSE" --> MCPServer
    Facturacion -- "Client SSE" --> MCPServer
    
    %% Base de Datos
    MCPServer --> DB
    Dashboard --> DB
    Cron --> DB
    Cron -->|Notificaciones| Telegram
```

---

## 📦 2. Componentes del Proyecto

| Archivo | Tecnología | Rol / Responsabilidad |
| :--- | :--- | :--- |
| **`main.py`** | `python-telegram-bot`, `MultiServerMCPClient` | **Cliente Bot**. Arranca en modo polling, se conecta al servidor MCP mediante SSE y arranca la interfaz en Telegram. |
| **`mcp_server.py`** | `FastMCP`, `Supabase` | **Backend de Herramientas**. Expone las operaciones a la base de datos como herramientas MCP (`@mcp.tool()`) accesibles por red (puerto 8001). |
| **`agents.py`** | LangGraph, Gemini | **Cerebro del SMA**. Recibe las herramientas inyectadas desde el servidor MCP (`set_mcp_tools`) y orquesta el flujo multiagente. |
| **`database.py`** | Supabase SDK | **Cliente de Base de Datos Base**. Mantiene la conexión principal para métodos auxiliares (`guardar_mensaje`, etc.). |
| **`tools.py`** | Python | Archivo legado, algunas de sus funciones migratorias fueron movidas a MCP pero conserva integraciones legacy (como la exportación a Google Sheets). |
| **`schema.sql`** | PostgreSQL | Define la estructura de tablas, índices y Foreign Keys desplegadas en Supabase. |
| **`dashboard.py`** | Streamlit | Panel web visual y de gestión administrativa. |
| **`notifier.py`** | Python | Tareas programadas diarias. |
| **`.env`** | Env | Configuración local (Supabase, Telegram, MCP_SERVER_URL). |

---

## 🚦 3. Flujo de un Mensaje (Secuencia)

```mermaid
sequenceDiagram
    autonumber
    actor Usuario as 📱 Usuario
    participant Main as 🔌 main.py (Bot)
    participant MCP as 🌐 mcp_server.py
    participant DB as 🗄️ Supabase
    participant SMA as 🧠 agents.py
    
    Main->>MCP: Se conecta al arrancar (SSE en 8001)
    MCP-->>Main: Envía lista de herramientas (@mcp.tool)
    Main->>SMA: Inyecta herramientas a los agentes
    Usuario->>Main: Envía mensaje (ej: "Agendar cita")
    Main->>DB: Consulta rol asignado al Chat ID
    DB-->>Main: Retorna rol
    Main->>SMA: procesar_mensaje()
    SMA->>SMA: Supervisor enruta a Recepción
    SMA->>MCP: Invoca herramienta MCP (agendar_cita)
    MCP->>DB: Realiza inserción
    DB-->>MCP: Retorna OK
    MCP-->>SMA: Retorna resultado
    SMA-->>Main: Respuesta final en HTML
    Main->>Usuario: "✅ Cita agendada"
```

---

## 🔒 4. Seguridad (RBAC y MCP)

El sistema de roles ha sido trasladado e integrado firmemente en el Servidor MCP:
1. Las llamadas desde el bot hacia las herramientas MCP incluyen `telegram_chat_id` y `user_role` de forma transparente.
2. Cada `@mcp.tool()` en `mcp_server.py` realiza la comprobación interna:
   ```python
   if user_role not in ["administrador", "recepcionista"]:
       return "❌ Acceso Denegado."
   ```
3. Esto garantiza que incluso si otro cliente de IA (por ejemplo, Claude Code) se conecta al servidor MCP, se deban inyectar los roles o autenticación apropiados.
