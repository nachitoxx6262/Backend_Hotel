"""
Migración: Agregar 'qr' al enum payment_method
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database.conexion import engine

def run():
    """Agregar valor 'qr' al enum payment_method"""
    with engine.connect() as conn:
        try:
            # Verificar si 'qr' ya existe en el enum
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_enum 
                    WHERE enumlabel = 'qr' 
                    AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'payment_method')
                );
            """))
            exists = result.scalar()
            
            if exists:
                print("✓ El valor 'qr' ya existe en payment_method")
                return
            
            # Agregar 'qr' al enum payment_method
            conn.execute(text("""
                ALTER TYPE payment_method ADD VALUE IF NOT EXISTS 'qr';
            """))
            conn.commit()
            
            print("✓ Valor 'qr' agregado al enum payment_method")
            
        except Exception as e:
            print(f"✗ Error al agregar 'qr' al enum: {e}")
            conn.rollback()
            raise

if __name__ == "__main__":
    print("=== Agregando 'qr' al enum payment_method ===")
    run()
    print("=== Migración completada ===")
