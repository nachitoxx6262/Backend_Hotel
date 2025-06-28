from typing import Optional
from pydantic import BaseModel, EmailStr, constr
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

class ClienteUpdate(ClienteBase):
    pass

class ClienteRead(ClienteBase):
    id: int
    empresa: Optional[EmpresaRead]

    class Config:
        orm_mode = True
