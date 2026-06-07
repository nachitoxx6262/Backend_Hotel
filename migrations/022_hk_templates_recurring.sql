-- Migración 022: Plantillas de limpieza (multi-tenant) + Reglas de limpieza recurrente
-- Ejecutar: python scripts/run_migration.py migrations/022_hk_templates_recurring.sql

-- ============================================================
-- 1. hk_templates -> multi-tenant + tipo
-- ============================================================
ALTER TABLE hk_templates
    ADD COLUMN IF NOT EXISTS empresa_usuario_id INTEGER REFERENCES empresa_usuarios(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) NOT NULL DEFAULT 'eventual';

-- El nombre era UNIQUE global (rompe multi-tenant): pasar a único por tenant
ALTER TABLE hk_templates DROP CONSTRAINT IF EXISTS hk_templates_nombre_key;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_hk_template_empresa_nombre') THEN
        ALTER TABLE hk_templates
            ADD CONSTRAINT uq_hk_template_empresa_nombre UNIQUE (empresa_usuario_id, nombre);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_hkt_empresa ON hk_templates (empresa_usuario_id);

-- ============================================================
-- 2. hk_recurring_rules (nueva)
-- ============================================================
CREATE TABLE IF NOT EXISTS hk_recurring_rules (
    id SERIAL PRIMARY KEY,
    empresa_usuario_id INTEGER NOT NULL REFERENCES empresa_usuarios(id) ON DELETE CASCADE,
    nombre VARCHAR(120) NOT NULL,
    cada_n_dias INTEGER NOT NULL DEFAULT 15,
    scope VARCHAR(20) NOT NULL DEFAULT 'todas',          -- 'todas' | 'tipo'
    room_type_id INTEGER REFERENCES room_types(id) ON DELETE CASCADE,
    template_id INTEGER REFERENCES hk_templates(id) ON DELETE SET NULL,
    prioridad VARCHAR(10) NOT NULL DEFAULT 'media',
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    ultima_generacion DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_hkrr_empresa ON hk_recurring_rules (empresa_usuario_id);

DO $$
BEGIN
    RAISE NOTICE '✅ Migración 022 completada: hk_templates (tenant+tipo) + hk_recurring_rules';
END $$;
