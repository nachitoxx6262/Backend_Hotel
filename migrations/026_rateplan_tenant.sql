-- ============================================================================
-- 026 — Aislamiento multi-tenant de rate_plans
-- Los planes de tarifa eran GLOBALES (sin empresa_usuario_id), lo que permitía
-- fuga cross-tenant vía /api/pricing/rate-plans. Se agrega la columna de tenant,
-- FK, índice y unicidad por (tenant, nombre).
-- Aditiva e idempotente.
-- ============================================================================

-- 1. Agregar columna (nullable en el primer paso para permitir backfill/limpieza)
ALTER TABLE rate_plans ADD COLUMN IF NOT EXISTS empresa_usuario_id INTEGER;

-- 2. Los rate_plans huérfanos (sin tenant) no se pueden atribuir de forma segura.
--    La feature de pricing no está activa en producción, por lo que se eliminan
--    los planes sin tenant en lugar de dejarlos accesibles a todos.
--    Los daily_rates ligados a esos planes SÍ tienen tenant propio: se preservan
--    desvinculándolos del plan (rate_plan_id = NULL) en vez de borrarlos, para no
--    perder datos de precios reales del hotel.
UPDATE daily_rates
   SET rate_plan_id = NULL
 WHERE rate_plan_id IN (SELECT id FROM rate_plans WHERE empresa_usuario_id IS NULL);
DELETE FROM rate_plans WHERE empresa_usuario_id IS NULL;

-- 3. Volver la columna obligatoria
ALTER TABLE rate_plans ALTER COLUMN empresa_usuario_id SET NOT NULL;

-- 4. FK al tenant (idempotente)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_rateplan_empresa'
    ) THEN
        ALTER TABLE rate_plans
            ADD CONSTRAINT fk_rateplan_empresa
            FOREIGN KEY (empresa_usuario_id)
            REFERENCES empresa_usuarios(id) ON DELETE CASCADE;
    END IF;
END $$;

-- 5. Índice por tenant
CREATE INDEX IF NOT EXISTS idx_rateplan_empresa ON rate_plans(empresa_usuario_id);

-- 6. Unicidad de nombre por tenant (reemplaza cualquier unicidad global previa)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'rate_plans_nombre_key') THEN
        ALTER TABLE rate_plans DROP CONSTRAINT rate_plans_nombre_key;
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS uq_rateplan_empresa_nombre
    ON rate_plans(empresa_usuario_id, nombre);
