# api.py — Punto de Entrada de la API REST FastAPI (AutomaDent)
# ==============================================================================
# Arranca el servidor REST de la clínica. Registra todos los routers y
# configura CORS para ser consumido por el frontend Angular.
#
# Para ejecutar (desarrollo):
#   uvicorn api:app --reload --port 8000
#
# Documentación interactiva (Swagger UI):
#   http://localhost:8000/docs
# ==============================================================================

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from routes.auth import router as auth_router
from routes.usuarios import router as usuarios_router
from routes.personal import router as personal_router
from routes.pacientes import router as pacientes_router
from routes.historias import router as historias_router
from routes.citas import router as citas_router
from routes.pagos import router as pagos_router

load_dotenv()

# ─── Configuración de la aplicación ──────────────────────────────────────────
app = FastAPI(
    title="AutomaDent API",
    description=(
        "API REST del Sistema de Gestión para la Clínica Dental AutomaDent. "
        "Proporciona CRUD completo para citas, pacientes, personal, historias clínicas y pagos. "
        "Autenticación mediante JWT."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS (Cross-Origin Resource Sharing) ────────────────────────────────────
# Permite peticiones desde el frontend Angular en desarrollo y producción.
ALLOWED_ORIGINS = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:4200,http://localhost:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Registro de Routers ──────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(usuarios_router)
app.include_router(personal_router)
app.include_router(pacientes_router)
app.include_router(historias_router)
app.include_router(citas_router)
app.include_router(pagos_router)


# ─── Health Check ────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def health_check():
    """Verifica que la API esté funcionando correctamente."""
    return {
        "status": "ok",
        "sistema": "AutomaDent API v1.0",
        "docs": "/docs",
    }
