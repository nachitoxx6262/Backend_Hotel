-- Migración 020: Política de limpieza configurable (stayover)
-- Ejecutar: python scripts/run_migration.py migrations/020_housekeeping_policy.sql
--
-- Agrega a hotel_settings la política de limpieza para habitaciones OCUPADAS:
--   stayover_policy: 'diaria' | 'solo_checkout' | 'cada_n_dias'
--   stayover_cada_n_dias: cada cuántas noches limpiar si la política es 'cada_n_dias'
-- El checkout siempre genera limpieza cuando housekeeping_enabled = true (no se configura acá).

ALTER TABLE hotel_settings
    ADD COLUMN IF NOT EXISTS stayover_policy VARCHAR(20) NOT NULL DEFAULT 'diaria',
    ADD COLUMN IF NOT EXISTS stayover_cada_n_dias INTEGER NOT NULL DEFAULT 3;

DO $$
BEGIN
    RAISE NOTICE '✅ Migración 020 completada: hotel_settings.stayover_policy / stayover_cada_n_dias';
END $$;
