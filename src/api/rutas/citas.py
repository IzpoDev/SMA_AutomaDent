# src/api/rutas/citas.py — CRUD de Citas
# ==============================================================================
# GET    /api/citas                   → Listar citas con filtros
# GET    /api/citas/disponibilidad    → Consultar horarios libres
# POST   /api/citas                   → Crear nueva cita
# PUT    /api/citas/{id}/estado       → Cambiar estado de la cita
# PUT    /api/citas/{id}              → Actualizar datos de la cita
# DELETE /api/citas/{id}              → Eliminar cita
# ==============================================================================

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel

from src.utils.database import supabase
from src.utils.config import TIMEZONE, DURACION_CITA_MIN, HORARIO_INICIO, HORARIO_FIN, DIAS_LABORALES
from src.utils.notificaciones import notificar_odontologo, notificar_cambio_estado_cita
from src.api.rutas.auth import require_staff

router = APIRouter(prefix="/api/citas", tags=["Citas"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class CrearCitaRequest(BaseModel):
    paciente_id: int
    odontologo_id: int
    fecha_hora: str
    motivo_consulta: Optional[str] = None


class ActualizarCitaRequest(BaseModel):
    odontologo_id: Optional[int] = None
    fecha_hora: Optional[str] = None
    motivo_consulta: Optional[str] = None


class CambiarEstadoRequest(BaseModel):
    nuevo_estado: str


# ==============================================================================
#  ENDPOINTS
# ==============================================================================

@router.get("/disponibilidad", summary="Consultar disponibilidad de agenda")
def consultar_disponibilidad(
    fecha: str = Query(..., description="Fecha en formato YYYY-MM-DD"),
    odontologo_id: Optional[int] = Query(None),
    especialidad: Optional[str] = Query(None),
    current_user: dict = Depends(require_staff),
):
    """Consulta los horarios libres disponibles para una fecha específica."""
    try:
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Formato de fecha inválido. Usa YYYY-MM-DD.",
        )

    hoy = datetime.now(TIMEZONE).date()
    if fecha_obj < hoy:
        raise HTTPException(status_code=422, detail="No puedes consultar fechas pasadas.")
    if fecha_obj.weekday() not in DIAS_LABORALES:
        raise HTTPException(status_code=422, detail="La clínica no atiende los domingos.")

    query = supabase.table("personal").select("id, nombre, apellido, especialidad").eq("rol", "odontologo")
    if odontologo_id:
        query = query.eq("id", odontologo_id)
    if especialidad:
        query = query.ilike("especialidad", f"%{especialidad}%")
    odont_res = query.execute()

    if not odont_res.data:
        raise HTTPException(status_code=404, detail="No se encontraron odontólogos.")

    inicio_dia = datetime(fecha_obj.year, fecha_obj.month, fecha_obj.day, 0, 0, 0, tzinfo=TIMEZONE).isoformat()
    fin_dia = datetime(fecha_obj.year, fecha_obj.month, fecha_obj.day, 23, 59, 59, tzinfo=TIMEZONE).isoformat()
    citas_res = (
        supabase.table("citas")
        .select("odontologo_id, fecha_hora")
        .gte("fecha_hora", inicio_dia)
        .lte("fecha_hora", fin_dia)
        .in_("estado", ["programada", "confirmada"])
        .execute()
    )

    ocupados: dict = {}
    for c in (citas_res.data or []):
        hora = datetime.fromisoformat(c["fecha_hora"]).strftime("%H:%M")
        ocupados.setdefault(c["odontologo_id"], set()).add(hora)

    hora_actual = datetime.now(TIMEZONE) if fecha_obj == hoy else None
    resultado = []
    for doc in odont_res.data:
        slots = []
        for h in range(HORARIO_INICIO, HORARIO_FIN):
            for m in range(0, 60, DURACION_CITA_MIN):
                slot_str = f"{h:02d}:{m:02d}"
                if hora_actual:
                    slot_dt = datetime(fecha_obj.year, fecha_obj.month, fecha_obj.day, h, m, tzinfo=TIMEZONE)
                    if slot_dt <= hora_actual:
                        continue
                if slot_str in ocupados.get(doc["id"], set()):
                    continue
                slots.append(slot_str)
        resultado.append({
            "odontologo_id": doc["id"],
            "nombre": f"Dr(a). {doc['nombre']} {doc['apellido']}",
            "especialidad": doc["especialidad"],
            "slots_disponibles": slots,
        })
    return {"fecha": fecha, "disponibilidad": resultado}


@router.get("/", summary="Listar citas")
def listar_citas(
    fecha: Optional[str] = Query(None),
    estado: Optional[str] = Query(None),
    odontologo_id: Optional[int] = Query(None),
    paciente_id: Optional[int] = Query(None),
    limite: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_staff),
):
    """Retorna el listado de citas con filtros opcionales."""
    query = supabase.table("citas").select(
        "id, fecha_hora, estado, motivo_consulta, paciente_id, odontologo_id, created_at"
    ).order("fecha_hora").limit(limite)

    if estado:
        if estado not in {"programada", "confirmada", "asistida", "cancelada", "no_show"}:
            raise HTTPException(status_code=422, detail="Estado inválido.")
        query = query.eq("estado", estado)
    if odontologo_id:
        query = query.eq("odontologo_id", odontologo_id)
    if paciente_id:
        query = query.eq("paciente_id", paciente_id)
    if fecha:
        try:
            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
            inicio = datetime(fecha_obj.year, fecha_obj.month, fecha_obj.day, 0, 0, 0, tzinfo=TIMEZONE).isoformat()
            fin = datetime(fecha_obj.year, fecha_obj.month, fecha_obj.day, 23, 59, 59, tzinfo=TIMEZONE).isoformat()
            query = query.gte("fecha_hora", inicio).lte("fecha_hora", fin)
        except ValueError:
            raise HTTPException(status_code=422, detail="Formato de fecha inválido.")

    citas = query.execute().data or []
    if citas:
        pac_ids = list({c["paciente_id"] for c in citas})
        doc_ids = list({c["odontologo_id"] for c in citas})
        pac_map = {p["id"]: f"{p['nombre']} {p['apellido']}" for p in
                   (supabase.table("pacientes").select("id, nombre, apellido").in_("id", pac_ids).execute().data or [])}
        doc_map = {d["id"]: f"Dr(a). {d['nombre']} {d['apellido']}" for d in
                   (supabase.table("personal").select("id, nombre, apellido").in_("id", doc_ids).execute().data or [])}
        for c in citas:
            c["paciente_nombre"] = pac_map.get(c["paciente_id"], "—")
            c["odontologo_nombre"] = doc_map.get(c["odontologo_id"], "—")

    return {"total": len(citas), "citas": citas}


@router.post("/", status_code=201, summary="Crear nueva cita")
def crear_cita(body: CrearCitaRequest, current_user: dict = Depends(require_staff)):
    """Agenda una nueva cita para un paciente con un odontólogo."""
    pac = supabase.table("pacientes").select("id, nombre, apellido").eq("id", body.paciente_id).limit(1).execute()
    if not pac.data:
        raise HTTPException(status_code=404, detail=f"Paciente ID {body.paciente_id} no encontrado.")

    doc = supabase.table("personal").select("id, nombre, apellido").eq("id", body.odontologo_id).eq("rol", "odontologo").limit(1).execute()
    if not doc.data:
        raise HTTPException(status_code=404, detail=f"Odontólogo ID {body.odontologo_id} no encontrado.")

    try:
        dt = datetime.fromisoformat(body.fecha_hora).replace(tzinfo=TIMEZONE)
    except ValueError:
        raise HTTPException(status_code=422, detail="Formato de fecha inválido. Usa YYYY-MM-DDTHH:MM.")

    if dt <= datetime.now(TIMEZONE):
        raise HTTPException(status_code=422, detail="No puedes agendar en el pasado.")

    ocupado = (
        supabase.table("citas").select("id")
        .eq("odontologo_id", body.odontologo_id)
        .eq("fecha_hora", dt.isoformat())
        .in_("estado", ["programada", "confirmada"])
        .limit(1).execute()
    )
    if ocupado.data:
        raise HTTPException(status_code=409, detail="El horario ya está ocupado para ese odontólogo.")

    nueva = supabase.table("citas").insert({
        "paciente_id": body.paciente_id,
        "odontologo_id": body.odontologo_id,
        "fecha_hora": dt.isoformat(),
        "estado": "programada",
        "motivo_consulta": body.motivo_consulta.strip() if body.motivo_consulta else None,
    }).execute()

    cita = nueva.data[0]
    pac_nombre = f"{pac.data[0]['nombre']} {pac.data[0]['apellido']}"
    doc_nombre = f"Dr(a). {doc.data[0]['nombre']} {doc.data[0]['apellido']}"

    notificar_odontologo(
        supabase, body.odontologo_id,
        f"🔔 <b>Nueva Cita Asignada</b>\n\n"
        f"📅 {dt.strftime('%d/%m/%Y')} a las {dt.strftime('%H:%M')}\n"
        f"👤 Paciente: <b>{pac_nombre}</b>\n"
        f"📝 Motivo: {body.motivo_consulta or 'No especificado'}\n"
        f"🆔 Cita #{cita['id']}",
    )
    return {"mensaje": "Cita agendada.", "cita": {**cita, "paciente_nombre": pac_nombre, "odontologo_nombre": doc_nombre}}


@router.put("/{cita_id}/estado", summary="Cambiar estado de la cita")
def cambiar_estado(cita_id: int, body: CambiarEstadoRequest, current_user: dict = Depends(require_staff)):
    """Actualiza el estado de una cita y notifica al paciente."""
    nuevo_estado = body.nuevo_estado
    if nuevo_estado == "atendida":
        nuevo_estado = "asistida"
    if nuevo_estado not in {"programada", "confirmada", "asistida", "cancelada", "no_show"}:
        raise HTTPException(status_code=422, detail="Estado inválido.")

    cita = supabase.table("citas").select("id, estado, paciente_id").eq("id", cita_id).limit(1).execute()
    if not cita.data:
        raise HTTPException(status_code=404, detail=f"Cita #{cita_id} no encontrada.")

    estado_anterior = cita.data[0]["estado"]
    supabase.table("citas").update({"estado": nuevo_estado}).eq("id", cita_id).execute()

    notificar_cambio_estado_cita(supabase, cita_id, cita.data[0]["paciente_id"], nuevo_estado)

    return {"mensaje": f"Estado de cita #{cita_id} actualizado.", "estado_anterior": estado_anterior, "estado_nuevo": nuevo_estado}


@router.put("/{cita_id}", summary="Actualizar datos de la cita")
def actualizar_cita(cita_id: int, body: ActualizarCitaRequest, current_user: dict = Depends(require_staff)):
    """Actualiza campos de una cita existente."""
    if not supabase.table("citas").select("id").eq("id", cita_id).limit(1).execute().data:
        raise HTTPException(status_code=404, detail=f"Cita #{cita_id} no encontrada.")

    campos = body.model_dump(exclude_none=True)
    if not campos:
        raise HTTPException(status_code=422, detail="Envía al menos un campo.")

    if "fecha_hora" in campos:
        try:
            campos["fecha_hora"] = datetime.fromisoformat(campos["fecha_hora"]).replace(tzinfo=TIMEZONE).isoformat()
        except ValueError:
            raise HTTPException(status_code=422, detail="Formato de fecha inválido.")

    res = supabase.table("citas").update(campos).eq("id", cita_id).execute()
    return {"mensaje": "Cita actualizada.", "cita": res.data[0]}


@router.delete("/{cita_id}", summary="Eliminar cita")
def eliminar_cita(cita_id: int, current_user: dict = Depends(require_staff)):
    """Elimina una cita de la base de datos."""
    if not supabase.table("citas").select("id").eq("id", cita_id).limit(1).execute().data:
        raise HTTPException(status_code=404, detail=f"Cita #{cita_id} no encontrada.")
    supabase.table("citas").delete().eq("id", cita_id).execute()
    return {"mensaje": f"Cita #{cita_id} eliminada."}
