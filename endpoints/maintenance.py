"""
Mantenimiento y Objetos Olvidados (Fase 2 de Housekeeping).
Entidades reales (no dentro de task.meta), con aislamiento por tenant y conexión con
el estado operativo de la habitación.
"""
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import conexion
from models.core import MaintenanceTicket, HKLostItem, Room
from models.usuario import Usuario
from utils.dependencies import get_current_user, require_staff
from utils.logging_utils import log_event
from utils.datetime_utils import utcnow

router = APIRouter(prefix="/pms", tags=["Mantenimiento"])

ESTADOS_TICKET = {"abierto", "en_progreso", "resuelto", "cancelado"}
ESTADOS_LOST = {"guardado", "entregado", "descartado"}


# ============================ Schemas ============================
class TicketCreate(BaseModel):
    room_id: int = Field(..., gt=0)
    descripcion: str = Field(..., min_length=1)
    tipo: Optional[str] = Field(None, max_length=50)
    prioridad: str = Field("media", pattern="^(baja|media|alta|urgente)$")
    bloquea_room: bool = False
    asignado_a: Optional[str] = Field(None, max_length=100)


class TicketUpdate(BaseModel):
    estado: Optional[str] = Field(None, pattern="^(abierto|en_progreso|resuelto|cancelado)$")
    prioridad: Optional[str] = Field(None, pattern="^(baja|media|alta|urgente)$")
    asignado_a: Optional[str] = Field(None, max_length=100)
    descripcion: Optional[str] = None
    bloquea_room: Optional[bool] = None


class LostItemCreate(BaseModel):
    descripcion: str = Field(..., min_length=1)
    room_id: Optional[int] = Field(None, gt=0)
    lugar: Optional[str] = Field(None, max_length=150)


class LostItemUpdate(BaseModel):
    estado: Optional[str] = Field(None, pattern="^(guardado|entregado|descartado)$")
    entregado_a: Optional[str] = Field(None, max_length=120)
    lugar: Optional[str] = Field(None, max_length=150)


def _tenant(current_user: Usuario) -> int:
    if not current_user.empresa_usuario_id:
        raise HTTPException(status_code=403, detail="Usuario sin tenant asociado")
    return current_user.empresa_usuario_id


def _ticket_dict(t: MaintenanceTicket, room_numero: Optional[str] = None) -> dict:
    return {
        "id": t.id, "room_id": t.room_id, "room_numero": room_numero,
        "estado": t.estado, "prioridad": t.prioridad, "tipo": t.tipo,
        "descripcion": t.descripcion, "bloquea_room": t.bloquea_room,
        "asignado_a": t.asignado_a, "creado_por": t.creado_por,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
    }


def _lost_dict(li: HKLostItem, room_numero: Optional[str] = None) -> dict:
    return {
        "id": li.id, "room_id": li.room_id, "room_numero": room_numero,
        "descripcion": li.descripcion, "lugar": li.lugar, "estado": li.estado,
        "entregado_a": li.entregado_a,
        "fecha_hallazgo": li.fecha_hallazgo.isoformat() if li.fecha_hallazgo else None,
        "created_by": li.created_by,
    }


# ============================ Mantenimiento ============================
@router.get("/maintenance/tickets")
def list_tickets(
    estado: Optional[str] = Query(None),
    room_id: Optional[int] = Query(None),
    current_user: Usuario = Depends(require_staff),
    db: Session = Depends(conexion.get_db),
):
    tenant_id = _tenant(current_user)
    q = db.query(MaintenanceTicket).filter(MaintenanceTicket.empresa_usuario_id == tenant_id)
    if estado:
        q = q.filter(MaintenanceTicket.estado == estado)
    if room_id:
        q = q.filter(MaintenanceTicket.room_id == room_id)
    tickets = q.order_by(MaintenanceTicket.created_at.desc()).all()
    rooms = {r.id: r.numero for r in db.query(Room.id, Room.numero).filter(Room.empresa_usuario_id == tenant_id)}
    return [_ticket_dict(t, rooms.get(t.room_id)) for t in tickets]


@router.post("/maintenance/tickets", status_code=status.HTTP_201_CREATED)
def create_ticket(
    data: TicketCreate,
    current_user: Usuario = Depends(require_staff),
    db: Session = Depends(conexion.get_db),
):
    tenant_id = _tenant(current_user)
    room = db.query(Room).filter(Room.id == data.room_id, Room.empresa_usuario_id == tenant_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")

    ticket = MaintenanceTicket(
        empresa_usuario_id=tenant_id, room_id=room.id, descripcion=data.descripcion,
        tipo=data.tipo, prioridad=data.prioridad, bloquea_room=data.bloquea_room,
        asignado_a=data.asignado_a, estado="abierto", creado_por=current_user.username,
    )
    db.add(ticket)
    # Si bloquea la habitación, pasarla a mantenimiento
    if data.bloquea_room and room.estado_operativo not in ("ocupada",):
        room.estado_operativo = "mantenimiento"
        room.updated_at = utcnow()
    db.commit()
    db.refresh(ticket)
    log_event("mantenimiento", current_user.username, "Ticket creado", f"id={ticket.id}, room={room.numero}")
    return _ticket_dict(ticket, room.numero)


@router.patch("/maintenance/tickets/{ticket_id}")
def update_ticket(
    ticket_id: int,
    data: TicketUpdate,
    current_user: Usuario = Depends(require_staff),
    db: Session = Depends(conexion.get_db),
):
    tenant_id = _tenant(current_user)
    ticket = db.query(MaintenanceTicket).filter(
        MaintenanceTicket.id == ticket_id, MaintenanceTicket.empresa_usuario_id == tenant_id
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")

    if data.prioridad is not None:
        ticket.prioridad = data.prioridad
    if data.asignado_a is not None:
        ticket.asignado_a = data.asignado_a
    if data.descripcion is not None:
        ticket.descripcion = data.descripcion
    if data.bloquea_room is not None:
        ticket.bloquea_room = data.bloquea_room

    if data.estado is not None and data.estado != ticket.estado:
        ticket.estado = data.estado
        if data.estado in ("resuelto", "cancelado"):
            ticket.closed_at = utcnow()
            # Liberar la habitación si estaba bloqueada por mantenimiento y no quedan
            # otros tickets bloqueantes abiertos
            room = db.query(Room).filter(Room.id == ticket.room_id, Room.empresa_usuario_id == tenant_id).first()
            if room and room.estado_operativo == "mantenimiento":
                otros = db.query(MaintenanceTicket).filter(
                    MaintenanceTicket.room_id == room.id,
                    MaintenanceTicket.empresa_usuario_id == tenant_id,
                    MaintenanceTicket.bloquea_room == True,
                    MaintenanceTicket.estado.in_(["abierto", "en_progreso"]),
                    MaintenanceTicket.id != ticket.id,
                ).first()
                if not otros:
                    room.estado_operativo = "disponible"
                    room.updated_at = utcnow()

    db.commit()
    db.refresh(ticket)
    room_numero = db.query(Room.numero).filter(Room.id == ticket.room_id).scalar()
    log_event("mantenimiento", current_user.username, "Ticket actualizado", f"id={ticket.id}, estado={ticket.estado}")
    return _ticket_dict(ticket, room_numero)


# ============================ Objetos olvidados ============================
@router.get("/lost-items")
def list_lost_items(
    estado: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: Usuario = Depends(require_staff),
    db: Session = Depends(conexion.get_db),
):
    tenant_id = _tenant(current_user)
    q = db.query(HKLostItem).filter(HKLostItem.empresa_usuario_id == tenant_id)
    if estado:
        q = q.filter(HKLostItem.estado == estado)
    if search and search.strip():
        like = f"%{search.strip()}%"
        q = q.filter(HKLostItem.descripcion.ilike(like))
    items = q.order_by(HKLostItem.fecha_hallazgo.desc()).all()
    rooms = {r.id: r.numero for r in db.query(Room.id, Room.numero).filter(Room.empresa_usuario_id == tenant_id)}
    return [_lost_dict(li, rooms.get(li.room_id)) for li in items]


@router.post("/lost-items", status_code=status.HTTP_201_CREATED)
def create_lost_item(
    data: LostItemCreate,
    current_user: Usuario = Depends(require_staff),
    db: Session = Depends(conexion.get_db),
):
    tenant_id = _tenant(current_user)
    room_numero = None
    if data.room_id:
        room = db.query(Room).filter(Room.id == data.room_id, Room.empresa_usuario_id == tenant_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="Habitación no encontrada")
        room_numero = room.numero

    li = HKLostItem(
        empresa_usuario_id=tenant_id, room_id=data.room_id, descripcion=data.descripcion,
        lugar=data.lugar, estado="guardado", fecha_hallazgo=utcnow(), created_by=current_user.username,
    )
    db.add(li)
    db.commit()
    db.refresh(li)
    log_event("objetos_olvidados", current_user.username, "Objeto registrado", f"id={li.id}")
    return _lost_dict(li, room_numero)


@router.patch("/lost-items/{item_id}")
def update_lost_item(
    item_id: int,
    data: LostItemUpdate,
    current_user: Usuario = Depends(require_staff),
    db: Session = Depends(conexion.get_db),
):
    tenant_id = _tenant(current_user)
    li = db.query(HKLostItem).filter(
        HKLostItem.id == item_id, HKLostItem.empresa_usuario_id == tenant_id
    ).first()
    if not li:
        raise HTTPException(status_code=404, detail="Objeto no encontrado")
    if data.estado is not None:
        li.estado = data.estado
    if data.entregado_a is not None:
        li.entregado_a = data.entregado_a
    if data.lugar is not None:
        li.lugar = data.lugar
    db.commit()
    db.refresh(li)
    room_numero = db.query(Room.numero).filter(Room.id == li.room_id).scalar() if li.room_id else None
    log_event("objetos_olvidados", current_user.username, "Objeto actualizado", f"id={li.id}, estado={li.estado}")
    return _lost_dict(li, room_numero)
