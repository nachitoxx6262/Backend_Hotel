from fastapi import FastAPI
import os

from database.conexion import Base, engine
import models  # 👈 asegura que todos los modelos estén registrados
from fastapi.middleware.cors import CORSMiddleware
from utils.tenant_middleware import TenantContextMiddleware, PostgreSQLRLSMiddleware
from utils.rate_limiter import setup_rate_limiting

try:
    #Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("[OK] Tablas creadas (o ya existian)")
except Exception as e:
    print(f"[ERROR] Error creando tablas: {e}")

app = FastAPI(debug=os.getenv("DEBUG", "false").lower() == "true")

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
from endpoints import roles, auth, hotel_calendar, pms_professional, habitaciones, clientes, settings, pricing, empresas, estadisticas, billing, admin, caja
app.include_router(auth.router)
app.include_router(billing.router)  # NUEVA: Billing endpoints
app.include_router(caja.router)  # NUEVA: Caja endpoints (Ingresos y Egresos)
app.include_router(roles.router)
app.include_router(hotel_calendar.router)
app.include_router(pricing.router)  # NUEVA: Pricing endpoints
app.include_router(pms_professional.router)
app.include_router(habitaciones.router)
app.include_router(clientes.router)
app.include_router(settings.router)
app.include_router(empresas.router)
app.include_router(estadisticas.router)
app.include_router(admin.router)


@app.get("/")
def read_root():
    return {"message": "¡Hola, FastAPI!"}
