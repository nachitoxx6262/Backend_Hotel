"""
Endpoints para gestión de Habitaciones y Tipos de Habitaciones
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
from pydantic import BaseModel

from database import conexion
from models.core import Room, RoomType, Reservation, ReservationRoom
from utils.logging_utils import log_event

router = APIRouter(prefix="/api/rooms", tags=["rooms"])

# Schemas
class RoomTypeCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    capacidad: int
    precio_base: Optional[float] = None
    amenidades: Optional[List[str]] = None
    activo: bool = True

class RoomTypeUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    capacidad: Optional[int] = None
    precio_base: Optional[float] = None
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
    numero: str
    room_type_id: int
    estado_operativo: str = "disponible"
    piso: Optional[int] = None
    notas: Optional[str] = None
    particularidades: Optional[dict] = None
    activo: bool = True

class RoomUpdate(BaseModel):
    numero: Optional[str] = None
    room_type_id: Optional[int] = None
    estado_operativo: Optional[str] = None
    piso: Optional[int] = None
    notas: Optional[str] = None
    particularidades: Optional[dict] = None
    activo: Optional[bool] = None

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
async def list_room_types(db: Session = Depends(conexion.get_db)):
    tipos = db.query(RoomType).filter(RoomType.activo == True).all()
    result = []
    for tipo in tipos:
        cantidad = db.query(func.count(Room.id)).filter(
            and_(Room.room_type_id == tipo.id, Room.activo == True)
        ).scalar()
        result.append({
            "id": tipo.id, "nombre": tipo.nombre, "descripcion": tipo.descripcion,
            "capacidad": tipo.capacidad, "precio_base": float(tipo.precio_base) if tipo.precio_base else None,
            "amenidades": tipo.amenidades or [], "activo": tipo.activo, "cantidad_habitaciones": cantidad or 0
        })
    return result

@router.post("/types", response_model=RoomTypeRead, status_code=status.HTTP_201_CREATED)
async def create_room_type(room_type: RoomTypeCreate, db: Session = Depends(conexion.get_db)):
    nueva = RoomType(**room_type.dict())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    result = {**room_type.dict(), "id": nueva.id, "cantidad_habitaciones": 0}
    if result.get('precio_base'):
        result['precio_base'] = float(result['precio_base'])
    return result

@router.put("/types/{type_id}", response_model=RoomTypeRead)
async def update_room_type(type_id: int, room_type: RoomTypeUpdate, db: Session = Depends(conexion.get_db)):
    tipo = db.query(RoomType).filter(RoomType.id == type_id).first()
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo de habitación no encontrado")
    
    # Actualizar campos
    update_data = room_type.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tipo, field, value)
    
    db.commit()
    db.refresh(tipo)
    
    cantidad = db.query(func.count(Room.id)).filter(
        and_(Room.room_type_id == tipo.id, Room.activo == True)
    ).scalar()
    
    return {
        "id": tipo.id, "nombre": tipo.nombre, "descripcion": tipo.descripcion,
        "capacidad": tipo.capacidad, "precio_base": float(tipo.precio_base) if tipo.precio_base else None,
        "amenidades": tipo.amenidades or [], "activo": tipo.activo, "cantidad_habitaciones": cantidad or 0
    }

@router.delete("/types/{type_id}")
async def delete_room_type(type_id: int, db: Session = Depends(conexion.get_db)):
    tipo = db.query(RoomType).filter(RoomType.id == type_id).first()
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo de habitación no encontrado")
    
    # Verificar que no tenga habitaciones asignadas
    cantidad = db.query(func.count(Room.id)).filter(Room.room_type_id == type_id).scalar()
    if cantidad > 0:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede eliminar. Hay {cantidad} habitación(es) asociada(s) a este tipo"
        )
    
    db.delete(tipo)
    db.commit()
    return {"message": "Tipo de habitación eliminado exitosamente"}

# Rooms Endpoints
@router.get("", response_model=List[RoomRead])
async def list_rooms(db: Session = Depends(conexion.get_db), activas_solo: bool = Query(True)):
    query = db.query(Room).options(joinedload(Room.tipo))
    if activas_solo:
        query = query.filter(Room.activo == True)
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

@router.post("", response_model=RoomRead, status_code=status.HTTP_201_CREATED)
async def create_room(room: RoomCreate, db: Session = Depends(conexion.get_db)):
    nueva = Room(**room.dict())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    db.refresh(nueva.tipo)
    return {
        **room.dict(), "id": nueva.id, "created_at": nueva.created_at,
        "updated_at": nueva.updated_at, "tipo_nombre": nueva.tipo.nombre,
        "capacidad": nueva.tipo.capacidad
    }
