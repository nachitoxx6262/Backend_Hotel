from typing import Optional, List
from datetime import date
from pydantic import BaseModel, Field, EmailStr, PositiveInt, constr, condecimal
# --------------------- HABITACION ---------------------
class HabitacionBase(BaseModel):
    numero: PositiveInt
    tipo: constr(strip_whitespace=True, min_length=1, max_length=30)
    estado: constr(strip_whitespace=True, min_length=1, max_length=30)
    mantenimiento: Optional[bool] = False
    observaciones: Optional[str] = None

class HabitacionCreate(HabitacionBase):
    pass

class HabitacionUpdate(HabitacionBase):
    pass

class HabitacionRead(HabitacionBase):
    id: int

    class Config:
        orm_mode = True