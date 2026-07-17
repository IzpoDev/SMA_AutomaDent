-- ============================================================
-- MIGRACIÓN: Crear tabla separada para resúmenes de chat
-- Ejecutar en Supabase SQL Editor
-- ============================================================

-- 1. Crear la nueva tabla dedicada para resúmenes
CREATE TABLE IF NOT EXISTS resumenes_chat (
    id         BIGSERIAL PRIMARY KEY,
    chat_id    TEXT        NOT NULL,
    content    TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Índice para búsquedas rápidas por chat_id y ordenamiento
CREATE INDEX IF NOT EXISTS idx_resumenes_chat_chat_id_created_at
    ON resumenes_chat (chat_id, created_at DESC);

-- 3. (Opcional) Migrar resúmenes existentes que quedaron atrapados en mensajes_chat
--    Descomentar si ya tienes filas con sender='summary' guardadas previamente
-- INSERT INTO resumenes_chat (chat_id, content, created_at)
-- SELECT chat_id, content, created_at
-- FROM   mensajes_chat
-- WHERE  sender = 'summary';

-- DELETE FROM mensajes_chat WHERE sender = 'summary';

-- ============================================================
-- VERIFICACIÓN
-- ============================================================
-- SELECT COUNT(*) FROM resumenes_chat;
-- SELECT * FROM resumenes_chat ORDER BY created_at DESC LIMIT 5;
