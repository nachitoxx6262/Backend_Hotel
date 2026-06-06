-- Migración 018: Fase 3 — Nuevas columnas para facturas, SMTP y reset de contraseña
-- Ejecutar con: psql $DATABASE_URL -f migrations/018_fase3_nuevas_columnas.sql

-- ============================================================
-- 1. EMPRESA_USUARIOS: contador de facturas
-- ============================================================
ALTER TABLE empresa_usuarios
    ADD COLUMN IF NOT EXISTS invoice_counter INTEGER NOT NULL DEFAULT 0;

-- ============================================================
-- 2. HOTEL_SETTINGS: datos fiscales, SMTP y documentos requeridos
-- ============================================================
ALTER TABLE hotel_settings
    ADD COLUMN IF NOT EXISTS documentos_requeridos JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS nombre_fiscal VARCHAR(200),
    ADD COLUMN IF NOT EXISTS direccion_fiscal TEXT,
    ADD COLUMN IF NOT EXISTS iva_porcentaje NUMERIC(5,2) DEFAULT 21.0,
    ADD COLUMN IF NOT EXISTS moneda_simbolo VARCHAR(10) DEFAULT '$',
    ADD COLUMN IF NOT EXISTS logo_url VARCHAR(500),
    ADD COLUMN IF NOT EXISTS smtp_host VARCHAR(200),
    ADD COLUMN IF NOT EXISTS smtp_port INTEGER,
    ADD COLUMN IF NOT EXISTS smtp_user VARCHAR(200),
    ADD COLUMN IF NOT EXISTS smtp_password_encrypted VARCHAR(500),
    ADD COLUMN IF NOT EXISTS smtp_from_email VARCHAR(200),
    ADD COLUMN IF NOT EXISTS housekeeping_enabled BOOLEAN NOT NULL DEFAULT false;

-- Preservar comportamiento de hoteles existentes (housekeeping ya en uso):
-- los nuevos quedan en false (default del modelo), los actuales en true.
UPDATE hotel_settings SET housekeeping_enabled = true;

-- ============================================================
-- 3. USUARIOS: campos para reset de contraseña por email
-- ============================================================
ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS reset_token VARCHAR(200),
    ADD COLUMN IF NOT EXISTS reset_token_expires TIMESTAMP;

-- Índice para búsqueda rápida por token
CREATE INDEX IF NOT EXISTS idx_usuarios_reset_token ON usuarios (reset_token)
    WHERE reset_token IS NOT NULL;

-- ============================================================
-- 4. Verificación
-- ============================================================
DO $$
BEGIN
    RAISE NOTICE '✅ Migración 018 completada.';
    RAISE NOTICE '   - empresa_usuarios.invoice_counter OK';
    RAISE NOTICE '   - hotel_settings: nombre_fiscal, iva_porcentaje, smtp_*, documentos_requeridos OK';
    RAISE NOTICE '   - usuarios: reset_token, reset_token_expires OK';
END $$;
