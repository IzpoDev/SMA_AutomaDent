# src/telegram/panel_personal.py — Panel Interactivo para Personal de la Clínica
# ==============================================================================
# Muestra un menú con botones InlineKeyboard cuando el personal usa /start.
# Maneja 4 acciones directas (sin pasar por el agente LLM):
#   1. Ver citas del día
#   2. Actualizar estado de una cita
#   3. Registrar pago de una cita
#   4. Enviar mensaje de finalización al paciente
# ==============================================================================

import asyncio
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
# pyrefly: ignore [missing-import]
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from src.utils.database import supabase
from src.utils.config import TIMEZONE
from src.utils.notificaciones import notificar_paciente
from src.utils.helpers import sanitize_html
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ─── Estados de conversación ──────────────────────────────────────────────────
# Actualizar estado
ACT_ESPERANDO_CITA_ID = 10
ACT_ESPERANDO_NUEVO_ESTADO = 11

# Registrar pago
PAG_ESPERANDO_CITA_ID = 20
PAG_ESPERANDO_MONTO = 21
PAG_ESPERANDO_METODO = 22

# Mensaje final
MSG_ESPERANDO_CITA_ID = 30

# ─── Constantes ───────────────────────────────────────────────────────────────
_ESTADOS_VALIDOS = ["confirmada", "asistida", "cancelada", "no_show"]
_METODOS_VALIDOS = ["efectivo", "tarjeta", "yape", "plin"]
_ROLES_PERSONAL = {"odontologo", "recepcionista", "administrador"}

# ─── Teclado principal del panel ─────────────────────────────────────────────
_MENU_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("📅 Ver mis citas", callback_data="panel_ver_citas")],
    [InlineKeyboardButton("✅ Actualizar estado de cita", callback_data="panel_actualizar_cita")],
    [InlineKeyboardButton("💳 Registrar pago", callback_data="panel_registrar_pago")],
    [InlineKeyboardButton("📨 Enviar mensaje final al paciente", callback_data="panel_mensaje_final")],
])


# ==============================================================================
#  HELPERS INTERNOS
# ==============================================================================

def _get_personal_id(chat_id: str) -> Optional[int]:
    """Obtiene el ID del personal a partir de su chat_id de Telegram."""
    res = (
        supabase.table("personal")
        .select("id")
        .eq("telefono", chat_id)
        .limit(1)
        .execute()
    )
    return res.data[0]["id"] if res.data else None


def _get_cita_detalle(cita_id: int) -> Optional[dict]:
    """Obtiene el detalle de una cita (con nombre del paciente y odontólogo)."""
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

    # Nombre del paciente
    pac = (
        supabase.table("pacientes")
        .select("id, nombre, apellido, telefono")
        .eq("id", cita["paciente_id"])
        .limit(1)
        .execute()
    )
    cita["paciente"] = pac.data[0] if pac.data else {}

    # Nombre del odontólogo
    doc = (
        supabase.table("personal")
        .select("nombre, apellido")
        .eq("id", cita["odontologo_id"])
        .limit(1)
        .execute()
    )
    cita["odontologo"] = doc.data[0] if doc.data else {}

    return cita


def _listar_citas_personal(chat_id: str, user_role: str) -> str:
    """Lista las citas del día para el personal según su rol.

    - Administrador/Recepcionista: todas las citas de hoy.
    - Odontólogo: solo sus propias citas de hoy.
    """
    hoy = datetime.now(TIMEZONE).date()
    inicio = datetime(hoy.year, hoy.month, hoy.day, 0, 0, 0, tzinfo=TIMEZONE).isoformat()
    fin = datetime(hoy.year, hoy.month, hoy.day, 23, 59, 59, tzinfo=TIMEZONE).isoformat()

    query = (
        supabase.table("citas")
        .select("id, fecha_hora, estado, motivo_consulta, paciente_id, odontologo_id")
        .gte("fecha_hora", inicio)
        .lte("fecha_hora", fin)
        .order("fecha_hora")
    )

    if user_role == "odontologo":
        personal_id = _get_personal_id(chat_id)
        if not personal_id:
            return "❌ No se encontró tu perfil en la base de datos."
        query = query.eq("odontologo_id", personal_id)

    citas = query.execute()
    if not citas.data:
        return "📭 No hay citas programadas para hoy."

    pac_map = {
        p["id"]: f"{p['nombre']} {p['apellido']}"
        for p in (supabase.table("pacientes").select("id, nombre, apellido").execute().data or [])
    }
    doc_map = {
        d["id"]: f"Dr(a). {d['nombre']} {d['apellido']}"
        for d in (supabase.table("personal").select("id, nombre, apellido").execute().data or [])
    }

    lineas = [f"<b>📅 Citas de hoy — {hoy.strftime('%d/%m/%Y')} ({len(citas.data)}):</b>"]
    for c in citas.data:
        dt = datetime.fromisoformat(c["fecha_hora"])
        estado_icon = {
            "programada": "🕐", "confirmada": "✅", "asistida": "✔️",
            "cancelada": "❌", "no_show": "⚠️",
        }.get(c["estado"], "•")
        lineas.append(
            f"\n<b>#{c['id']}</b> | {dt.strftime('%H:%M')} {estado_icon} <i>{c['estado'].upper()}</i>\n"
            f"   👤 {pac_map.get(c['paciente_id'], '—')}\n"
            f"   🩺 {doc_map.get(c['odontologo_id'], '—')}\n"
            f"   📋 {c.get('motivo_consulta') or '—'}"
        )
    return "\n".join(lineas)


# ==============================================================================
#  HANDLER PRINCIPAL: /start para personal
# ==============================================================================

async def start_personal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía el menú interactivo al personal de la clínica."""
    rol = context.user_data.get("rol", "personal")
    nombre = context.user_data.get("nombre_personal", "")
    saludo_nombre = f" <b>{nombre}</b>" if nombre else ""

    await update.message.reply_text(
        f"🔑 <b>Panel de Personal — AutomaDent</b>\n\n"
        f"Bienvenido(a){saludo_nombre} 👋\n"
        f"Rol: <b>{rol.upper()}</b>\n\n"
        f"¿Qué deseas hacer hoy?",
        parse_mode="HTML",
        reply_markup=_MENU_KEYBOARD,
    )


# ==============================================================================
#  HANDLER DE CALLBACKS (botones del menú)
# ==============================================================================

async def callback_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja los botones del panel de personal."""
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = str(update.effective_chat.id)
    user_role = context.user_data.get("rol", "administrador")

    # ── Ver citas ─────────────────────────────────────────────────────────────
    if data == "panel_ver_citas":
        texto = _listar_citas_personal(chat_id, user_role)
        await query.edit_message_text(
            texto, parse_mode="HTML", reply_markup=_back_keyboard()
        )
        return ConversationHandler.END

    # ── Actualizar estado ─────────────────────────────────────────────────────
    elif data == "panel_actualizar_cita":
        await query.edit_message_text(
            "✏️ <b>Actualizar Estado de Cita</b>\n\n"
            "Ingresa el <b>ID de la cita</b> a actualizar:",
            parse_mode="HTML",
            reply_markup=_back_keyboard(),
        )
        return ACT_ESPERANDO_CITA_ID

    # ── Registrar pago ────────────────────────────────────────────────────────
    elif data == "panel_registrar_pago":
        await query.edit_message_text(
            "💳 <b>Registrar Pago</b>\n\n"
            "Ingresa el <b>ID de la cita</b> a cobrar:\n"
            "<i>(La cita debe estar en estado 'asistida')</i>",
            parse_mode="HTML",
            reply_markup=_back_keyboard(),
        )
        return PAG_ESPERANDO_CITA_ID

    # ── Mensaje final al paciente ─────────────────────────────────────────────
    elif data == "panel_mensaje_final":
        await query.edit_message_text(
            "📨 <b>Mensaje Final al Paciente</b>\n\n"
            "Ingresa el <b>ID de la cita</b> cuyo paciente recibirá el mensaje de finalización:",
            parse_mode="HTML",
            reply_markup=_back_keyboard(),
        )
        return MSG_ESPERANDO_CITA_ID

    # ── Volver al menú ────────────────────────────────────────────────────────
    elif data == "panel_menu":
        await query.edit_message_text(
            "🔑 <b>Panel de Personal — AutomaDent</b>\n\n¿Qué deseas hacer?",
            parse_mode="HTML",
            reply_markup=_MENU_KEYBOARD,
        )
        return ConversationHandler.END

    return ConversationHandler.END


# ==============================================================================
#  FLUJO: Actualizar Estado de Cita
# ==============================================================================

async def act_recibir_cita_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el ID de cita para actualizar estado."""
    texto = update.message.text.strip()
    if not texto.isdigit():
        await update.message.reply_text("❌ Ingresa un número válido para el ID de la cita.")
        return ACT_ESPERANDO_CITA_ID

    cita_id = int(texto)
    cita = _get_cita_detalle(cita_id)
    if not cita:
        await update.message.reply_text(f"❌ No se encontró la cita #{cita_id}. Intenta de nuevo:")
        return ACT_ESPERANDO_CITA_ID

    context.user_data["cita_id_act"] = cita_id
    pac = cita["paciente"]
    dt = datetime.fromisoformat(cita["fecha_hora"])

    estados_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirmada", callback_data="estado_confirmada"),
         InlineKeyboardButton("✔️ Asistida", callback_data="estado_asistida")],
        [InlineKeyboardButton("❌ Cancelada", callback_data="estado_cancelada"),
         InlineKeyboardButton("⚠️ No Show", callback_data="estado_no_show")],
        [InlineKeyboardButton("« Volver al menú", callback_data="panel_menu")],
    ])

    await update.message.reply_text(
        f"<b>Cita #{cita_id}</b>\n"
        f"👤 Paciente: {pac.get('nombre', '')} {pac.get('apellido', '')}\n"
        f"📅 Fecha: {dt.strftime('%d/%m/%Y %H:%M')}\n"
        f"📌 Estado actual: <i>{cita['estado']}</i>\n\n"
        f"Selecciona el <b>nuevo estado</b>:",
        parse_mode="HTML",
        reply_markup=estados_keyboard,
    )
    return ACT_ESPERANDO_NUEVO_ESTADO


async def act_recibir_nuevo_estado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Aplica el nuevo estado a la cita."""
    query = update.callback_query
    await query.answer()

    if query.data == "panel_menu":
        await query.edit_message_text(
            "🔑 <b>Panel de Personal — AutomaDent</b>\n\n¿Qué deseas hacer?",
            parse_mode="HTML",
            reply_markup=_MENU_KEYBOARD,
        )
        return ConversationHandler.END

    nuevo_estado = query.data.replace("estado_", "")
    cita_id = context.user_data.get("cita_id_act")
    chat_id = str(update.effective_chat.id)
    user_role = context.user_data.get("rol", "administrador")

    if user_role not in _ROLES_PERSONAL:
        await query.edit_message_text("❌ Sin permisos para cambiar estado de citas.")
        return ConversationHandler.END

    # Aplicar cambio
    cita_res = (
        supabase.table("citas")
        .select("estado, paciente_id")
        .eq("id", cita_id)
        .limit(1)
        .execute()
    )
    if not cita_res.data:
        await query.edit_message_text(f"❌ Cita #{cita_id} no encontrada.")
        return ConversationHandler.END

    estado_anterior = cita_res.data[0]["estado"]
    supabase.table("citas").update({"estado": nuevo_estado}).eq("id", cita_id).execute()

    # Notificar al paciente
    paciente_id = cita_res.data[0].get("paciente_id")
    if paciente_id:
        from src.utils.notificaciones import notificar_cambio_estado_cita
        notificar_cambio_estado_cita(supabase, cita_id, paciente_id, nuevo_estado)

    logger.info(f"[PANEL] Cita #{cita_id}: {estado_anterior} → {nuevo_estado} por {chat_id}")

    await query.edit_message_text(
        f"✅ <b>Estado actualizado</b>\n\n"
        f"Cita <b>#{cita_id}</b>: <i>{estado_anterior}</i> → <b>{nuevo_estado}</b>\n"
        f"El paciente fue notificado automáticamente.",
        parse_mode="HTML",
        reply_markup=_back_keyboard(),
    )
    return ConversationHandler.END


# ==============================================================================
#  FLUJO: Registrar Pago
# ==============================================================================

async def pag_recibir_cita_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el ID de cita para registrar pago."""
    texto = update.message.text.strip()
    if not texto.isdigit():
        await update.message.reply_text("❌ Ingresa un número válido para el ID de la cita.")
        return PAG_ESPERANDO_CITA_ID

    cita_id = int(texto)
    cita = _get_cita_detalle(cita_id)
    if not cita:
        await update.message.reply_text(f"❌ No se encontró la cita #{cita_id}. Intenta de nuevo:")
        return PAG_ESPERANDO_CITA_ID

    if cita["estado"] != "asistida":
        await update.message.reply_text(
            f"❌ La cita #{cita_id} está en estado <b>{cita['estado']}</b>.\n"
            f"Solo se pueden cobrar citas en estado <b>asistida</b>.\n\n"
            f"Ingresa otro ID de cita:",
            parse_mode="HTML",
        )
        return PAG_ESPERANDO_CITA_ID

    pac = cita["paciente"]
    dt = datetime.fromisoformat(cita["fecha_hora"])
    context.user_data["cita_id_pag"] = cita_id

    await update.message.reply_text(
        f"<b>Cita #{cita_id}</b> — Listo para cobrar\n"
        f"👤 Paciente: {pac.get('nombre', '')} {pac.get('apellido', '')}\n"
        f"📅 Fecha: {dt.strftime('%d/%m/%Y %H:%M')}\n"
        f"📋 Motivo: {cita.get('motivo_consulta') or '—'}\n\n"
        f"Ingresa el <b>monto a cobrar</b> (S/):",
        parse_mode="HTML",
    )
    return PAG_ESPERANDO_MONTO


async def pag_recibir_monto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el monto de pago."""
    texto = update.message.text.strip().replace(",", ".")
    try:
        monto = float(texto)
        if monto <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Ingresa un monto válido mayor a 0. Ej: 120.50")
        return PAG_ESPERANDO_MONTO

    context.user_data["monto_pag"] = monto

    metodos_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 Efectivo", callback_data="metodo_efectivo"),
         InlineKeyboardButton("💳 Tarjeta", callback_data="metodo_tarjeta")],
        [InlineKeyboardButton("📱 Yape", callback_data="metodo_yape"),
         InlineKeyboardButton("📱 Plin", callback_data="metodo_plin")],
        [InlineKeyboardButton("« Volver al menú", callback_data="panel_menu")],
    ])

    await update.message.reply_text(
        f"Monto: <b>S/ {monto:.2f}</b>\n\nSelecciona el <b>método de pago</b>:",
        parse_mode="HTML",
        reply_markup=metodos_keyboard,
    )
    return PAG_ESPERANDO_METODO


async def pag_recibir_metodo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Aplica el registro de pago."""
    query = update.callback_query
    await query.answer()

    if query.data == "panel_menu":
        await query.edit_message_text(
            "🔑 <b>Panel de Personal — AutomaDent</b>\n\n¿Qué deseas hacer?",
            parse_mode="HTML",
            reply_markup=_MENU_KEYBOARD,
        )
        return ConversationHandler.END

    metodo = query.data.replace("metodo_", "")
    cita_id = context.user_data.get("cita_id_pag")
    monto = context.user_data.get("monto_pag")
    chat_id = str(update.effective_chat.id)
    user_role = context.user_data.get("rol", "administrador")

    if user_role not in _ROLES_PERSONAL:
        await query.edit_message_text("❌ Sin permisos para registrar pagos.")
        return ConversationHandler.END

    supabase.table("pagos").insert({
        "cita_id": cita_id,
        "monto": monto,
        "metodo_pago": metodo,
        "estado_pago": "pagado",
        "fecha_pago": datetime.now(TIMEZONE).isoformat(),
    }).execute()

    logger.info(f"[PANEL] Pago S/{monto:.2f} ({metodo}) para cita #{cita_id} por {chat_id}")

    await query.edit_message_text(
        f"✅ <b>Pago registrado exitosamente</b>\n\n"
        f"Cita: <b>#{cita_id}</b>\n"
        f"Monto: <b>S/ {monto:.2f}</b>\n"
        f"Método: <b>{metodo.capitalize()}</b>",
        parse_mode="HTML",
        reply_markup=_back_keyboard(),
    )
    return ConversationHandler.END


# ==============================================================================
#  FLUJO: Mensaje Final al Paciente
# ==============================================================================

async def msg_recibir_cita_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el ID de cita y envía el mensaje de finalización al paciente."""
    texto = update.message.text.strip()
    if not texto.isdigit():
        await update.message.reply_text("❌ Ingresa un número válido para el ID de la cita.")
        return MSG_ESPERANDO_CITA_ID

    cita_id = int(texto)
    cita = _get_cita_detalle(cita_id)
    if not cita:
        await update.message.reply_text(f"❌ No se encontró la cita #{cita_id}. Intenta de nuevo:")
        return MSG_ESPERANDO_CITA_ID

    pac = cita["paciente"]
    pac_chat_id = pac.get("telefono")
    if not pac_chat_id:
        await update.message.reply_text(
            f"❌ El paciente de la cita #{cita_id} no tiene un Telegram registrado."
        )
        return ConversationHandler.END

    dt = datetime.fromisoformat(cita["fecha_hora"])
    doc = cita["odontologo"]
    nombre_doc = f"Dr(a). {doc.get('nombre', '')} {doc.get('apellido', '')}".strip()
    nombre_pac = f"{pac.get('nombre', '')} {pac.get('apellido', '')}".strip()

    mensaje_paciente = (
        f"👋 Hola <b>{nombre_pac}</b>,\n\n"
        f"✅ Tu cita del <b>{dt.strftime('%d/%m/%Y')}</b> a las <b>{dt.strftime('%H:%M')}</b> "
        f"con <b>{nombre_doc}</b> ha concluido exitosamente.\n\n"
        f"📋 <b>Detalle de tu visita:</b>\n"
        f"   • Motivo: {cita.get('motivo_consulta') or '—'}\n"
        f"   • Estado: {cita['estado'].capitalize()}\n\n"
        f"🦷 ¡Gracias por confiar en <b>AutomaDent</b>! "
        f"Recuerda mantener tu higiene dental y agenda tu próxima visita cuando lo necesites.\n\n"
        f"<i>Si tienes alguna duda, escríbenos cuando gustes.</i>"
    )

    from src.utils.notificaciones import _enviar_mensaje_telegram
    enviado = _enviar_mensaje_telegram(pac_chat_id, mensaje_paciente)

    logger.info(
        f"[PANEL] Mensaje final cita #{cita_id} → paciente chat_id {pac_chat_id}: "
        f"{'OK' if enviado else 'FALLO'}"
    )

    if enviado:
        await update.message.reply_text(
            f"✅ <b>Mensaje enviado exitosamente</b>\n\n"
            f"Cita: <b>#{cita_id}</b>\n"
            f"Paciente: <b>{nombre_pac}</b>\n\n"
            f"<i>El paciente recibió el resumen de su visita.</i>",
            parse_mode="HTML",
            reply_markup=_back_keyboard(),
        )
    else:
        await update.message.reply_text(
            f"⚠️ No se pudo enviar el mensaje al paciente (chat_id: {pac_chat_id}).\n"
            f"Verifica que el paciente tenga activo el chat con el bot.",
            reply_markup=_back_keyboard(),
        )
    return ConversationHandler.END


# ==============================================================================
#  UTILIDAD: Teclado "Volver al menú"
# ==============================================================================

def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("« Volver al menú", callback_data="panel_menu")]
    ])


# ==============================================================================
#  CONSTRUCCIÓN DEL ConversationHandler
# ==============================================================================

def build_panel_conversation_handler() -> ConversationHandler:
    """Construye el ConversationHandler completo del panel de personal.

    Gestiona los flujos de:
    - Actualizar estado de cita (2 pasos)
    - Registrar pago (3 pasos)
    - Enviar mensaje final al paciente (1 paso)
    """
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(callback_panel, pattern="^panel_"),
        ],
        states={
            # Actualizar estado
            ACT_ESPERANDO_CITA_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, act_recibir_cita_id),
                CallbackQueryHandler(callback_panel, pattern="^panel_menu$"),
            ],
            ACT_ESPERANDO_NUEVO_ESTADO: [
                CallbackQueryHandler(act_recibir_nuevo_estado, pattern="^(estado_|panel_menu)"),
            ],
            # Registrar pago
            PAG_ESPERANDO_CITA_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, pag_recibir_cita_id),
                CallbackQueryHandler(callback_panel, pattern="^panel_menu$"),
            ],
            PAG_ESPERANDO_MONTO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, pag_recibir_monto),
            ],
            PAG_ESPERANDO_METODO: [
                CallbackQueryHandler(pag_recibir_metodo, pattern="^(metodo_|panel_menu)"),
            ],
            # Mensaje final
            MSG_ESPERANDO_CITA_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, msg_recibir_cita_id),
                CallbackQueryHandler(callback_panel, pattern="^panel_menu$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(callback_panel, pattern="^panel_menu$"),
        ],
        per_message=False,
        allow_reentry=True,
    )
