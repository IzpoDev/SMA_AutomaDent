# src/api/rutas/historias.py — Historias Clínicas y Evoluciones Médicas
# ==============================================================================
# Migrado de api/routes/historias.py — imports actualizados.
# ==============================================================================

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel

from src.utils.database import supabase
from src.api.rutas.auth import require_staff

router = APIRouter(prefix="/api/historias", tags=["Historias Clínicas"])


class ActualizarAntecedentesRequest(BaseModel):
    antecedentes_medicos: str


class RegistrarAtencionRequest(BaseModel):
    cita_id: int
    diagnostico: str
    tratamiento_realizado: str
    observaciones: Optional[str] = None


@router.get("/{paciente_id}", summary="Obtener historia clínica completa")
def obtener_historia(paciente_id: int, current_user: dict = Depends(require_staff)):
    """Retorna historia clínica completa de un paciente con sus atenciones."""
    pac_res = (
        supabase.table("pacientes")
        .select("id, nombre, apellido, telefono, email, fecha_nacimiento, fecha_registro")
        .eq("id", paciente_id).limit(1).execute()
    )
    if not pac_res.data:
        raise HTTPException(status_code=404, detail=f"Paciente ID {paciente_id} no encontrado.")

    historia_res = (
        supabase.table("historias_clinicas")
        .select("id, antecedentes_medicos, fecha_creacion")
        .eq("paciente_id", paciente_id).limit(1).execute()
    )
    if not historia_res.data:
        raise HTTPException(status_code=404, detail=f"Paciente ID {paciente_id} sin historia clínica.")

    historia = historia_res.data[0]
    atenciones = (
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
        "atenciones": atenciones.data or [],
    }


@router.put("/{paciente_id}/antecedentes", summary="Actualizar antecedentes médicos")
def actualizar_antecedentes(
    paciente_id: int,
    body: ActualizarAntecedentesRequest,
    current_user: dict = Depends(require_staff),
):
    """Actualiza los antecedentes médicos de un paciente."""
    historia = (
        supabase.table("historias_clinicas")
        .select("id").eq("paciente_id", paciente_id).limit(1).execute()
    )
    if not historia.data:
        raise HTTPException(status_code=404, detail=f"Historia clínica de paciente ID {paciente_id} no encontrada.")

    historia_id = historia.data[0]["id"]
    res = (
        supabase.table("historias_clinicas")
        .update({"antecedentes_medicos": body.antecedentes_medicos.strip()})
        .eq("id", historia_id).execute()
    )
    return {"mensaje": "Antecedentes actualizados.", "historia_id": historia_id,
            "antecedentes_medicos": res.data[0]["antecedentes_medicos"]}


@router.post("/atenciones", status_code=201, summary="Registrar atención médica")
def registrar_atencion(body: RegistrarAtencionRequest, current_user: dict = Depends(require_staff)):
    """Registra una nueva evolución clínica. La cita debe estar en estado 'asistida'."""
    cita_res = (
        supabase.table("citas")
        .select("id, estado, paciente_id").eq("id", body.cita_id).limit(1).execute()
    )
    if not cita_res.data:
        raise HTTPException(status_code=404, detail=f"Cita #{body.cita_id} no encontrada.")
    if cita_res.data[0]["estado"] != "asistida":
        raise HTTPException(status_code=422, detail=f"Cita #{body.cita_id} debe estar en estado 'asistida'.")

    historia = (
        supabase.table("historias_clinicas")
        .select("id").eq("paciente_id", cita_res.data[0]["paciente_id"]).limit(1).execute()
    )
    if not historia.data:
        raise HTTPException(status_code=404, detail="Paciente sin historia clínica.")

    if supabase.table("atenciones_medicas").select("id").eq("cita_id", body.cita_id).limit(1).execute().data:
        raise HTTPException(status_code=409, detail=f"Ya existe evolución para cita #{body.cita_id}.")

    res = supabase.table("atenciones_medicas").insert({
        "historia_id": historia.data[0]["id"],
        "cita_id": body.cita_id,
        "diagnostico": body.diagnostico.strip(),
        "tratamiento_realizado": body.tratamiento_realizado.strip(),
        "observaciones": body.observaciones.strip() if body.observaciones else None,
    }).execute()

    return {"mensaje": f"Atención registrada para cita #{body.cita_id}.", "atencion": res.data[0]}
