# mcp_server.py — Servidor MCP para AutomaDent (Supabase)
# ==============================================================================
# Expone TODAS las operaciones de la clínica via MCP (SSE en puerto 8001).
# Úsalo con:
#   python mcp_server.py
#
# Claude Code se conecta en: http://localhost:8001/sse
# El bot de Telegram también usa este servidor como capa de datos.
# ==============================================================================

import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from supabase import create_client, Client

load_dotenv()

# ─── Supabase ────────────────────────────────────────────────────────────────
supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_KEY"],
)

# ─── Configuración de la clínica ─────────────────────────────────────────────
TIMEZONE = ZoneInfo("America/Lima")
DURACION_CITA_MIN = 30
HORARIO_INICIO = 8
HORARIO_FIN = 18
DIAS_LABORALES = [0, 1, 2, 3, 4, 5]  # Lun–Sáb

mcp = FastMCP("AutomaDent Supabase Server", host="0.0.0.0", port=8001)


# ==============================================================================
#  UTILIDAD INTERNA: NOTIFICACIONES TELEGRAM
# ==============================================================================

def _notificar_paciente(paciente_id: int, mensaje: str) -> None:
    """Envía un mensaje Telegram al paciente cuando cambia el estado de su cita."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("[NOTIF PACIENTE] ❌ TELEGRAM_BOT_TOKEN no configurado.")
        return
    pac = supabase.table("pacientes").select("telefono").eq("id", paciente_id).limit(1).execute()
    if not pac.data:
        print(f"[NOTIF PACIENTE] ⚠️ Paciente ID {paciente_id} no encontrado en BD.")
        return
    chat_id = pac.data[0]["telefono"]
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": mensaje, "parse_mode": "HTML"},
            timeout=5,
        )
        if resp.status_code == 200:
            print(f"[NOTIF PACIENTE] ✅ Mensaje enviado al chat_id {chat_id}.")
        else:
            print(f"[NOTIF PACIENTE] ❌ Telegram respondió {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[NOTIF PACIENTE] ❌ Excepción al enviar a {chat_id}: {e}")


def _notificar_odontologo(odontologo_id: int, mensaje: str) -> None:
    """Envía un mensaje directo al odontólogo en Telegram cuando se le asigna una nueva cita."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("[NOTIF ODONTÓLOGO] ❌ TELEGRAM_BOT_TOKEN no configurado.")
        return
    doc = supabase.table("personal").select("telefono").eq("id", odontologo_id).limit(1).execute()
    if not doc.data or not doc.data[0].get("telefono"):
        print(f"[NOTIF ODONTÓLOGO] ⚠️ Odontólogo ID {odontologo_id} sin chat_id (telefono) en BD.")
        return
    chat_id = doc.data[0]["telefono"]
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": mensaje, "parse_mode": "HTML"},
            timeout=5,
        )
        if resp.status_code == 200:
            print(f"[NOTIF ODONTÓLOGO] ✅ Mensaje enviado al chat_id {chat_id}.")
        else:
            print(f"[NOTIF ODONTÓLOGO] ❌ Telegram respondió {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[NOTIF ODONTÓLOGO] ❌ Excepción al enviar a {chat_id}: {e}")


# ==============================================================================
#  HERRAMIENTAS DE RECEPCIÓN
# ==============================================================================

@mcp.tool()
def crear_paciente_y_historia(
    telegram_chat_id: str,
    user_role: str,
    nombre: str,
    apellido: str,
    email: str = "",
    fecha_nacimiento: str = "",
) -> str:
    """Registra un nuevo paciente y crea su historia clínica vacía.

    Args:
        telegram_chat_id: ID de Telegram del usuario.
        user_role: Rol del usuario ('paciente_no_registrado').
        nombre: Nombre del paciente.
        apellido: Apellido del paciente.
        email: Correo electrónico (opcional).
        fecha_nacimiento: Fecha de nacimiento YYYY-MM-DD (opcional).
    """
    existente = (
        supabase.table("pacientes")
        .select("id, nombre, apellido")
        .eq("telefono", telegram_chat_id)
        .limit(1)
        .execute()
    )
    if existente.data:
        return f"⚠️ Ya estás registrado como {existente.data[0]['nombre']} {existente.data[0]['apellido']}."

    datos = {
        "nombre": nombre.strip().title(),
        "apellido": apellido.strip().title(),
        "telefono": telegram_chat_id,
    }
    if email:
        datos["email"] = email.strip().lower()
    if fecha_nacimiento:
        datos["fecha_nacimiento"] = fecha_nacimiento

    resultado = supabase.table("pacientes").insert(datos).execute()
    paciente_id = resultado.data[0]["id"]
    supabase.table("historias_clinicas").insert({"paciente_id": paciente_id}).execute()

    return (
        f"✅ ¡Registro exitoso!\n"
        f"👤 Paciente: {datos['nombre']} {datos['apellido']}\n"
        f"📂 Historia clínica creada."
    )


@mcp.tool()
def consultar_disponibilidad_agenda(
    telegram_chat_id: str,
    user_role: str,
    fecha: str,
    especialidad: str = "",
) -> str:
    """Consulta los horarios disponibles de odontólogos para una fecha específica.

    Args:
        telegram_chat_id: ID de Telegram.
        user_role: Rol del usuario.
        fecha: Fecha en formato YYYY-MM-DD.
        especialidad: Filtro opcional (ej: 'ortodoncia').
    """
    try:
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        return "❌ Formato de fecha inválido. Usa YYYY-MM-DD (ej: 2026-05-23)."

    hoy = datetime.now(TIMEZONE).date()
    if fecha_obj < hoy:
        return "❌ No puedes consultar fechas pasadas."
    if fecha_obj.weekday() not in DIAS_LABORALES:
        return "❌ La clínica no atiende los domingos. Elige Lunes a Sábado."

    query = supabase.table("personal").select("id, nombre, apellido, especialidad").eq("rol", "odontologo")
    if especialidad:
        query = query.ilike("especialidad", f"%{especialidad}%")
    odontologos = query.execute()

    if not odontologos.data:
        return f"❌ No se encontraron odontólogos{' con especialidad ' + especialidad if especialidad else ''}."

    inicio_dia = datetime(fecha_obj.year, fecha_obj.month, fecha_obj.day, 0, 0, 0, tzinfo=TIMEZONE).isoformat()
    fin_dia = datetime(fecha_obj.year, fecha_obj.month, fecha_obj.day, 23, 59, 59, tzinfo=TIMEZONE).isoformat()

    citas_dia = (
        supabase.table("citas")
        .select("odontologo_id, fecha_hora")
        .gte("fecha_hora", inicio_dia)
        .lte("fecha_hora", fin_dia)
        .in_("estado", ["programada", "confirmada"])
        .execute()
    )

    ocupados: dict = {}
    for c in (citas_dia.data or []):
        doc_id = c["odontologo_id"]
        hora = datetime.fromisoformat(c["fecha_hora"]).strftime("%H:%M")
        ocupados.setdefault(doc_id, set()).add(hora)

    hora_actual = datetime.now(TIMEZONE) if fecha_obj == hoy else None
    todos_slots = []

    for doc in odontologos.data:
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
        if slots:
            todos_slots.append(
                f"🦷 Dr(a). {doc['nombre']} {doc['apellido']} ({doc['especialidad']}) [ID: {doc['id']}]\n"
                f"   🕐 {', '.join(slots)}"
            )

    if not todos_slots:
        return f"❌ No hay horarios disponibles para el {fecha}."
    return f"📅 Disponibilidad para el {fecha}:\n\n" + "\n\n".join(todos_slots)


@mcp.tool()
def agendar_cita(
    telegram_chat_id: str,
    user_role: str,
    odontologo_id: int,
    fecha_hora: str,
    motivo_consulta: str,
) -> str:
    """Agenda una nueva cita para el paciente registrado.

    Args:
        telegram_chat_id: ID de Telegram del paciente.
        user_role: Rol del usuario.
        odontologo_id: ID del odontólogo.
        fecha_hora: Fecha y hora ISO YYYY-MM-DDTHH:MM.
        motivo_consulta: Motivo de la consulta.
    """
    paciente = (
        supabase.table("pacientes")
        .select("id, nombre, apellido")
        .eq("telefono", telegram_chat_id)
        .limit(1)
        .execute()
    )
    if not paciente.data:
        return "❌ No estás registrado. Escribe 'Quiero registrarme' primero."

    doctor = (
        supabase.table("personal")
        .select("id, nombre, apellido")
        .eq("id", odontologo_id)
        .eq("rol", "odontologo")
        .limit(1)
        .execute()
    )
    if not doctor.data:
        return f"❌ No se encontró un odontólogo con ID {odontologo_id}."

    try:
        dt = datetime.fromisoformat(fecha_hora).replace(tzinfo=TIMEZONE)
    except ValueError:
        return "❌ Formato inválido. Usa YYYY-MM-DDTHH:MM."

    if dt <= datetime.now(TIMEZONE):
        return "❌ No puedes agendar citas en el pasado."

    nueva_cita = (
        supabase.table("citas")
        .insert({
            "paciente_id": paciente.data[0]["id"],
            "odontologo_id": odontologo_id,
            "fecha_hora": dt.isoformat(),
            "estado": "programada",
            "motivo_consulta": motivo_consulta.strip(),
        })
        .execute()
    )
    cita_id = nueva_cita.data[0]["id"]
    pac_nombre = f"{paciente.data[0]['nombre']} {paciente.data[0]['apellido']}"
    doc_nombre = f"Dr(a). {doctor.data[0]['nombre']} {doctor.data[0]['apellido']}"

    # Notificar al odontólogo sobre la nueva cita asignada
    mensaje_odontologo = (
        f"🔔 <b>Nueva Cita Asignada</b>\n\n"
        f"📅 Fecha: <b>{dt.strftime('%d/%m/%Y')}</b>\n"
        f"🕐 Hora: <b>{dt.strftime('%H:%M')}</b>\n"
        f"👤 Paciente: <b>{pac_nombre}</b>\n"
        f"📝 Motivo: {motivo_consulta.strip()}\n"
        f"🆔 Cita #{cita_id}\n\n"
        f"¡Revisa tu agenda actualizada!"
    )
    _notificar_odontologo(odontologo_id, mensaje_odontologo)

    return (
        f"✅ ¡Cita agendada!\n"
        f"🆔 Cita #{cita_id}\n"
        f"👤 Paciente: {pac_nombre}\n"
        f"🦷 {doc_nombre}\n"
        f"📅 {dt.strftime('%d/%m/%Y')} a las {dt.strftime('%H:%M')}"
    )


@mcp.tool()
def consultar_historial_paciente(
    telegram_chat_id: str,
    user_role: str,
    paciente_id: Optional[int] = None,
) -> str:
    """Consulta el historial clínico. Los pacientes solo ven el suyo propio.

    Args:
        telegram_chat_id: ID de Telegram.
        user_role: Rol del usuario.
        paciente_id: ID del paciente (solo para personal clínico).
    """
    if user_role == "paciente":
        pac = (
            supabase.table("pacientes")
            .select("id, nombre, apellido")
            .eq("telefono", telegram_chat_id)
            .limit(1)
            .execute()
        )
        if not pac.data:
            return "❌ No estás registrado en la clínica."
        target_id = pac.data[0]["id"]
    else:
        if not paciente_id:
            return "❌ Debes especificar un paciente_id."
        target_id = paciente_id

    historia = (
        supabase.table("historias_clinicas")
        .select("id, antecedentes_medicos, fecha_creacion")
        .eq("paciente_id", target_id)
        .limit(1)
        .execute()
    )
    if not historia.data:
        return "❌ No se encontró historia clínica."

    pac_info = supabase.table("pacientes").select("nombre, apellido").eq("id", target_id).limit(1).execute()
    nombre = f"{pac_info.data[0]['nombre']} {pac_info.data[0]['apellido']}" if pac_info.data else "Desconocido"

    evoluciones = (
        supabase.table("atenciones_medicas")
        .select("diagnostico, tratamiento_realizado, observaciones, fecha_atencion")
        .eq("historia_id", historia.data[0]["id"])
        .order("fecha_atencion", desc=True)
        .execute()
    )

    texto = (
        f"📂 Historia Clínica de {nombre}\n"
        f"📅 Creación: {historia.data[0]['fecha_creacion'][:10]}\n"
        f"🏥 Antecedentes: {historia.data[0].get('antecedentes_medicos') or 'Ninguno registrado.'}\n\n"
    )

    if not evoluciones.data:
        texto += "📝 Sin atenciones clínicas registradas."
    else:
        texto += f"📝 Evolución clínica ({len(evoluciones.data)} atenciones):\n"
        for i, evo in enumerate(evoluciones.data, 1):
            fecha = datetime.fromisoformat(str(evo["fecha_atencion"])).strftime("%d/%m/%Y")
            texto += (
                f"\nAtención #{i} ({fecha})\n"
                f"  🔍 Diagnóstico: {evo['diagnostico']}\n"
                f"  💊 Tratamiento: {evo['tratamiento_realizado']}\n"
                f"  📌 Observaciones: {evo.get('observaciones') or 'Ninguna'}\n"
            )
    return texto


# ==============================================================================
#  HERRAMIENTAS DEL ASISTENTE MÉDICO
# ==============================================================================

@mcp.tool()
def actualizar_estado_cita(
    telegram_chat_id: str,
    user_role: str,
    cita_id: int,
    nuevo_estado: str,
) -> str:
    """Actualiza el estado de una cita. Solo para odontólogos, recepcionistas y administradores.

    Args:
        telegram_chat_id: ID de Telegram.
        user_role: Rol del usuario.
        cita_id: ID de la cita.
        nuevo_estado: Estado destino. Válidos: 'confirmada', 'asistida' (o 'atendida'), 'cancelada', 'no_show'.
    """
    if user_role not in ["odontologo", "recepcionista", "administrador"]:
        return "❌ Acceso denegado. Solo el personal de la clínica puede cambiar el estado de las citas."

    # Alias: 'atendida' → 'asistida' (valor correcto en el ENUM de Supabase)
    if nuevo_estado == "atendida":
        nuevo_estado = "asistida"

    estados_validos = {"programada", "confirmada", "asistida", "cancelada", "no_show"}
    if nuevo_estado not in estados_validos:
        return f"❌ Estado inválido '{nuevo_estado}'. Usa: {', '.join(estados_validos)}."

    cita = (
        supabase.table("citas")
        .select("id, estado, paciente_id")
        .eq("id", cita_id)
        .limit(1)
        .execute()
    )
    if not cita.data:
        return f"❌ No se encontró la cita #{cita_id}."

    supabase.table("citas").update({"estado": nuevo_estado}).eq("id", cita_id).execute()

    mensajes_notificacion = {
        "confirmada": f"✅ <b>Tu cita #{cita_id} fue confirmada.</b>\n¡Te esperamos en AutomaDent!",
        "cancelada": f"❌ <b>Tu cita #{cita_id} fue cancelada.</b>\nContáctanos para reagendar.",
        "no_show": f"⚠️ <b>Tu cita #{cita_id} fue registrada como no asistida.</b>",
        "asistida": f"✅ <b>Tu cita #{cita_id} fue completada.</b>\n¡Gracias por visitarnos!",
    }
    paciente_id = cita.data[0].get("paciente_id")
    if paciente_id and nuevo_estado in mensajes_notificacion:
        _notificar_paciente(paciente_id, mensajes_notificacion[nuevo_estado])

    return f"✅ Cita #{cita_id}: '{cita.data[0]['estado']}' → '{nuevo_estado}'."


@mcp.tool()
def registrar_evolucion_medica(
    telegram_chat_id: str,
    user_role: str,
    cita_id: int,
    diagnostico: str,
    tratamiento_realizado: str,
    observaciones: str = "",
) -> str:
    """Registra la evolución médica de una cita. Solo para odontólogos.

    Args:
        telegram_chat_id: ID de Telegram.
        user_role: Rol del usuario.
        cita_id: ID de la cita (debe estar en estado 'asistida').
        diagnostico: Diagnóstico clínico.
        tratamiento_realizado: Tratamiento realizado.
        observaciones: Notas adicionales.
    """
    if user_role != "odontologo":
        return "❌ Solo los odontólogos pueden registrar evoluciones médicas."

    cita = (
        supabase.table("citas")
        .select("id, estado, paciente_id")
        .eq("id", cita_id)
        .limit(1)
        .execute()
    )
    if not cita.data:
        return f"❌ No se encontró la cita #{cita_id}."
    if cita.data[0]["estado"] != "asistida":
        return f"❌ La cita #{cita_id} debe marcarse primero como 'asistida'."

    historia = (
        supabase.table("historias_clinicas")
        .select("id")
        .eq("paciente_id", cita.data[0]["paciente_id"])
        .limit(1)
        .execute()
    )
    if not historia.data:
        return "❌ El paciente no tiene historia clínica."

    supabase.table("atenciones_medicas").insert({
        "historia_id": historia.data[0]["id"],
        "cita_id": cita_id,
        "diagnostico": diagnostico.strip(),
        "tratamiento_realizado": tratamiento_realizado.strip(),
        "observaciones": observaciones.strip() if observaciones else None,
    }).execute()

    return f"✅ Evolución médica registrada para la cita #{cita_id}."


# ==============================================================================
#  HERRAMIENTAS DE FACTURACIÓN
# ==============================================================================

@mcp.tool()
def registrar_pago(
    telegram_chat_id: str,
    user_role: str,
    cita_id: int,
    monto: float,
    metodo_pago: str,
) -> str:
    """Registra el pago de una cita. Solo para administradores y recepcionistas.

    Args:
        telegram_chat_id: ID de Telegram.
        user_role: Rol del usuario.
        cita_id: ID de la cita.
        monto: Monto en Soles.
        metodo_pago: 'efectivo', 'tarjeta', 'yape' o 'plin'.
    """
    if user_role not in ["administrador", "recepcionista", "odontologo"]:
        return "❌ Solo el personal administrativo puede registrar pagos."

    cita = (
        supabase.table("citas")
        .select("id, estado")
        .eq("id", cita_id)
        .limit(1)
        .execute()
    )
    if not cita.data:
        return f"❌ Cita #{cita_id} no encontrada."
    if cita.data[0]["estado"] != "asistida":
        return "❌ Solo se pueden cobrar citas en estado 'asistida'."

    supabase.table("pagos").insert({
        "cita_id": cita_id,
        "monto": monto,
        "metodo_pago": metodo_pago,
        "estado_pago": "pagado",
        "fecha_pago": datetime.now(TIMEZONE).isoformat(),
    }).execute()

    return f"✅ Pago de S/ {monto:.2f} con '{metodo_pago}' registrado para la cita #{cita_id}."


# ==============================================================================
#  HERRAMIENTAS ADMINISTRATIVAS (solo para Claude Code / personal)
# ==============================================================================

@mcp.tool()
def listar_pacientes(limite: int = 50) -> str:
    """Lista los pacientes registrados en la clínica.

    Args:
        limite: Número máximo de registros a devolver (default: 50).
    """
    pacientes = (
        supabase.table("pacientes")
        .select("id, nombre, apellido, telefono, email")
        .limit(limite)
        .order("id", desc=True)
        .execute()
    )
    if not pacientes.data:
        return "📭 No hay pacientes registrados."

    lineas = [f"👥 Pacientes registrados ({len(pacientes.data)}):"]
    for p in pacientes.data:
        lineas.append(
            f"  #{p['id']} — {p['nombre']} {p['apellido']} | Tel: {p['telefono']} | Email: {p.get('email') or '—'}"
        )
    return "\n".join(lineas)


@mcp.tool()
def listar_citas(
    telegram_chat_id: str,
    user_role: str,
    fecha: str = "",
    estado: str = "",
    limite: int = 30,
) -> str:
    """Lista citas de la clínica con filtros opcionales y control de acceso por rol.
    Los odontólogos solo ven sus propias citas. Recepcionistas y administradores ven todas.

    Args:
        telegram_chat_id: ID de Telegram del usuario que consulta.
        user_role: Rol del usuario ('odontologo', 'recepcionista', 'administrador').
        fecha: Filtrar por fecha YYYY-MM-DD (opcional).
        estado: Filtrar por estado: 'programada', 'confirmada', 'asistida', 'cancelada', 'no_show' (opcional).
        limite: Máximo de registros (default: 30).
    """
    if user_role == "paciente" or user_role == "paciente_no_registrado":
        return "❌ Acceso denegado. Esta función es exclusiva para el personal de la clínica."

    query = supabase.table("citas").select(
        "id, fecha_hora, estado, motivo_consulta, paciente_id, odontologo_id"
    )

    # RBAC: los odontólogos solo ven sus propias citas
    if user_role == "odontologo":
        doc = (
            supabase.table("personal")
            .select("id")
            .eq("telefono", telegram_chat_id)
            .eq("rol", "odontologo")
            .limit(1)
            .execute()
        )
        if not doc.data:
            return "❌ No se encontró tu perfil de odontólogo en la base de datos. Verifica que tu Telegram Chat ID esté registrado."
        query = query.eq("odontologo_id", doc.data[0]["id"])

    if fecha:
        try:
            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
            inicio = datetime(fecha_obj.year, fecha_obj.month, fecha_obj.day, 0, 0, 0, tzinfo=TIMEZONE).isoformat()
            fin = datetime(fecha_obj.year, fecha_obj.month, fecha_obj.day, 23, 59, 59, tzinfo=TIMEZONE).isoformat()
            query = query.gte("fecha_hora", inicio).lte("fecha_hora", fin)
        except ValueError:
            return "❌ Formato de fecha inválido. Usa YYYY-MM-DD."

    if estado:
        # Alias: 'atendida' → 'asistida'
        if estado == "atendida":
            estado = "asistida"
        query = query.eq("estado", estado)

    citas = query.order("fecha_hora", desc=False).limit(limite).execute()

    if not citas.data:
        return "📭 No se encontraron citas con esos filtros."

    pac_map = {p["id"]: f"{p['nombre']} {p['apellido']}" for p in
               (supabase.table("pacientes").select("id, nombre, apellido").execute().data or [])}
    doc_map = {d["id"]: f"{d['nombre']} {d['apellido']}" for d in
               (supabase.table("personal").select("id, nombre, apellido").execute().data or [])}

    lineas = [f"📅 Citas encontradas ({len(citas.data)}) para {user_role}:"]
    for c in citas.data:
        dt = datetime.fromisoformat(c["fecha_hora"])
        lineas.append(
            f"  #{c['id']} | {dt.strftime('%d/%m/%Y %H:%M')} | {c['estado'].upper()}\n"
            f"        Paciente: {pac_map.get(c['paciente_id'], '—')} | Dr: {doc_map.get(c['odontologo_id'], '—')}\n"
            f"        Motivo: {c.get('motivo_consulta') or '—'}"
        )
    return "\n".join(lineas)


@mcp.tool()
def obtener_mis_citas(telegram_chat_id: str, user_role: str) -> str:
    """Muestra las citas próximas del paciente que hace la consulta.

    Args:
        telegram_chat_id: ID de Telegram del paciente.
        user_role: Rol del usuario.
    """
    pac = (
        supabase.table("pacientes")
        .select("id, nombre, apellido")
        .eq("telefono", telegram_chat_id)
        .limit(1)
        .execute()
    )
    if not pac.data:
        return "❌ No estás registrado en la clínica."

    ahora = datetime.now(TIMEZONE).isoformat()
    citas = (
        supabase.table("citas")
        .select("id, fecha_hora, estado, motivo_consulta, odontologo_id")
        .eq("paciente_id", pac.data[0]["id"])
        .gte("fecha_hora", ahora)
        .in_("estado", ["programada", "confirmada"])
        .order("fecha_hora")
        .execute()
    )

    if not citas.data:
        return "📭 No tienes citas próximas programadas."

    doc_map = {d["id"]: f"Dr(a). {d['nombre']} {d['apellido']}" for d in
               (supabase.table("personal").select("id, nombre, apellido").execute().data or [])}

    lineas = [f"📅 Tus próximas citas, {pac.data[0]['nombre']}:"]
    for c in citas.data:
        dt = datetime.fromisoformat(c["fecha_hora"])
        lineas.append(
            f"  🦷 Cita #{c['id']} — {dt.strftime('%d/%m/%Y a las %H:%M')}\n"
            f"     Estado: {c['estado']} | {doc_map.get(c['odontologo_id'], '—')}\n"
            f"     Motivo: {c.get('motivo_consulta') or '—'}"
        )
    return "\n".join(lineas)


# ==============================================================================
#  ARRANQUE DEL SERVIDOR
# ==============================================================================

if __name__ == "__main__":
    print("AutomaDent MCP Server iniciando en http://localhost:8001/mcp ...")
    mcp.run(transport="streamable-http")
