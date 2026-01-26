"""
Endpoints para gestión de Configuraciones del Hotel (HotelSettings)
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_
from pydantic import BaseModel, Field

from database.conexion import get_db
from models.core import HotelSettings, Empresa
from utils.dependencies import get_current_user
from utils.logging_utils import log_event

router = APIRouter(prefix="/api/settings", tags=["settings"])


# Schemas
class HotelSettingsCreate(BaseModel):
    empresa_id: int
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

    class Config:
        from_attributes = True


class HotelSettingsRead(BaseModel):
    id: int
    empresa_id: int
    checkout_hour: int
    checkout_minute: int
    cleaning_start_hour: int
    cleaning_end_hour: int
    cleaning_end_hour: int
    auto_extend_stays: bool
    timezone: str
    overstay_price: Optional[float] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


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
        # Obtener el ID del usuario
        user_id = current_user.id if hasattr(current_user, 'id') else None
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usuario no identificado"
            )

        # Buscar las configuraciones del hotel (por ahora use primera empresa encontrada)
        # En el futuro, esto debería venir de una relación usuario -> empresa
        empresa = db.query(Empresa).filter(Empresa.activo == True).first()
        
        if not empresa:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No hay empresa disponible"
            )
        
        empresa_id = empresa.id

        # Buscar las configuraciones del hotel
        settings = db.query(HotelSettings).filter(
            HotelSettings.empresa_id == empresa_id
        ).first()

        if not settings:
            # Crear configuraciones por defecto si no existen
            new_settings = HotelSettings(
                empresa_id=empresa_id,
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
            
            log_event(
                "settings",
                str(user_id),
                "hotel_settings_created",
                f"empresa_id={empresa_id} action=default_settings_created"
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
        # Obtener el usuario actual (Usuario object)
        user_id = current_user.id if hasattr(current_user, 'id') else None
        user_role = current_user.rol if hasattr(current_user, 'rol') else "readonly"
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usuario no identificado"
            )

        # Verificar que el usuario tenga permisos de administrador
        if user_role not in ["admin", "manager", "administrator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para actualizar configuraciones"
            )

        # Buscar la empresa (por ahora use primera empresa activa)
        empresa = db.query(Empresa).filter(Empresa.activo == True).first()
        
        if not empresa:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No hay empresa disponible"
            )
        
        empresa_id = empresa.id

        # Buscar las configuraciones existentes
        settings = db.query(HotelSettings).filter(
            HotelSettings.empresa_id == empresa_id
        ).first()

        if not settings:
            # Crear nuevas configuraciones con los valores proporcionados
            new_settings = HotelSettings(
                empresa_id=empresa_id,
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
                f"empresa_id={empresa_id} action=settings_created"
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

        db.commit()
        db.refresh(settings)

        log_event(
            "settings",
            str(user_id),
            "hotel_settings_updated",
            f"empresa_id={empresa_id} checkout_hour={settings.checkout_hour} auto_extend_stays={settings.auto_extend_stays}"
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
        
        if user_role not in ["admin", "manager", "administrator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para crear configuraciones"
            )

        # Verificar que la empresa exista
        empresa = db.query(Empresa).filter(Empresa.id == settings_data.empresa_id).first()
        if not empresa:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Empresa no encontrada"
            )

        # Verificar que no exista ya configuración para esta empresa
        existing = db.query(HotelSettings).filter(
            HotelSettings.empresa_id == settings_data.empresa_id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe configuración para esta empresa"
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
            f"empresa_id={settings_data.empresa_id}"
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
