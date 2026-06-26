# 🚀 Guía de Levantamiento y Ejecución — AutomaDent

El proyecto AutomaDent ha sido reestructurado modularmente para facilitar su desarrollo, escalabilidad y despliegue. Esta guía detalla cómo levantar todos los servicios tanto en un entorno de desarrollo local como usando contenedores Docker.

---

## 📂 Estructura del Proyecto

El sistema está dividido en cuatro módulos principales:
- **`shared/`**: Base de datos compartida y scripts comunes (RAG, esquemas).
- **`bot/`**: Bot de Telegram y Servidor MCP (langchain, genai).
- **`api/`**: API REST en FastAPI para el consumo desde el frontend (Angular/Web).
- **`dashboard/`**: Panel de control administrativo construido con Streamlit.

---

## ⚙️ Requisitos Previos

- **Python 3.13+** (para ejecución local)
- **Docker y Docker Compose** (para ejecución en contenedores)
- **PowerShell** (si estás en Windows para los scripts `.ps1`)

---

## 🛠️ Configuración Inicial

### 1. Variables de Entorno (`.env`)
En la raíz del proyecto, asegúrate de tener el archivo `.env` configurado. Este archivo es compartido por todos los módulos.
```env
# Ejemplo de .env
SUPABASE_URL=tu_url_de_supabase
SUPABASE_SERVICE_KEY=tu_service_key

TELEGRAM_BOT_TOKEN=tu_token_de_telegram
GEMINI_API_KEY=tu_api_key_de_gemini

# Opcional
JWT_SECRET_KEY=clave_super_secreta_para_tokens
JWT_EXPIRE_MINUTES=480
```

### 2. Archivo de Credenciales (Google Sheets)
Si el bot va a interactuar con Google Sheets, asegúrate de colocar tu archivo `credentials.json` dentro de la carpeta `bot/`.

---

## 💻 Ejecución Local (Desarrollo)

Para probar y desarrollar sin Docker, usamos un script de PowerShell que configura los entornos y lanza todo.

### 1. Crear entorno virtual e instalar dependencias
Abre una terminal en la raíz del proyecto y ejecuta:
```powershell
python -m venv venv
.\venv\Scripts\activate

# Instalar dependencias de todos los módulos
pip install -r bot/requirements.txt
pip install -r api/requirements.txt
pip install -r dashboard/requirements.txt
```

### 2. Iniciar todos los servicios
Ejecuta el script orquestador desde la raíz:
```powershell
.\start_all.ps1
```
Este script abrirá 4 terminales independientes configurando el `PYTHONPATH` automáticamente:
1. **API REST:** `http://localhost:8000` (Swagger en `/docs`)
2. **Dashboard:** `http://localhost:8502`
3. **MCP Server:** `http://localhost:8001/mcp`
4. **Bot de Telegram:** Se quedará escuchando en modo polling.

Para detener los servicios, simplemente cierra cada ventana de PowerShell.

---

## 🐳 Ejecución con Docker (Producción)

El proyecto incluye un `compose.yml` en la raíz que orquesta los contenedores, los aísla en una red interna y maneja los volúmenes para el código compartido.

### 1. Construir las imágenes
En la raíz del proyecto ejecuta:
```powershell
docker compose build
```
*Esto leerá cada `Dockerfile` dentro de `bot/`, `api/` y `dashboard/` instalando solo las dependencias necesarias de cada uno.*

### 2. Levantar los contenedores
```powershell
docker compose up -d
```

### 3. Verificar el estado
Puedes ver los logs de cada servicio:
```powershell
docker compose logs -f api
docker compose logs -f bot
docker compose logs -f dashboard
docker compose logs -f mcp-server
```

**Accesos:**
- **API REST:** `http://localhost:8000`
- **Dashboard Streamlit:** `http://localhost:8502`

Para detener todo:
```powershell
docker compose down
```
