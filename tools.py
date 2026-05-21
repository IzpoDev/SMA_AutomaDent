# tools.py — Herramientas CRUD con seguridad por telegram_chat_id
# ================================================================
# Cada @tool recibe telegram_chat_id inyectado desde main.py.
# Las consultas a Supabase filtran por .eq("telefono", chat_id)
# para garantizar que cada usuario solo acceda a sus propios datos.
# ================================================================

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from langchain_core.tools import tool
from database import supabase

# ─── Configuración de la clínica ─────────────────────────────────
TIMEZONE = ZoneInfo("America/Lima")
DURACION_CITA_MIN = 30          # Duración estándar de cada cita en minutos
HORARIO_INICIO = 8              # 08:00
HORARIO_FIN = 18                # 18:00
DIAS_LABORALES = [0, 1, 2, 3, 4, 5]  # Lunes(0) a Sábado(5)


# ==================================================================
#  HERRAMIENTAS DEL AGENTE DE RECEPCIÓN
# ==================================================================

@tool
def crear_paciente_y_historia(
    telegram_chat_id: str,
    nombre: str,
    apellido: str,
    email: str = "",
    fecha_nacimiento: str = ""
) -> str:
    """Registra un nuevo paciente en la clínica y crea su historia clínica vacía.
    Usar SOLO cuando el paciente confirma que quiere registrarse por primera vez.
    Args:
        telegram_chat_id: ID del chat de Telegram del paciente.
        nombre: Nombre del paciente.
        apellido: Apellido del paciente.
        email: Correo electrónico (opcional).
        fecha_nacimiento: Fecha de nacimiento en formato YYYY-MM-DD (opcional).
    """
    # 1. Verificar si el paciente ya existe
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

    # 2. Insertar el paciente
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

    # 3. Crear historia clínica vacía asociada
    supabase.table("historias_clinicas").insert({
        "paciente_id": paciente_id,
    }).execute()

    return (
        f"✅ ¡Registro exitoso!\n"
        f"📋 Paciente: {nombre.strip().title()} {apellido.strip().title()}\n"
        f"🆔 ID: {paciente_id}\n"
        f"📂 Historia clínica creada.\n"
        f"Ya puedes agendar tu primera cita."
    )


@tool
def consultar_disponibilidad_agenda(
    telegram_chat_id: str,
    fecha: str,
    especialidad: str = ""
) -> str:
    """Consulta los horarios disponibles de odontólogos para una fecha específica.
    Args:
        telegram_chat_id: ID del chat de Telegram del paciente.
        fecha: Fecha a consultar en formato YYYY-MM-DD.
        especialidad: Filtro opcional de especialidad (ej: 'ortodoncia', 'endodoncia').
    """
    # 1. Validar formato de fecha
    try:
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        return "❌ Formato de fecha inválido. Usa el formato YYYY-MM-DD (ej: 2025-06-15)."

    # 2. Verificar que no sea un día pasado
    hoy = datetime.now(TIMEZONE).date()
    if fecha_obj < hoy:
        return "❌ No puedes consultar fechas pasadas. Elige una fecha de hoy en adelante."

    # 3. Verificar que sea día laboral
    if fecha_obj.weekday() not in DIAS_LABORALES:
        return "❌ La clínica no atiende los domingos. Elige otro día (Lunes a Sábado)."

    # 4. Obtener odontólogos
    query_personal = supabase.table("personal").select("id, nombre, apellido, especialidad").eq("rol", "odontologo")
    if especialidad:
        query_personal = query_personal.ilike("especialidad", f"%{especialidad}%")
    odontologos = query_personal.execute()

    if not odontologos.data:
        return f"❌ No se encontraron odontólogos{' con especialidad ' + especialidad if especialidad else ''}."

    # 5. Obtener citas ya agendadas para esa fecha
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

    # Agrupar horarios ocupados por odontólogo
    ocupados = {}
    for cita in (citas_dia.data or []):
        doc_id = cita["odontologo_id"]
        hora_cita = datetime.fromisoformat(cita["fecha_hora"])
        if doc_id not in ocupados:
            ocupados[doc_id] = set()
        ocupados[doc_id].add(hora_cita.strftime("%H:%M"))

    # 6. Generar slots disponibles
    todos_slots = []
    hora_actual = datetime.now(TIMEZONE) if fecha_obj == hoy else None

    for doc in odontologos.data:
        doc_id = doc["id"]
        slots_doc = []

        for hora in range(HORARIO_INICIO, HORARIO_FIN):
            for minuto in range(0, 60, DURACION_CITA_MIN):
                slot_str = f"{hora:02d}:{minuto:02d}"

                # Saltar si el slot ya pasó (solo para hoy)
                if hora_actual:
                    slot_dt = datetime(fecha_obj.year, fecha_obj.month, fecha_obj.day,
                                      hora, minuto, tzinfo=TIMEZONE)
                    if slot_dt <= hora_actual:
                        continue

                # Saltar si está ocupado
                if slot_str in ocupados.get(doc_id, set()):
                    continue

                slots_doc.append(slot_str)

        if slots_doc:
            doc_nombre = f"Dr(a). {doc['nombre']} {doc['apellido']} ({doc['especialidad']})"
            todos_slots.append(f"🦷 {doc_nombre} [ID: {doc_id}]\n   🕐 {', '.join(slots_doc)}")

    if not todos_slots:
        return f"❌ No hay horarios disponibles para el {fecha}. Intenta con otra fecha."

    encabezado = f"📅 Disponibilidad para el {fecha}:\n\n"
    return encabezado + "\n\n".join(todos_slots) + "\n\n💡 Para agendar, indícame el doctor y la hora que prefieres."


@tool
def agendar_cita(
    telegram_chat_id: str,
    odontologo_id: int,
    fecha_hora: str,
    motivo_consulta: str
) -> str:
    """Agenda una nueva cita para el paciente registrado.
    Args:
        telegram_chat_id: ID del chat de Telegram del paciente.
        odontologo_id: ID numérico del odontólogo elegido.
        fecha_hora: Fecha y hora en formato ISO YYYY-MM-DDTHH:MM (ej: 2025-06-15T10:00).
        motivo_consulta: Motivo de la consulta descrito por el paciente.
    """
    # 1. Verificar que el paciente existe
    paciente = (
        supabase.table("pacientes")
        .select("id, nombre, apellido")
        .eq("telefono", telegram_chat_id)
        .maybe_single()
        .execute()
    )
    if not paciente.data:
        return "❌ No estás registrado. Primero necesito registrarte como paciente."

    # 2. Verificar que el odontólogo existe
    doctor = (
        supabase.table("personal")
        .select("id, nombre, apellido, especialidad")
        .eq("id", odontologo_id)
        .eq("rol", "odontologo")
        .maybe_single()
        .execute()
    )
    if not doctor.data:
        return f"❌ No se encontró un odontólogo con ID {odontologo_id}."

    # 3. Parsear y validar fecha_hora
    try:
        dt = datetime.fromisoformat(fecha_hora).replace(tzinfo=TIMEZONE)
    except ValueError:
        return "❌ Formato de fecha/hora inválido. Usa YYYY-MM-DDTHH:MM (ej: 2025-06-15T10:00)."

    if dt <= datetime.now(TIMEZONE):
        return "❌ No puedes agendar citas en el pasado."

    if dt.weekday() not in DIAS_LABORALES:
        return "❌ La clínica no atiende los domingos."

    if not (HORARIO_INICIO <= dt.hour < HORARIO_FIN):
        return f"❌ Horario fuera de atención. La clínica atiende de {HORARIO_INICIO}:00 a {HORARIO_FIN}:00."

    # 4. Verificar que el slot esté libre
    slot_inicio = dt.isoformat()
    slot_fin = (dt + timedelta(minutes=DURACION_CITA_MIN)).isoformat()

    conflicto = (
        supabase.table("citas")
        .select("id")
        .eq("odontologo_id", odontologo_id)
        .gte("fecha_hora", slot_inicio)
        .lt("fecha_hora", slot_fin)
        .in_("estado", ["programada", "confirmada"])
        .maybe_single()
        .execute()
    )
    if conflicto.data:
        return "❌ Ese horario ya está ocupado. Consulta la disponibilidad para ver horarios libres."

    # 5. Insertar la cita
    nueva_cita = (
        supabase.table("citas")
        .insert({
            "paciente_id": paciente.data["id"],
            "odontologo_id": odontologo_id,
            "fecha_hora": dt.isoformat(),
            "estado": "programada",
            "motivo_consulta": motivo_consulta.strip(),
        })
        .execute()
    )
    cita_id = nueva_cita.data[0]["id"]
    doc_nombre = f"Dr(a). {doctor.data['nombre']} {doctor.data['apellido']}"

    return (
        f"✅ ¡Cita agendada exitosamente!\n\n"
        f"📋 Detalles:\n"
        f"  🆔 Cita #{cita_id}\n"
        f"  👤 Paciente: {paciente.data['nombre']} {paciente.data['apellido']}\n"
        f"  🦷 Doctor: {doc_nombre}\n"
        f"  📅 Fecha: {dt.strftime('%d/%m/%Y')}\n"
        f"  🕐 Hora: {dt.strftime('%H:%M')}\n"
        f"  📝 Motivo: {motivo_consulta.strip()}\n\n"
        f"Te enviaremos un recordatorio antes de tu cita. 😊"
    )


@tool
def consultar_historial_paciente(telegram_chat_id: str) -> str:
    """Consulta el historial clínico completo del paciente, incluyendo sus
    atenciones médicas previas (evoluciones).
    Args:
        telegram_chat_id: ID del chat de Telegram del paciente.
    """
    # 1. Obtener paciente
    paciente = (
        supabase.table("pacientes")
        .select("id, nombre, apellido")
        .eq("telefono", telegram_chat_id)
        .maybe_single()
        .execute()
    )
    if not paciente.data:
        return "❌ No estás registrado en la clínica."

    # 2. Obtener historia clínica
    historia = (
        supabase.table("historias_clinicas")
        .select("id, antecedentes_medicos, fecha_creacion")
        .eq("paciente_id", paciente.data["id"])
        .maybe_single()
        .execute()
    )
    if not historia.data:
        return "❌ No se encontró historia clínica. Contacta a recepción."

    # 3. Obtener evoluciones
    evoluciones = (
        supabase.table("atenciones_medicas")
        .select("diagnostico, tratamiento_realizado, observaciones, fecha_atencion")
        .eq("historia_id", historia.data["id"])
        .order("fecha_atencion", desc=True)
        .limit(10)
        .execute()
    )

    # 4. Formatear respuesta
    nombre = f"{paciente.data['nombre']} {paciente.data['apellido']}"
    antecedentes = historia.data.get("antecedentes_medicos") or "Sin antecedentes registrados."

    texto = (
        f"📂 Historia Clínica de {nombre}\n"
        f"📅 Creada: {historia.data['fecha_creacion'][:10]}\n"
        f"🏥 Antecedentes: {antecedentes}\n\n"
    )

    if not evoluciones.data:
        texto += "📝 Aún no hay atenciones médicas registradas."
    else:
        texto += f"📝 Últimas {len(evoluciones.data)} atenciones:\n"
        for i, evo in enumerate(evoluciones.data, 1):
            fecha = evo["fecha_atencion"][:10] if evo.get("fecha_atencion") else "N/D"
            texto += (
                f"\n── Atención #{i} ({fecha}) ──\n"
                f"  🔍 Diagnóstico: {evo['diagnostico']}\n"
                f"  💊 Tratamiento: {evo['tratamiento_realizado']}\n"
                f"  📌 Observaciones: {evo.get('observaciones') or 'Ninguna'}\n"
            )

    return texto


# ==================================================================
#  HERRAMIENTAS DEL AGENTE ASISTENTE MÉDICO
# ==================================================================

@tool
def actualizar_estado_cita(
    telegram_chat_id: str,
    cita_id: int,
    nuevo_estado: str
) -> str:
    """Cambia el estado de una cita. Solo puede ser usado por un odontólogo registrado.
    Args:
        telegram_chat_id: ID del chat de Telegram del doctor.
        cita_id: ID numérico de la cita a actualizar.
        nuevo_estado: Nuevo estado. Valores válidos: 'confirmada', 'asistida', 'cancelada', 'no_show'.
    """
    estados_validos = ["confirmada", "asistida", "cancelada", "no_show"]
    if nuevo_estado not in estados_validos:
        return f"❌ Estado inválido. Valores válidos: {', '.join(estados_validos)}."

    # 1. Verificar que quien llama es un odontólogo
    doctor = (
        supabase.table("personal")
        .select("id, nombre, apellido")
        .eq("telefono", telegram_chat_id)
        .eq("rol", "odontologo")
        .maybe_single()
        .execute()
    )
    if not doctor.data:
        return "❌ Solo los odontólogos pueden actualizar el estado de una cita."

    # 2. Verificar que la cita existe y pertenece a este doctor
    cita = (
        supabase.table("citas")
        .select("id, estado, odontologo_id")
        .eq("id", cita_id)
        .maybe_single()
        .execute()
    )
    if not cita.data:
        return f"❌ No se encontró la cita #{cita_id}."

    if cita.data["odontologo_id"] != doctor.data["id"]:
        return "❌ Esta cita no está asignada a ti. Solo puedes modificar tus propias citas."

    # 3. Actualizar estado
    supabase.table("citas").update({
        "estado": nuevo_estado
    }).eq("id", cita_id).execute()

    return (
        f"✅ Cita #{cita_id} actualizada.\n"
        f"  📌 Estado anterior: {cita.data['estado']}\n"
        f"  📌 Nuevo estado: {nuevo_estado}"
    )


@tool
def registrar_evolucion_medica(
    telegram_chat_id: str,
    cita_id: int,
    diagnostico: str,
    tratamiento_realizado: str,
    observaciones: str = ""
) -> str:
    """Registra la evolución médica (diagnóstico, tratamiento, observaciones) de una cita
    que ya fue marcada como 'asistida'. Solo puede ser usado por el odontólogo asignado.
    Args:
        telegram_chat_id: ID del chat de Telegram del doctor.
        cita_id: ID numérico de la cita atendida.
        diagnostico: Diagnóstico clínico.
        tratamiento_realizado: Descripción del tratamiento aplicado.
        observaciones: Notas adicionales (opcional).
    """
    # 1. Verificar que quien llama es un odontólogo
    doctor = (
        supabase.table("personal")
        .select("id, nombre")
        .eq("telefono", telegram_chat_id)
        .eq("rol", "odontologo")
        .maybe_single()
        .execute()
    )
    if not doctor.data:
        return "❌ Solo los odontólogos pueden registrar evoluciones médicas."

    # 2. Verificar la cita
    cita = (
        supabase.table("citas")
        .select("id, estado, odontologo_id, paciente_id")
        .eq("id", cita_id)
        .maybe_single()
        .execute()
    )
    if not cita.data:
        return f"❌ No se encontró la cita #{cita_id}."

    if cita.data["odontologo_id"] != doctor.data["id"]:
        return "❌ Esta cita no está asignada a ti."

    if cita.data["estado"] != "asistida":
        return f"❌ La cita debe estar en estado 'asistida' para registrar evolución. Estado actual: {cita.data['estado']}."

    # 3. Verificar que no exista ya una evolución para esta cita
    existente = (
        supabase.table("atenciones_medicas")
        .select("id")
        .eq("cita_id", cita_id)
        .maybe_single()
        .execute()
    )
    if existente.data:
        return f"❌ Ya existe una evolución registrada para la cita #{cita_id}."

    # 4. Obtener la historia clínica del paciente
    historia = (
        supabase.table("historias_clinicas")
        .select("id")
        .eq("paciente_id", cita.data["paciente_id"])
        .maybe_single()
        .execute()
    )
    if not historia.data:
        return "❌ Error: no se encontró la historia clínica del paciente."

    # 5. Insertar evolución
    supabase.table("atenciones_medicas").insert({
        "historia_id": historia.data["id"],
        "cita_id": cita_id,
        "diagnostico": diagnostico.strip(),
        "tratamiento_realizado": tratamiento_realizado.strip(),
        "observaciones": observaciones.strip() if observaciones else None,
    }).execute()

    return (
        f"✅ Evolución médica registrada para la cita #{cita_id}.\n"
        f"  🔍 Diagnóstico: {diagnostico.strip()}\n"
        f"  💊 Tratamiento: {tratamiento_realizado.strip()}\n"
        f"  📌 Observaciones: {observaciones.strip() or 'Ninguna'}"
    )


# ==================================================================
#  HERRAMIENTAS DEL AGENTE DE FACTURACIÓN
# ==================================================================

@tool
def registrar_pago(
    telegram_chat_id: str,
    cita_id: int,
    monto: float,
    metodo_pago: str
) -> str:
    """Registra el pago de una cita atendida.
    Args:
        telegram_chat_id: ID del chat de Telegram del usuario.
        cita_id: ID numérico de la cita a pagar.
        monto: Monto del pago en soles (S/).
        metodo_pago: Método de pago. Valores válidos: 'efectivo', 'tarjeta', 'yape', 'plin'.
    """
    metodos_validos = ["efectivo", "tarjeta", "yape", "plin"]
    if metodo_pago not in metodos_validos:
        return f"❌ Método de pago inválido. Valores válidos: {', '.join(metodos_validos)}."

    if monto <= 0:
        return "❌ El monto debe ser mayor a 0."

    # 1. Verificar que la cita existe y está en estado 'asistida'
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
        return f"❌ Solo se puede registrar pago para citas con estado 'asistida'. Estado actual: {cita.data['estado']}."

    # 2. Verificar que no exista un pago previo
    pago_existente = (
        supabase.table("pagos")
        .select("id, estado_pago")
        .eq("cita_id", cita_id)
        .maybe_single()
        .execute()
    )
    if pago_existente.data:
        estado = pago_existente.data["estado_pago"]
        if estado == "pagado":
            return f"❌ La cita #{cita_id} ya fue pagada."
        else:
            # Actualizar pago existente (estado 'pendiente' o 'fallido')
            supabase.table("pagos").update({
                "monto": monto,
                "metodo_pago": metodo_pago,
                "estado_pago": "pagado",
                "fecha_pago": datetime.now(TIMEZONE).isoformat(),
            }).eq("id", pago_existente.data["id"]).execute()

            return (
                f"✅ Pago actualizado para la cita #{cita_id}.\n"
                f"  💰 Monto: S/ {monto:.2f}\n"
                f"  💳 Método: {metodo_pago}\n"
                f"  📌 Estado: pagado"
            )

    # 3. Insertar nuevo pago
    supabase.table("pagos").insert({
        "cita_id": cita_id,
        "monto": monto,
        "metodo_pago": metodo_pago,
        "estado_pago": "pagado",
        "fecha_pago": datetime.now(TIMEZONE).isoformat(),
    }).execute()

    return (
        f"✅ ¡Pago registrado exitosamente!\n\n"
        f"  🆔 Cita: #{cita_id}\n"
        f"  💰 Monto: S/ {monto:.2f}\n"
        f"  💳 Método: {metodo_pago}\n"
        f"  ✔️ Estado: pagado\n\n"
        f"¡Gracias por tu pago! 😊"
    )


# ==================================================================
#  AGRUPACIÓN DE HERRAMIENTAS POR AGENTE
# ==================================================================

# Herramientas accesibles por el Agente de Recepción
tools_recepcion = [
    crear_paciente_y_historia,
    consultar_disponibilidad_agenda,
    agendar_cita,
    consultar_historial_paciente,
]

# Herramientas accesibles por el Agente Asistente Médico
tools_medico = [
    actualizar_estado_cita,
    registrar_evolucion_medica,
]

# Herramientas accesibles por el Agente de Facturación
tools_facturacion = [
    registrar_pago,
]

# Todas las herramientas (para referencia)
all_tools = tools_recepcion + tools_medico + tools_facturacion
