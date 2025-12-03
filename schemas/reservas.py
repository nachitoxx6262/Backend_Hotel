from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, Field, constr, condecimal, PositiveInt, model_validator, ConfigDict


class HistorialReservaRead(BaseModel):
    id: int
    estado: str
    usuario: str
    fecha: datetime

    model_config = ConfigDict(from_attributes=True)


class ReservaHabitacionCreate(BaseModel):
    habitacion_id: int
    precio_noche: condecimal(gt=0, max_digits=10, decimal_places=2)


class ReservaHabitacionRead(ReservaHabitacionCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class ReservaItemCreate(BaseModel):
    producto_id: Optional[int] = None
    descripcion: Optional[str] = None
    cantidad: PositiveInt = 1
    monto_total: condecimal(max_digits=12, decimal_places=2)
    tipo_item: constr(strip_whitespace=True, min_length=3, max_length=20)


class ReservaItemRead(ReservaItemCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class ReservaBase(BaseModel):
    cliente_id: Optional[int] = None
    empresa_id: Optional[int] = None
    fecha_checkin: date
    fecha_checkout: date
    estado: constr(strip_whitespace=True, min_length=1, max_length=20)
    notas: Optional[str] = None


class ReservaCreate(ReservaBase):
    habitaciones: List[ReservaHabitacionCreate]
    items: List[ReservaItemCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validar_reserva(self):
        if self.fecha_checkout <= self.fecha_checkin:
            raise ValueError("fecha_checkout debe ser posterior a fecha_checkin")
        if not self.habitaciones:
            raise ValueError("Se requiere al menos una habitacion")
        return self


class ReservaUpdate(BaseModel):
    fecha_checkin: Optional[date]
    fecha_checkout: Optional[date]
    estado: Optional[constr(strip_whitespace=True, min_length=1, max_length=20)]
    notas: Optional[str] = None

    @model_validator(mode="before")
    def validar_datos(cls, data):
        if isinstance(data, dict) and data:
            return data
        raise ValueError("Se requiere al menos un campo para actualizar")

    @model_validator(mode="after")
    def validar_fechas(self):
        if self.fecha_checkin and self.fecha_checkout and self.fecha_checkout <= self.fecha_checkin:
            raise ValueError("fecha_checkout debe ser posterior a fecha_checkin")
        return self


class ReservaRead(ReservaBase):
    id: int
    total: Optional[condecimal(max_digits=12, decimal_places=2)] = None
    deleted: Optional[bool] = False
    habitaciones: List[ReservaHabitacionRead] = Field(default_factory=list)
    items: List[ReservaItemRead] = Field(default_factory=list)
    historial: List[HistorialReservaRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


ReservaRead.update_forward_refs()
ReservaHabitacionRead.update_forward_refs()
ReservaItemRead.update_forward_refs()
