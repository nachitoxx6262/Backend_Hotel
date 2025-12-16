-- Migración: Actualizar cancelled_by de VARCHAR a INTEGER
-- Fecha: 2025-12-16
-- Descripción: Cambiar el tipo de la columna cancelled_by para guardar el ID del usuario en lugar del username

-- IMPORTANTE: Ejecutar este script manualmente en la base de datos

-- Paso 1: Crear una nueva columna temporal para el ID del usuario
ALTER TABLE reservations ADD COLUMN cancelled_by_new INTEGER;

-- Paso 2: Actualizar la nueva columna (si tienes datos existentes, necesitarás un mapeo manual)
-- Si no hay datos de cancelación existentes, puedes omitir este paso
-- UPDATE reservations SET cancelled_by_new = (SELECT id FROM usuarios WHERE username = cancelled_by) WHERE cancelled_by IS NOT NULL;

-- Paso 3: Eliminar la columna antigua
ALTER TABLE reservations DROP COLUMN cancelled_by;

-- Paso 4: Renombrar la nueva columna
ALTER TABLE reservations RENAME COLUMN cancelled_by_new TO cancelled_by;

-- Paso 5: Agregar comentario a la columna
COMMENT ON COLUMN reservations.cancelled_by IS 'ID del usuario que canceló la reserva';

-- Verificación
-- SELECT id, estado, cancel_reason, cancelled_at, cancelled_by FROM reservations WHERE estado = 'cancelada';
