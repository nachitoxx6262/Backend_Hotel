-- ============================================================================
-- 027 — RLS: función null-safe + política para rate_plans
-- Aditiva y segura de auto-aplicar. NO fuerza RLS sobre el owner (ver
-- migrations/rls_force_MANUAL.sql para el backstop real, que requiere correr
-- la app con un rol de DB no-owner).
-- ============================================================================

-- 1. get_current_tenant_id() null-safe: si el contexto no está seteado devuelve
--    NULL (fail-closed en las políticas) en vez de reventar con error.
CREATE OR REPLACE FUNCTION get_current_tenant_id() RETURNS INTEGER AS $$
    SELECT NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER;
$$ LANGUAGE SQL;

-- 2. Política RLS para rate_plans (antes no tenía; los planes eran globales).
--    Requiere la columna empresa_usuario_id agregada en la migración 026.
ALTER TABLE rate_plans ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS rls_rate_plans_access ON rate_plans;
CREATE POLICY rls_rate_plans_access ON rate_plans
    FOR ALL
    USING (empresa_usuario_id = get_current_tenant_id());
