# src/api/rutas/personal.py — CRUD de Personal de la Clínica
# ==============================================================================
# Migrado de api/routes/personal.py — imports actualizados.
# ==============================================================================

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel

from src.utils.database import supabase
from src.api.auth import hash_password
from src.api.rutas.auth import get_current_user, require_admin, require_staff

router = APIRouter(prefix="/api/personal", tags=["Personal"])


class CrearUsuarioEmbebido(BaseModel):
    username: str
    password: str


class CrearPersonalRequest(BaseModel):
    nombre: str
    apellido: str
    rol: str
    especialidad: Optional[str] = "General"
    telefono: Optional[str] = None
    crear_usuario: Optional[CrearUsuarioEmbebido] = None


class ActualizarPersonalRequest(BaseModel):
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    rol: Optional[str] = None
    especialidad: Optional[str] = None
    telefono: Optional[str] = None


@router.get("/", summary="Listar personal")
def listar_personal(current_user: dict = Depends(require_staff)):
    """Retorna el listado completo del personal de la clínica."""
    res = (
        supabase.table("personal")
        .select("id, nombre, apellido, rol, especialidad, telefono")
        .order("id")
        .execute()
    )
    return {"total": len(res.data or []), "personal": res.data or []}


@router.get("/{personal_id}", summary="Obtener miembro del personal")
def obtener_personal(personal_id: int, current_user: dict = Depends(require_staff)):
    """Retorna el detalle de un miembro del personal por su ID."""
    res = (
        supabase.table("personal")
        .select("id, nombre, apellido, rol, especialidad, telefono")
        .eq("id", personal_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail=f"Personal ID {personal_id} no encontrado.")
    return res.data[0]


@router.post("/", status_code=201, summary="Registrar nuevo personal")
def crear_personal(body: CrearPersonalRequest, current_user: dict = Depends(require_admin)):
    """Registra un nuevo miembro del personal, opcionalmente crea cuenta de acceso web."""
    roles_validos = {"odontologo", "recepcionista", "administrador"}
    if body.rol not in roles_validos:
        raise HTTPException(status_code=422, detail=f"Rol inválido '{body.rol}'.")

    if body.crear_usuario:
        existe = (
            supabase.table("usuarios")
            .select("id")
            .eq("username", body.crear_usuario.username.strip())
            .limit(1)
            .execute()
        )
        if existe.data:
            raise HTTPException(status_code=409, detail=f"Username '{body.crear_usuario.username}' en uso.")

    datos = {
        "nombre": body.nombre.strip().title(),
        "apellido": body.apellido.strip().title(),
        "rol": body.rol,
        "especialidad": body.especialidad.strip() if body.especialidad else "General",
        "telefono": body.telefono.strip() if body.telefono else None,
    }
    personal_res = supabase.table("personal").insert(datos).execute()
    nuevo = personal_res.data[0]

    usuario_creado = None
    if body.crear_usuario:
        u_res = supabase.table("usuarios").insert({
            "username": body.crear_usuario.username.strip(),
            "password_hash": hash_password(body.crear_usuario.password),
            "personal_id": nuevo["id"],
        }).execute()
        usuario_creado = {"id": u_res.data[0]["id"], "username": u_res.data[0]["username"]}

    return {"mensaje": "Personal registrado.", "personal": nuevo, "usuario": usuario_creado}


@router.put("/{personal_id}", summary="Actualizar datos del personal")
def actualizar_personal(
    personal_id: int,
    body: ActualizarPersonalRequest,
    current_user: dict = Depends(require_admin),
):
    """Actualiza campos del perfil de un miembro del personal."""
    if not supabase.table("personal").select("id").eq("id", personal_id).limit(1).execute().data:
        raise HTTPException(status_code=404, detail=f"Personal ID {personal_id} no encontrado.")

    campos = body.model_dump(exclude_none=True)
    if not campos:
        raise HTTPException(status_code=422, detail="Envía al menos un campo.")

    if "rol" in campos and campos["rol"] not in {"odontologo", "recepcionista", "administrador"}:
        raise HTTPException(status_code=422, detail=f"Rol inválido '{campos['rol']}'.")

    res = supabase.table("personal").update(campos).eq("id", personal_id).execute()
    return {"mensaje": "Personal actualizado.", "personal": res.data[0]}


@router.delete("/{personal_id}", summary="Eliminar miembro del personal")
def eliminar_personal(personal_id: int, current_user: dict = Depends(require_admin)):
    """Elimina un miembro del personal de la base de datos."""
    res = supabase.table("personal").select("id, nombre, apellido").eq("id", personal_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail=f"Personal ID {personal_id} no encontrado.")
    nombre = f"{res.data[0]['nombre']} {res.data[0]['apellido']}"
    supabase.table("personal").delete().eq("id", personal_id).execute()
    return {"mensaje": f"Personal '{nombre}' eliminado."}
