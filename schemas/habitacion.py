from typing import Optional
from pydantic import BaseModel, PositiveInt, constr, model_validator, ConfigDict


class HabitacionBase(BaseModel):
    numero: PositiveInt
    tipo: constr(strip_whitespace=True, min_length=1, max_length=30)
    estado: constr(strip_whitespace=True, min_length=1, max_length=30)
    mantenimiento: Optional[bool] = False
    observaciones: Optional[str] = None


class HabitacionCreate(HabitacionBase):
    pass


class HabitacionUpdate(BaseModel):
    numero: Optional[PositiveInt] = None
    tipo: Optional[constr(strip_whitespace=True, min_length=1, max_length=30)] = None
    estado: Optional[constr(strip_whitespace=True, min_length=1, max_length=30)] = None
    mantenimiento: Optional[bool] = None
    observaciones: Optional[str] = None

    @model_validator(mode="before")
    def validar_datos(cls, data):
        if isinstance(data, dict) and data:
            return data
        raise ValueError("Se requiere al menos un campo para actualizar")


class HabitacionRead(HabitacionBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
