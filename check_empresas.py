from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from database.conexion import DATABASE_URL
from models.core import Empresa

def check_empresas():
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        count = session.query(func.count(Empresa.id)).scalar()
        print(f"Total active companies: {count}")
        
        if count > 0:
            empresas = session.query(Empresa).all()
            for e in empresas:
                print(f"ID: {e.id}, Nombre: {e.nombre}, Activo: {e.activo}")
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    check_empresas()
