from typing import Optional
from datetime import datetime, date
from pydantic import BaseModel, EmailStr, constr, model_validator, ConfigDict, Field
from schemas.empresas import EmpresaRead


class ClienteBase(BaseModel):
    nombre: constr(strip_whitespace=True, min_length=1, max_length=60)
    apellido: constr(strip_whitespace=True, min_length=1, max_length=60)
    tipo_documento: constr(strip_whitespace=True, min_length=2, max_length=20)
    numero_documento: constr(strip_whitespace=True, min_length=2, max_length=40)
    nacionalidad: constr(strip_whitespace=True, min_length=2, max_length=60)
    email: EmailStr
    telefono: constr(strip_whitespace=True, min_length=3, max_length=30)
    empresa_id: Optional[int] = None


class ClienteCreate(ClienteBase):
    # Campos opcionales nuevos
    telefono_alternativo: Optional[constr(strip_whitespace=True, min_length=3, max_length=30)] = None
    fecha_nacimiento: Optional[date] = None
    genero: Optional[constr(max_length=10)] = None  # M, F, O
    direccion: Optional[constr(strip_whitespace=True, max_length=200)] = None
    ciudad: Optional[constr(strip_whitespace=True, max_length=100)] = None
    provincia: Optional[constr(strip_whitespace=True, max_length=100)] = None
    codigo_postal: Optional[constr(strip_whitespace=True, max_length=20)] = None
    tipo_cliente: str = Field(default="individual", pattern="^(individual|corporativo|vip)$")
    preferencias: Optional[str] = None
    nota_interna: Optional[str] = None


class ClienteUpdate(BaseModel):
    nombre: Optional[constr(strip_whitespace=True, min_length=1, max_length=60)] = None
    apellido: Optional[constr(strip_whitespace=True, min_length=1, max_length=60)] = None
    tipo_documento: Optional[constr(strip_whitespace=True, min_length=2, max_length=20)] = None
    numero_documento: Optional[constr(strip_whitespace=True, min_length=2, max_length=40)] = None
    nacionalidad: Optional[constr(strip_whitespace=True, min_length=2, max_length=60)] = None
    email: Optional[EmailStr] = None
    telefono: Optional[constr(strip_whitespace=True, min_length=3, max_length=30)] = None
    telefono_alternativo: Optional[constr(strip_whitespace=True, min_length=3, max_length=30)] = None
    fecha_nacimiento: Optional[date] = None
    genero: Optional[constr(max_length=10)] = None
    direccion: Optional[constr(strip_whitespace=True, max_length=200)] = None
    ciudad: Optional[constr(strip_whitespace=True, max_length=100)] = None
    provincia: Optional[constr(strip_whitespace=True, max_length=100)] = None
    codigo_postal: Optional[constr(strip_whitespace=True, max_length=20)] = None
    tipo_cliente: Optional[str] = Field(None, pattern="^(individual|corporativo|vip)$")
    empresa_id: Optional[int] = None
    preferencias: Optional[str] = None
    nota_interna: Optional[str] = None
    activo: Optional[bool] = None

    @model_validator(mode="before")
    def validar_datos(cls, data):
        if isinstance(data, dict) and data:
            return data
        raise ValueError("Se requiere al menos un campo para actualizar")


class ClienteRead(ClienteBase):
    id: int
    fecha_nacimiento: Optional[date]
    genero: Optional[str]
    direccion: Optional[str]
    ciudad: Optional[str]
    provincia: Optional[str]
    codigo_postal: Optional[str]
    tipo_cliente: str
    telefono_alternativo: Optional[str]
    preferencias: Optional[str]
    nota_interna: Optional[str]
    activo: bool
    deleted: bool
    blacklist: bool
    motivo_blacklist: Optional[str]
    creado_en: datetime
    actualizado_en: datetime
    actualizado_por: Optional[str] = None
    empresa: Optional[EmpresaRead]

    model_config = ConfigDict(from_attributes=True)
