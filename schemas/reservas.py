from typing import Optional, List
from datetime import date
from pydantic import BaseModel, Field, constr, condecimal, PositiveInt

# ----------- RESERVA HABITACION SCHEMAS -----------
class ReservaHabitacionCreate(BaseModel):
    habitacion_id: int
    precio_noche: condecimal(gt=0, max_digits=10, decimal_places=2)

class ReservaHabitacionRead(ReservaHabitacionCreate):
    id: int
    # habitacion: Optional[HabitacionRead]   # si querés traer datos de la habitación, descomenta esto

    class Config:
        orm_mode = True

# ----------- RESERVA ITEM SCHEMAS -----------
class ReservaItemCreate(BaseModel):
    producto_id: Optional[int] = None
    descripcion: Optional[str] = None
    cantidad: PositiveInt = 1
    monto_total: condecimal(max_digits=12, decimal_places=2)
    tipo_item: constr(strip_whitespace=True, min_length=3, max_length=20)

class ReservaItemRead(ReservaItemCreate):
    id: int
    # producto: Optional[ProductoServicioRead]  # si lo necesitás, descomenta

    class Config:
        orm_mode = True

# ----------- RESERVA SCHEMAS -----------
class ReservaBase(BaseModel):
    cliente_id: Optional[int] = None
    empresa_id: Optional[int] = None
    fecha_checkin: date
    fecha_checkout: date
    estado: constr(strip_whitespace=True, min_length=1, max_length=20)

class ReservaCreate(ReservaBase):
    habitaciones: List[ReservaHabitacionCreate]
    items: List[ReservaItemCreate] = Field(default_factory=list)

class ReservaUpdate(BaseModel):
    fecha_checkin: Optional[date]
    fecha_checkout: Optional[date]
    estado: Optional[constr(strip_whitespace=True, min_length=1, max_length=20)]

class ReservaRead(ReservaBase):
    id: int
    total: Optional[condecimal(max_digits=12, decimal_places=2)] = None
    # cliente: Optional[ClienteRead]  # descomenta si lo querés expandido
    # empresa: Optional[EmpresaRead]
    habitaciones: List[ReservaHabitacionRead] = Field(default_factory=list)
    items: List[ReservaItemRead] = Field(default_factory=list)

    class Config:
        orm_mode = True

# --- Referencias circulares (por si acaso) ---
ReservaRead.update_forward_refs()
ReservaHabitacionRead.update_forward_refs()
ReservaItemRead.update_forward_refs()
