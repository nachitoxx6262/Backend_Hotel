-- Migración para agregar columnas a housekeeping_tareas para soporte de templates y subtareas
-- Fecha: 2025-12-10

-- 1. Crear tabla housekeeping_tareas_templates si no existe
CREATE TABLE IF NOT EXISTS housekeeping_tareas_templates (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    descripcion TEXT,
    tareas JSONB NOT NULL DEFAULT '[]'::jsonb,
    checklist_default JSONB DEFAULT '{}'::jsonb,
    minibar_default JSONB DEFAULT '{}'::jsonb,
    particularidades_especiales JSONB DEFAULT '[]'::jsonb,
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Crear índice en nombre
CREATE INDEX IF NOT EXISTS idx_hk_template_nombre ON housekeeping_tareas_templates(nombre);

-- 3. Agregar columnas a housekeeping_tareas
ALTER TABLE housekeeping_tareas
ADD COLUMN IF NOT EXISTS template_id INTEGER,
ADD COLUMN IF NOT EXISTS es_padre BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS tarea_padre_id INTEGER;

-- 4. Agregar columna template_tareas_id a habitaciones
ALTER TABLE habitaciones
ADD COLUMN IF NOT EXISTS template_tareas_id INTEGER,
ADD COLUMN IF NOT EXISTS num_camas INTEGER DEFAULT 1,
ADD COLUMN IF NOT EXISTS tipo_camas VARCHAR(100),
ADD COLUMN IF NOT EXISTS particularidades JSONB DEFAULT '{}'::jsonb;

-- 5. Crear índices para mejorar performance
CREATE INDEX IF NOT EXISTS idx_hk_template_id ON housekeeping_tareas(template_id);
CREATE INDEX IF NOT EXISTS idx_hk_tarea_padre_id ON housekeeping_tareas(tarea_padre_id);
CREATE INDEX IF NOT EXISTS idx_habitacion_template ON habitaciones(template_tareas_id);

