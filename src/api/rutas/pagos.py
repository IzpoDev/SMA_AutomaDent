# src/api/rutas/pagos.py — CRUD de Pagos
# ==============================================================================
# Migrado de api/routes/pagos.py — imports actualizados.
# ==============================================================================

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel

from src.utils.database import supabase
from src.utils.config import TIMEZONE
from src.api.rutas.auth import require_staff

router = APIRouter(prefix="/api/pagos", tags=["Pagos"])


class RegistrarPagoRequest(BaseModel):
    cita_id: int
    monto: float
    metodo_pago: str


@router.get("/", summary="Listar pagos")
def listar_pagos(
    estado_pago: Optional[str] = Query(None),
    limite: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_staff),
):
    """Retorna el listado de transacciones con datos enriquecidos de cita."""
    query = (
        supabase.table("pagos")
        .select("id, cita_id, monto, metodo_pago, estado_pago, fecha_pago")
        .order("id", desc=True)
        .limit(limite)
    )
    if estado_pago:
        if estado_pago not in {"pagado", "pendiente", "fallido"}:
            raise HTTPException(status_code=422, detail="Estado inválido.")
        query = query.eq("estado_pago", estado_pago)

    pagos = query.execute().data or []
    if pagos:
        cita_ids = list({p["cita_id"] for p in pagos})
        citas = supabase.table("citas").select("id, paciente_id, odontologo_id, fecha_hora").in_("id", cita_ids).execute()
        citas_map = {c["id"]: c for c in (citas.data or [])}
        pac_ids = list({c["paciente_id"] for c in (citas.data or [])})
        doc_ids = list({c["odontologo_id"] for c in (citas.data or [])})
        pac_map = {p["id"]: f"{p['nombre']} {p['apellido']}" for p in
                   (supabase.table("pacientes").select("id, nombre, apellido").in_("id", pac_ids).execute().data or [])}
        doc_map = {d["id"]: f"Dr(a). {d['nombre']} {d['apellido']}" for d in
                   (supabase.table("personal").select("id, nombre, apellido").in_("id", doc_ids).execute().data or [])}
        for p in pagos:
            cita = citas_map.get(p["cita_id"], {})
            p["paciente_nombre"] = pac_map.get(cita.get("paciente_id"), "—")
            p["odontologo_nombre"] = doc_map.get(cita.get("odontologo_id"), "—")
            p["fecha_cita"] = cita.get("fecha_hora", "—")

    return {"total": len(pagos), "pagos": pagos}


@router.post("/", status_code=201, summary="Registrar pago")
def registrar_pago(body: RegistrarPagoRequest, current_user: dict = Depends(require_staff)):
    """Registra el pago de una cita en estado 'asistida'."""
    if body.metodo_pago not in {"efectivo", "tarjeta", "yape", "plin"}:
        raise HTTPException(status_code=422, detail="Método de pago inválido.")
    if body.monto <= 0:
        raise HTTPException(status_code=422, detail="El monto debe ser mayor a 0.")

    cita = supabase.table("citas").select("id, estado").eq("id", body.cita_id).limit(1).execute()
    if not cita.data:
        raise HTTPException(status_code=404, detail=f"Cita #{body.cita_id} no encontrada.")
    if cita.data[0]["estado"] != "asistida":
        raise HTTPException(status_code=422, detail="La cita debe estar en estado 'asistida'.")
    if supabase.table("pagos").select("id").eq("cita_id", body.cita_id).limit(1).execute().data:
        raise HTTPException(status_code=409, detail=f"Ya existe un pago para la cita #{body.cita_id}.")

    nuevo = supabase.table("pagos").insert({
        "cita_id": body.cita_id,
        "monto": body.monto,
        "metodo_pago": body.metodo_pago,
        "estado_pago": "pagado",
        "fecha_pago": datetime.now(TIMEZONE).isoformat(),
    }).execute()

    return {"mensaje": f"Pago de S/ {body.monto:.2f} registrado para cita #{body.cita_id}.", "pago": nuevo.data[0]}
