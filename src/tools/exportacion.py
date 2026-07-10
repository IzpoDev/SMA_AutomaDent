# src/tools/exportacion.py — Herramienta de Exportación a Google Sheets
# ==============================================================================
# Migrado de bot/tools.py (exportar_citas_excel).
# Exporta citas a Google Sheets y las comparte con el email proporcionado.
# ==============================================================================

import os
from datetime import datetime

from src.utils.config import TIMEZONE, CREDENTIALS_FILE, SCOPES_GOOGLE
from src.utils.database import supabase
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _get_sheets_service():
    """Retorna el cliente de la API de Google Sheets."""
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        if not os.path.exists(CREDENTIALS_FILE):
            return None
        credentials = Credentials.from_service_account_file(
            CREDENTIALS_FILE, scopes=SCOPES_GOOGLE
        )
        return build("sheets", "v4", credentials=credentials)
    except Exception as e:
        logger.error(f"Error cargando Sheets service: {e}")
        return None


def _get_drive_service():
    """Retorna el cliente de la API de Google Drive."""
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        if not os.path.exists(CREDENTIALS_FILE):
            return None
        credentials = Credentials.from_service_account_file(
            CREDENTIALS_FILE, scopes=SCOPES_GOOGLE
        )
        return build("drive", "v3", credentials=credentials)
    except Exception as e:
        logger.error(f"Error cargando Drive service: {e}")
        return None


def exportar_citas_excel(
    telegram_chat_id: str,
    user_role: str,
    email_compartir: str,
) -> str:
    """Exporta todas las citas a una hoja de Google Sheets y la comparte por email.

    Solo para personal autorizado (administrador o recepcionista).

    Args:
        telegram_chat_id: ID de Telegram.
        user_role: Rol del usuario.
        email_compartir: Correo Gmail para compartir la hoja.

    Returns:
        URL de la hoja creada o mensaje de error.
    """
    if user_role not in ["administrador", "recepcionista"]:
        return "❌ Acceso Denegado. Solo administradores o recepcionistas pueden exportar reportes."

    sheets_service = _get_sheets_service()
    drive_service = _get_drive_service()

    if not sheets_service or not drive_service:
        return "❌ El servicio de Google Sheets no está configurado (falta credentials.json)."

    try:
        # 1. Obtener citas de Supabase
        citas_res = (
            supabase.table("citas")
            .select("id, fecha_hora, estado, motivo_consulta, paciente_id, odontologo_id")
            .execute()
        )
        if not citas_res.data:
            return "📭 No hay citas para exportar."

        # Resolver nombres
        pacientes = supabase.table("pacientes").select("id, nombre, apellido").execute()
        pac_map = {p["id"]: f"{p['nombre']} {p['apellido']}" for p in (pacientes.data or [])}

        doctores = supabase.table("personal").select("id, nombre, apellido").execute()
        doc_map = {
            d["id"]: f"Dr(a). {d['nombre']} {d['apellido']}" for d in (doctores.data or [])
        }

        headers = ["Cita ID", "Fecha", "Hora", "Paciente", "Odontólogo", "Estado", "Motivo"]
        rows = [headers]
        for c in citas_res.data:
            dt = datetime.fromisoformat(c["fecha_hora"])
            rows.append([
                str(c["id"]),
                dt.strftime("%Y-%m-%d"),
                dt.strftime("%H:%M"),
                pac_map.get(c["paciente_id"], "Desconocido"),
                doc_map.get(c["odontologo_id"], "Desconocido"),
                c["estado"],
                c.get("motivo_consulta") or "",
            ])

        # 2. Crear la hoja en Google Drive
        titulo = f"Reporte de Citas AutomaDent - {datetime.now(TIMEZONE).strftime('%d-%m-%Y')}"
        spreadsheet_body = {"properties": {"title": titulo}}
        sheet_res = (
            sheets_service.spreadsheets()
            .create(body=spreadsheet_body, fields="spreadsheetId")
            .execute()
        )
        spreadsheet_id = sheet_res.get("spreadsheetId")

        # 3. Escribir datos
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="Sheet1!A1",
            valueInputOption="RAW",
            body={"values": rows},
        ).execute()

        # 4. Compartir con el usuario
        drive_service.permissions().create(
            fileId=spreadsheet_id,
            body={"type": "user", "role": "writer", "emailAddress": email_compartir.strip()},
        ).execute()

        url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
        return (
            f"✅ Reporte de citas exportado exitosamente.\n"
            f"📁 Título: {titulo}\n"
            f"✉️ Compartido con: {email_compartir}\n"
            f"🔗 Enlace: {url}"
        )

    except Exception as e:
        logger.error(f"Error exportando a Google Sheets: {e}")
        return f"❌ Error exportando a Google Sheets: {str(e)}"
