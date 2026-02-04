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
    empresa_usuario_id: Optional[int] = None
    es_super_admin: bool = False
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
    empresa_usuario_id: Optional[int] = None  # Tenant ID para multi-tenant
    es_super_admin: bool = False  # Flag para super admin SaaS


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


# ========== SCHEMAS MULTI-TENANT ==========

class TrialStatusResponse(BaseModel):
    """Información del estado del trial"""
    is_active: bool
    days_remaining: Optional[int]
    expires_at: Optional[str]
    status: str  # "active" | "expired" | "not_trial"
    message: str
    
    class Config:
        from_attributes = True


class EmpresaUsuarioResponse(BaseModel):
    """Información pública de una empresa usuario (tenant)"""
    id: int
    nombre_hotel: str
    ciudad: Optional[str]
    provincia: Optional[str]
    plan_tipo: str
    activa: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class SubscriptionResponse(BaseModel):
    """Información de la suscripción SaaS"""
    id: int
    empresa_usuario_id: int
    plan_id: int
    estado: str  # "activo" | "vencido" | "cancelado" | "bloqueado"
    fecha_proxima_renovacion: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True


class MultiTenantLoginResponse(BaseModel):
    """Respuesta de login multi-tenant"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: int
    username: str
    empresa_usuario_id: Optional[int]
    es_super_admin: bool
    trial_status: Optional[TrialStatusResponse]
    
    class Config:
        from_attributes = True


class RegisterEmpresaUsuarioRequest(BaseModel):
    """Request para registrar nuevo hotel (SaaS signup)"""
    nombre_hotel: str = Field(..., min_length=3, max_length=150)
    cuit: str = Field(..., pattern=r"^\d{11}$")  # CUIT argentino: 11 dígitos
    
    contacto_nombre: str = Field(..., min_length=2, max_length=100)
    contacto_email: EmailStr
    contacto_telefono: str = Field(..., min_length=10, max_length=30)
    
    direccion: str = Field(..., min_length=5, max_length=200)
    ciudad: str = Field(..., min_length=2, max_length=100)
    provincia: str = Field(..., min_length=2, max_length=100)
    
    admin_username: str = Field(..., min_length=3, max_length=50)
    admin_email: EmailStr
    admin_password: str = Field(..., min_length=8, max_length=72)
    
    @validator('admin_password')
    def validate_password(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError('La contraseña debe contener al menos una mayúscula')
        if not any(c.islower() for c in v):
            raise ValueError('La contraseña debe contener al menos una minúscula')
        if not any(c.isdigit() for c in v):
            raise ValueError('La contraseña debe contener al menos un número')
        return v

