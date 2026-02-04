-- Migración: Asignar empresa_usuario_id a room_types sin tenant
-- Asigna los room_types sin tenant (empresa_usuario_id IS NULL) al tenant demo (17)

-- Primero, verificar cuáles room_types no tienen tenant asignado
-- SELECT id, nombre, empresa_usuario_id FROM room_types WHERE empresa_usuario_id IS NULL;

-- Asignar empresa_usuario_id = 17 (demo) a todos los room_types sin tenant
UPDATE room_types 
SET empresa_usuario_id = 17 
WHERE empresa_usuario_id IS NULL;

-- Verificar la actualización
-- SELECT id, nombre, empresa_usuario_id FROM room_types;
