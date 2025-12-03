from typing import Optional
from pydantic import BaseModel, EmailStr, constr, model_validator, ConfigDict
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
    pass


class ClienteUpdate(BaseModel):
    nombre: Optional[constr(strip_whitespace=True, min_length=1, max_length=60)] = None
    apellido: Optional[constr(strip_whitespace=True, min_length=1, max_length=60)] = None
    tipo_documento: Optional[constr(strip_whitespace=True, min_length=2, max_length=20)] = None
    numero_documento: Optional[constr(strip_whitespace=True, min_length=2, max_length=40)] = None
    nacionalidad: Optional[constr(strip_whitespace=True, min_length=2, max_length=60)] = None
    email: Optional[EmailStr] = None
    telefono: Optional[constr(strip_whitespace=True, min_length=3, max_length=30)] = None
    empresa_id: Optional[int] = None

    @model_validator(mode="before")
    def validar_datos(cls, data):
        if isinstance(data, dict) and data:
            return data
        raise ValueError("Se requiere al menos un campo para actualizar")


class ClienteRead(ClienteBase):
    id: int
    deleted: bool
    blacklist: bool
    empresa: Optional[EmpresaRead]

    model_config = ConfigDict(from_attributes=True)
