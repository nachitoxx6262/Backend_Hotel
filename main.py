from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import os
import logging

from database.conexion import Base, engine
import models  # asegura que todos los modelos estén registrados
from fastapi.middleware.cors import CORSMiddleware
from utils.tenant_middleware import TenantContextMiddleware, PostgreSQLRLSMiddleware
from utils.rate_limiter import setup_rate_limiting

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("[OK] Tablas creadas (o ya existian)")
        print("[OK] Tablas creadas (o ya existian)")
    except Exception as e:
        logger.error(f"[ERROR] Error creando tablas: {e}")
        print(f"[ERROR] Error creando tablas: {e}")
    yield
    # Shutdown
    engine.dispose()
    logger.info("[OK] Conexiones de base de datos cerradas")


app = FastAPI(
    debug=os.getenv("DEBUG", "false").lower() == "true",
    lifespan=lifespan,
    title="Hotel Management API",
    version="1.0.0",
    description="Sistema de gestión hotelera multi-tenant",
)

# ========== RATE LIMITING ==========
limiter = setup_rate_limiting(app)

# ========== MIDDLEWARES ==========
# IMPORTANTE: El orden importa - se ejecutan en orden inverso al agregado
# CORS debe ser el último en agregarse para ser el primero en procesarse
# Configurar CORS
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Middleware para contexto multitenant
app.add_middleware(TenantContextMiddleware)

# Middleware para RLS de PostgreSQL
app.add_middleware(PostgreSQLRLSMiddleware)

# ========== ROUTERS ==========
from endpoints import roles, auth, hotel_calendar, pms_professional, habitaciones, clientes, settings, pricing, empresas, estadisticas, billing, admin, caja, ical_export, mercadopago as mp_router, maintenance, housekeeping_config
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(caja.router)
app.include_router(roles.router)
app.include_router(hotel_calendar.router)
app.include_router(pricing.router)
app.include_router(pms_professional.router)
app.include_router(habitaciones.router)
app.include_router(clientes.router)
app.include_router(settings.router)
app.include_router(empresas.router)
app.include_router(estadisticas.router)
app.include_router(admin.router)
app.include_router(ical_export.router)
app.include_router(mp_router.router)
app.include_router(maintenance.router)
app.include_router(housekeeping_config.router)


@app.get("/")
def read_root():
    return {"message": "¡Hola, FastAPI!"}


@app.get("/health", tags=["Sistema"])
def health_check():
    """
    Health check para load balancers y monitoreo.
    Verifica conectividad con la base de datos.
    """
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "database": "connected"}
        )
    except Exception as e:
        logger.error(f"Health check falló: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": "disconnected", "detail": str(e)}
        )
