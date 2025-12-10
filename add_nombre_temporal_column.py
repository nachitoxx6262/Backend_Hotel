"""
Script de migración para agregar la columna nombre_temporal a la tabla reservas
Ejecutar una sola vez: python add_nombre_temporal_column.py
"""

from sqlalchemy import create_engine, text

import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

def add_nombre_temporal_column():
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.connect() as connection:
            # Verificar si la columna ya existe
            result = connection.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='reservas' AND column_name='nombre_temporal'
            """))
            
            if result.fetchone() is None:
                # La columna no existe, agregarla
                connection.execute(text("""
                    ALTER TABLE reservas 
                    ADD COLUMN nombre_temporal VARCHAR(100) NULL
                """))
                connection.commit()
                print("✅ Columna 'nombre_temporal' agregada exitosamente a la tabla 'reservas'")
            else:
                print("ℹ️  La columna 'nombre_temporal' ya existe en la tabla 'reservas'")
                
    except Exception as e:
        print(f"❌ Error al agregar la columna: {e}")
    finally:
        engine.dispose()

if __name__ == "__main__":
    print("Iniciando migración...")
    add_nombre_temporal_column()
    print("Migración completada.")
