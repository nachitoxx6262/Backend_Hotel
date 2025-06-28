from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

# URL de conexión clásica (síncrona) — usa psycopg2 por defecto
DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

# Crear el engine sincronico
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Crear la sesión sincronica
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base
Base = declarative_base()

# ✅ IMPORTANTE: NO pongas create_all aquí directamente si estás importando este archivo desde otros lados.
# Hacelo desde main.py luego de importar los modelos
# Base.metadata.create_all(bind=engine)

# Función para obtener la sesión
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
