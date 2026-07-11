-- ============================================================================
-- RLS BACKSTOP REAL — APLICACIÓN MANUAL (NO auto-corre en el deploy)
-- ============================================================================
--
-- POR QUÉ ES MANUAL:
-- La app se conecta hoy como el OWNER de las tablas. En PostgreSQL, el owner
-- IGNORA las políticas RLS por defecto: sólo `FORCE ROW LEVEL SECURITY` las
-- aplica también al owner. Pero si forzás RLS mientras la app sigue conectada
-- como owner, TODAS las queries sin contexto de tenant (login, registro de
-- empresa, operaciones de super-admin, crons) devolverán CERO filas y romperán
-- producción.
--
-- ORDEN CORRECTO DE ROLLOUT (hacer y TESTEAR en staging primero):
--
--   1) Crear un rol de aplicación NO-owner y darle permisos de datos:
--        CREATE ROLE hotel_app WITH LOGIN PASSWORD '<fuerte>';
--        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO hotel_app;
--        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO hotel_app;
--        ALTER DEFAULT PRIVILEGES IN SCHEMA public
--            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO hotel_app;
--        ALTER DEFAULT PRIVILEGES IN SCHEMA public
--            GRANT USAGE, SELECT ON SEQUENCES TO hotel_app;
--
--   2) Cambiar la DATABASE_URL de la app para conectarse como hotel_app
--      (las migraciones y create_all se siguen corriendo como owner).
--
--   3) Verificar que super-admin y operaciones sin tenant sigan funcionando:
--      las políticas que dependen de es_super_admin deben cubrir esos casos, o
--      esas operaciones deben setear explícitamente el contexto. Revisar login
--      y register-empresa-usuario (que operan sin tenant seteado todavía).
--
--   4) Recién entonces, forzar RLS sobre las tablas multi-tenant:

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'empresa_usuarios','usuarios','cliente_corporativo','room_types','rooms',
        'daily_rates','rate_plans','reservations','reservation_rooms',
        'reservation_guests','stays','stay_room_occupancies','stay_charges',
        'stay_payments','housekeeping_tasks','roles','subscriptions',
        'payment_attempts','hotel_settings'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY;', t);
    END LOOP;
END $$;

-- NOTA: la tabla `clientes` tiene hoy una política USING (TRUE) (migración 007);
-- antes de forzar RLS conviene ligarla a empresa_usuario_id y darle política real.
