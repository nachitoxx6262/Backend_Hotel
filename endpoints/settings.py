"""
Endpoints para gestión de Configuraciones del Hotel (HotelSettings)
"""
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_
from pydantic import BaseModel, Field, field_validator

from database.conexion import get_db
from models.core import HotelSettings, EmpresaUsuario
from utils.dependencies import get_current_user
from utils.logging_utils import log_event

router = APIRouter(prefix="/api/settings", tags=["settings"])


# Schemas
class HotelSettingsCreate(BaseModel):
    empresa_usuario_id: int
    checkout_hour: int = Field(default=12, ge=0, le=23)
    checkout_minute: int = Field(default=0, ge=0, le=59)
    cleaning_start_hour: int = Field(default=10, ge=0, le=23)
    cleaning_end_hour: int = Field(default=12, ge=0, le=23)
    auto_extend_stays: bool = True
    timezone: str = "America/Argentina/Buenos_Aires"
    overstay_price: Optional[float] = None

    class Config:
        from_attributes = True


class HotelSettingsUpdate(BaseModel):
    checkout_hour: Optional[int] = Field(None, ge=0, le=23)
    checkout_minute: Optional[int] = Field(None, ge=0, le=59)
    cleaning_start_hour: Optional[int] = Field(None, ge=0, le=23)
    cleaning_end_hour: Optional[int] = Field(None, ge=0, le=23)
    auto_extend_stays: Optional[bool] = None
    timezone: Optional[str] = None
    overstay_price: Optional[float] = None

    # Documentos requeridos en check-in
    documentos_requeridos: Optional[list] = None

    # Datos fiscales
    nombre_fiscal: Optional[str] = Field(None, max_length=200)
    direccion_fiscal: Optional[str] = None
    iva_porcentaje: Optional[float] = Field(None, ge=0, le=100)
    moneda_simbolo: Optional[str] = Field(None, max_length=10)
    logo_url: Optional[str] = Field(None, max_length=500)

    # SMTP por tenant
    smtp_host: Optional[str] = Field(None, max_length=200)
    smtp_port: Optional[int] = Field(None, ge=1, le=65535)
    smtp_user: Optional[str] = Field(None, max_length=200)
    smtp_password: Optional[str] = None  # se guardará cifrado
    smtp_from_email: Optional[str] = Field(None, max_length=200)

    # Feature flags
    housekeeping_enabled: Optional[bool] = None

    class Config:
        from_attributes = True


class HotelSettingsRead(BaseModel):
    id: int
    empresa_usuario_id: int
    checkout_hour: int
    checkout_minute: int
    cleaning_start_hour: int
    cleaning_end_hour: int
    auto_extend_stays: bool
    timezone: str
    overstay_price: Optional[float] = None

    # Datos fiscales
    nombre_fiscal: Optional[str] = None
    direccion_fiscal: Optional[str] = None
    iva_porcentaje: Optional[float] = None
    moneda_simbolo: Optional[str] = None
    logo_url: Optional[str] = None

    # Documentos requeridos en check-in
    documentos_requeridos: Optional[list] = None

    # SMTP (nunca exponer password)
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_from_email: Optional[str] = None

    # Feature flags
    housekeeping_enabled: bool = False

    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
    
    @field_validator('created_at', 'updated_at', mode='before')
    @classmethod
    def convert_datetime_to_iso(cls, v):
        """Convierte datetime a string ISO 8601"""
        if isinstance(v, datetime):
            return v.isoformat()
        return v


# Endpoints


@router.get("", response_model=HotelSettingsRead)
def get_hotel_settings(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Obtiene las configuraciones del hotel actual del usuario.
    """
    try:
        # Validar que el usuario está autenticado
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario no autenticado"
            )
        
        # Get tenant ID from authenticated user
        empresa_usuario_id = current_user.empresa_usuario_id if hasattr(current_user, 'empresa_usuario_id') else None
        
        if not empresa_usuario_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no asociado a ningún hotel/tenant"
            )

        # Buscar las configuraciones del hotel
        settings = db.query(HotelSettings).filter(
            HotelSettings.empresa_usuario_id == empresa_usuario_id
        ).first()

        if not settings:
            # Crear configuraciones por defecto si no existen
            new_settings = HotelSettings(
                empresa_usuario_id=empresa_usuario_id,
                checkout_hour=12,
                checkout_minute=0,
                cleaning_start_hour=10,
                cleaning_end_hour=12,
                auto_extend_stays=True,
                timezone="America/Argentina/Buenos_Aires",
                overstay_price=None
            )
            db.add(new_settings)
            db.commit()
            db.refresh(new_settings)
            
            user_id = current_user.id if hasattr(current_user, 'id') else "system"
            log_event(
                "settings",
                str(user_id),
                "hotel_settings_created",
                f"empresa_usuario_id={empresa_usuario_id} action=default_settings_created"
            )
            
            return HotelSettingsRead.from_orm(new_settings)

        return HotelSettingsRead.from_orm(settings)

    except HTTPException:
        raise
    except Exception as e:
        log_event(
            "settings",
            str(current_user.id if hasattr(current_user, 'id') else "system"),
            "hotel_settings_get_error",
            f"error={str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error obteniendo configuraciones del hotel"
        )


@router.put("", response_model=HotelSettingsRead)
def update_hotel_settings(
    settings_data: HotelSettingsUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Actualiza las configuraciones del hotel.
    Solo usuarios con permisos de administrador pueden actualizar.
    """
    try:
        # Validar que el usuario está autenticado
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario no autenticado"
            )
        
        user_id = current_user.id if hasattr(current_user, 'id') else "system"
        
        # Get tenant ID from authenticated user
        empresa_usuario_id = current_user.empresa_usuario_id if hasattr(current_user, 'empresa_usuario_id') else None
        
        if not empresa_usuario_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no asociado a ningún hotel/tenant"
            )

        # Buscar las configuraciones existentes
        settings = db.query(HotelSettings).filter(
            HotelSettings.empresa_usuario_id == empresa_usuario_id
        ).first()

        if not settings:
            # Crear nuevas configuraciones con los valores proporcionados
            new_settings = HotelSettings(
                empresa_usuario_id=empresa_usuario_id,
                checkout_hour=settings_data.checkout_hour or 12,
                checkout_minute=settings_data.checkout_minute or 0,
                cleaning_start_hour=settings_data.cleaning_start_hour or 10,
                cleaning_end_hour=settings_data.cleaning_end_hour or 12,
                auto_extend_stays=settings_data.auto_extend_stays if settings_data.auto_extend_stays is not None else True,
                timezone=settings_data.timezone or "America/Argentina/Buenos_Aires",
                overstay_price=settings_data.overstay_price
            )
            db.add(new_settings)
            db.commit()
            db.refresh(new_settings)
            
            log_event(
                "settings",
                str(user_id),
                "hotel_settings_updated",
                f"empresa_usuario_id={empresa_usuario_id} action=settings_created"
            )
            
            return HotelSettingsRead.from_orm(new_settings)

        # Actualizar campos proporcionados
        if settings_data.checkout_hour is not None:
            settings.checkout_hour = settings_data.checkout_hour
        if settings_data.checkout_minute is not None:
            settings.checkout_minute = settings_data.checkout_minute
        if settings_data.cleaning_start_hour is not None:
            settings.cleaning_start_hour = settings_data.cleaning_start_hour
        if settings_data.cleaning_end_hour is not None:
            settings.cleaning_end_hour = settings_data.cleaning_end_hour
        if settings_data.auto_extend_stays is not None:
            settings.auto_extend_stays = settings_data.auto_extend_stays
        if settings_data.timezone is not None:
            settings.timezone = settings_data.timezone
        if settings_data.overstay_price is not None:
            settings.overstay_price = settings_data.overstay_price

        # Datos fiscales
        if settings_data.documentos_requeridos is not None:
            settings.documentos_requeridos = settings_data.documentos_requeridos
        if settings_data.nombre_fiscal is not None:
            settings.nombre_fiscal = settings_data.nombre_fiscal
        if settings_data.direccion_fiscal is not None:
            settings.direccion_fiscal = settings_data.direccion_fiscal
        if settings_data.iva_porcentaje is not None:
            settings.iva_porcentaje = settings_data.iva_porcentaje
        if settings_data.moneda_simbolo is not None:
            settings.moneda_simbolo = settings_data.moneda_simbolo
        if settings_data.logo_url is not None:
            settings.logo_url = settings_data.logo_url

        # SMTP
        if settings_data.smtp_host is not None:
            settings.smtp_host = settings_data.smtp_host
        if settings_data.smtp_port is not None:
            settings.smtp_port = settings_data.smtp_port
        if settings_data.smtp_user is not None:
            settings.smtp_user = settings_data.smtp_user
        if settings_data.smtp_from_email is not None:
            settings.smtp_from_email = settings_data.smtp_from_email
        if settings_data.smtp_password is not None:
            import os
            fernet_key = os.getenv("FERNET_KEY", "")
            # Nunca persistir la contraseña SMTP en texto plano: si no se puede
            # cifrar (sin FERNET_KEY o clave inválida), se rechaza el guardado.
            if not fernet_key:
                raise HTTPException(
                    status_code=500,
                    detail="Servidor sin FERNET_KEY configurada — no se puede guardar la contraseña SMTP de forma segura.",
                )
            try:
                from cryptography.fernet import Fernet
                f = Fernet(fernet_key.encode())
                settings.smtp_password_encrypted = f.encrypt(settings_data.smtp_password.encode()).decode()
            except Exception:
                raise HTTPException(
                    status_code=500,
                    detail="FERNET_KEY inválida — no se pudo cifrar la contraseña SMTP.",
                )

        # Feature flags
        if settings_data.housekeeping_enabled is not None:
            settings.housekeeping_enabled = settings_data.housekeeping_enabled

        db.commit()
        db.refresh(settings)

        log_event(
            "settings",
            str(user_id),
            "hotel_settings_updated",
            f"empresa_usuario_id={empresa_usuario_id} checkout_hour={settings.checkout_hour} auto_extend_stays={settings.auto_extend_stays}"
        )

        return HotelSettingsRead.from_orm(settings)

    except HTTPException:
        raise
    except Exception as e:
        log_event(
            "settings",
            str(current_user.id if hasattr(current_user, 'id') else "system"),
            "hotel_settings_update_error",
            f"error={str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error actualizando configuraciones del hotel"
        )


@router.post("", response_model=HotelSettingsRead)
def create_hotel_settings(
    settings_data: HotelSettingsCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Crea nuevas configuraciones para un hotel.
    """
    try:
        # Verificar que el usuario tenga permisos
        user_id = current_user.id if hasattr(current_user, 'id') else None
        user_role = current_user.rol if hasattr(current_user, 'rol') else "readonly"
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usuario no identificado"
            )
        
        if user_role not in ["admin", "gerente", "administrator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para crear configuraciones"
            )

        if not current_user.es_super_admin and settings_data.empresa_usuario_id != current_user.empresa_usuario_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para crear configuraciones de otro hotel"
            )

        # Verificar que el tenant exista
        empresa_usuario = db.query(EmpresaUsuario).filter(
            EmpresaUsuario.id == settings_data.empresa_usuario_id,
            EmpresaUsuario.deleted.is_(False)
        ).first()
        if not empresa_usuario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant/Hotel no encontrado"
            )

        # Verificar que no exista ya configuración para este tenant
        existing = db.query(HotelSettings).filter(
            HotelSettings.empresa_usuario_id == settings_data.empresa_usuario_id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe configuración para este hotel"
            )

        # Crear nuevas configuraciones
        new_settings = HotelSettings(**settings_data.dict())
        db.add(new_settings)
        db.commit()
        db.refresh(new_settings)

        log_event(
            "settings",
            str(user_id),
            "hotel_settings_created",
            f"empresa_usuario_id={settings_data.empresa_usuario_id}"
        )

        return HotelSettingsRead.from_orm(new_settings)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_event(
            "settings",
            str(current_user.id if hasattr(current_user, 'id') else "system"),
            "hotel_settings_create_error",
            f"error={str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creando configuraciones del hotel"
        )
