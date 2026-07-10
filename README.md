# AutomaDent — Sistema Multiagente para Clínica Dental 🦷

Proyecto reestructurado bajo una arquitectura limpia, modular y escalable para Agentes de IA.

## Requisitos de Entorno

Asegúrate de configurar las variables del archivo `.env` antes de ejecutar. El sistema requiere:
- Supabase (con extensión pgvector y RPC `buscar_documentos`)
- Clave de API de Gemini (Google GenAI)
- Token de Bot de Telegram

## Instalación

```bash
# 1. Crear entorno virtual
python -m venv venv

# 2. Activar entorno virtual
# En Windows:
.\venv\Scripts\activate

# 3. Instalar dependencias consolidadas
pip install -r requirements.txt
```

## Ejecución de Servicios con CLI Unificado

El proyecto cuenta con un CLI de ejecución única en `src/main.py`:

```bash
# Iniciar Bot de Telegram (levanta el servidor MCP en background automáticamente)
python -m src.main bot

# Iniciar la API REST (FastAPI en puerto 8000)
python -m src.main api

# Iniciar el Servidor MCP de forma independiente (puerto 8001)
python -m src.main mcp

# Iniciar el Dashboard Streamlit (puerto 8502)
python -m src.main dashboard

# Ejecutar despachador de notificaciones (ej. para cron a las 7am/7pm)
python -m src.main notifier
```

## Estructura del Código

- `src/utils/`: Base de datos, notificaciones deduplicadas, logger y constantes de la clínica.
- `src/modelos/`: Gestión de clientes LLM y generación de embeddings.
- `src/prompts/`: System Prompts y prompts específicos de los agentes.
- `src/agent/`: StateGraph de LangGraph, lógica de nodos y orquestador.
- `src/tools/`: Herramientas de dominio de la clínica registradas en el servidor MCP.
- `src/telegram/`: Handler del bot de Telegram y autenticación basada en roles.
- `src/api/`: API REST FastAPI para control administrativo.
- `src/dashboard/`: Portal administrativo basado en Streamlit.
