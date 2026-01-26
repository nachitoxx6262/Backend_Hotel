from sqlalchemy import text
from database.conexion import SessionLocal

def migrate():
    db = SessionLocal()
    try:
        print("Migrating: Adding timezone column to hotel_settings...")
        # Check if column exists
        result = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='hotel_settings' AND column_name='timezone'"))
        if result.fetchone():
            print("Column 'timezone' already exists. Skipping.")
        else:
            db.execute(text("ALTER TABLE hotel_settings ADD COLUMN timezone VARCHAR(50) NOT NULL DEFAULT 'America/Argentina/Buenos_Aires'"))
            db.commit()
            print("Migration successful: Added 'timezone' column.")
            
    except Exception as e:
        db.rollback()
        print(f"Migration failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
