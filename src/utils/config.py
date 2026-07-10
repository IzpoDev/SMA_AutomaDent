# src/utils/config.py — Configuración Centralizada de la Clínica AutomaDent
# ==============================================================================
# Fuente única de verdad para constantes clínicas y parámetros del sistema.
# Reemplaza las constantes repetidas en: tools.py, mcp_server.py, citas.py,
# agents.py (4+ archivos previos).
# ==============================================================================

import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# ─── Zona Horaria ─────────────────────────────────────────────────────────────
TIMEZONE = ZoneInfo(os.environ.get("CLINIC_TIMEZONE", "America/Lima"))

# ─── Configuración del Horario de la Clínica ─────────────────────────────────
DURACION_CITA_MIN: int = 30          # Duración estándar de cada cita en minutos
HORARIO_INICIO: int = 8              # 08:00 AM
HORARIO_FIN: int = 18               # 06:00 PM
DIAS_LABORALES: list[int] = [0, 1, 2, 3, 4, 5]  # Lunes(0) a Sábado(5)

# ─── Google Sheets / Drive ────────────────────────────────────────────────────
CREDENTIALS_FILE: str = os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json")
SCOPES_GOOGLE: list[str] = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ─── MCP Server ───────────────────────────────────────────────────────────────
MCP_SERVER_URL: str = os.environ.get("MCP_SERVER_URL", "http://localhost:8001/mcp")
MCP_SERVER_PORT: int = int(os.environ.get("MCP_SERVER_PORT", 8001))
MCP_SERVER_HOST: str = os.environ.get("MCP_SERVER_HOST", "0.0.0.0")

# ─── Bot de Telegram ──────────────────────────────────────────────────────────
TELEGRAM_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# ─── Supabase ────────────────────────────────────────────────────────────────
SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY: str = os.environ.get("SUPABASE_SERVICE_KEY", "")

# ─── Modelos LLM (cascada de fallback) ───────────────────────────────────────
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
MODEL_CASCADE: list[str] = [
    "gemini-2.0-flash-lite",                  # Principal — Mayor cuota diaria
    "gemini-2.5-flash-lite-preview-06-17",    # Fallback 1
    "gemini-2.5-flash",                        # Fallback 2
]
MODEL_TEMPERATURE: float = 0.3

# ─── Embeddings / RAG ────────────────────────────────────────────────────────
EMBEDDING_MODEL: str = "gemini-embedding-001"
RAG_THRESHOLD: float = 0.65
RAG_TOP_K: int = 3
EMBEDDING_DIMS: int = 768

# ─── Memoria del Agente ───────────────────────────────────────────────────────
TURNOS_PARA_RESUMIR: int = 10   # Resumir historial cada 10 mensajes
LIMITE_HISTORIAL: int = 8       # Mensajes recientes a mantener en contexto

# ─── API REST ─────────────────────────────────────────────────────────────────
JWT_SECRET_KEY: str = os.environ.get(
    "JWT_SECRET_KEY", "automadent-super-secret-change-in-production"
)
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRE_MINUTES: int = int(os.environ.get("JWT_EXPIRE_MINUTES", 480))

CORS_ORIGINS: list[str] = os.environ.get(
    "CORS_ORIGINS", "http://localhost:4200,http://localhost:3000"
).split(",")

# ─── Dashboard ───────────────────────────────────────────────────────────────
DASHBOARD_PASSWORD: str = os.environ.get("DASHBOARD_PASSWORD", "dent123")

# ─── Logging ─────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
LOG_DIR: str = os.environ.get("LOG_DIR", "./logs")
