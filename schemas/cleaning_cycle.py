from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field, ConfigDict


class CleaningChecklistItemBase(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str] = None
    orden: int
    done: bool
    observaciones: Optional[str] = None
    parent_id: Optional[int] = None
    extra: Optional[Any] = None

    model_config = ConfigDict(from_attributes=True)


class CleaningChecklistItemUpdate(BaseModel):
    done: Optional[bool] = None
    observaciones: Optional[str] = None


class CleaningEventBase(BaseModel):
    id: int
    tipo_evento: str
    descripcion: Optional[str] = None
    timestamp: datetime
    extra_json: Optional[Any] = None
    responsable: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CleaningEventCreate(BaseModel):
    tipo_evento: str = Field(..., min_length=3, max_length=50)
    descripcion: Optional[str] = None
    extra_json: Optional[Any] = None
    responsable: Optional[str] = None


class CleaningLostItemBase(BaseModel):
    id: int
    descripcion: str
    lugar: Optional[str] = None
    entregado_a: Optional[str] = None
    created_at: datetime
    responsable: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CleaningLostItemCreate(BaseModel):
    descripcion: str = Field(..., min_length=2, max_length=500)
    lugar: Optional[str] = None
    entregado_a: Optional[str] = None
    responsable: Optional[str] = None


class CleaningIncidentBase(BaseModel):
    id: int
    tipo: str
    gravedad: str
    descripcion: str
    fotos_url: Optional[Any] = None
    created_at: datetime
    responsable: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CleaningIncidentCreate(BaseModel):
    tipo: str = Field(..., min_length=2, max_length=50)
    gravedad: str = Field("media", pattern="^(alta|media|baja)$")
    descripcion: str = Field(..., min_length=5)
    fotos_url: Optional[Any] = None
    responsable: Optional[str] = None


class CleaningCycleBase(BaseModel):
    id: int
    habitacion_id: int
    reserva_id: Optional[int] = None
    estado: str
    responsable_inicio: Optional[str] = None
    responsable_fin: Optional[str] = None
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    observaciones_finales: Optional[str] = None
    minibar_snapshot: Optional[Any] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CleaningCycleCreate(BaseModel):
    habitacion_id: int
    reserva_id: Optional[int] = None
    responsable: Optional[str] = None


class CleaningCycleList(CleaningCycleBase):
    habitacion_numero: Optional[int] = None  # Número real de habitación
    checklist_items: List[CleaningChecklistItemBase] = []
    incidents_count: int = 0
    lost_items_count: int = 0
    events_count: int = 0


class CleaningCycleDetail(CleaningCycleBase):
    checklist_items: List[CleaningChecklistItemBase] = []
    events: List[CleaningEventBase] = []
    lost_items: List[CleaningLostItemBase] = []
    incidents: List[CleaningIncidentBase] = []


class CleaningCycleStart(BaseModel):
    responsable: Optional[str] = None


class CleaningCycleFinish(BaseModel):
    responsable: Optional[str] = None
    observaciones_finales: Optional[str] = None
    enviar_mantenimiento: bool = False


class CleaningCyclePauseResume(BaseModel):
    responsable: Optional[str] = None


class CleaningChecklistToggle(BaseModel):
    done: bool
    observaciones: Optional[str] = None
