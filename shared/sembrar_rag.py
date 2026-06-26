#!/usr/bin/env python3
# sembrar_rag.py — Script para poblar la tabla documentos_rag en Supabase
# ==============================================================================
# Ejecutar una sola vez (o cuando haya que actualizar el conocimiento base):
#   python sembrar_rag.py
#
# Requisitos:
#   - Variables de entorno: SUPABASE_URL, SUPABASE_SERVICE_KEY, GEMINI_API_KEY
#   - Tabla documentos_rag y función buscar_documentos ya creadas en Supabase
# ==============================================================================

import os
import sys
import time

# Añadir el directorio raíz al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from google import genai
from google.genai import types as genai_types
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
_genai_client = genai.Client(api_key=GEMINI_API_KEY)

EMBEDDING_MODEL = "gemini-embedding-001"

# ==============================================================================
#  BASE DE CONOCIMIENTO DE LA CLÍNICA AutomaDent
# ==============================================================================

DOCUMENTOS = [
    # ── HORARIOS ──────────────────────────────────────────────────────────────
    {
        "titulo": "Horarios de atención",
        "categoria": "horarios",
        "contenido": (
            "AutomaDent atiende de lunes a sábado de 8:00 AM a 6:00 PM. "
            "Los domingos y feriados nacionales la clínica permanece cerrada. "
            "Cada cita tiene una duración estándar de 30 minutos. "
            "Para emergencias dentales, comunicarse directamente por Telegram."
        ),
    },
    # ── UBICACIÓN ─────────────────────────────────────────────────────────────
    {
        "titulo": "Ubicación y contacto",
        "categoria": "informacion_general",
        "contenido": (
            "AutomaDent está ubicada en Lima, Perú. "
            "El canal principal de atención y agendamiento de citas es a través de este bot de Telegram. "
            "También puedes contactarnos por este mismo chat para consultas generales."
        ),
    },
    # ── PRECIOS — LIMPIEZAS ───────────────────────────────────────────────────
    {
        "titulo": "Precios de limpieza dental",
        "categoria": "precios",
        "contenido": (
            "Limpieza dental básica (profilaxis): S/ 80. "
            "Limpieza dental completa con ultrasonido: S/ 120. "
            "Se recomienda realizarla cada 6 meses para mantener una buena salud bucal. "
            "Incluye revisión de encías y pulido dental."
        ),
    },
    # ── PRECIOS — BRACKETS ────────────────────────────────────────────────────
    {
        "titulo": "Precios de ortodoncia y brackets",
        "categoria": "precios",
        "contenido": (
            "Brackets metálicos convencionales: desde S/ 2,500 (tratamiento completo). "
            "Brackets cerámicos (estéticos): desde S/ 3,200. "
            "Alineadores transparentes (tipo Invisalign): desde S/ 4,500. "
            "El precio incluye consulta inicial, instalación y controles mensuales. "
            "El tiempo estimado de tratamiento varía entre 12 y 24 meses según el caso."
        ),
    },
    # ── PRECIOS — BLANQUEAMIENTO ──────────────────────────────────────────────
    {
        "titulo": "Precios de blanqueamiento dental",
        "categoria": "precios",
        "contenido": (
            "Blanqueamiento dental en consultorio (láser): S/ 350. "
            "Blanqueamiento casero con cubetas personalizadas: S/ 200. "
            "Los resultados duran entre 1 y 2 años dependiendo de hábitos alimenticios. "
            "No apto para pacientes con sensibilidad dental severa sin evaluación previa."
        ),
    },
    # ── PRECIOS — EXTRACCIONES ────────────────────────────────────────────────
    {
        "titulo": "Precios de extracciones dentales",
        "categoria": "precios",
        "contenido": (
            "Extracción dental simple: S/ 80. "
            "Extracción de muela del juicio (simple): S/ 150. "
            "Extracción de muela del juicio (quirúrgica): S/ 300. "
            "Todos los procedimientos incluyen anestesia local."
        ),
    },
    # ── PRECIOS — IMPLANTES ───────────────────────────────────────────────────
    {
        "titulo": "Precios de implantes dentales",
        "categoria": "precios",
        "contenido": (
            "Implante dental unitario (titanio): desde S/ 2,800 (incluye corona). "
            "Consulta de evaluación para implantes: S/ 0 (gratuita). "
            "El proceso completo toma entre 3 y 6 meses. "
            "Se requiere una evaluación radiográfica previa para confirmar la viabilidad."
        ),
    },
    # ── PRECIOS — RESINAS Y CARIES ────────────────────────────────────────────
    {
        "titulo": "Precios de tratamiento de caries y resinas",
        "categoria": "precios",
        "contenido": (
            "Resina dental (obturación simple): S/ 80 por pieza. "
            "Tratamiento de conducto (endodoncia) diente anterior: S/ 300. "
            "Tratamiento de conducto (endodoncia) diente posterior: S/ 400. "
            "Corona dental (porcelana): S/ 600 por pieza."
        ),
    },
    # ── ESPECIALIDADES ────────────────────────────────────────────────────────
    {
        "titulo": "Especialidades y servicios de AutomaDent",
        "categoria": "servicios",
        "contenido": (
            "AutomaDent ofrece las siguientes especialidades:\n"
            "- Ortodoncia (brackets y alineadores)\n"
            "- Cirugía oral (extracciones, muelas del juicio, implantes)\n"
            "- Endodoncia (tratamientos de conducto)\n"
            "- Periodoncia (tratamiento de encías)\n"
            "- Odontopediatría (atención para niños desde 3 años)\n"
            "- Estética dental (blanqueamiento, carillas, diseño de sonrisa)\n"
            "- Odontología general (limpiezas, caries, emergencias)"
        ),
    },
    # ── MÉTODOS DE PAGO ───────────────────────────────────────────────────────
    {
        "titulo": "Métodos de pago aceptados",
        "categoria": "informacion_general",
        "contenido": (
            "AutomaDent acepta los siguientes métodos de pago:\n"
            "- Efectivo (soles)\n"
            "- Tarjeta de crédito o débito\n"
            "- Yape\n"
            "- Plin\n"
            "Los pagos se registran a través de la recepcionista o el sistema del bot. "
            "No se aceptan cheques ni transferencias bancarias directas."
        ),
    },
    # ── PREPARACIÓN PARA CITAS ────────────────────────────────────────────────
    {
        "titulo": "Preparación para citas dentales",
        "categoria": "informacion_general",
        "contenido": (
            "Para su cita en AutomaDent, se recomienda:\n"
            "- Llegar 5 minutos antes de la hora programada.\n"
            "- Informar sobre alergias a medicamentos o anestésicos.\n"
            "- Traer estudios radiográficos previos si los tiene.\n"
            "- En caso de cita de emergencia, comunicarse directamente por Telegram.\n"
            "- Cancelaciones deben realizarse con al menos 2 horas de anticipación."
        ),
    },
    # ── PREGUNTAS FRECUENTES ──────────────────────────────────────────────────
    {
        "titulo": "Preguntas frecuentes",
        "categoria": "faq",
        "contenido": (
            "¿Cuánto cuesta una consulta inicial? La consulta de evaluación inicial es gratuita para implantes. Para otras especialidades, el costo varía entre S/ 0 y S/ 50.\n\n"
            "¿Atienden a niños? Sí, contamos con odontopediatría desde los 3 años.\n\n"
            "¿Puedo agendar por este chat? Sí, este bot de Telegram permite agendar, consultar disponibilidad y ver tu historial de citas.\n\n"
            "¿Cuánto dura una limpieza? Aproximadamente 30-45 minutos.\n\n"
            "¿Tienen estacionamiento? Consultar disponibilidad al momento de la cita.\n\n"
            "¿Hacen radiografías? Sí, contamos con radiografías digitales en la clínica."
        ),
    },
]


# ==============================================================================
#  FUNCIONES AUXILIARES
# ==============================================================================

def generar_embedding(texto: str) -> list[float]:
    """Genera el embedding de un texto usando gemini-embedding-001 (768 dims)."""
    result = _genai_client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texto,
        config=genai_types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=768,
        ),
    )
    return list(result.embeddings[0].values)


def limpiar_tabla() -> None:
    """Elimina todos los documentos existentes antes de re-sembrar."""
    print("[*] Limpiando tabla documentos_rag existente...")
    supabase.table("documentos_rag").delete().neq("id", 0).execute()
    print("    OK - Tabla limpiada.")


def sembrar_documento(doc: dict, idx: int, total: int) -> bool:
    """Genera el embedding e inserta el documento en Supabase."""
    titulo = doc["titulo"]
    contenido = doc["contenido"]
    categoria = doc["categoria"]

    print(f"   [{idx}/{total}] Generando embedding para: '{titulo}'...")
    try:
        embedding = generar_embedding(f"{titulo}\n\n{contenido}")
        supabase.table("documentos_rag").insert({
            "titulo": titulo,
            "contenido": contenido,
            "categoria": categoria,
            "embedding": embedding,
        }).execute()
        print(f"          OK - Insertado correctamente.")
        return True
    except Exception as e:
        print(f"          ERROR: {e}")
        return False


# ==============================================================================
#  SCRIPT PRINCIPAL
# ==============================================================================

def main():
    print("=" * 60)
    print("  AutomaDent -- Sembrado RAG (pgvector en Supabase)")
    print("=" * 60)
    print(f"  Total de documentos a sembrar: {len(DOCUMENTOS)}")
    print()

    # Preguntar si limpiar antes de sembrar
    limpiar = input("Deseas limpiar la tabla antes de sembrar? (s/N): ").strip().lower()
    if limpiar == "s":
        limpiar_tabla()

    print("\nSembrando documentos...\n")
    exitosos = 0
    total = len(DOCUMENTOS)

    for i, doc in enumerate(DOCUMENTOS, 1):
        ok = sembrar_documento(doc, i, total)
        if ok:
            exitosos += 1
        # Respetar rate limit de embeddings (100 RPM = ~1.67 req/seg)
        time.sleep(0.7)

    print()
    print("=" * 60)
    print(f"  Sembrado completo: {exitosos}/{total} documentos insertados.")
    print("=" * 60)

    # Verificación rápida
    count = supabase.table("documentos_rag").select("id", count="exact").execute()
    print(f"  Total en tabla documentos_rag: {count.count} documentos.")
    print()


if __name__ == "__main__":
    main()
