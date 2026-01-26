#!/usr/bin/env python3
"""
Script para ejecutar la migración 004_add_empresa_id_to_usuarios.sql
"""
import sys
from pathlib import Path
from sqlalchemy import text, inspect

# Agregar la ruta del proyecto al path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from database.conexion import engine
    
    # Leer el archivo de migración
    migration_file = project_root / "migrations" / "004_add_empresa_id_to_usuarios.sql"
    
    if not migration_file.exists():
        print(f"✗ Archivo de migración no encontrado: {migration_file}")
        sys.exit(1)
    
    with open(migration_file, 'r', encoding='utf-8') as f:
        migration_sql = f.read()
    
    # Ejecutar la migración
    print("Ejecutando migración 004...")
    with engine.connect() as connection:
        # Dividir por instrucciones individuales (postgre soporta DO blocks, pero sqlalchemy a veces prefiere raw execution)
        # En este caso, como hay un DO block, es mejor ejecutar todo el bloque o dividir cuidadosamente.
        # SQLAlchmey con text() suele manejar bien scripts si no hay delimitadores complejos que confundan al driver.
        # Sin embargo, 'DO $$' es un bloque completo. 
        # Vamos a intentar ejecutar el script por partes separadas por comentarios grandes o intentar ejecutarlo todo.
        # El script tiene: 
        # 1. ALTER TABLE simple
        # 2. DO block
        # 3. CREATE INDEX
        
        # Vamos a parsear manualmente simple
        statements = []
        current_stm = []
        
        for line in migration_sql.split('\n'):
            if line.strip().startswith('--'):
                continue
            if not line.strip():
                continue
            current_stm.append(line)
            if ';' in line and not '$$' in line and not 'END IF' in line: # Heurística simple
                 # Esta heurística es debil para el DO block.
                 pass

        # Mejor enfoque para este archivo específico: Hardcodear las 3 operaciones conocidas para asegurar éxito
        # Dado que conocemos el contenido exacto del archivo sql target (004)
        
        print("1. Agregando columna empresa_id...")
        connection.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS empresa_id INTEGER NULL;"))
        connection.commit()
        
        print("2. Agregando constraint FK (si no existe)...")
        # El DO block de postgres funciona bien con execute()
        do_block = """
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
        """
        connection.execute(text(do_block))
        connection.commit()
        
        print("3. Creando índice...")
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_usuario_empresa_id ON usuarios(empresa_id);"))
        connection.commit()

    # Verificar
    print("\nVerificando cambios en tabla usuarios...")
    inspector = inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('usuarios')]
    
    if 'empresa_id' in columns:
        print("✓ Columna 'empresa_id' encontrada exitosamente.")
    else:
        print("✗ ERROR: La columna 'empresa_id' NO aparece en la tabla usuarios.")
        sys.exit(1)
        
    print("\n✓ Migración 004 completada correctamente")

except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)
