"""
Script para agregar columna precio_base a la tabla room_types
"""
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

# Construir URL de la base de datos desde variables de entorno
DB_NAME = os.getenv("DB_NAME", "hotelbeta_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "admin")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
print(f"Conectando a base de datos: {DB_NAME}")

# Crear engine
engine = create_engine(DATABASE_URL)

# SQL para agregar la columna
add_column_sql = """
ALTER TABLE room_types 
ADD COLUMN IF NOT EXISTS precio_base NUMERIC(12, 2);
"""

try:
    with engine.connect() as conn:
        print("Ejecutando migración: agregar columna precio_base a room_types...")
        conn.execute(text(add_column_sql))
        conn.commit()
        print("✅ Migración completada exitosamente")
        
        # Verificar
        result = conn.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'room_types' AND column_name = 'precio_base'
        """))
        row = result.fetchone()
        if row:
            print(f"✅ Columna verificada: {row[0]} ({row[1]})")
        else:
            print("⚠️ No se pudo verificar la columna")
            
except Exception as e:
    print(f"❌ Error durante la migración: {e}")
    exit(1)
