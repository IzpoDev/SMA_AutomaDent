# src/telegram/panel_personal.py — Panel Interactivo para Personal de la Clínica
# ==============================================================================
# Muestra un menú con botones InlineKeyboard cuando el personal usa /start.
# Implementa una máquina de estados via context.user_data["panel_step"] —
# sin usar ConversationHandler, para garantizar compatibilidad con el flujo
# de /start externo y mensajes de texto del usuario.
#
# Flujo híbrido:
#   - Botones: menú principal, selección de estado, selección de método de pago
#   - Texto libre: ingresar ID de cita, monto de pago
# ==============================================================================

from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
# pyrefly: ignore [missing-import]
from telegram.ext import ContextTypes

from src.utils.database import supabase
from src.utils.config import TIMEZONE
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ==============================================================================
#  CONSTANTES DE ESTADO (guardadas en context.user_data["panel_step"])
# ==============================================================================

STEP_IDLE = None                # Sin flujo activo → mensajes van al LLM
STEP_ACT_CITA_ID = "act_cita"  # Esperando ID de cita para actualizar estado
STEP_PAG_CITA_ID = "pag_cita"  # Esperando ID de cita para registrar pago
STEP_PAG_MONTO   = "pag_monto" # Esperando monto del pago
STEP_MSG_CITA_ID = "msg_cita"  # Esperando ID de cita para mensaje final

# Roles que tienen acceso al panel
ROLES_PERSONAL = {"odontologo", "recepcionista", "administrador"}

# ==============================================================================
#  TECLADOS
# ==============================================================================

_MENU_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("📅 Ver mis citas de hoy", callback_data="panel_ver_citas")],
    [InlineKeyboardButton("✅ Actualizar estado de cita", callback_data="panel_actualizar_cita")],
    [InlineKeyboardButton("💳 Registrar pago", callback_data="panel_registrar_pago")],
    [InlineKeyboardButton("📨 Enviar mensaje final al paciente", callback_data="panel_mensaje_final")],
])

_ESTADOS_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("✅ Confirmada", callback_data="estado_confirmada"),
     InlineKeyboardButton("✔️ Asistida", callback_data="estado_asistida")],
    [InlineKeyboardButton("❌ Cancelada", callback_data="estado_cancelada"),
     InlineKeyboardButton("⚠️ No Show", callback_data="estado_no_show")],
    [InlineKeyboardButton("« Cancelar", callback_data="panel_menu")],
])

_METODOS_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("💵 Efectivo", callback_data="metodo_efectivo"),
     InlineKeyboardButton("💳 Tarjeta", callback_data="metodo_tarjeta")],
    [InlineKeyboardButton("📱 Yape", callback_data="metodo_yape"),
     InlineKeyboardButton("📱 Plin", callback_data="metodo_plin")],
    [InlineKeyboardButton("« Cancelar", callback_data="panel_menu")],
])

def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Volver al menú principal", callback_data="panel_menu")]
    ])


# ==============================================================================
#  HELPERS INTERNOS
# ==============================================================================

def _get_cita_detalle(cita_id: int) -> Optional[dict]:
    """Obtiene el detalle completo de una cita con datos de paciente y odontólogo."""
    cita_res = (
        supabase.table("citas")
        .select("id, fecha_hora, estado, motivo_consulta, paciente_id, odontologo_id")
        .eq("id", cita_id)
        .limit(1)
        .execute()
    )
    if not cita_res.data:
        return None
    cita = cita_res.data[0]

    pac_res = (
        supabase.table("pacientes")
        .select("id, nombre, apellido, telefono")
        .eq("id", cita["paciente_id"])
        .limit(1)
        .execute()
    )
    cita["paciente"] = pac_res.data[0] if pac_res.data else {}

    doc_res = (
        supabase.table("personal")
        .select("nombre, apellido")
        .eq("id", cita["odontologo_id"])
        .limit(1)
        .execute()
    )
    cita["odontologo"] = doc_res.data[0] if doc_res.data else {}

    return cita


def _listar_citas_hoy(chat_id: str, user_role: str) -> str:
    """Lista citas del día actual. Administradores y recepcionistas ven todas;
    odontólogos ven solo las suyas."""
    hoy = datetime.now(TIMEZONE).date()
    inicio = datetime(hoy.year, hoy.month, hoy.day, 0, 0, 0, tzinfo=TIMEZONE).isoformat()
    fin    = datetime(hoy.year, hoy.month, hoy.day, 23, 59, 59, tzinfo=TIMEZONE).isoformat()

    query = (
        supabase.table("citas")
        .select("id, fecha_hora, estado, motivo_consulta, paciente_id, odontologo_id")
        .gte("fecha_hora", inicio)
        .lte("fecha_hora", fin)
        .order("fecha_hora")
    )

    if user_role == "odontologo":
        doc = (
            supabase.table("personal")
            .select("id")
            .eq("telefono", chat_id)
            .limit(1)
            .execute()
        )
        if not doc.data:
            return "❌ No se encontró tu perfil de odontólogo en la base de datos."
        query = query.eq("odontologo_id", doc.data[0]["id"])

    citas = query.execute()
    if not citas.data:
        return f"📭 No hay citas programadas para hoy ({hoy.strftime('%d/%m/%Y')})."

    pac_map = {
        p["id"]: f"{p['nombre']} {p['apellido']}"
        for p in (supabase.table("pacientes").select("id, nombre, apellido").execute().data or [])
    }
    doc_map = {
        d["id"]: f"Dr(a). {d['nombre']} {d['apellido']}"
        for d in (supabase.table("personal").select("id, nombre, apellido").execute().data or [])
    }

    _ESTADO_ICON = {
        "programada": "🕐", "confirmada": "✅", "asistida": "✔️",
        "cancelada": "❌", "no_show": "⚠️",
    }

    lineas = [f"<b>📅 Citas de hoy — {hoy.strftime('%d/%m/%Y')} ({len(citas.data)} citas):</b>"]
    for c in citas.data:
        dt   = datetime.fromisoformat(c["fecha_hora"])
        icon = _ESTADO_ICON.get(c["estado"], "•")
        lineas.append(
            f"\n<b>#{c['id']}</b> | {dt.strftime('%H:%M')} {icon} <i>{c['estado'].upper()}</i>\n"
            f"   👤 {pac_map.get(c['paciente_id'], '—')}\n"
            f"   🩺 {doc_map.get(c['odontologo_id'], '—')}\n"
            f"   📋 {c.get('motivo_consulta') or '—'}"
        )
    return "\n".join(lineas)


def _set_step(context: ContextTypes.DEFAULT_TYPE, step) -> None:
    """Guarda el paso actual del flujo del panel en user_data."""
    context.user_data["panel_step"] = step


def _clear_step(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Limpia el estado del panel (vuelve al flujo normal/LLM)."""
    context.user_data["panel_step"] = None
    context.user_data.pop("cita_id_act", None)
    context.user_data.pop("cita_id_pag", None)
    context.user_data.pop("monto_pag", None)
    context.user_data.pop("cita_id_msg", None)


# ==============================================================================
#  START PERSONAL — muestra el menú principal
# ==============================================================================

async def start_personal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía el menú interactivo de botones al personal de la clínica."""
    _clear_step(context)  # Asegurar que no haya flujo colgado al hacer /start
    rol    = context.user_data.get("rol", "personal")
    nombre = context.user_data.get("nombre_personal", "")
    saludo = f" <b>{nombre}</b>" if nombre else ""

    await update.message.reply_text(
        f"🔑 <b>Panel de Personal — AutomaDent</b>\n\n"
        f"Bienvenido(a){saludo} 👋\n"
        f"Rol: <b>{rol.upper()}</b>\n\n"
        f"¿Qué deseas hacer hoy?",
        parse_mode="HTML",
        reply_markup=_MENU_KEYBOARD,
    )


# ==============================================================================
#  HANDLE PANEL CALLBACK — maneja todos los botones del panel
# ==============================================================================

async def handle_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler directo para todos los botones del panel (panel_*, estado_*, metodo_*).

    No usa ConversationHandler. El estado se gestiona en context.user_data.
    """
    query = update.callback_query
    data  = query.data
    chat_id = str(update.effective_chat.id) if update.effective_chat else "desconocido"
    rol   = context.user_data.get("rol", "administrador")

    logger.info(f"🔮 [CALLBACK RECIBIDO] chat_id={chat_id} | rol={rol} | data='{data}'")

    try:
        await query.answer()  # Confirma el tap inmediatamente (evita el botón girando)

        # ── Menú principal ────────────────────────────────────────────────────────
        if data == "panel_menu":
            _clear_step(context)
            await query.edit_message_text(
                "🔑 <b>Panel de Personal — AutomaDent</b>\n\n¿Qué deseas hacer?",
                parse_mode="HTML",
                reply_markup=_MENU_KEYBOARD,
            )
            return

        # ── Ver citas de hoy ─────────────────────────────────────────────────────
        if data == "panel_ver_citas":
            logger.info(f"📅 [PANEL] Procesando ver citas para chat_id={chat_id}")
            texto = _listar_citas_hoy(chat_id, rol)
            await query.edit_message_text(
                texto, parse_mode="HTML", reply_markup=_back_keyboard()
            )
            return

        # ── Iniciar flujo: Actualizar estado ─────────────────────────────────────
        if data == "panel_actualizar_cita":
            _set_step(context, STEP_ACT_CITA_ID)
            await query.edit_message_text(
                "✏️ <b>Actualizar Estado de Cita</b>\n\n"
                "Escríbeme el <b>ID de la cita</b> que deseas actualizar:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Cancelar", callback_data="panel_menu")
                ]]),
            )
            return

        # ── Iniciar flujo: Registrar pago ─────────────────────────────────────────
        if data == "panel_registrar_pago":
            _set_step(context, STEP_PAG_CITA_ID)
            await query.edit_message_text(
                "💳 <b>Registrar Pago</b>\n\n"
                "Escríbeme el <b>ID de la cita</b> a cobrar:\n"
                "<i>(La cita debe estar en estado 'asistida')</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Cancelar", callback_data="panel_menu")
                ]]),
            )
            return

        # ── Iniciar flujo: Mensaje final ──────────────────────────────────────────
        if data == "panel_mensaje_final":
            _set_step(context, STEP_MSG_CITA_ID)
            await query.edit_message_text(
                "📨 <b>Mensaje Final al Paciente</b>\n\n"
                "Escríbeme el <b>ID de la cita</b> cuyo paciente recibirá\n"
                "el mensaje de finalización:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Cancelar", callback_data="panel_menu")
                ]]),
            )
            return

        # ── Selección de nuevo estado (flujo actualizar) ──────────────────────────
        if data.startswith("estado_"):
            logger.info(f"✏️ [PANEL] Aplicando nuevo estado: {data}")
            await _aplicar_nuevo_estado(query, context, chat_id, rol, data)
            return

        # ── Selección de método de pago (flujo pago) ──────────────────────────────
        if data.startswith("metodo_"):
            logger.info(f"💳 [PANEL] Aplicando pago método: {data}")
            await _aplicar_pago(query, context, chat_id, rol, data)
            return

    except Exception as e:
        logger.error(f"❌ [CALLBACK ERROR] Error procesando callback data='{data}': {e}", exc_info=True)
        try:
            await query.edit_message_text(
                f"⚠️ Ocurrió un error al procesar la solicitud: <code>{e}</code>",
                parse_mode="HTML",
                reply_markup=_back_keyboard()
            )
        except Exception as e2:
            logger.error(f"❌ [CALLBACK ERROR] No se pudo enviar mensaje de error: {e2}")


# ==============================================================================
#  HANDLE PANEL TEXTO — maneja el texto escrito por el usuario dentro de un flujo
# ==============================================================================

async def handle_panel_texto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Interpreta el texto enviado por el usuario según el paso activo del panel.

    Llamado desde handle_message en bot.py cuando panel_step != None.
    """
    step  = context.user_data.get("panel_step")
    texto = update.message.text.strip()

    if step == STEP_ACT_CITA_ID:
        await _flujo_act_recibir_cita_id(update, context, texto)

    elif step == STEP_PAG_CITA_ID:
        await _flujo_pag_recibir_cita_id(update, context, texto)

    elif step == STEP_PAG_MONTO:
        await _flujo_pag_recibir_monto(update, context, texto)

    elif step == STEP_MSG_CITA_ID:
        await _flujo_msg_recibir_cita_id(update, context, texto)

    else:
        # Estado desconocido — limpiar y mostrar menú
        _clear_step(context)
        await update.message.reply_text(
            "¿Qué deseas hacer?",
            reply_markup=_MENU_KEYBOARD,
        )


# ==============================================================================
#  FLUJOS INTERNOS — ACTUALIZAR ESTADO
# ==============================================================================

async def _flujo_act_recibir_cita_id(
    update: Update, context: ContextTypes.DEFAULT_TYPE, texto: str
) -> None:
    """Recibe el ID de cita y muestra botones de selección de estado."""
    if not texto.isdigit():
        await update.message.reply_text(
            "❌ Ingresa solo el número del ID de la cita. Ej: <b>15</b>",
            parse_mode="HTML",
        )
        return

    cita_id = int(texto)
    cita    = _get_cita_detalle(cita_id)
    if not cita:
        await update.message.reply_text(
            f"❌ No encontré la cita <b>#{cita_id}</b>. Verifica el ID e intenta de nuevo:",
            parse_mode="HTML",
        )
        return

    context.user_data["cita_id_act"] = cita_id
    pac = cita["paciente"]
    dt  = datetime.fromisoformat(cita["fecha_hora"])

    await update.message.reply_text(
        f"<b>Cita #{cita_id}</b>\n"
        f"👤 Paciente: <b>{pac.get('nombre', '')} {pac.get('apellido', '')}</b>\n"
        f"📅 Fecha: {dt.strftime('%d/%m/%Y %H:%M')}\n"
        f"📋 Motivo: {cita.get('motivo_consulta') or '—'}\n"
        f"📌 Estado actual: <i>{cita['estado']}</i>\n\n"
        f"Selecciona el <b>nuevo estado</b>:",
        parse_mode="HTML",
        reply_markup=_ESTADOS_KEYBOARD,
    )
    # Mantener el step en ACT_CITA_ID — el siguiente paso es via botón (estado_*)


async def _aplicar_nuevo_estado(
    query, context: ContextTypes.DEFAULT_TYPE,
    chat_id: str, rol: str, data: str
) -> None:
    """Aplica el cambio de estado a la cita y notifica al paciente."""
    nuevo_estado = data.replace("estado_", "")
    cita_id      = context.user_data.get("cita_id_act")

    if not cita_id:
        await query.edit_message_text(
            "❌ No hay cita seleccionada. Vuelve al menú e inténtalo de nuevo.",
            reply_markup=_back_keyboard(),
        )
        _clear_step(context)
        return

    cita_res = (
        supabase.table("citas")
        .select("estado, paciente_id")
        .eq("id", cita_id)
        .limit(1)
        .execute()
    )
    if not cita_res.data:
        await query.edit_message_text(
            f"❌ Cita #{cita_id} no encontrada.", reply_markup=_back_keyboard()
        )
        _clear_step(context)
        return

    estado_anterior = cita_res.data[0]["estado"]
    supabase.table("citas").update({"estado": nuevo_estado}).eq("id", cita_id).execute()

    paciente_id = cita_res.data[0].get("paciente_id")
    if paciente_id:
        from src.utils.notificaciones import notificar_cambio_estado_cita
        notificar_cambio_estado_cita(supabase, cita_id, paciente_id, nuevo_estado)

    logger.info(f"[PANEL] Cita #{cita_id}: {estado_anterior} → {nuevo_estado} por {chat_id} ({rol})")
    _clear_step(context)

    await query.edit_message_text(
        f"✅ <b>Estado actualizado correctamente</b>\n\n"
        f"Cita <b>#{cita_id}</b>\n"
        f"<i>{estado_anterior}</i>  →  <b>{nuevo_estado}</b>\n\n"
        f"El paciente fue notificado automáticamente por Telegram.",
        parse_mode="HTML",
        reply_markup=_back_keyboard(),
    )


# ==============================================================================
#  FLUJOS INTERNOS — REGISTRAR PAGO
# ==============================================================================

async def _flujo_pag_recibir_cita_id(
    update: Update, context: ContextTypes.DEFAULT_TYPE, texto: str
) -> None:
    """Recibe el ID de cita para el pago y valida que esté en estado 'asistida'."""
    if not texto.isdigit():
        await update.message.reply_text(
            "❌ Ingresa solo el número del ID de la cita. Ej: <b>15</b>",
            parse_mode="HTML",
        )
        return

    cita_id = int(texto)
    cita    = _get_cita_detalle(cita_id)
    if not cita:
        await update.message.reply_text(
            f"❌ No encontré la cita <b>#{cita_id}</b>. Verifica el ID e intenta de nuevo:",
            parse_mode="HTML",
        )
        return

    if cita["estado"] != "asistida":
        await update.message.reply_text(
            f"❌ La cita <b>#{cita_id}</b> está en estado <i>{cita['estado']}</i>.\n"
            f"Solo se pueden cobrar citas en estado <b>asistida</b>.\n\n"
            f"Ingresa otro ID de cita:",
            parse_mode="HTML",
        )
        return

    context.user_data["cita_id_pag"] = cita_id
    _set_step(context, STEP_PAG_MONTO)

    pac = cita["paciente"]
    doc = cita["odontologo"]
    dt  = datetime.fromisoformat(cita["fecha_hora"])

    await update.message.reply_text(
        f"✅ <b>Cita #{cita_id} — Lista para cobrar</b>\n\n"
        f"👤 Paciente: <b>{pac.get('nombre', '')} {pac.get('apellido', '')}</b>\n"
        f"🩺 Doctor: Dr(a). {doc.get('nombre', '')} {doc.get('apellido', '')}\n"
        f"📅 Fecha: {dt.strftime('%d/%m/%Y %H:%M')}\n"
        f"📋 Motivo: {cita.get('motivo_consulta') or '—'}\n\n"
        f"Ingresa el <b>monto a cobrar</b> en soles (S/). Ej: <b>120.50</b>",
        parse_mode="HTML",
    )


async def _flujo_pag_recibir_monto(
    update: Update, context: ContextTypes.DEFAULT_TYPE, texto: str
) -> None:
    """Recibe el monto y muestra botones de método de pago."""
    try:
        monto = float(texto.replace(",", "."))
        if monto <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Ingresa un monto válido mayor a 0. Ej: <b>120.50</b>",
            parse_mode="HTML",
        )
        return

    context.user_data["monto_pag"] = monto

    await update.message.reply_text(
        f"Monto: <b>S/ {monto:.2f}</b>\n\n"
        f"Selecciona el <b>método de pago</b>:",
        parse_mode="HTML",
        reply_markup=_METODOS_KEYBOARD,
    )
    # El siguiente paso es via botón (metodo_*) — no se cambia el step aquí


async def _aplicar_pago(
    query, context: ContextTypes.DEFAULT_TYPE,
    chat_id: str, rol: str, data: str
) -> None:
    """Registra el pago en Supabase."""
    metodo  = data.replace("metodo_", "")
    cita_id = context.user_data.get("cita_id_pag")
    monto   = context.user_data.get("monto_pag")

    if not cita_id or monto is None:
        await query.edit_message_text(
            "❌ Faltan datos del pago. Vuelve al menú e inténtalo de nuevo.",
            reply_markup=_back_keyboard(),
        )
        _clear_step(context)
        return

    try:
        supabase.table("pagos").insert({
            "cita_id":     cita_id,
            "monto":       monto,
            "metodo_pago": metodo,
            "estado_pago": "pagado",
            "fecha_pago":  datetime.now(TIMEZONE).isoformat(),
        }).execute()
    except Exception as e:
        logger.error(f"[PANEL] Error registrando pago: {e}")
        await query.edit_message_text(
            "❌ Ocurrió un error al registrar el pago. Inténtalo de nuevo.",
            reply_markup=_back_keyboard(),
        )
        _clear_step(context)
        return

    logger.info(f"[PANEL] Pago S/{monto:.2f} ({metodo}) cita #{cita_id} por {chat_id} ({rol})")
    _clear_step(context)

    await query.edit_message_text(
        f"✅ <b>Pago registrado exitosamente</b>\n\n"
        f"Cita: <b>#{cita_id}</b>\n"
        f"Monto: <b>S/ {monto:.2f}</b>\n"
        f"Método: <b>{metodo.capitalize()}</b>\n"
        f"Estado: <b>Pagado</b>",
        parse_mode="HTML",
        reply_markup=_back_keyboard(),
    )


# ==============================================================================
#  FLUJOS INTERNOS — MENSAJE FINAL AL PACIENTE
# ==============================================================================

async def _flujo_msg_recibir_cita_id(
    update: Update, context: ContextTypes.DEFAULT_TYPE, texto: str
) -> None:
    """Recibe el ID de cita y envía el mensaje de finalización al paciente."""
    if not texto.isdigit():
        await update.message.reply_text(
            "❌ Ingresa solo el número del ID de la cita. Ej: <b>15</b>",
            parse_mode="HTML",
        )
        return

    cita_id = int(texto)
    cita    = _get_cita_detalle(cita_id)
    if not cita:
        await update.message.reply_text(
            f"❌ No encontré la cita <b>#{cita_id}</b>. Verifica el ID e intenta de nuevo:",
            parse_mode="HTML",
        )
        return

    pac       = cita["paciente"]
    doc       = cita["odontologo"]
    pac_chat  = pac.get("telefono")

    if not pac_chat:
        await update.message.reply_text(
            f"❌ El paciente de la cita <b>#{cita_id}</b> no tiene Telegram registrado.",
            parse_mode="HTML",
            reply_markup=_back_keyboard(),
        )
        _clear_step(context)
        return

    dt          = datetime.fromisoformat(cita["fecha_hora"])
    nombre_pac  = f"{pac.get('nombre', '')} {pac.get('apellido', '')}".strip()
    nombre_doc  = f"Dr(a). {doc.get('nombre', '')} {doc.get('apellido', '')}".strip()

    mensaje_paciente = (
        f"👋 Hola <b>{nombre_pac}</b>,\n\n"
        f"✅ Tu cita del <b>{dt.strftime('%d/%m/%Y')}</b> a las "
        f"<b>{dt.strftime('%H:%M')}</b> con <b>{nombre_doc}</b> "
        f"ha concluido exitosamente.\n\n"
        f"📋 <b>Resumen de tu visita:</b>\n"
        f"   • Motivo: {cita.get('motivo_consulta') or '—'}\n"
        f"   • Estado: <b>{cita['estado'].capitalize()}</b>\n\n"
        f"🦷 ¡Gracias por confiar en <b>AutomaDent</b>!\n"
        f"Recuerda mantener tu higiene dental y agenda tu próxima visita cuando lo necesites.\n\n"
        f"<i>Si tienes alguna duda, escríbenos cuando gustes.</i>"
    )

    from src.utils.notificaciones import _enviar_mensaje_telegram
    enviado = _enviar_mensaje_telegram(pac_chat, mensaje_paciente)

    logger.info(
        f"[PANEL] Msg final cita #{cita_id} → paciente chat {pac_chat}: "
        f"{'OK' if enviado else 'FALLO'}"
    )
    _clear_step(context)

    if enviado:
        await update.message.reply_text(
            f"✅ <b>Mensaje enviado exitosamente</b>\n\n"
            f"Cita: <b>#{cita_id}</b>\n"
            f"Paciente: <b>{nombre_pac}</b>\n\n"
            f"<i>El paciente recibió el resumen de su visita por Telegram.</i>",
            parse_mode="HTML",
            reply_markup=_back_keyboard(),
        )
    else:
        await update.message.reply_text(
            f"⚠️ <b>No se pudo enviar el mensaje</b>\n\n"
            f"Verifica que el paciente haya iniciado el chat con el bot.\n"
            f"<i>Chat ID: {pac_chat}</i>",
            parse_mode="HTML",
            reply_markup=_back_keyboard(),
        )
