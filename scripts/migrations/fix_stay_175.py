"""Assign tenant to stay 175"""
from database.conexion import get_db
from models.core import Stay

def main():
    db = next(get_db())
    
    print("\n=== FIXING STAY 175 ===")
    stay = db.query(Stay).filter(Stay.id == 175).first()
    
    if not stay:
        print("❌ Stay 175 not found")
        return
    
    print(f"Before: empresa_usuario_id = {stay.empresa_usuario_id}")
    
    stay.empresa_usuario_id = 17
    db.commit()
    
    print(f"After: empresa_usuario_id = {stay.empresa_usuario_id}")
    print("✅ Stay 175 updated successfully")
    
    db.close()

if __name__ == "__main__":
    main()
