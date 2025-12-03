from fastapi import FastAPI

from database.conexion import Base, engine
import models  # 👈 asegura que todos los modelos estén registrados
from fastapi.middleware.cors import CORSMiddleware
try:
    #Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("✅ Tablas creadas (o ya existían)")
except Exception as e:
    print(f"❌ Error creando tablas: {e}")

app = FastAPI(debug=True)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,       # o ["*"] si querés habilitar todos
    allow_credentials=True,
    allow_methods=["*"],         # GET, POST, PUT, DELETE...
    allow_headers=["*"],
)
from endpoints import clientes,empresas,reservas,habitacion
app.include_router(clientes.router)
app.include_router(empresas.router)
app.include_router(reservas.router)
app.include_router(habitacion.router)

@app.get("/")
def read_root():
    return {"message": "¡Hola, FastAPI!"}
