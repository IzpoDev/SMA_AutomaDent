# routes/historias.py — Historias Clínicas y Evoluciones Médicas
# ==============================================================================
# GET  /api/historias/{paciente_id}              → Historia clínica completa
# PUT  /api/historias/{paciente_id}/antecedentes → Actualizar antecedentes médicos
# POST /api/historias/atenciones                 → Registrar nueva atención/evolución
# ==============================================================================

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional

from database import supabase
from routes.auth import require_staff

router = APIRouter(prefix="/api/historias", tags=["Historias Clínicas"])


# ─── Schemas ─────────────────────────────────────────────────────────────────

class ActualizarAntecedentesRequest(BaseModel):
    antecedentes_medicos: str


class RegistrarAtencionRequest(BaseModel):
    cita_id: int
    diagnostico: str
    tratamiento_realizado: str
    observaciones: Optional[str] = None


# ==============================================================================
#  ENDPOINTS
# ==============================================================================

@router.get("/{paciente_id}", summary="Obtener historia clínica completa")
def obtener_historia(paciente_id: int, current_user: dict = Depends(require_staff)):
    """
    Retorna la historia clínica de un paciente, incluyendo:
    - Datos personales del paciente.
    - Antecedentes médicos generales.
    - Lista cronológica de atenciones clínicas (evoluciones).
    """
    # Verificar que el paciente existe
    pac_res = (
        supabase.table("pacientes")
        .select("id, nombre, apellido, telefono, email, fecha_nacimiento, fecha_registro")
        .eq("id", paciente_id)
        .limit(1)
        .execute()
    )
    if not pac_res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró un paciente con ID {paciente_id}.",
        )

    # Obtener la historia clínica
    historia_res = (
        supabase.table("historias_clinicas")
        .select("id, antecedentes_medicos, fecha_creacion")
        .eq("paciente_id", paciente_id)
        .limit(1)
        .execute()
    )
    if not historia_res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El paciente ID {paciente_id} no tiene historia clínica registrada.",
        )

    historia = historia_res.data[0]

    # Obtener las atenciones médicas
    atenciones_res = (
        supabase.table("atenciones_medicas")
        .select("id, cita_id, diagnostico, tratamiento_realizado, observaciones, fecha_atencion")
        .eq("historia_id", historia["id"])
        .order("fecha_atencion", desc=True)
        .execute()
    )

    return {
        "paciente": pac_res.data[0],
        "historia": {
            "id": historia["id"],
            "antecedentes_medicos": historia.get("antecedentes_medicos") or "",
            "fecha_creacion": historia["fecha_creacion"],
        },
        "atenciones": atenciones_res.data or [],
    }


@router.put("/{paciente_id}/antecedentes", summary="Actualizar antecedentes médicos")
def actualizar_antecedentes(
    paciente_id: int,
    body: ActualizarAntecedentesRequest,
    current_user: dict = Depends(require_staff),
):
    """
    Actualiza los antecedentes médicos generales de un paciente
    (alergias, enfermedades crónicas, medicamentos, etc.).
    """
    historia_res = (
        supabase.table("historias_clinicas")
        .select("id")
        .eq("paciente_id", paciente_id)
        .limit(1)
        .execute()
    )
    if not historia_res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró historia clínica para el paciente ID {paciente_id}.",
        )

    historia_id = historia_res.data[0]["id"]
    res = (
        supabase.table("historias_clinicas")
        .update({"antecedentes_medicos": body.antecedentes_medicos.strip()})
        .eq("id", historia_id)
        .execute()
    )
    return {
        "mensaje": "Antecedentes médicos actualizados exitosamente.",
        "historia_id": historia_id,
        "antecedentes_medicos": res.data[0]["antecedentes_medicos"],
    }


@router.post("/atenciones", status_code=status.HTTP_201_CREATED, summary="Registrar atención médica")
def registrar_atencion(body: RegistrarAtencionRequest, current_user: dict = Depends(require_staff)):
    """
    Registra una nueva evolución/atención clínica en la historia del paciente.

    La **cita** debe estar en estado `asistida` para poder registrar la evolución.
    Los roles permitidos son: `odontologo`, `recepcionista`, `administrador`.
    """
    # Verificar que la cita exista y esté en estado asistida
    cita_res = (
        supabase.table("citas")
        .select("id, estado, paciente_id")
        .eq("id", body.cita_id)
        .limit(1)
        .execute()
    )
    if not cita_res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró la cita #{body.cita_id}.",
        )
    if cita_res.data[0]["estado"] != "asistida":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"La cita #{body.cita_id} debe estar en estado 'asistida' para registrar la evolución.",
        )

    paciente_id = cita_res.data[0]["paciente_id"]

    # Obtener la historia clínica del paciente
    historia_res = (
        supabase.table("historias_clinicas")
        .select("id")
        .eq("paciente_id", paciente_id)
        .limit(1)
        .execute()
    )
    if not historia_res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El paciente no tiene historia clínica registrada.",
        )

    # Verificar que no exista ya una evolución para esta cita
    duplicado = (
        supabase.table("atenciones_medicas")
        .select("id")
        .eq("cita_id", body.cita_id)
        .limit(1)
        .execute()
    )
    if duplicado.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe una evolución médica registrada para la cita #{body.cita_id}.",
        )

    historia_id = historia_res.data[0]["id"]
    datos_atencion = {
        "historia_id": historia_id,
        "cita_id": body.cita_id,
        "diagnostico": body.diagnostico.strip(),
        "tratamiento_realizado": body.tratamiento_realizado.strip(),
        "observaciones": body.observaciones.strip() if body.observaciones else None,
    }
    res = supabase.table("atenciones_medicas").insert(datos_atencion).execute()

    return {
        "mensaje": f"Atención médica registrada exitosamente para la cita #{body.cita_id}.",
        "atencion": res.data[0],
    }
