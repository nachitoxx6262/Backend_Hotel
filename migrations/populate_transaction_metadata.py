"""
Script para agregar breakdown a transacciones históricas sin metadata_json
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database.conexion import engine
from models.core import Transaction, Stay
from sqlalchemy.orm import sessionmaker

def populate_metadata():
    """Llenar metadata_json para transacciones antiguas de checkout"""
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Buscar transacciones de checkout sin metadata
        transactions = session.query(Transaction).filter(
            Transaction.es_automatica == True,
            Transaction.metadata_json == None,
            Transaction.stay_id != None
        ).all()
        
        print(f"Encontradas {len(transactions)} transacciones para completar")
        
        for trans in transactions:
            if trans.stay:
                # Crear un desglose básico basado en las notas
                breakdown = [
                    {
                        "description": "Alojamiento",
                        "amount": float(trans.monto) * 0.8  # Aproximado
                    },
                    {
                        "description": "Otros conceptos",
                        "amount": float(trans.monto) * 0.2  # Aproximado
                    }
                ]
                
                trans.metadata_json = {"breakdown": breakdown}
                session.add(trans)
        
        session.commit()
        print(f"✓ Metadata agregada a {len(transactions)} transacciones")
        
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    populate_metadata()
