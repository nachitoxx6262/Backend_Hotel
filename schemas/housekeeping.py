from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# ===== TEMPLATES =====

class HousekeepingTareaTemplateBase(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100)
    descripcion: Optional[str] = None
    tareas: List[dict] = []  # [{nombre: str, orden: int, subtareas: [...]}]
    checklist_default: Optional[dict] = None
    minibar_default: Optional[dict] = None
    particularidades_especiales: Optional[List[str]] = None
    activo: bool = True


class HousekeepingTareaTemplateCreate(HousekeepingTareaTemplateBase):
    pass


class HousekeepingTareaTemplateUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    tareas: Optional[List[dict]] = None
    checklist_default: Optional[dict] = None
    minibar_default: Optional[dict] = None
    particularidades_especiales: Optional[List[str]] = None
    activo: Optional[bool] = None


class HousekeepingTareaTemplateRead(HousekeepingTareaTemplateBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ===== TAREAS =====

class HousekeepingIncidenciaBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tipo: str
    gravedad: str
    descripcion: str
    fotos_url: Optional[Any] = None
    created_at: datetime
    created_by: Optional[str] = None


class HousekeepingObjetoPerdidoBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    descripcion: str
    lugar: Optional[str] = None
    fecha_hallazgo: datetime
    entregado_a: Optional[str] = None
    created_at: datetime
    created_by: Optional[str] = None


class HousekeepingTareaBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    habitacion_id: int
    template_id: Optional[int] = None
    es_padre: Optional[bool] = False
    tarea_padre_id: Optional[int] = None
    estado: str
    prioridad: str
    asignado_a: Optional[str] = None
    ultimo_huesped: Optional[str] = None
    notas: Optional[str] = None
    checklist_result: Optional[Any] = None
    minibar: Optional[Any] = None
    cleaning_started_at: Optional[datetime] = None
    cleaning_finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    incidencias: List[HousekeepingIncidenciaBase] = []
    objetos_perdidos: List[HousekeepingObjetoPerdidoBase] = []


class HousekeepingObservacion(BaseModel):
    notas: str = Field(..., min_length=1, max_length=2000)


class HousekeepingIniciar(BaseModel):
    asignado_a: Optional[str] = None


class HousekeepingFinalizar(BaseModel):
    resultado: str = Field(..., pattern="^(ok|incidencia)$")
    notas: Optional[str] = None
    checklist_result: Optional[Any] = None
    minibar: Optional[Any] = None
    incidencia_tipo: Optional[str] = None
    incidencia_gravedad: Optional[str] = None
    incidencia_descripcion: Optional[str] = None


class HousekeepingIncidenciaCreate(BaseModel):
    tipo: str
    gravedad: str
    descripcion: str
    fotos_url: Optional[Any] = None


class HousekeepingObjetoPerdidoCreate(BaseModel):
    descripcion: str
    lugar: Optional[str] = None
    entregado_a: Optional[str] = None


class HousekeepingTareaDetalle(HousekeepingTareaBase):
    pass
