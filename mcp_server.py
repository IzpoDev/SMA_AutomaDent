# mcp_server.py — Servidor Model Context Protocol (MCP) para Google Sheets
# ==============================================================================
# Expone herramientas a través del protocolo MCP usando FastMCP.
# Interactúa con Google Sheets usando la cuenta de servicio (credentials.json).
#
# Para ejecutar en segundo plano desde el bot (Cliente MCP):
#   python mcp_server.py
# ==============================================================================

import os
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

# Configuración del logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_sheets_server")

# ─── Configuración de FastMCP ────────────────────────────────────────────────
mcp = FastMCP("Google Sheets Server")

# Alcances (scopes) requeridos para Google Sheets y Drive
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

CREDENTIALS_FILE = "credentials.json"

def get_sheets_service():
    """Inicializa y retorna el servicio de la API de Google Sheets."""
    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"❌ No se encontró el archivo de credenciales {CREDENTIALS_FILE} en el directorio raíz."
        )
    
    credentials = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    service = build("sheets", "v4", credentials=credentials)
    return service

def get_drive_service():
    """Inicializa y retorna el servicio de la API de Google Drive."""
    credentials = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    service = build("drive", "v3", credentials=credentials)
    return service


# ==============================================================================
#  HERRAMIENTAS EXPUESTAS POR EL SERVIDOR MCP
# ==============================================================================

@mcp.tool()
def crear_nueva_hoja_calculo(titulo: str, email_compartir: Optional[str] = None) -> str:
    """Crea una nueva hoja de cálculo en Google Sheets y la comparte con un correo opcional.
    
    Args:
        titulo: Nombre de la hoja de cálculo.
        email_compartir: Correo Gmail al cual darle permisos de edición (opcional).
    """
    try:
        sheets_service = get_sheets_service()
        
        # 1. Crear la hoja
        spreadsheet_body = {
            "properties": {
                "title": titulo
            }
        }
        request = sheets_service.spreadsheets().create(body=spreadsheet_body, fields="spreadsheetId")
        response = request.execute()
        spreadsheet_id = response.get("spreadsheetId")
        url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
        
        # 2. Compartir la hoja si se especificó correo
        if email_compartir:
            drive_service = get_drive_service()
            user_permission = {
                "type": "user",
                "role": "writer",
                "emailAddress": email_compartir.strip()
            }
            drive_service.permissions().create(
                fileId=spreadsheet_id,
                body=user_permission,
                fields="id"
            ).execute()
            compartido_msg = f" y compartida con {email_compartir}"
        else:
            # Alternativamente, hacerla accesible para cualquiera con el enlace (lectura)
            drive_service = get_drive_service()
            permission = {
                "type": "anyone",
                "role": "reader"
            }
            drive_service.permissions().create(
                fileId=spreadsheet_id,
                body=permission
            ).execute()
            compartido_msg = " (Configurada como pública para cualquiera con el enlace)"
            
        return f"✅ Hoja de cálculo '{titulo}' creada exitosamente{compartido_msg}.\n🔗 URL: {url}\n🆔 ID: {spreadsheet_id}"
        
    except Exception as e:
        logger.error(f"Error creando hoja de cálculo: {e}")
        return f"❌ Error al crear la hoja de cálculo: {str(e)}"


@mcp.tool()
def exportar_citas_a_sheets(
    spreadsheet_id: str,
    citas: List[Dict[str, Any]],
    rango: str = "Hoja 1!A1"
) -> str:
    """Exporta una lista de citas médicas a una hoja de cálculo existente.
    
    Args:
        spreadsheet_id: El ID de la hoja de cálculo de Google.
        citas: Lista de diccionarios que representan las citas a exportar.
               Cada diccionario debe contener: id, paciente, doctor, fecha, hora, estado, motivo.
        rango: El rango de la hoja donde escribir (ej: 'Hoja 1!A1').
    """
    try:
        sheets_service = get_sheets_service()
        
        # 1. Definir los encabezados de la tabla
        headers = ["Cita ID", "Paciente", "Doctor/Odontólogo", "Fecha", "Hora", "Estado", "Motivo de Consulta"]
        
        # 2. Convertir los datos de citas en filas
        rows = [headers]
        for cita in citas:
            rows.append([
                str(cita.get("id", "")),
                str(cita.get("paciente", "")),
                str(cita.get("doctor", "")),
                str(cita.get("fecha", "")),
                str(cita.get("hora", "")),
                str(cita.get("estado", "")),
                str(cita.get("motivo", ""))
            ])
            
        # 3. Preparar la solicitud de actualización
        body = {
            "values": rows
        }
        
        # Escribir en la hoja
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=rango,
            valueInputOption="RAW",
            body=body
        ).execute()
        
        return f"✅ Se exportaron exitosamente {len(citas)} citas a la hoja de cálculo (Rango: {rango})."
        
    except Exception as e:
        logger.error(f"Error exportando citas: {e}")
        return f"❌ Error al exportar citas a Sheets: {str(e)}"


@mcp.tool()
def exportar_pagos_a_sheets(
    spreadsheet_id: str,
    pagos: List[Dict[str, Any]],
    rango: str = "Hoja 1!A1"
) -> str:
    """Exporta un reporte de pagos recibidos a una hoja de cálculo existente.
    
    Args:
        spreadsheet_id: ID de la hoja de cálculo.
        pagos: Lista de pagos. Cada diccionario debe contener: pago_id, cita_id, paciente, monto, metodo, estado, fecha.
        rango: Rango donde escribir (ej: 'Hoja 1!A1').
    """
    try:
        sheets_service = get_sheets_service()
        
        headers = ["Pago ID", "Cita ID", "Paciente", "Monto (S/)", "Método de Pago", "Estado de Pago", "Fecha Pago"]
        rows = [headers]
        total_monto = 0.0
        
        for p in pagos:
            monto = float(p.get("monto", 0.0))
            total_monto += monto
            rows.append([
                str(p.get("pago_id", "")),
                str(p.get("cita_id", "")),
                str(p.get("paciente", "")),
                f"{monto:.2f}",
                str(p.get("metodo", "")),
                str(p.get("estado", "")),
                str(p.get("fecha", ""))
            ])
            
        # Añadir fila de resumen
        rows.append([])
        rows.append(["", "", "TOTAL RECAUDADO:", f"{total_monto:.2f}", "", "", ""])
        
        body = {
            "values": rows
        }
        
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=rango,
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()
        
        return f"✅ Se exportaron exitosamente {len(pagos)} registros de pagos. Total acumulado: S/ {total_monto:.2f}."
        
    except Exception as e:
        logger.error(f"Error exportando pagos: {e}")
        return f"❌ Error al exportar pagos a Sheets: {str(e)}"


# ==============================================================================
#  ARRANQUE DEL SERVIDOR
# ==============================================================================

if __name__ == "__main__":
    # Arrancar el servidor en modo stdio (requerido por el protocolo MCP)
    mcp.run("stdio")
