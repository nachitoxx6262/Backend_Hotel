from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from pydantic import BaseModel, EmailStr
from datetime import datetime, date

from database.conexion import get_db
from models.core import Cliente, Stay, StayCharge, StayPayment, Room, RoomType, Reservation, StayRoomOccupancy
from utils.dependencies import get_current_user
from utils.logging_utils import log_event

router = APIRouter(prefix="/clientes", tags=["Clientes"])

# --- Schemas ---
class ClienteBase(BaseModel):
    nombre: str
    apellido: str
    tipo_documento: str = "DNI"
    numero_documento: str
    email: Optional[EmailStr] = None
    telefono: Optional[str] = None
    nacionalidad: Optional[str] = None
    nota_interna: Optional[str] = None
    blacklist: bool = False
    motivo_blacklist: Optional[str] = None
    activo: bool = True

class ClienteCreate(ClienteBase):
    pass

class ClienteUpdate(BaseModel):
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    tipo_documento: Optional[str] = None
    numero_documento: Optional[str] = None
    email: Optional[EmailStr] = None
    telefono: Optional[str] = None
    nacionalidad: Optional[str] = None
    nota_interna: Optional[str] = None
    blacklist: Optional[bool] = None
    motivo_blacklist: Optional[str] = None
    activo: Optional[bool] = None

class ClienteRead(ClienteBase):
    id: int

    class Config:
        orm_mode = True

# --- Endpoints ---

@router.get("", response_model=List[ClienteRead])
def get_clientes(
    skip: int = 0,
    limit: int = 50,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Listar clientes activos con paginación y búsqueda opcional.
    """
    tenant_id = current_user.empresa_usuario_id
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Usuario no autenticado o sin tenant asociado")
    query = db.query(Cliente).filter(
        Cliente.empresa_usuario_id == tenant_id,
        Cliente.activo == True
    )

    if q:
        search = f"%{q}%"
        query = query.filter(
            or_(
                Cliente.nombre.ilike(search),
                Cliente.apellido.ilike(search),
                Cliente.numero_documento.ilike(search),
                Cliente.email.ilike(search)
            )
        )

    clientes = query.order_by(Cliente.apellido, Cliente.nombre).offset(skip).limit(limit).all()
    return clientes


@router.get("/eliminados", response_model=List[ClienteRead])
def get_deleted_clientes(
    skip: int = 0,
    limit: int = 50,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Listar clientes eliminados (inactivos) con paginación y búsqueda opcional.
    """
    tenant_id = current_user.empresa_usuario_id
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Usuario no autenticado o sin tenant asociado")
    query = db.query(Cliente).filter(
        Cliente.empresa_usuario_id == tenant_id,
        Cliente.activo == False
    )

    if q:
        search = f"%{q}%"
        query = query.filter(
            or_(
                Cliente.nombre.ilike(search),
                Cliente.apellido.ilike(search),
                Cliente.numero_documento.ilike(search),
                Cliente.email.ilike(search)
            )
        )

    clientes = query.order_by(Cliente.apellido, Cliente.nombre).offset(skip).limit(limit).all()
    return clientes

@router.get("/{cliente_id}", response_model=ClienteRead)
def get_cliente(cliente_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    tenant_id = current_user.empresa_usuario_id
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Usuario no autenticado o sin tenant asociado")
    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id,
        Cliente.empresa_usuario_id == tenant_id
    ).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return cliente

@router.post("", response_model=ClienteRead, status_code=status.HTTP_201_CREATED)
def create_cliente(cliente: ClienteCreate, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    tenant_id = current_user.empresa_usuario_id
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Usuario no autenticado o sin tenant asociado")
    # Validar duplicados de documento
    existing = db.query(Cliente).filter(
        Cliente.tipo_documento == cliente.tipo_documento,
        Cliente.numero_documento == cliente.numero_documento,
        Cliente.empresa_usuario_id == tenant_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Ya existe un cliente con ese documento")

    db_cliente = Cliente(**cliente.dict(), empresa_usuario_id=tenant_id)
    db.add(db_cliente)
    db.commit()
    db.refresh(db_cliente)
    return db_cliente

@router.put("/{cliente_id}", response_model=ClienteRead)
def update_cliente(cliente_id: int, cliente_update: ClienteUpdate, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    tenant_id = current_user.empresa_usuario_id
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Usuario no autenticado o sin tenant asociado")
    db_cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id,
        Cliente.empresa_usuario_id == tenant_id
    ).first()
    if not db_cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    update_data = cliente_update.dict(exclude_unset=True)
    
    # Si cambia documento, validar duplicado
    if "numero_documento" in update_data and update_data["numero_documento"] != db_cliente.numero_documento:
         existing = db.query(Cliente).filter(
            Cliente.numero_documento == update_data["numero_documento"],
            Cliente.tipo_documento == update_data.get("tipo_documento", db_cliente.tipo_documento),
                Cliente.empresa_usuario_id == tenant_id,
            Cliente.id != cliente_id
        ).first()
         if existing:
            raise HTTPException(status_code=400, detail="Ya existe otro cliente con ese documento")

    for key, value in update_data.items():
        setattr(db_cliente, key, value)

    db.commit()
    db.refresh(db_cliente)
    return db_cliente

@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cliente(cliente_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    tenant_id = current_user.empresa_usuario_id
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Usuario no autenticado o sin tenant asociado")
    db_cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id,
        Cliente.empresa_usuario_id == tenant_id
    ).first()
    if not db_cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    
    # Soft delete
    db_cliente.activo = False
    db.commit()


@router.put("/{cliente_id}/restaurar", response_model=ClienteRead)
def restore_cliente(cliente_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Restaurar cliente eliminado"""
    tenant_id = current_user.empresa_usuario_id
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Usuario no autenticado o sin tenant asociado")
    db_cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id,
        Cliente.empresa_usuario_id == tenant_id
    ).first()
    if not db_cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    
    db_cliente.activo = True
    db.commit()
    db.refresh(db_cliente)
    return db_cliente


@router.get("/{cliente_id}/perfil")
def get_cliente_perfil(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Obtener perfil completo del cliente con historial de estancias, facturación y estadísticas
    """
    tenant_id = current_user.empresa_usuario_id
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Usuario no autenticado o sin tenant asociado")
    
    # Obtener cliente
    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id,
        Cliente.empresa_usuario_id == tenant_id
    ).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    
    # Obtener TODAS las estancias (cerradas y activas) del cliente a través de reservations
    try:
        stays = db.query(Stay).join(Reservation).filter(
            Reservation.cliente_id == cliente_id,
            Stay.empresa_usuario_id == tenant_id
        ).order_by(Stay.created_at.desc()).all()
        log_event("clientes", f"user_{current_user.id}", "perfil_query", f"cliente={cliente_id} stays={len(stays)} tenant={tenant_id}")
    except Exception as e:
        # Si hay error en el join, devolver lista vacía
        log_event("clientes", f"user_{current_user.id}", "perfil_query_error", f"cliente={cliente_id} error={str(e)}")
        stays = []
    
    # Procesar historial de estancias con detalles
    historial_estancias = []
    total_estancias_cerradas = 0
    
    for stay in stays:
        try:
            # Contar solo las cerradas
            if stay.estado == "cerrada":
                total_estancias_cerradas += 1
            
            # Calcular total de cargos
            total_cargos = db.query(func.sum(StayCharge.monto_total)).filter(
                StayCharge.stay_id == stay.id
            ).scalar() or 0
            
            # Calcular total pagado (excluyendo reversos)
            total_pagado = db.query(func.sum(StayPayment.monto)).filter(
                StayPayment.stay_id == stay.id,
                StayPayment.es_reverso == False
            ).scalar() or 0
            
            # Obtener información de la habitación desde occupancy
            occupancy = db.query(StayRoomOccupancy).filter(
                StayRoomOccupancy.stay_id == stay.id
            ).first()
            
            room = None
            room_type = None
            if occupancy:
                room = db.query(Room).filter(Room.id == occupancy.room_id).first()
                if room:
                    room_type = db.query(RoomType).filter(RoomType.id == room.room_type_id).first()
            
            # Calcular noches usando las fechas de la reservation
            noches = 0
            fecha_entrada = None
            fecha_salida = None
            
            if stay.reservation:
                fecha_entrada = stay.reservation.fecha_checkin
                fecha_salida = stay.reservation.fecha_checkout
                if fecha_entrada and fecha_salida:
                    noches = (fecha_salida - fecha_entrada).days
            
            historial_estancias.append({
                "stay_id": stay.id,
                "numero_habitacion": room.numero if room else None,
                "tipo_habitacion": room_type.nombre if room_type else None,
                "fecha_entrada": fecha_entrada.isoformat() if fecha_entrada else None,
                "fecha_salida": fecha_salida.isoformat() if fecha_salida else None,
                "noches": noches,
                "cargos_totales": float(total_cargos),
                "pagado": float(total_pagado),
                "estado": stay.estado
            })
            log_event("clientes", f"user_{current_user.id}", "perfil_stay_ok", f"stay={stay.id}")
        except Exception as e:
            # Si hay error procesando este stay, continuar con el siguiente
            log_event("clientes", f"user_{current_user.id}", "perfil_stay_error", f"stay={stay.id} error={str(e)}")
            continue
    
    return {
        "cliente": {
            "id": cliente.id,
            "nombre": cliente.nombre,
            "apellido": cliente.apellido,
            "tipo_documento": cliente.tipo_documento,
            "numero_documento": cliente.numero_documento,
            "email": cliente.email,
            "telefono": cliente.telefono,
            "nacionalidad": cliente.nacionalidad,
            "nota_interna": cliente.nota_interna,
            "blacklist": cliente.blacklist,
            "motivo_blacklist": cliente.motivo_blacklist,
            "activo": cliente.activo
        },
        "historial_estancias": historial_estancias,
        "total_estancias_cerradas": total_estancias_cerradas,
        "ultima_salida": None,  # Simplificado por ahora
        "es_blacklist": cliente.blacklist,
        "motivo_blacklist": cliente.motivo_blacklist
    }

