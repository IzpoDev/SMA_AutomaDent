-- ================================================================
-- SCHEMA: Sistema Multiagente Clínica Dental AutomaDent
-- NOTA: Este esquema YA ESTÁ DESPLEGADO en Supabase (AgenteDent-bd).
-- Este archivo es referencia documental únicamente.
-- ================================================================

-- ==========================================
-- 1. Tipos Enumerados (Enums)
-- ==========================================
CREATE TYPE rol_personal AS ENUM ('odontologo', 'recepcionista', 'administrador');
CREATE TYPE estado_cita AS ENUM ('programada', 'confirmada', 'asistida', 'cancelada', 'no_show');
CREATE TYPE metodo_pago AS ENUM ('efectivo', 'tarjeta', 'yape', 'plin');
CREATE TYPE estado_pago AS ENUM ('pendiente', 'pagado', 'fallido');

-- ==========================================
-- 2. Tablas
-- ==========================================

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

-- ==========================================
-- 3. Índices
-- ==========================================
CREATE INDEX idx_pacientes_telefono ON pacientes(telefono);
CREATE INDEX idx_citas_fecha_hora ON citas(fecha_hora);
CREATE INDEX idx_citas_estado ON citas(estado);
