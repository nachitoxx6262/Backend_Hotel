-- Migración 010: ajustar RLS de clientes para tenant_id
ALTER TABLE clientes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS rls_clientes_access ON clientes;

CREATE POLICY rls_clientes_access ON clientes
    FOR ALL
    USING (empresa_usuario_id = get_current_tenant_id());
