from typing import Optional
from pydantic import BaseModel, EmailStr, constr, model_validator, ConfigDict


class EmpresaBase(BaseModel):
    nombre: constr(strip_whitespace=True, min_length=1, max_length=100)
    cuit: constr(strip_whitespace=True, min_length=6, max_length=20)
    email: EmailStr
    telefono: constr(strip_whitespace=True, min_length=3, max_length=30)
    direccion: Optional[constr(strip_whitespace=True, max_length=200)] = None
    deleted: bool = False
    blacklist: bool = False


class EmpresaCreate(EmpresaBase):
    pass


class EmpresaUpdate(BaseModel):
    nombre: Optional[constr(strip_whitespace=True, min_length=1, max_length=100)] = None
    cuit: Optional[constr(strip_whitespace=True, min_length=6, max_length=20)] = None
    email: Optional[EmailStr] = None
    telefono: Optional[constr(strip_whitespace=True, min_length=3, max_length=30)] = None
    direccion: Optional[constr(strip_whitespace=True, max_length=200)] = None
    deleted: Optional[bool] = None
    blacklist: Optional[bool] = None

    @model_validator(mode="before")
    def validar_datos(cls, data):
        if isinstance(data, dict) and data:
            return data
        raise ValueError("Se requiere al menos un campo para actualizar")


class EmpresaRead(EmpresaBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
