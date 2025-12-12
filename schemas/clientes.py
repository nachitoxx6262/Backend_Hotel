from typing import Optional
from datetime import datetime, date
from pydantic import BaseModel, EmailStr, constr, model_validator, ConfigDict, Field
from schemas.empresas import EmpresaRead


class ClienteBase(BaseModel):
    nombre: constr(strip_whitespace=True, min_length=1, max_length=60)
    apellido: constr(strip_whitespace=True, min_length=1, max_length=60)
    tipo_documento: Optional[constr(strip_whitespace=True, min_length=2, max_length=20)] = "DNI"
    numero_documento: constr(strip_whitespace=True, min_length=2, max_length=40)
    nacionalidad: Optional[constr(strip_whitespace=True, min_length=2, max_length=60)] = None
    email: Optional[EmailStr] = None
    telefono: Optional[constr(strip_whitespace=True, min_length=3, max_length=30)] = None
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


class ClienteRead(BaseModel):
    # Campos obligatorios
    id: int
    nombre: constr(strip_whitespace=True, min_length=1, max_length=60)
    apellido: constr(strip_whitespace=True, min_length=1, max_length=60)
    tipo_documento: constr(strip_whitespace=True, min_length=2, max_length=20)
    numero_documento: constr(strip_whitespace=True, min_length=2, max_length=40)

    # Campos opcionales (permitir None o cadena vacía desde BD)
    nacionalidad: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    telefono_alternativo: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    genero: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    provincia: Optional[str] = None
    codigo_postal: Optional[str] = None
    empresa_id: Optional[int] = None
    tipo_cliente: str
    preferencias: Optional[str] = None
    nota_interna: Optional[str] = None

    # Estado
    activo: bool
    deleted: bool
    blacklist: bool
    motivo_blacklist: Optional[str] = None

    # Auditoría
    creado_en: datetime
    actualizado_en: datetime
    actualizado_por: Optional[str] = None

    # Relaciones expandidas
    empresa: Optional[EmpresaRead] = None

    model_config = ConfigDict(from_attributes=True)
