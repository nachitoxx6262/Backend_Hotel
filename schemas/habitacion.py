from typing import Optional, List, Dict, Any
from datetime import datetime, date
from pydantic import BaseModel, PositiveInt, Field, model_validator, ConfigDict


class HabitacionBase(BaseModel):
    numero: PositiveInt = Field(..., gt=0, description="Número único de habitación")
    categoria_id: int = Field(..., gt=0, description="ID de la categoría de habitación")
    estado: str = Field(..., min_length=1, max_length=30, description="Estado de la habitación")
    piso: Optional[int] = Field(None, ge=0, description="Número de piso")
    observaciones: Optional[str] = None
    fotos_url: Optional[str] = Field(None, description="URLs de fotos de la habitación (JSON)")
    # Nuevos campos para camas y particularidades
    num_camas: Optional[int] = Field(1, ge=1, description="Número total de camas")
    tipo_camas: Optional[str] = Field(None, max_length=100, description="Descripción del tipo de camas (Ej: 1 doble + 2 simples)")
    particularidades: Optional[Dict[str, Any]] = Field(None, description="Detalles especiales de la habitación")
    template_tareas_id: Optional[int] = Field(None, gt=0, description="ID del template de tareas de limpieza")
    activo: Optional[bool] = Field(True, description="Si la habitación está activa")


class HabitacionCreate(HabitacionBase):
    pass


class HabitacionUpdate(BaseModel):
    numero: Optional[PositiveInt] = Field(None, gt=0)
    categoria_id: Optional[int] = Field(None, gt=0)
    estado: Optional[str] = Field(None, min_length=1, max_length=30)
    piso: Optional[int] = Field(None, ge=0)
    observaciones: Optional[str] = None
    fotos_url: Optional[str] = None
    num_camas: Optional[int] = Field(None, ge=1)
    tipo_camas: Optional[str] = Field(None, max_length=100)
    particularidades: Optional[Dict[str, Any]] = None
    template_tareas_id: Optional[int] = Field(None, gt=0)
    activo: Optional[bool] = None

    @model_validator(mode="before")
    def validar_datos(cls, data):
        if isinstance(data, dict) and data:
            return data
        raise ValueError("Se requiere al menos un campo para actualizar")


class HabitacionRead(HabitacionBase):
    id: int
    deleted: bool = False
    fotos_url: Optional[str] = None
    actualizado_por: Optional[str] = None
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
    # Campos calculados para el frontend
    categoria_nombre: Optional[str] = None
    precio_noche: Optional[float] = None
    descripcion: Optional[str] = None  # Alias de observaciones

    model_config = ConfigDict(from_attributes=True)


class OcupacionHabitacion(BaseModel):
    reserva_id: int
    huesped: str
    fecha_checkin: date
    fecha_checkout: date
    estado: str
    empresa: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class EventoHistorialHabitacion(BaseModel):
    fecha: datetime
    estado_anterior: Optional[str] = None
    estado_nuevo: str
    usuario: str
    motivo: Optional[str] = None
    reserva_id: int

    model_config = ConfigDict(from_attributes=True)


class MantenimientoHabitacionRead(BaseModel):
    id: int
    tipo: str
    estado: str
    descripcion: str
    observaciones: Optional[str] = None
    fecha_programada: date
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    responsable: Optional[str] = None
    supervisor: Optional[str] = None
    costo_estimado: Optional[float] = None
    costo_real: Optional[float] = None
    creado_en: Optional[datetime] = None
    creado_por: Optional[str] = None
    actualizado_en: Optional[datetime] = None
    actualizado_por: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class HistorialHabitacionResponse(BaseModel):
    habitacion_id: int
    numero: int
    ocupaciones: List[OcupacionHabitacion]
    historial_estados: List[EventoHistorialHabitacion]
    mantenimientos: List[MantenimientoHabitacionRead]

    model_config = ConfigDict(from_attributes=True)
