from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, Field, constr, condecimal, PositiveInt, model_validator, ConfigDict


class HistorialReservaRead(BaseModel):
    id: int
    estado_anterior: Optional[str] = None
    estado_nuevo: str
    usuario: str
    fecha: datetime
    motivo: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ReservaHabitacionCreate(BaseModel):
    habitacion_id: int
    precio_noche: condecimal(gt=0, max_digits=10, decimal_places=2)


class ReservaHabitacionRead(ReservaHabitacionCreate):
    id: int
    cantidad_noches: int
    subtotal_habitacion: condecimal(max_digits=12, decimal_places=2)
    habitacion_numero: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class ReservaItemCreate(BaseModel):
    producto_id: Optional[int] = None
    descripcion: Optional[str] = None
    cantidad: PositiveInt = 1
    monto_unitario: condecimal(ge=0, max_digits=10, decimal_places=2)
    monto_total: condecimal(ge=0, max_digits=12, decimal_places=2)
    tipo_item: constr(strip_whitespace=True, min_length=3, max_length=20)


class ReservaItemRead(ReservaItemCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class ReservaBase(BaseModel):
    cliente_id: Optional[int] = None
    empresa_id: Optional[int] = None
    nombre_temporal: Optional[constr(strip_whitespace=True, max_length=100)] = None  # Para reservas sin asignar
    fecha_checkin: date
    fecha_checkout: date
    cantidad_adultos: Optional[int] = Field(1, ge=1)
    cantidad_menores: Optional[int] = Field(0, ge=0)
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


class ReservaMove(BaseModel):
    fecha_checkin: date = Field(..., alias="fechaCheckin")
    fecha_checkout: date = Field(..., alias="fechaCheckout")
    reserva_habitacion_id: int = Field(..., alias="reservaHabitacionId")
    nueva_habitacion_id: Optional[int] = Field(None, alias="nuevaHabitacionId")
    usuario: constr(strip_whitespace=True, min_length=1, max_length=50) = "admin"
    motivo: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validar_rango(self):
        if self.fecha_checkout <= self.fecha_checkin:
            raise ValueError("fecha_checkout debe ser posterior a fecha_checkin")
        return self


class ReservaRead(ReservaBase):
    id: int
    subtotal: Optional[condecimal(max_digits=12, decimal_places=2)] = None
    descuento: Optional[condecimal(max_digits=12, decimal_places=2)] = None
    impuestos: Optional[condecimal(max_digits=12, decimal_places=2)] = None
    total: Optional[condecimal(max_digits=12, decimal_places=2)] = None
    deleted: Optional[bool] = False
    creado_en: Optional[datetime] = None
    creado_por: Optional[str] = None
    actualizado_en: Optional[datetime] = None
    actualizado_por: Optional[str] = None
    habitaciones: List[ReservaHabitacionRead] = Field(default_factory=list)
    items: List[ReservaItemRead] = Field(default_factory=list)
    historial: List[HistorialReservaRead] = Field(default_factory=list)
    fecha_entrada: Optional[date] = None  # Alias para frontend
    fecha_salida: Optional[date] = None   # Alias para frontend
    numero_noches: Optional[int] = None
    # Campos calculados para el frontend
    cliente_nombre: Optional[str] = None
    empresa_nombre: Optional[str] = None
    habitacion_numero: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


ReservaRead.update_forward_refs()
ReservaHabitacionRead.update_forward_refs()
ReservaItemRead.update_forward_refs()
