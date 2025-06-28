from typing import Optional
from pydantic import BaseModel, EmailStr, constr

class EmpresaBase(BaseModel):
    nombre: constr(strip_whitespace=True, min_length=1, max_length=100)
    cuit: constr(strip_whitespace=True, min_length=6, max_length=20)
    email: EmailStr
    telefono: constr(strip_whitespace=True, min_length=3, max_length=30)
    direccion: Optional[constr(strip_whitespace=True, max_length=200)] = None

class EmpresaCreate(EmpresaBase):
    pass

class EmpresaUpdate(EmpresaBase):
    pass

class EmpresaRead(EmpresaBase):
    id: int

    class Config:
        orm_mode = True
