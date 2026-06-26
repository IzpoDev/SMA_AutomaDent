# routes/usuarios.py — CRUD de Cuentas de Usuario del Sistema
# ==============================================================================
# GET    /api/usuarios        → Lista todas las cuentas
# POST   /api/usuarios        → Crea una cuenta nueva (con personal_id opcional)
# DELETE /api/usuarios/{id}   → Elimina una cuenta de usuario
# ==============================================================================

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional

from database import supabase
from auth import hash_password
from routes.auth import get_current_user, require_admin

router = APIRouter(prefix="/api/usuarios", tags=["Usuarios del Sistema"])


# ─── Schemas ─────────────────────────────────────────────────────────────────

class CrearUsuarioRequest(BaseModel):
    username: str
    password: str
    personal_id: Optional[int] = None


# ==============================================================================
#  ENDPOINTS
# ==============================================================================

@router.get("/", summary="Listar usuarios del sistema")
def listar_usuarios(current_user: dict = Depends(require_admin)):
    """
    Retorna el listado completo de cuentas de usuario registradas en el sistema.
    Solo accesible para Administradores.
    """
    res = (
        supabase.table("usuarios")
        .select("id, username, personal_id")
        .order("id")
        .execute()
    )

    usuarios = res.data or []

    # Enriquecer con el nombre y rol del personal si tiene personal_id
    if usuarios:
        personal_ids = [u["personal_id"] for u in usuarios if u.get("personal_id")]
        if personal_ids:
            personal_res = (
                supabase.table("personal")
                .select("id, nombre, apellido, rol")
                .in_("id", personal_ids)
                .execute()
            )
            personal_map = {p["id"]: p for p in (personal_res.data or [])}
            for u in usuarios:
                pid = u.get("personal_id")
                if pid and pid in personal_map:
                    p = personal_map[pid]
                    u["nombre_personal"] = f"{p['nombre']} {p['apellido']}"
                    u["rol"] = p["rol"]
                else:
                    u["nombre_personal"] = None
                    u["rol"] = "administrador"

    return {"total": len(usuarios), "usuarios": usuarios}


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Crear cuenta de usuario")
def crear_usuario(body: CrearUsuarioRequest, current_user: dict = Depends(require_admin)):
    """
    Crea una nueva cuenta de acceso al sistema web.

    - Si se proporciona **personal_id**, se verifica que el personal exista.
    - Si no se proporciona, la cuenta se crea con `personal_id = NULL` y tendrá rol de Administrador general.
    - El **password** se almacena encriptado con bcrypt.
    """
    # 1. Verificar que el username no exista
    existe = (
        supabase.table("usuarios")
        .select("id")
        .eq("username", body.username.strip())
        .limit(1)
        .execute()
    )
    if existe.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El username '{body.username}' ya está en uso.",
        )

    # 2. Verificar que el personal_id exista si fue proporcionado
    personal_id = None
    if body.personal_id:
        personal_check = (
            supabase.table("personal")
            .select("id")
            .eq("id", body.personal_id)
            .limit(1)
            .execute()
        )
        if not personal_check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No existe un miembro del personal con ID {body.personal_id}.",
            )
        personal_id = body.personal_id

    # 3. Insertar el usuario con la contraseña hasheada
    nuevo = {
        "username": body.username.strip(),
        "password_hash": hash_password(body.password),
        "personal_id": personal_id,
    }
    res = supabase.table("usuarios").insert(nuevo).execute()

    return {
        "mensaje": "Usuario creado exitosamente.",
        "usuario": {
            "id": res.data[0]["id"],
            "username": res.data[0]["username"],
            "personal_id": res.data[0]["personal_id"],
        },
    }


@router.delete("/{usuario_id}", summary="Eliminar cuenta de usuario")
def eliminar_usuario(usuario_id: int, current_user: dict = Depends(require_admin)):
    """
    Elimina una cuenta de usuario del sistema. 
    
    No elimina el registro de `personal` asociado (gracias a la FK con `ON DELETE SET NULL`).
    """
    # Verificar que el usuario existe
    res = (
        supabase.table("usuarios")
        .select("id, username")
        .eq("id", usuario_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró un usuario con ID {usuario_id}.",
        )

    # Evitar que el admin se elimine a sí mismo
    if str(usuario_id) == current_user.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes eliminar tu propia cuenta de usuario.",
        )

    supabase.table("usuarios").delete().eq("id", usuario_id).execute()

    return {"mensaje": f"Usuario '{res.data[0]['username']}' eliminado exitosamente."}
