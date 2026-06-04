# routes/citas.py — CRUD de Citas
# ==============================================================================
# GET    /api/citas                   → Listar citas con filtros
# GET    /api/citas/disponibilidad    → Consultar horarios libres
# POST   /api/citas                   → Crear nueva cita
# PUT    /api/citas/{id}/estado       → Cambiar estado de la cita
# PUT    /api/citas/{id}              → Actualizar datos de la cita
# DELETE /api/citas/{id}              → Eliminar cita
# ==============================================================================

import os
import requests as http_requests
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel

from database import supabase
from routes.auth import require_staff

router = APIRouter(prefix="/api/citas", tags=["Citas"])

TIMEZONE = ZoneInfo("America/Lima")
DURACION_CITA_MIN = 30
HORARIO_INICIO = 8
HORARIO_FIN = 18
DIAS_LABORALES = [0, 1, 2, 3, 4, 5]  # Lun–Sáb


# ─── Utilidades de notificación ───────────────────────────────────────────────

def _notificar_telegram(chat_id: str, mensaje: str) -> None:
    """Envía un mensaje vía Telegram. No bloquea si falla."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or not chat_id:
        return
    try:
        http_requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": mensaje, "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception:
        pass  # Las notificaciones no deben bloquear la respuesta de la API


# ─── Schemas ─────────────────────────────────────────────────────────────────

class CrearCitaRequest(BaseModel):
    paciente_id: int
    odontologo_id: int
    fecha_hora: str  # ISO: YYYY-MM-DDTHH:MM
    motivo_consulta: Optional[str] = None


class ActualizarCitaRequest(BaseModel):
    odontologo_id: Optional[int] = None
    fecha_hora: Optional[str] = None
    motivo_consulta: Optional[str] = None


class CambiarEstadoRequest(BaseModel):
    nuevo_estado: str  # programada|confirmada|asistida|cancelada|no_show


# ==============================================================================
#  ENDPOINTS
# ==============================================================================

@router.get("/disponibilidad", summary="Consultar disponibilidad de agenda")
def consultar_disponibilidad(
    fecha: str = Query(..., description="Fecha en formato YYYY-MM-DD"),
    odontologo_id: Optional[int] = Query(None, description="Filtrar por ID de odontólogo"),
    especialidad: Optional[str] = Query(None, description="Filtrar por especialidad"),
    current_user: dict = Depends(require_staff),
):
    """
    Consulta los horarios libres disponibles para una fecha específica.
    Retorna los slots disponibles por odontólogo, excluyendo los ya ocupados.
    """
    try:
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Formato de fecha inválido. Usa YYYY-MM-DD.",
        )

    hoy = datetime.now(TIMEZONE).date()
    if fecha_obj < hoy:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No puedes consultar disponibilidad en fechas pasadas.",
        )
    if fecha_obj.weekday() not in DIAS_LABORALES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La clínica no atiende los domingos. Elige entre Lunes y Sábado.",
        )

    # Obtener odontólogos
    query = supabase.table("personal").select("id, nombre, apellido, especialidad").eq("rol", "odontologo")
    if odontologo_id:
        query = query.eq("id", odontologo_id)
    if especialidad:
        query = query.ilike("especialidad", f"%{especialidad}%")
    odont_res = query.execute()

    if not odont_res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontraron odontólogos con esos filtros.",
        )

    # Obtener citas del día
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
        doc_id = c["odontologo_id"]
        hora = datetime.fromisoformat(c["fecha_hora"]).strftime("%H:%M")
        ocupados.setdefault(doc_id, set()).add(hora)

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
    fecha: Optional[str] = Query(None, description="Filtrar por fecha YYYY-MM-DD"),
    estado: Optional[str] = Query(None, description="Filtrar por estado"),
    odontologo_id: Optional[int] = Query(None),
    paciente_id: Optional[int] = Query(None),
    limite: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_staff),
):
    """
    Retorna el listado de citas con filtros opcionales.
    Incluye nombres resueltos de paciente y odontólogo.
    """
    query = supabase.table("citas").select(
        "id, fecha_hora, estado, motivo_consulta, paciente_id, odontologo_id, created_at"
    ).order("fecha_hora", desc=False).limit(limite)

    if estado:
        estados_validos = {"programada", "confirmada", "asistida", "cancelada", "no_show"}
        if estado not in estados_validos:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Estado inválido. Usa: {', '.join(estados_validos)}.",
            )
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
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Formato de fecha inválido. Usa YYYY-MM-DD.",
            )

    citas = query.execute().data or []

    # Resolver nombres
    pac_map, doc_map = {}, {}
    if citas:
        pac_ids = list({c["paciente_id"] for c in citas})
        doc_ids = list({c["odontologo_id"] for c in citas})
        pacs = supabase.table("pacientes").select("id, nombre, apellido").in_("id", pac_ids).execute()
        docs = supabase.table("personal").select("id, nombre, apellido").in_("id", doc_ids).execute()
        pac_map = {p["id"]: f"{p['nombre']} {p['apellido']}" for p in (pacs.data or [])}
        doc_map = {d["id"]: f"Dr(a). {d['nombre']} {d['apellido']}" for d in (docs.data or [])}
        for c in citas:
            c["paciente_nombre"] = pac_map.get(c["paciente_id"], "—")
            c["odontologo_nombre"] = doc_map.get(c["odontologo_id"], "—")

    return {"total": len(citas), "citas": citas}


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Crear nueva cita")
def crear_cita(body: CrearCitaRequest, current_user: dict = Depends(require_staff)):
    """
    Agenda una nueva cita para un paciente con un odontólogo.

    - Valida que el paciente y el odontólogo existan.
    - Valida que el slot no esté ya ocupado.
    - Envía una notificación automática por Telegram al odontólogo si tiene su chat_id registrado.
    """
    # Validar paciente
    pac = supabase.table("pacientes").select("id, nombre, apellido").eq("id", body.paciente_id).limit(1).execute()
    if not pac.data:
        raise HTTPException(status_code=404, detail=f"No se encontró el paciente ID {body.paciente_id}.")

    # Validar odontólogo
    doc = supabase.table("personal").select("id, nombre, apellido, telefono").eq("id", body.odontologo_id).eq("rol", "odontologo").limit(1).execute()
    if not doc.data:
        raise HTTPException(status_code=404, detail=f"No se encontró un odontólogo con ID {body.odontologo_id}.")

    # Parsear la fecha
    try:
        dt = datetime.fromisoformat(body.fecha_hora).replace(tzinfo=TIMEZONE)
    except ValueError:
        raise HTTPException(status_code=422, detail="Formato de fecha inválido. Usa YYYY-MM-DDTHH:MM.")

    if dt <= datetime.now(TIMEZONE):
        raise HTTPException(status_code=422, detail="No puedes agendar citas en el pasado.")

    # Verificar disponibilidad del slot
    slot_ocupado = (
        supabase.table("citas")
        .select("id")
        .eq("odontologo_id", body.odontologo_id)
        .eq("fecha_hora", dt.isoformat())
        .in_("estado", ["programada", "confirmada"])
        .limit(1)
        .execute()
    )
    if slot_ocupado.data:
        raise HTTPException(status_code=409, detail="El horario seleccionado ya está ocupado para ese odontólogo.")

    # Insertar la cita
    nueva_cita = supabase.table("citas").insert({
        "paciente_id": body.paciente_id,
        "odontologo_id": body.odontologo_id,
        "fecha_hora": dt.isoformat(),
        "estado": "programada",
        "motivo_consulta": body.motivo_consulta.strip() if body.motivo_consulta else None,
    }).execute()

    cita = nueva_cita.data[0]
    pac_nombre = f"{pac.data[0]['nombre']} {pac.data[0]['apellido']}"
    doc_nombre = f"Dr(a). {doc.data[0]['nombre']} {doc.data[0]['apellido']}"

    # Notificar al odontólogo
    if doc.data[0].get("telefono"):
        _notificar_telegram(
            doc.data[0]["telefono"],
            f"🔔 <b>Nueva Cita Asignada</b>\n\n"
            f"📅 Fecha: <b>{dt.strftime('%d/%m/%Y')}</b>\n"
            f"🕐 Hora: <b>{dt.strftime('%H:%M')}</b>\n"
            f"👤 Paciente: <b>{pac_nombre}</b>\n"
            f"📝 Motivo: {body.motivo_consulta or 'No especificado'}\n"
            f"🆔 Cita #{cita['id']}"
        )

    return {
        "mensaje": "Cita agendada exitosamente.",
        "cita": {**cita, "paciente_nombre": pac_nombre, "odontologo_nombre": doc_nombre},
    }


@router.put("/{cita_id}/estado", summary="Cambiar estado de la cita")
def cambiar_estado(cita_id: int, body: CambiarEstadoRequest, current_user: dict = Depends(require_staff)):
    """
    Actualiza el estado de una cita. También envía notificación por Telegram al paciente.

    Estados válidos: `programada`, `confirmada`, `asistida`, `cancelada`, `no_show`.
    El alias `atendida` es equivalente a `asistida`.
    """
    estados_validos = {"programada", "confirmada", "asistida", "cancelada", "no_show"}
    nuevo_estado = body.nuevo_estado
    if nuevo_estado == "atendida":
        nuevo_estado = "asistida"
    if nuevo_estado not in estados_validos:
        raise HTTPException(status_code=422, detail=f"Estado inválido. Usa: {', '.join(estados_validos)}.")

    cita_res = supabase.table("citas").select("id, estado, paciente_id").eq("id", cita_id).limit(1).execute()
    if not cita_res.data:
        raise HTTPException(status_code=404, detail=f"No se encontró la cita #{cita_id}.")

    cita = cita_res.data[0]
    estado_anterior = cita["estado"]
    supabase.table("citas").update({"estado": nuevo_estado}).eq("id", cita_id).execute()

    # Notificar al paciente
    pac_res = supabase.table("pacientes").select("telefono").eq("id", cita["paciente_id"]).limit(1).execute()
    mensajes = {
        "confirmada": f"✅ <b>Tu cita #{cita_id} fue confirmada.</b>\n¡Te esperamos en AutomaDent!",
        "cancelada": f"❌ <b>Tu cita #{cita_id} fue cancelada.</b>\nContáctanos para reagendar.",
        "no_show": f"⚠️ <b>Tu cita #{cita_id} fue registrada como no asistida.</b>",
        "asistida": f"✅ <b>Tu cita #{cita_id} fue completada.</b>\n¡Gracias por visitarnos!",
    }
    if pac_res.data and pac_res.data[0].get("telefono") and nuevo_estado in mensajes:
        _notificar_telegram(pac_res.data[0]["telefono"], mensajes[nuevo_estado])

    return {
        "mensaje": f"Estado de la cita #{cita_id} actualizado.",
        "estado_anterior": estado_anterior,
        "estado_nuevo": nuevo_estado,
    }


@router.put("/{cita_id}", summary="Actualizar datos de la cita")
def actualizar_cita(cita_id: int, body: ActualizarCitaRequest, current_user: dict = Depends(require_staff)):
    """
    Actualiza los datos de una cita existente (odontólogo, fecha/hora o motivo).
    Solo se actualizan los campos enviados.
    """
    existe = supabase.table("citas").select("id").eq("id", cita_id).limit(1).execute()
    if not existe.data:
        raise HTTPException(status_code=404, detail=f"No se encontró la cita #{cita_id}.")

    campos = body.model_dump(exclude_none=True)
    if not campos:
        raise HTTPException(status_code=422, detail="Debes enviar al menos un campo para actualizar.")

    if "fecha_hora" in campos:
        try:
            dt = datetime.fromisoformat(campos["fecha_hora"]).replace(tzinfo=TIMEZONE)
            campos["fecha_hora"] = dt.isoformat()
        except ValueError:
            raise HTTPException(status_code=422, detail="Formato de fecha inválido. Usa YYYY-MM-DDTHH:MM.")

    res = supabase.table("citas").update(campos).eq("id", cita_id).execute()
    return {"mensaje": "Cita actualizada exitosamente.", "cita": res.data[0]}


@router.delete("/{cita_id}", summary="Eliminar cita")
def eliminar_cita(cita_id: int, current_user: dict = Depends(require_staff)):
    """
    Elimina una cita de la base de datos permanentemente.
    """
    existe = supabase.table("citas").select("id").eq("id", cita_id).limit(1).execute()
    if not existe.data:
        raise HTTPException(status_code=404, detail=f"No se encontró la cita #{cita_id}.")

    supabase.table("citas").delete().eq("id", cita_id).execute()
    return {"mensaje": f"Cita #{cita_id} eliminada exitosamente."}
