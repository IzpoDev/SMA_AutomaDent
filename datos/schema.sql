-- ================================================================
-- SCHEMA: Sistema Multiagente Clínica Dental AutomaDent
-- NOTA: Este esquema ya se encuentra en Supabase.
-- ================================================================

-- 1. Tipos Enumerados (Enums)
CREATE TYPE rol_personal AS ENUM ('odontologo', 'recepcionista', 'administrador');
CREATE TYPE estado_cita AS ENUM ('programada', 'confirmada', 'asistida', 'cancelada', 'no_show');
CREATE TYPE metodo_pago AS ENUM ('efectivo', 'tarjeta', 'yape', 'plin');
CREATE TYPE estado_pago AS ENUM ('pendiente', 'pagado', 'fallido');

-- 2. Tablas
CREATE TABLE pacientes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    telefono VARCHAR(20) NOT NULL UNIQUE,
    email VARCHAR(150) UNIQUE,
    fecha_nacimiento DATE,
    fecha_registro TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE personal (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    rol rol_personal NOT NULL,
    especialidad VARCHAR(100) DEFAULT 'General',
    telefono VARCHAR(20)
);

CREATE TABLE citas (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    paciente_id BIGINT NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
    odontologo_id BIGINT NOT NULL REFERENCES personal(id) ON DELETE RESTRICT,
    fecha_hora TIMESTAMPTZ NOT NULL,
    estado estado_cita NOT NULL DEFAULT 'programada',
    motivo_consulta TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE historias_clinicas (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    paciente_id BIGINT NOT NULL UNIQUE REFERENCES pacientes(id) ON DELETE CASCADE,
    fecha_creacion TIMESTAMPTZ DEFAULT NOW(),
    antecedentes_medicos TEXT
);

CREATE TABLE atenciones_medicas (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    historia_id BIGINT NOT NULL REFERENCES historias_clinicas(id) ON DELETE CASCADE,
    cita_id BIGINT NOT NULL UNIQUE REFERENCES citas(id) ON DELETE RESTRICT,
    diagnostico TEXT NOT NULL,
    tratamiento_realizado TEXT NOT NULL,
    observaciones TEXT,
    fecha_atencion TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE pagos (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cita_id BIGINT NOT NULL UNIQUE REFERENCES citas(id) ON DELETE CASCADE,
    monto NUMERIC(10, 2) NOT NULL CHECK (monto >= 0),
    metodo_pago metodo_pago,
    estado_pago estado_pago NOT NULL DEFAULT 'pendiente',
    fecha_pago TIMESTAMPTZ
);

CREATE TABLE mensajes_chat (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chat_id VARCHAR(50) NOT NULL,
    sender VARCHAR(10) NOT NULL CHECK (sender IN ('user', 'bot', 'summary')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tabla para RAG con pgvector (el vector de embeddings debe ser de 768 dimensiones para Gemini-embedding-001)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documentos_soporte (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    titulo VARCHAR(200) NOT NULL,
    contenido TEXT NOT NULL,
    embedding vector(768),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Índices
CREATE INDEX idx_pacientes_telefono ON pacientes(telefono);
CREATE INDEX idx_citas_fecha_hora ON citas(fecha_hora);
CREATE INDEX idx_citas_estado ON citas(estado);

-- 4. Función de búsqueda de similitud coseno para RAG (RPC)
CREATE OR REPLACE FUNCTION buscar_documentos (
  query_embedding vector(768),
  match_threshold float,
  match_count int
)
RETURNS TABLE (
  id bigint,
  titulo varchar,
  contenido text,
  similitud float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    documentos_soporte.id,
    documentos_soporte.titulo,
    documentos_soporte.contenido,
    1 - (documentos_soporte.embedding <=> query_embedding) AS similitud
  FROM documentos_soporte
  WHERE 1 - (documentos_soporte.embedding <=> query_embedding) > match_threshold
  ORDER BY documentos_soporte.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
