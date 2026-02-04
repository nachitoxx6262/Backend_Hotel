"""
Migración: Agregar 'tarjeta_credito' y 'tarjeta_debito' al enum payment_method
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database.conexion import engine

def run():
    """Agregar valores 'tarjeta_credito' y 'tarjeta_debito' al enum payment_method"""
    with engine.connect() as conn:
        try:
            # Verificar y agregar 'tarjeta_credito'
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_enum 
                    WHERE enumlabel = 'tarjeta_credito' 
                    AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'payment_method')
                );
            """))
            exists_credito = result.scalar()
            
            if not exists_credito:
                conn.execute(text("""
                    ALTER TYPE payment_method ADD VALUE IF NOT EXISTS 'tarjeta_credito';
                """))
                conn.commit()
                print("✓ Valor 'tarjeta_credito' agregado al enum payment_method")
            else:
                print("✓ El valor 'tarjeta_credito' ya existe en payment_method")
            
            # Verificar y agregar 'tarjeta_debito'
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_enum 
                    WHERE enumlabel = 'tarjeta_debito' 
                    AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'payment_method')
                );
            """))
            exists_debito = result.scalar()
            
            if not exists_debito:
                conn.execute(text("""
                    ALTER TYPE payment_method ADD VALUE IF NOT EXISTS 'tarjeta_debito';
                """))
                conn.commit()
                print("✓ Valor 'tarjeta_debito' agregado al enum payment_method")
            else:
                print("✓ El valor 'tarjeta_debito' ya existe en payment_method")
            
        except Exception as e:
            print(f"✗ Error al agregar valores al enum: {e}")
            conn.rollback()
            raise

if __name__ == "__main__":
    print("=== Agregando 'tarjeta_credito' y 'tarjeta_debito' al enum payment_method ===")
    run()
    print("=== Migración completada ===")
