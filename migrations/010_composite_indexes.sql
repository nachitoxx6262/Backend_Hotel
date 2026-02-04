-- Migration: Agregar índices compuestos para optimizar queries frecuentes
-- Fecha: 2026-02-04
-- Objetivo: Mejorar performance en queries de calendario y búsquedas frecuentes

-- Índices en Reservations (tabla de búsquedas frecuentes)
CREATE INDEX IF NOT EXISTS idx_reservations_empresa_estado_checkin 
ON reservations(empresa_usuario_id, estado, fecha_checkin);

CREATE INDEX IF NOT EXISTS idx_reservations_empresa_estado_checkout 
ON reservations(empresa_usuario_id, estado, fecha_checkout);

CREATE INDEX IF NOT EXISTS idx_reservations_empresa_estado_rango
ON reservations(empresa_usuario_id, estado, fecha_checkin, fecha_checkout);

-- Índices en Stays (tabla de búsquedas de ocupación actual)
CREATE INDEX IF NOT EXISTS idx_stays_empresa_estado_checkin 
ON stays(empresa_usuario_id, estado, checkin_real);

CREATE INDEX IF NOT EXISTS idx_stays_empresa_estado_active
ON stays(empresa_usuario_id, estado) 
WHERE estado IN ('pendiente_checkin', 'ocupada', 'pendiente_checkout');

-- Índices en StayRoomOccupancy (búsquedas por período y habitación)
CREATE INDEX IF NOT EXISTS idx_occupancy_stay_desde_hasta 
ON stay_room_occupancies(stay_id, desde, hasta);

CREATE INDEX IF NOT EXISTS idx_occupancy_room_rango 
ON stay_room_occupancies(room_id, desde, hasta);

-- Índices en StayCharge y StayPayment (para reportes financieros)
CREATE INDEX IF NOT EXISTS idx_charges_stay_created 
ON stay_charges(stay_id, created_at);

CREATE INDEX IF NOT EXISTS idx_payments_stay_timestamp 
ON stay_payments(stay_id, timestamp);

-- Índices para auditoría y logs
CREATE INDEX IF NOT EXISTS idx_audit_empresa_timestamp 
ON audit_events(empresa_usuario_id, timestamp);

CREATE INDEX IF NOT EXISTS idx_audit_action_timestamp 
ON audit_events(action, timestamp);

-- Índice para búsquedas por número de documento (usado en check-in)
CREATE INDEX IF NOT EXISTS idx_cliente_numero_documento_empresa 
ON clientes(numero_documento, empresa_usuario_id);

-- Índices para búsquedas de tarifas diarias
CREATE INDEX IF NOT EXISTS idx_daily_rates_room_fecha 
ON daily_rates(room_id, fecha);

CREATE INDEX IF NOT EXISTS idx_daily_rates_empresa_fecha 
ON daily_rates(empresa_usuario_id, fecha);

-- Mostrar resumen de índices creados
SELECT 
  schemaname,
  tablename,
  indexname
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
