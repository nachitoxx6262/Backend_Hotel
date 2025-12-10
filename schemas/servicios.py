from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, Field, EmailStr, PositiveInt, constr, condecimal, ConfigDict
# --------------------- PRODUCTO/SERVICIO/DESCUENTO ---------------------
class ProductoServicioBase(BaseModel):
    nombre: constr(strip_whitespace=True, min_length=1, max_length=100)
    tipo: constr(strip_whitespace=True, min_length=3, max_length=20)
    descripcion: Optional[str] = None
    precio_unitario: condecimal(max_digits=10, decimal_places=2)
    activo: Optional[bool] = True

class ProductoServicioCreate(ProductoServicioBase):
    pass

class ProductoServicioUpdate(BaseModel):
    nombre: Optional[constr(strip_whitespace=True, min_length=1, max_length=100)] = None
    tipo: Optional[constr(strip_whitespace=True, min_length=3, max_length=20)] = None
    descripcion: Optional[str] = None
    precio_unitario: Optional[condecimal(max_digits=10, decimal_places=2)] = None
    activo: Optional[bool] = None

class ProductoServicioRead(ProductoServicioBase):
    id: int
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
    actualizado_por: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
