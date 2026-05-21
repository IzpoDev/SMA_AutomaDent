# tools.py — Herramientas CRUD con seguridad por telegram_chat_id y roles (RBAC)
# ==============================================================================
# Cada herramienta recibe telegram_chat_id y user_role inyectados desde main.py.
# Se valida que el rol tenga permisos adecuados para ejecutar la acción.
# ==============================================================================

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from langchain_core.tools import tool
from database import supabase

# ─── Configuración de la clínica ─────────────────────────────────────────────
TIMEZONE = ZoneInfo("America/Lima")
DURACION_CITA_MIN = 30          # Duración estándar de cada cita en minutos
HORARIO_INICIO = 8              # 08:00
HORARIO_FIN = 18                # 18:00
DIAS_LABORALES = [0, 1, 2, 3, 4, 5]  # Lunes(0) a Sábado(5)

CREDENTIALS_FILE = "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]


# ==============================================================================
#  UTILIDADES DE GOOGLE SHEETS (LÓGICA INTERNA)
# ==============================================================================

def get_sheets_service():
    """Retorna el cliente de la API de Google Sheets utilizando credentials.json."""
    if not os.path.exists(CREDENTIALS_FILE):
        return None
    credentials = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    return build("sheets", "v4", credentials=credentials)

def get_drive_service():
    """Retorna el cliente de la API de Google Drive."""
    if not os.path.exists(CREDENTIALS_FILE):
        return None
    credentials = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    return build("drive", "v3", credentials=credentials)


# ==============================================================================
#  HERRAMIENTAS DEL AGENTE DE RECEPCIÓN
# ==============================================================================

@tool
def crear_paciente_y_historia(
    telegram_chat_id: str,
    user_role: str,
    nombre: str,
    apellido: str,
    email: str = "",
    fecha_nacimiento: str = ""
) -> str:
    """Registra un nuevo paciente en la clínica y crea su historia clínica vacía.
    
    Args:
        telegram_chat_id: ID de Telegram del usuario.
        user_role: Rol del usuario.
        nombre: Nombre del paciente.
        apellido: Apellido del paciente.
        email: Correo electrónico (opcional).
        fecha_nacimiento: Fecha de nacimiento YYYY-MM-DD (opcional).
    """
    # 1. Verificar si ya existe
    existente = (
        supabase.table("pacientes")
        .select("id, nombre, apellido")
        .eq("telefono", telegram_chat_id)
        .maybe_single()
        .execute()
    )
    if existente.data:
        nombre_completo = f"{existente.data['nombre']} {existente.data['apellido']}"
        return f"⚠️ Ya estás registrado como {nombre_completo}. No es necesario registrarte de nuevo."

    # 2. Insertar paciente
    datos_paciente = {
        "nombre": nombre.strip().title(),
        "apellido": apellido.strip().title(),
        "telefono": telegram_chat_id,
    }
    if email:
        datos_paciente["email"] = email.strip().lower()
    if fecha_nacimiento:
        datos_paciente["fecha_nacimiento"] = fecha_nacimiento

    resultado_paciente = (
        supabase.table("pacientes")
        .insert(datos_paciente)
        .execute()
    )
    paciente_id = resultado_paciente.data[0]["id"]

    # 3. Crear historia clínica
    supabase.table("historias_clinicas").insert({
        "paciente_id": paciente_id,
    }).execute()

    return (
        f"✅ ¡Registro exitoso!\n"
        f"👤 Paciente: {nombre.strip().title()} {apellido.strip().title()}\n"
        f"📂 Historia clínica creada de forma segura."
    )


@tool
def consultar_disponibilidad_agenda(
    telegram_chat_id: str,
    user_role: str,
    fecha: str,
    especialidad: str = ""
) -> str:
    """Consulta los horarios disponibles de odontólogos para una fecha específica.
    
    Args:
        telegram_chat_id: ID de Telegram del usuario.
        user_role: Rol del usuario.
        fecha: Fecha a consultar en formato YYYY-MM-DD.
        especialidad: Filtro opcional de especialidad (ej: 'ortodoncia', 'endodoncia').
    """
    try:
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        return "❌ Formato de fecha inválido. Usa el formato YYYY-MM-DD (ej: 2025-06-15)."

    hoy = datetime.now(TIMEZONE).date()
    if fecha_obj < hoy:
        return "❌ No puedes consultar fechas pasadas."

    if fecha_obj.weekday() not in DIAS_LABORALES:
        return "❌ La clínica no atiende los domingos. Elige Lunes a Sábado."

    # Obtener odontólogos
    query_personal = supabase.table("personal").select("id, nombre, apellido, especialidad").eq("rol", "odontologo")
    if especialidad:
        query_personal = query_personal.ilike("especialidad", f"%{especialidad}%")
    odontologos = query_personal.execute()

    if not odontologos.data:
        return f"❌ No se encontraron odontólogos{' con especialidad ' + especialidad if especialidad else ''}."

    # Citas agendadas para el día
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

    ocupados = {}
    for cita in (citas_dia.data or []):
        doc_id = cita["odontologo_id"]
        hora_cita = datetime.fromisoformat(cita["fecha_hora"])
        if doc_id not in ocupados:
            ocupados[doc_id] = set()
        ocupados[doc_id].add(hora_cita.strftime("%H:%M"))

    todos_slots = []
    hora_actual = datetime.now(TIMEZONE) if fecha_obj == hoy else None

    for doc in odontologos.data:
        doc_id = doc["id"]
        slots_doc = []

        for hora in range(HORARIO_INICIO, HORARIO_FIN):
            for minuto in range(0, 60, DURACION_CITA_MIN):
                slot_str = f"{hora:02d}:{minuto:02d}"

                if hora_actual:
                    slot_dt = datetime(fecha_obj.year, fecha_obj.month, fecha_obj.day, hora, minuto, tzinfo=TIMEZONE)
                    if slot_dt <= hora_actual:
                        continue

                if slot_str in ocupados.get(doc_id, set()):
                    continue

                slots_doc.append(slot_str)

        if slots_doc:
            doc_nombre = f"Dr(a). {doc['nombre']} {doc['apellido']} ({doc['especialidad']})"
            todos_slots.append(f"🦷 {doc_nombre} [ID: {doc_id}]\n   🕐 {', '.join(slots_doc)}")

    if not todos_slots:
        return f"❌ No hay horarios disponibles para el {fecha}."

    return f"📅 Disponibilidad para el {fecha}:\n\n" + "\n\n".join(todos_slots)


@tool
def agendar_cita(
    telegram_chat_id: str,
    user_role: str,
    odontologo_id: int,
    fecha_hora: str,
    motivo_consulta: str
) -> str:
    """Agenda una nueva cita para el paciente.
    
    Args:
        telegram_chat_id: ID de Telegram del usuario.
        user_role: Rol del usuario.
        odontologo_id: ID del odontólogo.
        fecha_hora: Fecha y hora en formato ISO YYYY-MM-DDTHH:MM (ej: 2025-06-15T10:00).
        motivo_consulta: Motivo de consulta.
    """
    # 1. Buscar paciente
    paciente = (
        supabase.table("pacientes")
        .select("id, nombre, apellido")
        .eq("telefono", telegram_chat_id)
        .maybe_single()
        .execute()
    )
    if not paciente.data:
        return "❌ No estás registrado como paciente. Escribe 'Quiero registrarme' primero."

    # 2. Verificar odontólogo
    doctor = (
        supabase.table("personal")
        .select("id, nombre, apellido")
        .eq("id", odontologo_id)
        .eq("rol", "odontologo")
        .maybe_single()
        .execute()
    )
    if not doctor.data:
        return f"❌ No se encontró un odontólogo con ID {odontologo_id}."

    # 3. Validaciones de fecha
    try:
        dt = datetime.fromisoformat(fecha_hora).replace(tzinfo=TIMEZONE)
    except ValueError:
        return "❌ Formato inválido. Usa YYYY-MM-DDTHH:MM."

    if dt <= datetime.now(TIMEZONE):
        return "❌ No puedes agendar citas en el pasado."

    # 4. Insertar cita
    nueva_cita = (
        supabase.table("citas")
        .insert({
            "paciente_id": paciente.data["id"],
            "odontologo_id": odontologo_id,
            "fecha_hora": dt.isoformat(),
            "estado": "programada",
            "motivo_consulta": motivo_consulta.strip()
        })
        .execute()
    )
    
    cita_id = nueva_cita.data[0]["id"]
    doc_nombre = f"Dr(a). {doctor.data['nombre']} {doctor.data['apellido']}"
    
    return (
        f"✅ ¡Cita agendada exitosamente!\n\n"
        f"🆔 Cita #{cita_id}\n"
        f"👤 Paciente: {paciente.data['nombre']} {paciente.data['apellido']}\n"
        f"🦷 Odontólogo: {doc_nombre}\n"
        f"📅 Fecha: {dt.strftime('%d/%m/%Y')}\n"
        f"🕐 Hora: {dt.strftime('%H:%M')}"
    )


@tool
def consultar_historial_paciente(
    telegram_chat_id: str,
    user_role: str,
    paciente_id: Optional[int] = None
) -> str:
    """Consulta el historial clínico. Los pacientes solo ven su propio historial. 
    Los doctores/recepcionistas pueden ver el historial de cualquier paciente usando paciente_id.
    
    Args:
        telegram_chat_id: ID de Telegram del usuario.
        user_role: Rol del usuario.
        paciente_id: ID del paciente a consultar (solo válido para personal clínico).
    """
    # Control de Acceso (RBAC)
    if user_role == "paciente":
        # Pacientes solo consultan su propio historial
        paciente = (
            supabase.table("pacientes")
            .select("id, nombre, apellido")
            .eq("telefono", telegram_chat_id)
            .maybe_single()
            .execute()
        )
        if not paciente.data:
            return "❌ No estás registrado en la clínica."
        target_paciente_id = paciente.data["id"]
    else:
        # Personal clínico (odontólogos, recepcionistas, admin)
        if not paciente_id:
            return "❌ Debes especificar un `paciente_id` para realizar la consulta."
        target_paciente_id = paciente_id

    # Buscar historia clínica
    historia = (
        supabase.table("historias_clinicas")
        .select("id, antecedentes_medicos, fecha_creacion")
        .eq("paciente_id", target_paciente_id)
        .maybe_single()
        .execute()
    )
    if not historia.data:
        return "❌ No se encontró historia clínica para el paciente."

    # Obtener el nombre del paciente
    pac_info = supabase.table("pacientes").select("nombre, apellido").eq("id", target_paciente_id).maybe_single().execute()
    nombre_paciente = f"{pac_info.data['nombre']} {pac_info.data['apellido']}" if pac_info.data else "Desconocido"

    # Consultar evoluciones
    evoluciones = (
        supabase.table("atenciones_medicas")
        .select("diagnostico, tratamiento_realizado, observaciones, fecha_atencion")
        .eq("historia_id", historia.data["id"])
        .order("fecha_atencion", desc=True)
        .execute()
    )

    texto = (
        f"📂 *Historia Clínica de {nombre_paciente}*\n"
        f"📅 Fecha Creación: {historia.data['fecha_creacion'][:10]}\n"
        f"🏥 Antecedentes: {historia.data.get('antecedentes_medicos') or 'Ninguno registrado.'}\n\n"
    )

    if not evoluciones.data:
        texto += "📝 No se registran atenciones clínicas previas."
    else:
        texto += f"📝 Evolución clínica ({len(evoluciones.data)} atenciones):\n"
        for i, evo in enumerate(evoluciones.data, 1):
            fecha = pd.to_datetime(evo["fecha_atencion"]).strftime("%d/%m/%Y")
            texto += (
                f"\n*Atención #{i} ({fecha})*\n"
                f"  🔍 Diagnóstico: {evo['diagnostico']}\n"
                f"  💊 Tratamiento: {evo['tratamiento_realizado']}\n"
                f"  📌 Observaciones: {evo.get('observaciones') or 'Ninguna'}\n"
            )

    return texto


# ==============================================================================
#  HERRAMIENTAS DEL AGENTE ASISTENTE MÉDICO
# ==============================================================================

@tool
def actualizar_estado_cita(
    telegram_chat_id: str,
    user_role: str,
    cita_id: int,
    nuevo_estado: str
) -> str:
    """Actualiza el estado de una cita. Solo para Odontólogos o Recepcionistas.
    
    Args:
        telegram_chat_id: ID de Telegram.
        user_role: Rol del usuario.
        cita_id: ID de la cita.
        nuevo_estado: Nuevo estado ('confirmada', 'asistida', 'cancelada', 'no_show').
    """
    if user_role not in ["odontologo", "recepcionista", "administrador"]:
        return "❌ Acceso Denegado. Solo el personal de la clínica puede cambiar el estado de las citas."

    cita = (
        supabase.table("citas")
        .select("id, estado")
        .eq("id", cita_id)
        .maybe_single()
        .execute()
    )
    if not cita.data:
        return f"❌ No se encontró la cita #{cita_id}."

    supabase.table("citas").update({"estado": nuevo_estado}).eq("id", cita_id).execute()

    return f"✅ Estado de cita #{cita_id} cambiado de '{cita.data['estado']}' a '{nuevo_estado}'."


@tool
def registrar_evolucion_medica(
    telegram_chat_id: str,
    user_role: str,
    cita_id: int,
    diagnostico: str,
    tratamiento_realizado: str,
    observaciones: str = ""
) -> str:
    """Registra la evolución médica de una cita atendida. Solo para Odontólogos.
    
    Args:
        telegram_chat_id: ID de Telegram.
        user_role: Rol del usuario.
        cita_id: ID de la cita.
        diagnostico: Diagnóstico clínico.
        tratamiento_realizado: Tratamiento realizado.
        observaciones: Notas adicionales.
    """
    if user_role != "odontologo":
        return "❌ Acceso Denegado. Solo los odontólogos pueden registrar evoluciones médicas."

    # Verificar cita asistida
    cita = (
        supabase.table("citas")
        .select("id, estado, paciente_id")
        .eq("id", cita_id)
        .maybe_single()
        .execute()
    )
    if not cita.data:
        return f"❌ No se encontró la cita #{cita_id}."

    if cita.data["estado"] != "asistida":
        return f"❌ La cita #{cita_id} debe marcarse primero como 'asistida' para registrar la evolución."

    # Obtener historia clínica
    historia = (
        supabase.table("historias_clinicas")
        .select("id")
        .eq("paciente_id", cita.data["paciente_id"])
        .maybe_single()
        .execute()
    )
    if not historia.data:
        return "❌ El paciente no cuenta con una historia clínica creada."

    # Insertar evolución
    supabase.table("atenciones_medicas").insert({
        "historia_id": historia.data["id"],
        "cita_id": cita_id,
        "diagnostico": diagnostico.strip(),
        "tratamiento_realizado": tratamiento_realizado.strip(),
        "observaciones": observaciones.strip() if observaciones else None
    }).execute()

    return f"✅ Evolución médica guardada correctamente para la cita #{cita_id}."


# ==============================================================================
#  HERRAMIENTAS DEL AGENTE DE FACTURACIÓN
# ==============================================================================

@tool
def registrar_pago(
    telegram_chat_id: str,
    user_role: str,
    cita_id: int,
    monto: float,
    metodo_pago: str
) -> str:
    """Registra el pago de una cita asistida. Solo para Administradores o Recepcionistas.
    
    Args:
        telegram_chat_id: ID de Telegram.
        user_role: Rol del usuario.
        cita_id: ID de la cita.
        monto: Monto cobrado en Soles (S/).
        metodo_pago: Método de pago ('efectivo', 'tarjeta', 'yape', 'plin').
    """
    if user_role not in ["administrador", "recepcionista"]:
        return "❌ Acceso Denegado. Solo personal administrativo puede registrar pagos."

    cita = (
        supabase.table("citas")
        .select("id, estado")
        .eq("id", cita_id)
        .maybe_single()
        .execute()
    )
    if not cita.data:
        return f"❌ Cita #{cita_id} no encontrada."

    if cita.data["estado"] != "asistida":
        return f"❌ No se puede cobrar una cita que no está en estado 'asistida'."

    # Registrar el pago
    supabase.table("pagos").insert({
        "cita_id": cita_id,
        "monto": monto,
        "metodo_pago": metodo_pago,
        "estado_pago": "pagado",
        "fecha_pago": datetime.now(TIMEZONE).isoformat()
    }).execute()

    return f"✅ Pago registrado de S/ {monto:.2f} con método '{metodo_pago}' para la cita #{cita_id}."


# ==============================================================================
#  HERRAMIENTA DE EXPORTACIÓN A GOOGLE SHEETS (NATIVA/MCP INTEGRADO)
# ==============================================================================

@tool
def exportar_citas_excel(
    telegram_chat_id: str,
    user_role: str,
    email_compartir: str
) -> str:
    """Exporta todas las citas registradas en Supabase a una hoja de Google Sheets.
    Crea la hoja de cálculo y la comparte con el email proporcionado. Solo para Personal Autorizado.
    
    Args:
        telegram_chat_id: ID de Telegram.
        user_role: Rol del usuario.
        email_compartir: Correo electrónico Gmail para compartir la hoja.
    """
    if user_role not in ["administrador", "recepcionista"]:
        return "❌ Acceso Denegado. Solo administradores o recepcionistas pueden exportar reportes."

    sheets_service = get_sheets_service()
    drive_service = get_drive_service()

    if not sheets_service or not drive_service:
        return "❌ El servicio de Google Sheets no está configurado (falta credentials.json)."

    try:
        # 1. Obtener citas de Supabase
        citas_df = (
            supabase.table("citas")
            .select("id, fecha_hora, estado, motivo_consulta, paciente_id, odontologo_id")
            .execute()
        )
        if not citas_df.data:
            return "📭 No hay citas para exportar."

        # Resolver nombres de pacientes y doctores
        pacientes = supabase.table("pacientes").select("id, nombre, apellido").execute()
        pac_map = {p["id"]: f"{p['nombre']} {p['apellido']}" for p in (pacientes.data or [])}
        
        doctores = supabase.table("personal").select("id, nombre, apellido").execute()
        doc_map = {d["id"]: f"Dr(a). {d['nombre']} {d['apellido']}" for d in (doctores.data or [])}

        headers = ["Cita ID", "Fecha", "Hora", "Paciente", "Odontólogo", "Estado", "Motivo"]
        rows = [headers]

        for c in citas_df.data:
            dt = datetime.fromisoformat(c["fecha_hora"])
            rows.append([
                str(c["id"]),
                dt.strftime("%Y-%m-%d"),
                dt.strftime("%H:%M"),
                pac_map.get(c["paciente_id"], "Desconocido"),
                doc_map.get(c["odontologo_id"], "Desconocido"),
                c["estado"],
                c.get("motivo_consulta") or ""
            ])

        # 2. Crear la hoja en Google Drive
        titulo = f"Reporte de Citas AutomaDent - {datetime.now(TIMEZONE).strftime('%d-%m-%Y')}"
        spreadsheet_body = {"properties": {"title": titulo}}
        sheet_res = sheets_service.spreadsheets().create(body=spreadsheet_body, fields="spreadsheetId").execute()
        spreadsheet_id = sheet_res.get("spreadsheetId")

        # 3. Escribir datos
        body = {"values": rows}
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="Sheet1!A1",
            valueInputOption="RAW",
            body=body
        ).execute()

        # 4. Compartir con el usuario
        user_permission = {
            "type": "user",
            "role": "writer",
            "emailAddress": email_compartir.strip()
        }
        drive_service.permissions().create(
            fileId=spreadsheet_id,
            body=user_permission
        ).execute()

        url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
        return f"✅ Reporte de citas exportado exitosamente.\n📁 Título: {titulo}\n✉️ Compartido con: {email_compartir}\n🔗 Enlace: {url}"

    except Exception as e:
        return f"❌ Error exportando a Google Sheets: {str(e)}"


# ==============================================================================
#  AGRUPACIÓN DE HERRAMIENTAS POR AGENTE
# ==============================================================================

tools_recepcion = [
    crear_paciente_y_historia,
    consultar_disponibilidad_agenda,
    agendar_cita,
    consultar_historial_paciente,
    exportar_citas_excel
]

tools_medico = [
    actualizar_estado_cita,
    registrar_evolucion_medica,
]

tools_facturacion = [
    registrar_pago,
]

all_tools = tools_recepcion + tools_medico + tools_facturacion
