-- Migración: Limpiar columnas duplicadas en hotel_settings
-- Problema: hay empresa_id (NOT NULL) y empresa_usuario_id (nullable)
-- Solución: Usar empresa_usuario_id y eliminar empresa_id

-- Primero, copiar datos de empresa_id a empresa_usuario_id si es necesario
UPDATE hotel_settings
SET empresa_usuario_id = empresa_id
WHERE empresa_usuario_id IS NULL;

-- Hacer empresa_usuario_id NOT NULL
ALTER TABLE hotel_settings
ALTER COLUMN empresa_usuario_id SET NOT NULL;

-- Eliminar la columna empresa_id que está duplicada
ALTER TABLE hotel_settings
DROP COLUMN IF EXISTS empresa_id CASCADE;

-- Verificar que hotel_settings tiene la estructura correcta
-- SELECT * FROM hotel_settings LIMIT 1;
