"""Check stay for reservation 241"""
from database.conexion import get_db
from models.core import Stay

def main():
    db = next(get_db())
    
    print("\n=== STAY FOR RESERVATION 241 ===")
    stay = db.query(Stay).filter(Stay.reservation_id == 241).first()
    
    if stay:
        print(f"Stay ID: {stay.id}")
        print(f"Estado: {stay.estado}")
        print(f"empresa_usuario_id: {stay.empresa_usuario_id}")
        print(f"reservation_id: {stay.reservation_id}")
        print(f"room_id: {stay.room_id}")
        print(f"checkin_real: {stay.checkin_real}")
        print(f"checkout_real: {stay.checkout_real}")
        
        if stay.empresa_usuario_id != 17:
            print(f"\n❌ PROBLEMA: Stay tiene tenant {stay.empresa_usuario_id} pero debería ser 17")
        else:
            print(f"\n✅ Stay tiene tenant correcto (17)")
    else:
        print("❌ NO HAY STAY para reservation 241")
    
    db.close()

if __name__ == "__main__":
    main()
