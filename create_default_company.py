from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.conexion import DATABASE_URL
from models.core import Empresa

def create_default_company():
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Check if exists again to be safe
        existing = session.query(Empresa).first()
        if existing:
            print(f"Company already exists: {existing.nombre}")
            return

        new_company = Empresa(
            nombre="Hotel Demo",
            cuit="20-12345678-9",
            tipo_empresa="Hotel",
            direccion="Calle Falsa 123",
            ciudad="Buenos Aires",
            provincia="Buenos Aires",
            activo=True
        )
        session.add(new_company)
        session.commit()
        print(f"successfully created company: {new_company.nombre}")
                
    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    create_default_company()
