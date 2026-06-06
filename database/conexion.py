from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from fastapi import Request
import os
from dotenv import load_dotenv

load_dotenv()

# URL de conexión clásica (síncrona) — usa psycopg2 por defecto
DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

# Crear el engine sincronico con configuración de pool
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,          # Verifica conexión antes de usar
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),          # Conexiones permanentes
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),    # Conexiones extra bajo carga
    pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),    # Segundos de espera por conexión libre
    pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),  # Reciclar conexiones cada 30 min
)

# Crear la sesión sincronica
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base
Base = declarative_base()

# ✅ IMPORTANTE: NO pongas create_all aquí directamente si estás importando este archivo desde otros lados.
# Hacelo desde main.py luego de importar los modelos
#Base.metadata.drop_all(bind=engine)
# Base.metadata.create_all(bind=engine)


# Función para obtener la sesión
def get_db(request: Request = None):
    db = SessionLocal()
    try:
        if request is not None and hasattr(request, "state"):
            try:
                from utils.tenant_middleware import set_rls_context
                tenant_id = getattr(request.state, "tenant_id", None)
                user_id = getattr(request.state, "current_user_id", None)
                is_super_admin = getattr(request.state, "is_super_admin", False)
                if user_id is not None:
                    set_rls_context(db, tenant_id, user_id, is_super_admin)
            except Exception:
                pass
        yield db
    finally:
        db.close()
