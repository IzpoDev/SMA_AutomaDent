# src/api/rutas/usuarios.py — CRUD de Cuentas de Usuario del Sistema
# ==============================================================================
# Migrado de api/routes/usuarios.py — imports actualizados.
# ==============================================================================

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel

from src.utils.database import supabase
from src.api.auth import hash_password
from src.api.rutas.auth import get_current_user, require_admin

router = APIRouter(prefix="/api/usuarios", tags=["Usuarios del Sistema"])


class CrearUsuarioRequest(BaseModel):
    username: str
    password: str
    personal_id: Optional[int] = None


@router.get("/", summary="Listar usuarios del sistema")
def listar_usuarios(current_user: dict = Depends(require_admin)):
    """Retorna el listado completo de cuentas de usuario. Solo Administradores."""
    res = supabase.table("usuarios").select("id, username, personal_id").order("id").execute()
    usuarios = res.data or []
    if usuarios:
        personal_ids = [u["personal_id"] for u in usuarios if u.get("personal_id")]
        if personal_ids:
            personal_res = supabase.table("personal").select("id, nombre, apellido, rol").in_("id", personal_ids).execute()
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


@router.post("/", status_code=201, summary="Crear cuenta de usuario")
def crear_usuario(body: CrearUsuarioRequest, current_user: dict = Depends(require_admin)):
    """Crea una nueva cuenta de acceso al sistema web."""
    if supabase.table("usuarios").select("id").eq("username", body.username.strip()).limit(1).execute().data:
        raise HTTPException(status_code=409, detail=f"Username '{body.username}' ya en uso.")

    personal_id = None
    if body.personal_id:
        if not supabase.table("personal").select("id").eq("id", body.personal_id).limit(1).execute().data:
            raise HTTPException(status_code=404, detail=f"Personal ID {body.personal_id} no encontrado.")
        personal_id = body.personal_id

    res = supabase.table("usuarios").insert({
        "username": body.username.strip(),
        "password_hash": hash_password(body.password),
        "personal_id": personal_id,
    }).execute()

    return {"mensaje": "Usuario creado.", "usuario": {
        "id": res.data[0]["id"],
        "username": res.data[0]["username"],
        "personal_id": res.data[0]["personal_id"],
    }}


@router.delete("/{usuario_id}", summary="Eliminar cuenta de usuario")
def eliminar_usuario(usuario_id: int, current_user: dict = Depends(require_admin)):
    """Elimina una cuenta de usuario del sistema."""
    res = supabase.table("usuarios").select("id, username").eq("id", usuario_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail=f"Usuario ID {usuario_id} no encontrado.")
    if str(usuario_id) == current_user.get("sub"):
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propia cuenta.")
    supabase.table("usuarios").delete().eq("id", usuario_id).execute()
    return {"mensaje": f"Usuario '{res.data[0]['username']}' eliminado."}
