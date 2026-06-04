# routes/pagos.py — CRUD de Pagos
# ==============================================================================
# GET    /api/pagos          → Listar todos los pagos (con filtros)
# POST   /api/pagos          → Registrar un pago para una cita asistida
# ==============================================================================

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel

from database import supabase
from routes.auth import require_staff

router = APIRouter(prefix="/api/pagos", tags=["Pagos"])
TIMEZONE = ZoneInfo("America/Lima")


# ─── Schemas ─────────────────────────────────────────────────────────────────

class RegistrarPagoRequest(BaseModel):
    cita_id: int
    monto: float
    metodo_pago: str  # efectivo | tarjeta | yape | plin


# ==============================================================================
#  ENDPOINTS
# ==============================================================================

@router.get("/", summary="Listar pagos")
def listar_pagos(
    estado_pago: Optional[str] = Query(None, description="Filtrar por estado: 'pagado' o 'pendiente'"),
    limite: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_staff),
):
    """
    Retorna el listado de transacciones financieras registradas.
    Incluye los datos enriquecidos de la cita (paciente y odontólogo).
    """
    query = supabase.table("pagos").select(
        "id, cita_id, monto, metodo_pago, estado_pago, fecha_pago"
    ).order("id", desc=True).limit(limite)

    if estado_pago:
        if estado_pago not in {"pagado", "pendiente", "fallido"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Estado de pago inválido. Usa: 'pagado', 'pendiente' o 'fallido'.",
            )
        query = query.eq("estado_pago", estado_pago)

    pagos = query.execute().data or []

    # Enriquecer con datos de la cita (paciente y odontólogo)
    if pagos:
        cita_ids = list({p["cita_id"] for p in pagos})
        citas_res = (
            supabase.table("citas")
            .select("id, paciente_id, odontologo_id, fecha_hora")
            .in_("id", cita_ids)
            .execute()
        )
        citas_map = {c["id"]: c for c in (citas_res.data or [])}

        pac_ids = list({c["paciente_id"] for c in (citas_res.data or [])})
        doc_ids = list({c["odontologo_id"] for c in (citas_res.data or [])})

        pac_map, doc_map = {}, {}
        if pac_ids:
            pacs = supabase.table("pacientes").select("id, nombre, apellido").in_("id", pac_ids).execute()
            pac_map = {p["id"]: f"{p['nombre']} {p['apellido']}" for p in (pacs.data or [])}
        if doc_ids:
            docs = supabase.table("personal").select("id, nombre, apellido").in_("id", doc_ids).execute()
            doc_map = {d["id"]: f"Dr(a). {d['nombre']} {d['apellido']}" for d in (docs.data or [])}

        for p in pagos:
            cita = citas_map.get(p["cita_id"], {})
            p["paciente_nombre"] = pac_map.get(cita.get("paciente_id"), "—")
            p["odontologo_nombre"] = doc_map.get(cita.get("odontologo_id"), "—")
            p["fecha_cita"] = cita.get("fecha_hora", "—")

    return {"total": len(pagos), "pagos": pagos}


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Registrar pago")
def registrar_pago(body: RegistrarPagoRequest, current_user: dict = Depends(require_staff)):
    """
    Registra el pago de una cita que se encuentra en estado `asistida`.

    - **cita_id**: ID de la cita a pagar (debe estar en estado `asistida`).
    - **monto**: Monto en Soles (S/).
    - **metodo_pago**: Método utilizado (`efectivo`, `tarjeta`, `yape`, `plin`).
    """
    metodos_validos = {"efectivo", "tarjeta", "yape", "plin"}
    if body.metodo_pago not in metodos_validos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Método de pago inválido. Usa: {', '.join(metodos_validos)}.",
        )

    if body.monto <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El monto debe ser mayor a 0.",
        )

    # Verificar que la cita existe y está en estado asistida
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
            detail=f"Solo se pueden registrar pagos para citas en estado 'asistida'. Estado actual: '{cita_res.data[0]['estado']}'.",
        )

    # Verificar que no exista ya un pago para esta cita
    pago_existente = (
        supabase.table("pagos")
        .select("id")
        .eq("cita_id", body.cita_id)
        .limit(1)
        .execute()
    )
    if pago_existente.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un pago registrado para la cita #{body.cita_id}.",
        )

    # Registrar el pago
    nuevo_pago = supabase.table("pagos").insert({
        "cita_id": body.cita_id,
        "monto": body.monto,
        "metodo_pago": body.metodo_pago,
        "estado_pago": "pagado",
        "fecha_pago": datetime.now(TIMEZONE).isoformat(),
    }).execute()

    return {
        "mensaje": f"Pago de S/ {body.monto:.2f} registrado exitosamente para la cita #{body.cita_id}.",
        "pago": nuevo_pago.data[0],
    }
