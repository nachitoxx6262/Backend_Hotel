"""
Script de migración para agregar columna metadata_json a la tabla transactions
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database.conexion import engine

def migrate():
    """Ejecutar la migración"""
    try:
        with engine.connect() as connection:
            # Verificar si la columna ya existe
            result = connection.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='transactions' AND column_name='metadata_json'
            """))
            
            column_exists = result.fetchone() is not None
            
            if column_exists:
                print("✓ Columna metadata_json ya existe en transactions")
                return True
            
            # Agregar la columna
            print("Agregando columna metadata_json a tabla transactions...")
            connection.execute(text("""
                ALTER TABLE transactions 
                ADD COLUMN metadata_json JSONB NULL
            """))
            
            # Crear índice para mejor performance
            connection.execute(text("""
                CREATE INDEX idx_transaction_metadata 
                ON transactions USING GIN(metadata_json)
            """))
            
            connection.commit()
            print("✓ Migración completada exitosamente")
            return True
            
    except Exception as e:
        print(f"✗ Error en migración: {str(e)}")
        return False

if __name__ == "__main__":
    success = migrate()
    exit(0 if success else 1)
