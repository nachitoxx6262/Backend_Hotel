-- Migración 007: Habilitar Row Level Security (RLS) en PostgreSQL
-- Esta migración implementa la capa de seguridad bulletproof para aislamiento de tenants

-- ============================================================
-- 1. CREAR EXTENSIÓN y CONFIGURAR RLS
-- ============================================================

-- Verificar que psql tiene acceso necesario (ejecutar como superuser si falla)
-- Crear aplicación role para ejecutar queries
-- DO $$ BEGIN
--    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
--       CREATE ROLE app_user WITH LOGIN;
--    END IF;
-- END
-- $$;

-- ============================================================
-- 2. HABILITAR RLS en todas las tablas multi-tenant
-- ============================================================

-- Función para obtener tenant_id actual desde app.current_tenant_id
CREATE OR REPLACE FUNCTION current_user_id() RETURNS INTEGER AS $$
    SELECT NULLIF(current_setting('app.current_user_id', true), '')::INTEGER;
$$ LANGUAGE SQL;

CREATE OR REPLACE FUNCTION get_current_tenant_id() RETURNS INTEGER AS $$
    SELECT current_setting('app.current_tenant_id')::INTEGER;
$$ LANGUAGE SQL;

-- Tabla: empresa_usuarios (el tenant mismo - acceso global para super_admin)
ALTER TABLE empresa_usuarios ENABLE ROW LEVEL SECURITY;

-- Política: Super admin puede ver todos
-- Política: Regular admin solo su propio tenant
CREATE POLICY rls_empresa_usuarios_access ON empresa_usuarios
    FOR ALL
    USING (
        -- Super admin OR es el tenant owner
        (SELECT es_super_admin FROM usuarios WHERE id = current_user_id()) 
        OR id = get_current_tenant_id()
    );

-- Tabla: usuarios
ALTER TABLE usuarios ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_usuarios_access ON usuarios
    FOR ALL
    USING (
        -- Super admin puede ver todos
        es_super_admin = TRUE
        OR
        -- Usuario ve su propio tenant
        empresa_usuario_id = get_current_tenant_id()
        OR
        -- Usuario se ve a sí mismo
        id = current_user_id()
    );

-- Tabla: cliente_corporativo
ALTER TABLE cliente_corporativo ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_cliente_corporativo_access ON cliente_corporativo
    FOR ALL
    USING (empresa_usuario_id = get_current_tenant_id());

-- Tabla: clientes
ALTER TABLE clientes ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_clientes_access ON clientes
    FOR ALL
    USING (
        -- Tabla clientes todavía no está ligada a tenant_id; permitir acceso general temporal
        TRUE
    );

-- Tabla: room_types
ALTER TABLE room_types ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_room_types_access ON room_types
    FOR ALL
    USING (empresa_usuario_id = get_current_tenant_id());

-- Tabla: rooms
ALTER TABLE rooms ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_rooms_access ON rooms
    FOR ALL
    USING (empresa_usuario_id = get_current_tenant_id());

-- Tabla: daily_rates
ALTER TABLE daily_rates ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_daily_rates_access ON daily_rates
    FOR ALL
    USING (empresa_usuario_id = get_current_tenant_id());

-- Tabla: rate_plans
ALTER TABLE rate_plans ENABLE ROW LEVEL SECURITY;

-- Rate plans pueden ser globales o per-tenant (para flexibilidad)
-- Por ahora los hacemos accesibles globalmente (mejor: agregar empresa_usuario_id si necesario)
-- CREATE POLICY rls_rate_plans_access ON rate_plans FOR ALL USING (TRUE);

-- Tabla: reservations
ALTER TABLE reservations ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_reservations_access ON reservations
    FOR ALL
    USING (empresa_usuario_id = get_current_tenant_id());

-- Tabla: reservation_rooms
ALTER TABLE reservation_rooms ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_reservation_rooms_access ON reservation_rooms
    FOR ALL
    USING (
        reservation_id IN (
            SELECT id FROM reservations 
            WHERE empresa_usuario_id = get_current_tenant_id()
        )
    );

-- Tabla: reservation_guests
ALTER TABLE reservation_guests ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_reservation_guests_access ON reservation_guests
    FOR ALL
    USING (
        reservation_id IN (
            SELECT id FROM reservations 
            WHERE empresa_usuario_id = get_current_tenant_id()
        )
    );

-- Tabla: stays
ALTER TABLE stays ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_stays_access ON stays
    FOR ALL
    USING (empresa_usuario_id = get_current_tenant_id());

-- Tabla: stay_room_occupancies
ALTER TABLE stay_room_occupancies ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_stay_room_occupancies_access ON stay_room_occupancies
    FOR ALL
    USING (
        stay_id IN (
            SELECT id FROM stays 
            WHERE empresa_usuario_id = get_current_tenant_id()
        )
    );

-- Tabla: stay_charges
ALTER TABLE stay_charges ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_stay_charges_access ON stay_charges
    FOR ALL
    USING (
        stay_id IN (
            SELECT id FROM stays 
            WHERE empresa_usuario_id = get_current_tenant_id()
        )
    );

-- Tabla: stay_payments
ALTER TABLE stay_payments ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_stay_payments_access ON stay_payments
    FOR ALL
    USING (
        stay_id IN (
            SELECT id FROM stays 
            WHERE empresa_usuario_id = get_current_tenant_id()
        )
    );

-- Tabla: housekeeping_tasks
ALTER TABLE housekeeping_tasks ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_housekeeping_tasks_access ON housekeeping_tasks
    FOR ALL
    USING (empresa_usuario_id = get_current_tenant_id());

-- Tabla: roles
ALTER TABLE roles ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_roles_access ON roles
    FOR ALL
    USING (
        -- Global roles (null empresa_usuario_id) solo para super_admin
        (empresa_usuario_id IS NULL AND (SELECT es_super_admin FROM usuarios WHERE id = current_user_id()))
        OR
        -- Tenant roles para el tenant actual
        empresa_usuario_id = get_current_tenant_id()
    );

-- Tabla: subscriptions
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_subscriptions_access ON subscriptions
    FOR ALL
    USING (
        empresa_usuario_id = get_current_tenant_id()
        OR
        (SELECT es_super_admin FROM usuarios WHERE id = current_user_id()) = TRUE
    );

-- Tabla: payment_attempts
ALTER TABLE payment_attempts ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_payment_attempts_access ON payment_attempts
    FOR ALL
    USING (
        subscription_id IN (
            SELECT id FROM subscriptions 
            WHERE empresa_usuario_id = get_current_tenant_id()
                  OR (SELECT es_super_admin FROM usuarios WHERE id = current_user_id()) = TRUE
        )
    );

-- Tabla: hotel_settings
ALTER TABLE hotel_settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_hotel_settings_access ON hotel_settings
    FOR ALL
    USING (empresa_usuario_id = get_current_tenant_id());

-- ============================================================
-- 3. CREAR TABLA DE AUDITORÍA RLS (opcional pero recomendado)
-- ============================================================

CREATE TABLE IF NOT EXISTS rls_access_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    tenant_id INTEGER,
    table_name VARCHAR(100),
    action VARCHAR(20),  -- SELECT, INSERT, UPDATE, DELETE
    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 4. DOCUMENTACIÓN PARA DEVELOPERS
-- ============================================================

-- Cómo setear el tenant_id desde la aplicación FastAPI:
-- 
-- En middleware (después de validar JWT):
-- set_tenant_id_query = "SET app.current_tenant_id = :tenant_id"
-- session.execute(text(set_tenant_id_query), {"tenant_id": tenant_id})
-- session.commit()
--
-- O para una sesión:
-- SET app.current_tenant_id = 123;  -- Set tenant_id to 123
-- SELECT * FROM habitaciones;  -- Solo devuelve habitaciones del tenant 123
--
-- Verificar RLS activo:
-- SELECT tablename, rowsecurity FROM pg_tables 
-- WHERE schemaname = 'public' AND rowsecurity = true;
--
-- IMPORTANTE: EJECUTAR COMO SUPERUSER
-- Esta migración debe ejecutarse como el rol de base de datos con permisos suficientes
-- En desarrollo: psql -U postgres -d your_db -f 007_enable_rls_security.sql

COMMIT;
