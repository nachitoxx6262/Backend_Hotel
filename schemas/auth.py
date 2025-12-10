"""
Schemas Pydantic para autenticación y autorización
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, validator


# ========== SCHEMAS DE USUARIO ==========

class UsuarioBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    nombre: Optional[str] = Field(None, max_length=60)
    apellido: Optional[str] = Field(None, max_length=60)
    rol: str = Field(default="readonly", pattern="^(admin|gerente|recepcionista|readonly)$")


class UsuarioCreate(UsuarioBase):
    password: str = Field(..., min_length=8, max_length=72)
    
    @validator('password')
    def validate_password(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError('La contraseña debe contener al menos una mayúscula')
        if not any(c.islower() for c in v):
            raise ValueError('La contraseña debe contener al menos una minúscula')
        if not any(c.isdigit() for c in v):
            raise ValueError('La contraseña debe contener al menos un número')
        return v


class UsuarioUpdate(BaseModel):
    email: Optional[EmailStr] = None
    nombre: Optional[str] = Field(None, max_length=60)
    apellido: Optional[str] = Field(None, max_length=60)
    rol: Optional[str] = Field(None, pattern="^(admin|gerente|recepcionista|readonly)$")
    activo: Optional[bool] = None


class UsuarioRead(BaseModel):
    id: int
    username: str
    email: str
    nombre: Optional[str]
    apellido: Optional[str]
    rol: str
    activo: bool
    fecha_creacion: datetime
    ultimo_login: Optional[datetime]
    
    class Config:
        from_attributes = True


class UsuarioInDB(UsuarioRead):
    hashed_password: str
    deleted: bool
    intentos_fallidos: int
    bloqueado_hasta: Optional[datetime]
    
    class Config:
        from_attributes = True


# ========== SCHEMAS DE AUTENTICACIÓN ==========

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=1, max_length=72)


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos


class TokenData(BaseModel):
    username: Optional[str] = None
    rol: Optional[str] = None
    user_id: Optional[int] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=72)
    new_password: str = Field(..., min_length=8, max_length=72)
    
    @validator('new_password')
    def validate_password(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError('La contraseña debe contener al menos una mayúscula')
        if not any(c.islower() for c in v):
            raise ValueError('La contraseña debe contener al menos una minúscula')
        if not any(c.isdigit() for c in v):
            raise ValueError('La contraseña debe contener al menos un número')
        return v


class ResetPasswordRequest(BaseModel):
    email: EmailStr


class PasswordResetToken(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=72)
