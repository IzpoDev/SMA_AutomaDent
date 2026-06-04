# database.py — Cliente Supabase centralizado (Singleton)

import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str = os.environ["SUPABASE_SERVICE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def guardar_mensaje(chat_id: str, sender: str, content: str) -> None:
    """Guarda un mensaje en la tabla mensajes_chat."""
    try:
        supabase.table("mensajes_chat").insert({
            "chat_id": str(chat_id),
            "sender": sender,
            "content": content
        }).execute()
    except Exception as e:
        print(f"Error guardando mensaje en la base de datos: {e}")

def obtener_historial_mensajes(chat_id: str, limite: int = 20) -> list:
    """Obtiene los últimos N mensajes del historial del chat en orden cronológico."""
    try:
        res = (
            supabase.table("mensajes_chat")
            .select("sender, content")
            .eq("chat_id", str(chat_id))
            .order("created_at", desc=True)
            .limit(limite)
            .execute()
        )
        return list(reversed(res.data)) if res.data else []
    except Exception as e:
        print(f"Error obteniendo historial de mensajes: {e}")
        return []

