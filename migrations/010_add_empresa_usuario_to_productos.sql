-- Migration: Add empresa_usuario_id to productos_servicios table
-- Date: 2026-01-27
-- Description: Add multi-tenant support to productos_servicios

-- 1. Add empresa_usuario_id column
ALTER TABLE productos_servicios 
ADD COLUMN empresa_usuario_id INTEGER;

-- 2. Add foreign key constraint
ALTER TABLE productos_servicios 
ADD CONSTRAINT fk_productos_empresa_usuario 
FOREIGN KEY (empresa_usuario_id) 
REFERENCES empresa_usuarios(id) 
ON DELETE CASCADE;

-- 3. Create index for better query performance
CREATE INDEX idx_producto_empresa_usuario ON productos_servicios(empresa_usuario_id);

-- 4. Data migration: Assign existing productos to first empresa (if any exist)
-- This is a safe default - in production you may want to review this
UPDATE productos_servicios 
SET empresa_usuario_id = (SELECT MIN(id) FROM empresa_usuarios)
WHERE empresa_usuario_id IS NULL 
AND EXISTS (SELECT 1 FROM empresa_usuarios);

-- 5. Optional: Make column NOT NULL after data migration (commented out for safety)
-- ALTER TABLE productos_servicios ALTER COLUMN empresa_usuario_id SET NOT NULL;
