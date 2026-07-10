# src/api/app.py — Aplicación FastAPI (AutomaDent)
# ==============================================================================
# Punto de entrada de la API REST. Registra routers y configura CORS.
#
# Ejecutar en desarrollo:
#   uvicorn src.api.app:app --reload --port 8000
#
# Documentación Swagger:
#   http://localhost:8000/docs
# ==============================================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.utils.config import CORS_ORIGINS
from src.api.rutas.auth import router as auth_router
from src.api.rutas.usuarios import router as usuarios_router
from src.api.rutas.personal import router as personal_router
from src.api.rutas.pacientes import router as pacientes_router
from src.api.rutas.historias import router as historias_router
from src.api.rutas.citas import router as citas_router
from src.api.rutas.pagos import router as pagos_router

# ─── Aplicación ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="AutomaDent API",
    description=(
        "API REST del Sistema de Gestión para la Clínica Dental AutomaDent. "
        "Proporciona CRUD completo para citas, pacientes, personal, historias clínicas y pagos. "
        "Autenticación mediante JWT."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(usuarios_router)
app.include_router(personal_router)
app.include_router(pacientes_router)
app.include_router(historias_router)
app.include_router(citas_router)
app.include_router(pagos_router)


# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def health_check():
    """Verifica que la API esté funcionando correctamente."""
    return {"status": "ok", "sistema": "AutomaDent API v2.0", "docs": "/docs"}
