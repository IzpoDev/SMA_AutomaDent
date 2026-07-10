# src/api/rutas/pacientes.py — CRUD de Pacientes
# ==============================================================================
# Migrado de api/routes/pacientes.py — imports actualizados.
# ==============================================================================

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel

from src.utils.database import supabase
from src.api.rutas.auth import require_staff

router = APIRouter(prefix="/api/pacientes", tags=["Pacientes"])


class CrearPacienteRequest(BaseModel):
    nombre: str
    apellido: str
    telefono: str
    email: Optional[str] = None
    fecha_nacimiento: Optional[str] = None


class ActualizarPacienteRequest(BaseModel):
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    fecha_nacimiento: Optional[str] = None


@router.get("/", summary="Listar pacientes")
def listar_pacientes(
    buscar: Optional[str] = Query(None),
    limite: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_staff),
):
    """Retorna el listado de pacientes registrados con búsqueda opcional."""
    res = (
        supabase.table("pacientes")
        .select("id, nombre, apellido, telefono, email, fecha_nacimiento, fecha_registro")
        .order("id", desc=True)
        .limit(limite)
        .execute()
    )
    pacientes = res.data or []
    if buscar and pacientes:
        termino = buscar.lower()
        pacientes = [
            p for p in pacientes
            if termino in p.get("nombre", "").lower()
            or termino in p.get("apellido", "").lower()
            or termino in (p.get("telefono") or "").lower()
        ]
    return {"total": len(pacientes), "pacientes": pacientes}


@router.get("/{paciente_id}", summary="Detalle de un paciente")
def obtener_paciente(paciente_id: int, current_user: dict = Depends(require_staff)):
    """Retorna la información completa de un paciente por su ID."""
    res = (
        supabase.table("pacientes")
        .select("id, nombre, apellido, telefono, email, fecha_nacimiento, fecha_registro")
        .eq("id", paciente_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail=f"Paciente ID {paciente_id} no encontrado.")
    return res.data[0]


@router.post("/", status_code=201, summary="Registrar nuevo paciente")
def crear_paciente(body: CrearPacienteRequest, current_user: dict = Depends(require_staff)):
    """Registra un nuevo paciente y crea automáticamente su historia clínica vacía."""
    existente = (
        supabase.table("pacientes")
        .select("id, nombre, apellido")
        .eq("telefono", body.telefono.strip())
        .limit(1)
        .execute()
    )
    if existente.data:
        p = existente.data[0]
        raise HTTPException(
            status_code=409,
            detail=f"El teléfono '{body.telefono}' ya pertenece a '{p['nombre']} {p['apellido']}'.",
        )

    datos = {
        "nombre": body.nombre.strip().title(),
        "apellido": body.apellido.strip().title(),
        "telefono": body.telefono.strip(),
    }
    if body.email:
        datos["email"] = body.email.strip().lower()
    if body.fecha_nacimiento:
        datos["fecha_nacimiento"] = body.fecha_nacimiento

    paciente_res = supabase.table("pacientes").insert(datos).execute()
    nuevo = paciente_res.data[0]
    supabase.table("historias_clinicas").insert({"paciente_id": nuevo["id"]}).execute()

    return {"mensaje": "Paciente registrado y historia clínica creada.", "paciente": nuevo}


@router.put("/{paciente_id}", summary="Actualizar datos del paciente")
def actualizar_paciente(
    paciente_id: int,
    body: ActualizarPacienteRequest,
    current_user: dict = Depends(require_staff),
):
    """Actualiza campos de un paciente existente."""
    if not supabase.table("pacientes").select("id").eq("id", paciente_id).limit(1).execute().data:
        raise HTTPException(status_code=404, detail=f"Paciente ID {paciente_id} no encontrado.")

    campos = body.model_dump(exclude_none=True)
    if not campos:
        raise HTTPException(status_code=422, detail="Envía al menos un campo.")

    res = supabase.table("pacientes").update(campos).eq("id", paciente_id).execute()
    return {"mensaje": "Paciente actualizado.", "paciente": res.data[0]}


@router.delete("/{paciente_id}", summary="Eliminar paciente")
def eliminar_paciente(paciente_id: int, current_user: dict = Depends(require_staff)):
    """Elimina un paciente (su historia clínica se elimina en cascada)."""
    res = supabase.table("pacientes").select("id, nombre, apellido").eq("id", paciente_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail=f"Paciente ID {paciente_id} no encontrado.")
    nombre = f"{res.data[0]['nombre']} {res.data[0]['apellido']}"
    supabase.table("pacientes").delete().eq("id", paciente_id).execute()
    return {"mensaje": f"Paciente '{nombre}' eliminado."}
