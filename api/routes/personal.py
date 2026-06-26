# routes/personal.py — CRUD de Personal de la Clínica
# ==============================================================================
# GET    /api/personal           → Listar todo el personal
# GET    /api/personal/{id}      → Obtener un miembro específico
# POST   /api/personal           → Registrar nuevo personal (+ usuario opcional)
# PUT    /api/personal/{id}      → Actualizar datos del personal
# DELETE /api/personal/{id}      → Eliminar miembro del personal
# ==============================================================================

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional

from database import supabase
from auth import hash_password
from routes.auth import get_current_user, require_admin, require_staff

router = APIRouter(prefix="/api/personal", tags=["Personal"])


# ─── Schemas ─────────────────────────────────────────────────────────────────

class CrearUsuarioEmbebido(BaseModel):
    """Datos opcionales para crear la cuenta de acceso web junto al personal."""
    username: str
    password: str


class CrearPersonalRequest(BaseModel):
    nombre: str
    apellido: str
    rol: str  # 'odontologo' | 'recepcionista' | 'administrador'
    especialidad: Optional[str] = "General"
    telefono: Optional[str] = None
    crear_usuario: Optional[CrearUsuarioEmbebido] = None


class ActualizarPersonalRequest(BaseModel):
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    rol: Optional[str] = None
    especialidad: Optional[str] = None
    telefono: Optional[str] = None


# ==============================================================================
#  ENDPOINTS
# ==============================================================================

@router.get("/", summary="Listar personal")
def listar_personal(current_user: dict = Depends(require_staff)):
    """
    Retorna el listado completo del personal de la clínica (odontólogos, recepcionistas y administradores).
    Accesible para cualquier miembro del personal autenticado.
    """
    res = (
        supabase.table("personal")
        .select("id, nombre, apellido, rol, especialidad, telefono")
        .order("id")
        .execute()
    )
    return {"total": len(res.data or []), "personal": res.data or []}


@router.get("/{personal_id}", summary="Obtener miembro del personal")
def obtener_personal(personal_id: int, current_user: dict = Depends(require_staff)):
    """
    Retorna el detalle de un miembro del personal por su ID.
    """
    res = (
        supabase.table("personal")
        .select("id, nombre, apellido, rol, especialidad, telefono")
        .eq("id", personal_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró personal con ID {personal_id}.",
        )
    return res.data[0]


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Registrar nuevo personal")
def crear_personal(body: CrearPersonalRequest, current_user: dict = Depends(require_admin)):
    """
    Registra un nuevo miembro del personal en la clínica.

    - **crear_usuario** (opcional): Si se incluye, también se crea una cuenta de acceso web
      en la tabla `usuarios` vinculada automáticamente al personal registrado.
    - Los roles válidos son: `odontologo`, `recepcionista`, `administrador`.
    """
    roles_validos = {"odontologo", "recepcionista", "administrador"}
    if body.rol not in roles_validos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Rol inválido '{body.rol}'. Valores válidos: {', '.join(roles_validos)}.",
        )

    # 1. Verificar username único si se va a crear el usuario
    if body.crear_usuario:
        existe_username = (
            supabase.table("usuarios")
            .select("id")
            .eq("username", body.crear_usuario.username.strip())
            .limit(1)
            .execute()
        )
        if existe_username.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"El username '{body.crear_usuario.username}' ya está en uso.",
            )

    # 2. Insertar en personal
    datos_personal = {
        "nombre": body.nombre.strip().title(),
        "apellido": body.apellido.strip().title(),
        "rol": body.rol,
        "especialidad": body.especialidad.strip() if body.especialidad else "General",
        "telefono": body.telefono.strip() if body.telefono else None,
    }
    personal_res = supabase.table("personal").insert(datos_personal).execute()
    nuevo_personal = personal_res.data[0]
    personal_id = nuevo_personal["id"]

    # 3. Si se solicitó, crear el usuario vinculado
    usuario_creado = None
    if body.crear_usuario:
        usuario_datos = {
            "username": body.crear_usuario.username.strip(),
            "password_hash": hash_password(body.crear_usuario.password),
            "personal_id": personal_id,
        }
        usuario_res = supabase.table("usuarios").insert(usuario_datos).execute()
        usuario_creado = {
            "id": usuario_res.data[0]["id"],
            "username": usuario_res.data[0]["username"],
        }

    return {
        "mensaje": "Personal registrado exitosamente.",
        "personal": nuevo_personal,
        "usuario": usuario_creado,
    }


@router.put("/{personal_id}", summary="Actualizar datos del personal")
def actualizar_personal(
    personal_id: int,
    body: ActualizarPersonalRequest,
    current_user: dict = Depends(require_admin),
):
    """
    Actualiza uno o más campos del perfil de un miembro del personal.
    Solo se actualizan los campos que se envíen (los demás se mantienen).
    """
    # Verificar existencia
    existe = (
        supabase.table("personal")
        .select("id")
        .eq("id", personal_id)
        .limit(1)
        .execute()
    )
    if not existe.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró personal con ID {personal_id}.",
        )

    # Construir solo los campos a actualizar
    campos = body.model_dump(exclude_none=True)
    if not campos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Debes enviar al menos un campo para actualizar.",
        )

    if "rol" in campos and campos["rol"] not in {"odontologo", "recepcionista", "administrador"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Rol inválido '{campos['rol']}'.",
        )

    res = supabase.table("personal").update(campos).eq("id", personal_id).execute()
    return {"mensaje": "Personal actualizado exitosamente.", "personal": res.data[0]}


@router.delete("/{personal_id}", summary="Eliminar miembro del personal")
def eliminar_personal(personal_id: int, current_user: dict = Depends(require_admin)):
    """
    Elimina un miembro del personal de la base de datos.
    
    Si tenía una cuenta de usuario en `usuarios`, su `personal_id` quedará en `NULL`
    automáticamente (por la restricción `ON DELETE SET NULL` definida en la tabla).
    """
    res = (
        supabase.table("personal")
        .select("id, nombre, apellido")
        .eq("id", personal_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró personal con ID {personal_id}.",
        )

    nombre = f"{res.data[0]['nombre']} {res.data[0]['apellido']}"
    supabase.table("personal").delete().eq("id", personal_id).execute()

    return {"mensaje": f"Personal '{nombre}' eliminado exitosamente."}
