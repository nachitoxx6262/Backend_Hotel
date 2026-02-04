-- Migración 009: agregar columna deleted a empresa_usuarios
ALTER TABLE empresa_usuarios
ADD COLUMN IF NOT EXISTS deleted BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE empresa_usuarios
SET deleted = FALSE
WHERE deleted IS NULL;
