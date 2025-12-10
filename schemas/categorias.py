"""
Schemas (Pydantic) para Categorías de Habitaciones
"""
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List, Union
import json


class CategoriaCreate(BaseModel):
    """Schema para crear una categoría"""
    nombre: str = Field(..., min_length=1, max_length=100, description="Nombre de la categoría")
    descripcion: Optional[str] = Field(None, max_length=500, description="Descripción detallada")
    capacidad_personas: int = Field(..., gt=0, description="Capacidad máxima de personas")
    precio_base_noche: float = Field(..., ge=0, description="Precio base por noche")
    amenidades: Optional[List[str]] = Field(default_factory=list, description="Lista de amenidades")


class CategoriaUpdate(BaseModel):
    """Schema para actualizar una categoría"""
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=500)
    capacidad_personas: Optional[int] = Field(None, gt=0)
    precio_base_noche: Optional[float] = Field(None, ge=0)
    amenidades: Optional[List[str]] = Field(None)
    activo: Optional[bool] = Field(None)


class CategoriaRead(BaseModel):
    """Schema para leer/responder categorías"""
    id: int
    nombre: str
    descripcion: Optional[str]
    capacidad_personas: int
    precio_base_noche: float
    amenidades: Optional[Union[List[str], str]] = None
    activo: bool
    creado_en: datetime
    actualizado_en: datetime

    @field_validator("amenidades", mode="before")
    @classmethod
    def parse_amenidades(cls, v):
        """Convierte string JSON a lista si es necesario"""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                # Si es un string simple, devolverlo como lista
                return [v] if v else []
        elif isinstance(v, list):
            return v
        return [] if v is None else v

    class Config:
        from_attributes = True

