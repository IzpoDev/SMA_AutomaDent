# src/api/rutas/auth.py — Endpoints de Autenticación
# ==============================================================================
# POST /api/auth/login → Valida username+password y retorna token JWT.
# GET  /api/auth/me    → Retorna los datos del usuario autenticado actual.
# ==============================================================================

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from src.utils.database import supabase
from src.api.auth import verify_password, create_access_token, decode_access_token

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])
security = HTTPBearer()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario_id: int
    username: str
    rol: str
    personal_id: Optional[int] = None
    nombre_completo: Optional[str] = None


# ==============================================================================
#  DEPENDENCIAS DE AUTENTICACIÓN (reutilizables en otras rutas)
# ==============================================================================

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Dependencia que valida el JWT e inyecta el payload del usuario."""
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependencia que exige rol 'administrador'."""
    if current_user.get("rol") != "administrador":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado. Se requiere rol de Administrador.",
        )
    return current_user


def require_staff(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependencia que permite cualquier rol del personal de la clínica."""
    if current_user.get("rol") not in ["administrador", "recepcionista", "odontologo"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado. Solo el personal de la clínica puede acceder.",
        )
    return current_user


# ==============================================================================
#  ENDPOINTS
# ==============================================================================

@router.post("/login", response_model=TokenResponse, summary="Iniciar sesión")
def login(body: LoginRequest):
    """Autentica a un usuario del sistema y retorna un token JWT."""
    res = (
        supabase.table("usuarios")
        .select("id, username, password_hash, personal_id")
        .eq("username", body.username.strip())
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
        )

    usuario = res.data[0]
    if not verify_password(body.password, usuario["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
        )

    rol = "administrador"
    nombre_completo = None
    personal_id = usuario.get("personal_id")

    if personal_id:
        personal_res = (
            supabase.table("personal")
            .select("rol, nombre, apellido")
            .eq("id", personal_id)
            .limit(1)
            .execute()
        )
        if personal_res.data:
            rol = personal_res.data[0]["rol"]
            nombre_completo = (
                f"{personal_res.data[0]['nombre']} {personal_res.data[0]['apellido']}"
            )

    token_data = {
        "sub": str(usuario["id"]),
        "username": usuario["username"],
        "rol": rol,
        "personal_id": personal_id,
    }
    access_token = create_access_token(token_data)

    return TokenResponse(
        access_token=access_token,
        usuario_id=usuario["id"],
        username=usuario["username"],
        rol=rol,
        personal_id=personal_id,
        nombre_completo=nombre_completo,
    )


@router.get("/me", summary="Datos del usuario autenticado")
def me(current_user: dict = Depends(get_current_user)):
    """Retorna los datos del usuario autenticado a partir del token JWT."""
    return {
        "usuario_id": current_user.get("sub"),
        "username": current_user.get("username"),
        "rol": current_user.get("rol"),
        "personal_id": current_user.get("personal_id"),
    }
