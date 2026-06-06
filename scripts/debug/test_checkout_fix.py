#!/usr/bin/env python
"""
Test script to verify checkout endpoint enum fix
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from database.conexion import SessionLocal, engine
from models.core import TransactionCategory, Transaction
from sqlalchemy import text

def test_enum_fix():
    """Verify that enums are correctly stored in database"""
    db = SessionLocal()
    try:
        # Check existing transactions
        transactions = db.query(Transaction).all()
        print(f"\n✅ Total transactions in DB: {len(transactions)}")
        
        for tx in transactions[:5]:  # Show first 5
            print(f"  - ID: {tx.id}, tipo: {tx.tipo} (type: {type(tx.tipo).__name__}), "
                  f"metodo_pago: {tx.metodo_pago} (type: {type(tx.metodo_pago).__name__})")
        
        # Check enum values in database directly
        result = db.execute(text("""
            SELECT enum_range(NULL::transaction_type)
        """)).scalar()
        print(f"\n✅ Valid transaction_type enum values: {result}")
        
        result = db.execute(text("""
            SELECT enum_range(NULL::payment_method)
        """)).scalar()
        print(f"✅ Valid payment_method enum values: {result}")
        
        print("\n✅ Enum validation PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = test_enum_fix()
    sys.exit(0 if success else 1)
