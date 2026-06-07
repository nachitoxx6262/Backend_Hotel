-- Migración 019: Constraints UNIQUE por tenant (aislamiento multi-tenant)
-- Ejecutar con: python scripts/run_migration.py migrations/019_per_tenant_unique_constraints.sql
--
-- Problema:
--   * cliente_corporativo.cuit tenía UNIQUE GLOBAL (uq_cliente_corporativo_cuit)
--   * clientes(tipo_documento, numero_documento) tenía UNIQUE GLOBAL (uq_doc)
--   Dos hoteles distintos NO podían registrar una empresa con el mismo CUIT ni un
--   huésped con el mismo documento → IntegrityError/500 y, peor, fuga de información
--   (la existencia de datos de otro tenant afectaba a este).
--
-- Solución:
--   Reemplazar las constraints globales por constraints COMPUESTAS que incluyen
--   empresa_usuario_id (el tenant). Así cada hotel tiene su propio espacio de CUITs
--   y documentos.
--
-- Seguridad de datos:
--   La constraint global previa garantizaba unicidad global, que IMPLICA unicidad
--   por tenant. Por lo tanto la nueva constraint compuesta (menos restrictiva) NO
--   puede fallar por datos existentes: es imposible que haya duplicados
--   (empresa_usuario_id, cuit) o (empresa_usuario_id, tipo_documento, numero_documento).
--   No se requiere limpieza previa.

-- ============================================================
-- 1. cliente_corporativo.cuit  →  UNIQUE (empresa_usuario_id, cuit)
-- ============================================================
ALTER TABLE cliente_corporativo
    DROP CONSTRAINT IF EXISTS uq_cliente_corporativo_cuit;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cliente_corporativo_cuit_empresa'
    ) THEN
        ALTER TABLE cliente_corporativo
            ADD CONSTRAINT uq_cliente_corporativo_cuit_empresa
            UNIQUE (empresa_usuario_id, cuit);
    END IF;
END $$;

-- ============================================================
-- 2. clientes(tipo_documento, numero_documento)
--      →  UNIQUE (empresa_usuario_id, tipo_documento, numero_documento)
-- ============================================================
ALTER TABLE clientes
    DROP CONSTRAINT IF EXISTS uq_doc;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_doc_empresa'
    ) THEN
        ALTER TABLE clientes
            ADD CONSTRAINT uq_doc_empresa
            UNIQUE (empresa_usuario_id, tipo_documento, numero_documento);
    END IF;
END $$;

-- ============================================================
-- 3. Verificación
-- ============================================================
DO $$
DECLARE
    cuit_ok   BOOLEAN;
    doc_ok    BOOLEAN;
    old_cuit  BOOLEAN;
    old_doc   BOOLEAN;
BEGIN
    SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_cliente_corporativo_cuit_empresa') INTO cuit_ok;
    SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_doc_empresa') INTO doc_ok;
    SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_cliente_corporativo_cuit') INTO old_cuit;
    SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_doc') INTO old_doc;

    IF NOT cuit_ok THEN RAISE EXCEPTION 'Falta uq_cliente_corporativo_cuit_empresa'; END IF;
    IF NOT doc_ok  THEN RAISE EXCEPTION 'Falta uq_doc_empresa'; END IF;
    IF old_cuit    THEN RAISE EXCEPTION 'La constraint global uq_cliente_corporativo_cuit sigue presente'; END IF;
    IF old_doc     THEN RAISE EXCEPTION 'La constraint global uq_doc sigue presente'; END IF;

    RAISE NOTICE '✅ Migración 019 completada.';
    RAISE NOTICE '   - cliente_corporativo: UNIQUE (empresa_usuario_id, cuit)';
    RAISE NOTICE '   - clientes: UNIQUE (empresa_usuario_id, tipo_documento, numero_documento)';
    RAISE NOTICE '   - constraints globales eliminadas';
END $$;
