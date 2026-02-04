-- Migración: Agregar empresa_usuario_id a clientes
-- Fecha: 2026-01-27
-- Descripción: Agrega columna empresa_usuario_id a tabla clientes para soporte multi-tenant

-- 1. Agregar columna empresa_usuario_id (nullable temporalmente)
ALTER TABLE clientes 
ADD COLUMN IF NOT EXISTS empresa_usuario_id INTEGER;

-- 2. Agregar foreign key constraint
ALTER TABLE clientes 
ADD CONSTRAINT fk_clientes_empresa_usuario 
FOREIGN KEY (empresa_usuario_id) 
REFERENCES empresa_usuarios(id) 
ON DELETE CASCADE;

-- 3. Crear índice para mejorar performance
CREATE INDEX IF NOT EXISTS idx_cliente_empresa ON clientes(empresa_usuario_id);

-- 4. Actualizar clientes existentes: asignar a la primera empresa (o NULL si no hay empresas)
-- En producción, esto debería hacerse manualmente con más cuidado
DO $$
DECLARE
    primera_empresa_id INTEGER;
BEGIN
    -- Obtener el ID de la primera empresa
    SELECT id INTO primera_empresa_id FROM empresa_usuarios ORDER BY id LIMIT 1;
    
    -- Solo actualizar si hay una empresa y hay clientes sin empresa asignada
    IF primera_empresa_id IS NOT NULL THEN
        UPDATE clientes 
        SET empresa_usuario_id = primera_empresa_id 
        WHERE empresa_usuario_id IS NULL;
    END IF;
END $$;

-- 5. Hacer la columna NOT NULL después de asignar valores
-- COMENTADO: Descomentar solo cuando todos los clientes tengan una empresa asignada
-- ALTER TABLE clientes ALTER COLUMN empresa_usuario_id SET NOT NULL;

COMMENT ON COLUMN clientes.empresa_usuario_id IS 'FK a empresa_usuarios - Tenant owner del cliente';
