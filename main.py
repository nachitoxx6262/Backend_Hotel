from fastapi import FastAPI

from database.conexion import Base, engine
import models  # 👈 asegura que todos los modelos estén registrados

try:
    Base.metadata.create_all(bind=engine)
    print("✅ Tablas creadas (o ya existían)")
except Exception as e:
    print(f"❌ Error creando tablas: {e}")

app = FastAPI(debug=True)


from endpoints import clientes,empresas,reservas,habitacion
app.include_router(clientes.router)
app.include_router(empresas.router)
app.include_router(reservas.router)
app.include_router(habitacion.router)

@app.get("/")
def read_root():
    return {"message": "¡Hola, FastAPI!"}
