"""
Endpoints para gestión de Habitaciones y Tipos de Habitaciones
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field, field_validator

from database import conexion
from models.core import Room, RoomType, Reservation, ReservationRoom, Stay, StayRoomOccupancy
from utils.logging_utils import log_event
from utils.dependencies import get_current_user, require_admin_or_manager

router = APIRouter(prefix="/api/rooms", tags=["rooms"])

# Schemas
_ESTADOS_OPERATIVOS = {"disponible", "ocupada", "mantenimiento", "fuera_de_servicio", "bloqueada"}


class RoomTypeCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100, strip_whitespace=True)
    descripcion: Optional[str] = Field(None, max_length=500)
    capacidad: int = Field(..., ge=1, le=100)
    precio_base: Optional[float] = Field(None, ge=0)
    amenidades: Optional[List[str]] = None
    activo: bool = True

    @field_validator("amenidades")
    @classmethod
    def amenidades_no_vacias(cls, v):
        if v is not None:
            return [a.strip() for a in v if a and a.strip()]
        return v


class RoomTypeUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=100, strip_whitespace=True)
    descripcion: Optional[str] = Field(None, max_length=500)
    capacidad: Optional[int] = Field(None, ge=1, le=100)
    precio_base: Optional[float] = Field(None, ge=0)
    amenidades: Optional[List[str]] = None
    activo: Optional[bool] = None

class RoomTypeRead(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str] = None
    capacidad: int
    precio_base: Optional[float] = None
    amenidades: Optional[List[str]] = None
    activo: bool
    cantidad_habitaciones: int = 0
    class Config:
        from_attributes = True

class RoomCreate(BaseModel):
    numero: str = Field(..., min_length=1, max_length=20, strip_whitespace=True)
    room_type_id: int = Field(..., gt=0)
    estado_operativo: str = Field(default="disponible")
    piso: Optional[int] = Field(None, ge=0, le=200)
    notas: Optional[str] = Field(None, max_length=1000)
    particularidades: Optional[dict] = None
    activo: bool = True

    @field_validator("numero")
    @classmethod
    def normalizar_numero(cls, v):
        # Normalizar: eliminar espacios internos múltiples, uppercase
        return " ".join(v.split()).upper()

    @field_validator("estado_operativo")
    @classmethod
    def validar_estado(cls, v):
        if v not in _ESTADOS_OPERATIVOS:
            raise ValueError(
                f"estado_operativo debe ser uno de: {', '.join(sorted(_ESTADOS_OPERATIVOS))}"
            )
        return v


class RoomUpdate(BaseModel):
    numero: Optional[str] = Field(None, min_length=1, max_length=20, strip_whitespace=True)
    room_type_id: Optional[int] = Field(None, gt=0)
    estado_operativo: Optional[str] = None
    piso: Optional[int] = Field(None, ge=0, le=200)
    notas: Optional[str] = Field(None, max_length=1000)
    particularidades: Optional[dict] = None
    activo: Optional[bool] = None

    @field_validator("numero")
    @classmethod
    def normalizar_numero(cls, v):
        if v is not None:
            return " ".join(v.split()).upper()
        return v

    @field_validator("estado_operativo")
    @classmethod
    def validar_estado(cls, v):
        if v is not None and v not in _ESTADOS_OPERATIVOS:
            raise ValueError(
                f"estado_operativo debe ser uno de: {', '.join(sorted(_ESTADOS_OPERATIVOS))}"
            )
        return v

class RoomRead(BaseModel):
    id: int
    numero: str
    room_type_id: int
    estado_operativo: str
    piso: Optional[int] = None
    notas: Optional[str] = None
    particularidades: Optional[dict] = None
    activo: bool
    created_at: datetime
    updated_at: datetime
    tipo_nombre: Optional[str] = None
    capacidad: Optional[int] = None
    class Config:
        from_attributes = True

# Room Types Endpoints
@router.get("/types", response_model=List[RoomTypeRead])
async def list_room_types(
    db: Session = Depends(conexion.get_db),
    current_user = Depends(get_current_user)
):
    if not current_user or not current_user.empresa_usuario_id:
        raise HTTPException(status_code=401, detail="No autenticado o sin tenant asociado")
    
    tenant_id = current_user.empresa_usuario_id
    tipos = db.query(RoomType).filter(
        RoomType.empresa_usuario_id == tenant_id,
        RoomType.activo == True
    ).all()
    result = []
    for tipo in tipos:
        cantidad = db.query(func.count(Room.id)).filter(
            and_(
                Room.room_type_id == tipo.id,
                Room.empresa_usuario_id == tenant_id,
                Room.activo == True
            )
        ).scalar()
        result.append({
            "id": tipo.id, "nombre": tipo.nombre, "descripcion": tipo.descripcion,
            "capacidad": tipo.capacidad, "precio_base": float(tipo.precio_base) if tipo.precio_base is not None else None,
            "amenidades": tipo.amenidades or [], "activo": tipo.activo, "cantidad_habitaciones": cantidad or 0
        })
    return result

@router.post("/types", response_model=RoomTypeRead, status_code=status.HTTP_201_CREATED)
async def create_room_type(
    room_type: RoomTypeCreate,
    db: Session = Depends(conexion.get_db),
    current_user = Depends(require_admin_or_manager)
):
    if not current_user or not current_user.empresa_usuario_id:
        raise HTTPException(status_code=401, detail="No autenticado o sin tenant asociado")
    
    tenant_id = current_user.empresa_usuario_id
    nueva = RoomType(**room_type.dict(), empresa_usuario_id=tenant_id)
    db.add(nueva)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Ya existe un tipo de habitación con el nombre '{room_type.nombre}'")
    db.refresh(nueva)
    result = {**room_type.dict(), "id": nueva.id, "cantidad_habitaciones": 0}
    if result.get('precio_base') is not None:
        result['precio_base'] = float(result['precio_base'])
    return result

@router.put("/types/{type_id}", response_model=RoomTypeRead)
async def update_room_type(
    type_id: int,
    room_type: RoomTypeUpdate,
    db: Session = Depends(conexion.get_db),
    current_user = Depends(require_admin_or_manager)
):
    if not current_user or not current_user.empresa_usuario_id:
        raise HTTPException(status_code=401, detail="No autenticado o sin tenant asociado")
    
    tenant_id = current_user.empresa_usuario_id
    tipo = db.query(RoomType).filter(
        RoomType.id == type_id,
        RoomType.empresa_usuario_id == tenant_id
    ).first()
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo de habitación no encontrado o no pertenece a tu empresa")
    
    # Actualizar campos
    update_data = room_type.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tipo, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe un tipo de habitación con ese nombre")
    db.refresh(tipo)

    cantidad = db.query(func.count(Room.id)).filter(
        and_(
            Room.room_type_id == tipo.id,
            Room.empresa_usuario_id == tenant_id,
            Room.activo == True
        )
    ).scalar()
    
    return {
        "id": tipo.id, "nombre": tipo.nombre, "descripcion": tipo.descripcion,
        "capacidad": tipo.capacidad, "precio_base": float(tipo.precio_base) if tipo.precio_base is not None else None,
        "amenidades": tipo.amenidades or [], "activo": tipo.activo, "cantidad_habitaciones": cantidad or 0
    }

@router.delete("/types/{type_id}")
async def delete_room_type(
    type_id: int,
    db: Session = Depends(conexion.get_db),
    current_user = Depends(require_admin_or_manager)
):
    if not current_user or not current_user.empresa_usuario_id:
        raise HTTPException(status_code=401, detail="No autenticado o sin tenant asociado")
    
    tenant_id = current_user.empresa_usuario_id
    tipo = db.query(RoomType).filter(
        RoomType.id == type_id,
        RoomType.empresa_usuario_id == tenant_id
    ).first()
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo de habitación no encontrado o no pertenece a tu empresa")
    
    # Verificar que no tenga habitaciones asignadas
    cantidad = db.query(func.count(Room.id)).filter(
        Room.room_type_id == type_id,
        Room.empresa_usuario_id == tenant_id,
        Room.activo == True
    ).scalar()
    if cantidad > 0:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede eliminar. Hay {cantidad} habitación(es) asociada(s) a este tipo"
        )

    tipo.activo = False
    db.commit()
    return {"message": "Tipo de habitación desactivado exitosamente"}

# Rooms Endpoints
@router.get("", response_model=List[RoomRead])
async def list_rooms(
    db: Session = Depends(conexion.get_db),
    activas_solo: bool = Query(True),
    room_type_id: Optional[int] = Query(None),
    estado: Optional[str] = Query(None),
    current_user = Depends(get_current_user)
):
    if not current_user or not current_user.empresa_usuario_id:
        raise HTTPException(status_code=401, detail="No autenticado o sin tenant asociado")

    tenant_id = current_user.empresa_usuario_id
    query = db.query(Room).options(joinedload(Room.tipo)).filter(
        Room.empresa_usuario_id == tenant_id
    )
    if activas_solo:
        query = query.filter(Room.activo == True)
    if room_type_id:
        query = query.filter(Room.room_type_id == room_type_id)
    if estado:
        query = query.filter(Room.estado_operativo == estado)
    habitaciones = query.all()
    result = []
    for hab in habitaciones:
        result.append({
            "id": hab.id, "numero": hab.numero, "room_type_id": hab.room_type_id,
            "estado_operativo": hab.estado_operativo, "piso": hab.piso, "notas": hab.notas,
            "particularidades": hab.particularidades or {}, "activo": hab.activo,
            "created_at": hab.created_at, "updated_at": hab.updated_at,
            "tipo_nombre": hab.tipo.nombre if hab.tipo else None,
            "capacidad": hab.tipo.capacidad if hab.tipo else None
        })
    return result


@router.put("/{room_id}", response_model=RoomRead)
async def update_room(
    room_id: int,
    room: RoomUpdate,
    db: Session = Depends(conexion.get_db),
    current_user = Depends(require_admin_or_manager)
):
    if not current_user or not current_user.empresa_usuario_id:
        raise HTTPException(status_code=401, detail="No autenticado o sin tenant asociado")

    tenant_id = current_user.empresa_usuario_id

    db_room = db.query(Room).filter(
        Room.id == room_id,
        Room.empresa_usuario_id == tenant_id
    ).first()
    if not db_room:
        raise HTTPException(status_code=404, detail="Habitación no encontrada o no pertenece a tu empresa")

    update_data = room.dict(exclude_unset=True)

    if "room_type_id" in update_data:
        room_type = db.query(RoomType).filter(
            RoomType.id == update_data["room_type_id"],
            RoomType.empresa_usuario_id == tenant_id,
            RoomType.activo == True
        ).first()
        if not room_type:
            raise HTTPException(status_code=404, detail="Tipo de habitación no encontrado o no pertenece a tu empresa")

    for field, value in update_data.items():
        setattr(db_room, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe una habitación con ese número")
    db.refresh(db_room)
    db.refresh(db_room.tipo)

    return {
        "id": db_room.id,
        "numero": db_room.numero,
        "room_type_id": db_room.room_type_id,
        "estado_operativo": db_room.estado_operativo,
        "piso": db_room.piso,
        "notas": db_room.notas,
        "particularidades": db_room.particularidades or {},
        "activo": db_room.activo,
        "created_at": db_room.created_at,
        "updated_at": db_room.updated_at,
        "tipo_nombre": db_room.tipo.nombre if db_room.tipo else None,
        "capacidad": db_room.tipo.capacidad if db_room.tipo else None
    }


@router.delete("/{room_id}")
async def delete_room(
    room_id: int,
    db: Session = Depends(conexion.get_db),
    current_user = Depends(require_admin_or_manager)
):
    if not current_user or not current_user.empresa_usuario_id:
        raise HTTPException(status_code=401, detail="No autenticado o sin tenant asociado")

    tenant_id = current_user.empresa_usuario_id
    db_room = db.query(Room).filter(
        Room.id == room_id,
        Room.empresa_usuario_id == tenant_id
    ).first()
    if not db_room:
        raise HTTPException(status_code=404, detail="Habitación no encontrada o no pertenece a tu empresa")

    # No permitir eliminar una habitación actualmente ocupada (ocupación real abierta:
    # StayRoomOccupancy.hasta IS NULL con una estadía no cerrada).
    ocupacion_activa = db.query(StayRoomOccupancy.id).join(
        Stay, Stay.id == StayRoomOccupancy.stay_id
    ).filter(
        StayRoomOccupancy.room_id == room_id,
        StayRoomOccupancy.hasta.is_(None),
        Stay.estado != "cerrada"
    ).first()
    if ocupacion_activa or db_room.estado_operativo == "ocupada":
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar: la habitación está ocupada actualmente"
        )

    # No permitir eliminar si tiene reservas activas o futuras (no canceladas/cerradas).
    reserva_activa = db.query(ReservationRoom.id).join(
        Reservation, Reservation.id == ReservationRoom.reservation_id
    ).filter(
        ReservationRoom.room_id == room_id,
        Reservation.empresa_usuario_id == tenant_id,
        Reservation.estado.in_(["confirmada", "ocupada"])
    ).first()
    if reserva_activa:
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar: la habitación tiene reservas activas o futuras"
        )

    # Soft delete
    db_room.activo = False
    db.commit()
    log_event("rooms", current_user.username, "Habitación eliminada", f"room_id={room_id}, numero={db_room.numero}")
    return {"message": "Habitación desactivada exitosamente"}

@router.post("", response_model=RoomRead, status_code=status.HTTP_201_CREATED)
async def create_room(
    room: RoomCreate,
    db: Session = Depends(conexion.get_db),
    current_user = Depends(require_admin_or_manager)
):
    if not current_user or not current_user.empresa_usuario_id:
        raise HTTPException(status_code=401, detail="No autenticado o sin tenant asociado")
    
    tenant_id = current_user.empresa_usuario_id

    # Límite de habitaciones del plan
    from models.core import Subscription
    from utils.subscription_service import check_resource_limit
    subscription = db.query(Subscription).filter_by(empresa_usuario_id=tenant_id).first()
    check_resource_limit(db, tenant_id, subscription, "habitaciones")

    # Validar que el tipo de habitación pertenece al tenant
    room_type = db.query(RoomType).filter(
        RoomType.id == room.room_type_id,
        RoomType.empresa_usuario_id == tenant_id
    ).first()
    if not room_type:
        raise HTTPException(status_code=404, detail="Tipo de habitación no encontrado o no pertenece a tu empresa")

    nueva = Room(**room.dict(), empresa_usuario_id=tenant_id)
    db.add(nueva)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Ya existe una habitación con el número {room.numero}")
    db.refresh(nueva)
    db.refresh(nueva.tipo)
    return {
        **room.dict(), "id": nueva.id, "created_at": nueva.created_at,
        "updated_at": nueva.updated_at, "tipo_nombre": nueva.tipo.nombre,
        "capacidad": nueva.tipo.capacidad
    }
