from pydantic import BaseModel, Field
from typing import List, Optional


class PermisoBase(BaseModel):
    codigo: str = Field(..., min_length=3, max_length=100)
    nombre: str = Field(..., min_length=3, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=255)
    activo: bool = True


class PermisoCreate(PermisoBase):
    pass


class PermisoUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=3, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=255)
    activo: Optional[bool] = None


class PermisoRead(PermisoBase):
    id: int

    class Config:
        from_attributes = True


class RolBase(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=50)
    descripcion: Optional[str] = Field(None, max_length=255)
    activo: bool = True


class RolCreate(RolBase):
    permisos_codigos: Optional[List[str]] = []


class RolUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=3, max_length=50)
    descripcion: Optional[str] = Field(None, max_length=255)
    activo: Optional[bool] = None
    permisos_codigos: Optional[List[str]] = None


class RolRead(RolBase):
    id: int
    permisos: List[PermisoRead] = []

    class Config:
        from_attributes = True


class AsignarPermisosRequest(BaseModel):
    permisos_codigos: List[str] = Field(..., min_items=1)


class AsignarRolesRequest(BaseModel):
    roles_nombres: List[str] = Field(..., min_items=1)
