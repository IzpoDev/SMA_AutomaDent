# scripts/sembrar_rag.py — Sembrado de la Base de Conocimiento RAG
# ==============================================================================
# Migrado y refactorizado de shared/sembrar_rag.py.
# Lee los archivos markdown de datos/conocimiento_rag/ y los indexa
# generando embeddings con Google GenAI y guardándolos en Supabase (pgvector).
# ==============================================================================

import os
import glob
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from src.utils.database import supabase
from src.modelos.embeddings import generar_embedding_documento
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Directorio que contiene los documentos de conocimiento
CONOCIMIENTO_DIR = Path("datos/conocimiento_rag")

def sembrar():
    """Genera embeddings para los documentos markdown y los sube a Supabase."""
    if not os.path.exists(CONOCIMIENTO_DIR):
        logger.warning(f"Directorio {CONOCIMIENTO_DIR} no encontrado. Creando directorio...")
        CONOCIMIENTO_DIR.mkdir(parents=True, exist_ok=True)
        # Crear un archivo de prueba para RAG si no existe ninguno
        prueba_file = CONOCIMIENTO_DIR / "clinica_info.md"
        with open(prueba_file, "w", encoding="utf-8") as f:
            f.write("# Información General de AutomaDent\n\nAutomaDent es una clínica dental inteligente con atención de lunes a sábado de 8am a 6pm.")
        logger.info(f"Creado archivo de ejemplo: {prueba_file}")

    files = glob.glob(str(CONOCIMIENTO_DIR / "*.md"))
    if not files:
        logger.info("No se encontraron archivos markdown para sembrar.")
        return

    logger.info(f"Encontrados {len(files)} archivos para sembrar en RAG.")

    # Limpiar tabla RAG para evitar duplicados
    try:
        supabase.table("documentos_soporte").delete().neq("id", 0).execute()
        logger.info("Tabla documentos_soporte limpiada.")
    except Exception as e:
        logger.error(f"Error limpiando tabla documentos_soporte: {e}")

    for file_path in files:
        nombre_archivo = Path(file_path).name
        logger.info(f"Procesando: {nombre_archivo}")
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                contenido = f.read().strip()
                
            if not contenido:
                continue

            # Generar título simple a partir de la primera línea o del nombre del archivo
            lineas = contenido.split("\n")
            titulo = lineas[0].replace("#", "").strip() if lineas[0].startswith("#") else nombre_archivo

            # Generar embedding (truncado a 768 dims)
            embedding = generar_embedding_documento(contenido)

            # Insertar en Supabase
            supabase.table("documentos_soporte").insert({
                "titulo": titulo,
                "contenido": contenido,
                "embedding": embedding
            }).execute()
            
            logger.info(f"✅ Documento '{titulo}' sembrado exitosamente.")
        except Exception as e:
            logger.error(f"❌ Error sembrando {nombre_archivo}: {e}")

if __name__ == "__main__":
    sembrar()
