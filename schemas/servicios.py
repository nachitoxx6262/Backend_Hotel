from typing import Optional, List
from datetime import date
from pydantic import BaseModel, Field, EmailStr, PositiveInt, constr, condecimal
# --------------------- PRODUCTO/SERVICIO/DESCUENTO ---------------------
class ProductoServicioBase(BaseModel):
    nombre: constr(strip_whitespace=True, min_length=1, max_length=100)
    tipo: constr(strip_whitespace=True, min_length=3, max_length=20)
    descripcion: Optional[str] = None
    precio_unitario: condecimal(max_digits=10, decimal_places=2)

class ProductoServicioCreate(ProductoServicioBase):
    pass

class ProductoServicioUpdate(ProductoServicioBase):
    pass

class ProductoServicioRead(ProductoServicioBase):
    id: int

    class Config:
        orm_mode = True
