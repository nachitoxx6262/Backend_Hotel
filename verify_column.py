"""
Verificar que la columna nombre_temporal existe en la tabla reservas
"""
from sqlalchemy import create_engine, text, inspect
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

def verify_column():
    engine = create_engine(DATABASE_URL)
    
    try:
        inspector = inspect(engine)
        columns = inspector.get_columns('reservas')
        
        print("Columnas en la tabla 'reservas':")
        print("-" * 60)
        for col in columns:
            print(f"  - {col['name']}: {col['type']}")
        
        print("-" * 60)
        
        # Verificar específicamente nombre_temporal
        column_names = [col['name'] for col in columns]
        if 'nombre_temporal' in column_names:
            print("✅ La columna 'nombre_temporal' EXISTE en la tabla 'reservas'")
        else:
            print("❌ La columna 'nombre_temporal' NO EXISTE en la tabla 'reservas'")
            print("\n⚠️  Ejecute: python add_nombre_temporal_column.py")
                
    except Exception as e:
        print(f"❌ Error al verificar columna: {e}")
    finally:
        engine.dispose()

if __name__ == "__main__":
    verify_column()
