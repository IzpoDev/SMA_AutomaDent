# routes/pacientes.py — CRUD de Pacientes
# ==============================================================================
# GET    /api/pacientes           → Listar pacientes (con búsqueda opcional)
# GET    /api/pacientes/{id}      → Detalle de un paciente
# POST   /api/pacientes           → Registrar nuevo paciente + historia clínica
# PUT    /api/pacientes/{id}      → Actualizar datos del paciente
# DELETE /api/pacientes/{id}      → Eliminar paciente
# ==============================================================================

from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel
from typing import Optional

from database import supabase
from routes.auth import require_staff

router = APIRouter(prefix="/api/pacientes", tags=["Pacientes"])


# ─── Schemas ─────────────────────────────────────────────────────────────────

class CrearPacienteRequest(BaseModel):
    nombre: str
    apellido: str
    telefono: str
    email: Optional[str] = None
    fecha_nacimiento: Optional[str] = None  # formato YYYY-MM-DD


class ActualizarPacienteRequest(BaseModel):
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    fecha_nacimiento: Optional[str] = None


# ==============================================================================
#  ENDPOINTS
# ==============================================================================

@router.get("/", summary="Listar pacientes")
def listar_pacientes(
    buscar: Optional[str] = Query(None, description="Buscar por nombre, apellido o teléfono"),
    limite: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_staff),
):
    """
    Retorna el listado de pacientes registrados en la clínica.
    Se puede filtrar con el parámetro `buscar` (nombre, apellido o teléfono).
    """
    query = supabase.table("pacientes").select(
        "id, nombre, apellido, telefono, email, fecha_nacimiento, fecha_registro"
    ).order("id", desc=True).limit(limite)

    res = query.execute()
    pacientes = res.data or []

    # Filtro de búsqueda local (Supabase ilike no soporta OR nativo en el SDK)
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
    """
    Retorna la información completa de un paciente por su ID.
    """
    res = (
        supabase.table("pacientes")
        .select("id, nombre, apellido, telefono, email, fecha_nacimiento, fecha_registro")
        .eq("id", paciente_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró un paciente con ID {paciente_id}.",
        )
    return res.data[0]


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Registrar nuevo paciente")
def crear_paciente(body: CrearPacienteRequest, current_user: dict = Depends(require_staff)):
    """
    Registra un nuevo paciente y crea automáticamente su historia clínica vacía.

    - El **telefono** se usa como identificador de Telegram (chat_id) para el bot.
    - El **email** y **fecha_nacimiento** son opcionales.
    """
    # Verificar que el teléfono no esté ya registrado
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
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El teléfono '{body.telefono}' ya pertenece al paciente '{p['nombre']} {p['apellido']}'.",
        )

    # Insertar el paciente
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
    nuevo_paciente = paciente_res.data[0]

    # Crear historia clínica vacía automáticamente
    supabase.table("historias_clinicas").insert(
        {"paciente_id": nuevo_paciente["id"]}
    ).execute()

    return {
        "mensaje": "Paciente registrado y historia clínica creada exitosamente.",
        "paciente": nuevo_paciente,
    }


@router.put("/{paciente_id}", summary="Actualizar datos del paciente")
def actualizar_paciente(
    paciente_id: int,
    body: ActualizarPacienteRequest,
    current_user: dict = Depends(require_staff),
):
    """
    Actualiza uno o más campos de la información de un paciente.
    Solo se actualizan los campos enviados; el resto se mantiene.
    """
    existe = (
        supabase.table("pacientes")
        .select("id")
        .eq("id", paciente_id)
        .limit(1)
        .execute()
    )
    if not existe.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró un paciente con ID {paciente_id}.",
        )

    campos = body.model_dump(exclude_none=True)
    if not campos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Debes enviar al menos un campo para actualizar.",
        )

    res = supabase.table("pacientes").update(campos).eq("id", paciente_id).execute()
    return {"mensaje": "Paciente actualizado exitosamente.", "paciente": res.data[0]}


@router.delete("/{paciente_id}", summary="Eliminar paciente")
def eliminar_paciente(paciente_id: int, current_user: dict = Depends(require_staff)):
    """
    Elimina un paciente de la base de datos.
    Su historia clínica se eliminará en cascada (por el `ON DELETE CASCADE` de la FK).
    """
    res = (
        supabase.table("pacientes")
        .select("id, nombre, apellido")
        .eq("id", paciente_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró un paciente con ID {paciente_id}.",
        )

    nombre = f"{res.data[0]['nombre']} {res.data[0]['apellido']}"
    supabase.table("pacientes").delete().eq("id", paciente_id).execute()
    return {"mensaje": f"Paciente '{nombre}' eliminado exitosamente."}
