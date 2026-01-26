-- Add empresa_id column to usuarios for tenant scoping
ALTER TABLE usuarios
ADD COLUMN IF NOT EXISTS empresa_id INTEGER NULL;

-- Add FK to empresas
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_usuarios_empresa_id' AND table_name = 'usuarios'
    ) THEN
        ALTER TABLE usuarios
        ADD CONSTRAINT fk_usuarios_empresa_id FOREIGN KEY (empresa_id)
            REFERENCES empresas(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Optional: index for lookups
CREATE INDEX IF NOT EXISTS idx_usuario_empresa_id ON usuarios(empresa_id);
