-- Migración 021: Mantenimiento y Objetos Olvidados como entidades reales
-- Ejecutar: python scripts/run_migration.py migrations/021_maintenance_lostitems.sql
--
-- maintenance_tickets: agrega aislamiento multi-tenant (empresa_usuario_id).
-- hk_lost_items: se desacopla del flujo muerto (hk_cycles) para usarse standalone por
--   habitación: agrega empresa_usuario_id, room_id y estado; cycle_id pasa a nullable.

-- ============================================================
-- 1. maintenance_tickets -> tenant
-- ============================================================
ALTER TABLE maintenance_tickets
    ADD COLUMN IF NOT EXISTS empresa_usuario_id INTEGER REFERENCES empresa_usuarios(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_mt_empresa ON maintenance_tickets (empresa_usuario_id);

-- ============================================================
-- 2. hk_lost_items -> standalone por habitación + tenant + estado
-- ============================================================
ALTER TABLE hk_lost_items
    ADD COLUMN IF NOT EXISTS empresa_usuario_id INTEGER REFERENCES empresa_usuarios(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS estado VARCHAR(20) NOT NULL DEFAULT 'guardado';

-- cycle_id deja de ser obligatorio (ahora un objeto olvidado puede existir sin ciclo)
ALTER TABLE hk_lost_items ALTER COLUMN cycle_id DROP NOT NULL;

CREATE INDEX IF NOT EXISTS idx_hklost_empresa ON hk_lost_items (empresa_usuario_id);
CREATE INDEX IF NOT EXISTS idx_hklost_room ON hk_lost_items (room_id);

DO $$
BEGIN
    RAISE NOTICE '✅ Migración 021 completada: maintenance_tickets.empresa_usuario_id + hk_lost_items (tenant/room/estado, cycle_id nullable)';
END $$;
