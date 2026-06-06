"""Check hotel_settings for tenant 17"""
from database.conexion import get_db
from models.core import HotelSettings

def main():
    db = next(get_db())
    
    print("\n=== HOTEL_SETTINGS FOR TENANT 17 ===")
    settings = db.query(HotelSettings).filter(HotelSettings.empresa_usuario_id == 17).first()
    
    if settings:
        print(f"ID: {settings.id}")
        print(f"empresa_usuario_id: {settings.empresa_usuario_id}")
        print(f"checkout_hour: {settings.checkout_hour}")
        print(f"checkout_minute: {settings.checkout_minute}")
        print(f"timezone: {settings.timezone}")
        print(f"created_at: {settings.created_at}")
        print(f"updated_at: {settings.updated_at}")
        print("\n✅ Settings exist")
    else:
        print("❌ NO SETTINGS for tenant 17")
        print("\nAttempting to create default settings...")
        
        new_settings = HotelSettings(
            empresa_usuario_id=17,
            checkout_hour=12,
            checkout_minute=0,
            cleaning_start_hour=10,
            cleaning_end_hour=12,
            auto_extend_stays=True,
            timezone="America/Argentina/Buenos_Aires",
            overstay_price=None
        )
        db.add(new_settings)
        db.commit()
        db.refresh(new_settings)
        
        print(f"\n✅ Created settings ID {new_settings.id}")
    
    db.close()

if __name__ == "__main__":
    main()
