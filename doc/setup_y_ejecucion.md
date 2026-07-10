# 🚀 Guía de Levantamiento y Ejecución — AutomaDent

El proyecto AutomaDent ha sido reestructurado modularmente para facilitar su desarrollo, escalabilidad y despliegue. Esta guía detalla cómo levantar todos los servicios tanto en un entorno de desarrollo local como usando contenedores Docker.

---

## 📂 Estructura del Proyecto

El sistema está empaquetado bajo el módulo raíz `src/` que agrupa las distintas capas lógicas y servicios:
- **`src/utils/`**: Base de datos, logger, notificaciones y parámetros comunes.
- **`src/modelos/`**: Clientes LLM y embeddings.
- **`src/prompts/`**: Prompts de los agentes.
- **`src/agent/`**: Grafo de LangGraph y memoria del SMA.
- **`src/tools/`**: Servidor MCP y herramientas del dominio dental.
- **`src/telegram/`**: Interfaz de bot.
- **`src/api/`**: API REST FastAPI.
- **`src/dashboard/`**: Dashboard Streamlit administrativo.

---

## ⚙️ Requisitos Previos

- **Python 3.11+** (para ejecución local)
- **Docker y Docker Compose** (para ejecución en contenedores)
- **PowerShell** (para Windows con `start_all.ps1`)

---

## 🛠️ Configuración Inicial

### 1. Variables de Entorno (`.env`)
En la raíz del proyecto, asegúrate de tener el archivo `.env` configurado.
```env
SUPABASE_URL=tu_url_de_supabase
SUPABASE_SERVICE_KEY=tu_service_key

TELEGRAM_BOT_TOKEN=tu_token_de_telegram
GEMINI_API_KEY=tu_api_key_de_gemini

# Opcionales y defaults
CLINIC_TIMEZONE=America/Lima
LOG_LEVEL=INFO
JWT_SECRET_KEY=automadent-super-secret-change-in-production
JWT_EXPIRE_MINUTES=480
CORS_ORIGINS=http://localhost:4200,http://localhost:3000
DASHBOARD_PASSWORD=dent123
```

### 2. Archivo de Credenciales (Google Sheets)
Si el bot va a interactuar con Google Sheets para exportar reportes, coloca el archivo `credentials.json` en la raíz del proyecto.

---

## 💻 Ejecución Local (Desarrollo)

Usamos el CLI de control unificado a través de `src.main` y un entorno virtual único en el raíz.

### 1. Crear entorno virtual e instalar dependencias
Abre una terminal en la raíz del proyecto y ejecuta:
```powershell
python -m venv venv
.\venv\Scripts\activate

# Instalar las dependencias consolidadas
pip install -r requirements.txt
```

### 2. Iniciar todos los servicios
Ejecuta el script de control desde la raíz:
```powershell
.\start_all.ps1
```
Este script levantará de forma asíncrona en terminales individuales:
1. **API REST:** `http://localhost:8000` (Swagger en `/docs`)
2. **Dashboard:** `http://localhost:8502`
3. **MCP Server:** `http://localhost:8001/mcp`
4. **Bot de Telegram:** Polling activo (el bot gestiona internamente la conexión y subproceso del servidor MCP si es necesario).

---

## 🐳 Ejecución con Docker (Producción)

El proyecto incluye un archivo `compose.yml` en la raíz que utiliza los Dockerfiles de `docker/` para aislar los microservicios.

### 1. Construir las imágenes
```bash
docker compose build
```

### 2. Levantar los contenedores
```bash
docker compose up -d
```

### 3. Verificar el estado
```bash
docker compose logs -f api
docker compose logs -f bot
docker compose logs -f dashboard
docker compose logs -f mcp-server
```
