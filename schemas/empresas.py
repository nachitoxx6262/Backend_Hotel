from typing import Optional
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, EmailStr, constr, model_validator, ConfigDict, Field


class EmpresaBase(BaseModel):
    nombre: constr(strip_whitespace=True, min_length=1, max_length=150)
    cuit: constr(strip_whitespace=True, min_length=6, max_length=20)
    tipo_empresa: constr(strip_whitespace=True, min_length=1, max_length=50)


class EmpresaCreate(EmpresaBase):
    # Contacto principal
    contacto_principal_nombre: constr(strip_whitespace=True, min_length=1, max_length=100)
    contacto_principal_email: EmailStr
    contacto_principal_telefono: constr(strip_whitespace=True, min_length=3, max_length=30)
    
    # Dirección
    direccion: constr(strip_whitespace=True, min_length=1, max_length=200)
    ciudad: constr(strip_whitespace=True, min_length=1, max_length=100)
    
    # Opcionales
    contacto_principal_titulo: Optional[constr(strip_whitespace=True, max_length=100)] = None
    contacto_principal_celular: Optional[constr(strip_whitespace=True, max_length=30)] = None
    provincia: Optional[constr(strip_whitespace=True, max_length=100)] = None
    codigo_postal: Optional[constr(strip_whitespace=True, max_length=20)] = None
    dias_credito: int = Field(default=30, ge=0)
    limite_credito: Decimal = Field(default=0, ge=0)
    tasa_descuento: Decimal = Field(default=0, ge=0, le=100)
    nota_interna: Optional[str] = None


class EmpresaUpdate(BaseModel):
    nombre: Optional[constr(strip_whitespace=True, min_length=1, max_length=150)] = None
    tipo_empresa: Optional[constr(strip_whitespace=True, max_length=50)] = None
    contacto_principal_nombre: Optional[constr(strip_whitespace=True, max_length=100)] = None
    contacto_principal_titulo: Optional[constr(strip_whitespace=True, max_length=100)] = None
    contacto_principal_email: Optional[EmailStr] = None
    contacto_principal_telefono: Optional[constr(strip_whitespace=True, max_length=30)] = None
    contacto_principal_celular: Optional[constr(strip_whitespace=True, max_length=30)] = None
    direccion: Optional[constr(strip_whitespace=True, max_length=200)] = None
    ciudad: Optional[constr(strip_whitespace=True, max_length=100)] = None
    provincia: Optional[constr(strip_whitespace=True, max_length=100)] = None
    codigo_postal: Optional[constr(strip_whitespace=True, max_length=20)] = None
    dias_credito: Optional[int] = Field(None, ge=0)
    limite_credito: Optional[Decimal] = Field(None, ge=0)
    tasa_descuento: Optional[Decimal] = Field(None, ge=0, le=100)
    nota_interna: Optional[str] = None
    activo: Optional[bool] = None

    @model_validator(mode="before")
    def validar_datos(cls, data):
        if isinstance(data, dict) and data:
            return data
        raise ValueError("Se requiere al menos un campo para actualizar")


class EmpresaRead(EmpresaBase):
    id: int
    contacto_principal_nombre: str
    contacto_principal_email: str
    contacto_principal_telefono: str
    contacto_principal_titulo: Optional[str]
    contacto_principal_celular: Optional[str]
    direccion: str
    ciudad: str
    provincia: Optional[str]
    codigo_postal: Optional[str]
    dias_credito: int
    limite_credito: Decimal
    tasa_descuento: Decimal
    activo: bool
    deleted: bool
    blacklist: bool
    motivo_blacklist: Optional[str]
    nota_interna: Optional[str]
    creado_en: datetime
    actualizado_en: datetime
    actualizado_por: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
