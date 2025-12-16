"""
Hotel Calendar Endpoints
Endpoints para el nuevo sistema de calendario con Reservations y Stays separados
"""

from datetime import datetime, date, timedelta
from typing import List, Optional
from decimal import Decimal
from typing import Union

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
from pydantic import BaseModel, Field

from database.conexion import get_db
from models.core import (
    Reservation, ReservationRoom, ReservationGuest,
    Stay, StayRoomOccupancy, StayCharge, StayPayment,
    Room, RoomType, Cliente, Empresa, AuditEvent
)
from utils.logging_utils import log_event


router = APIRouter(prefix="/api/calendar", tags=["Hotel Calendar"])


# ========================================================================
# SCHEMAS
# ========================================================================

class CalendarBlock(BaseModel):
    """Bloque en el calendario (reserva o estadía)"""
    id: int
    kind: str  # "reservation" | "stay"
    room_id: int
    room_numero: str
    fecha_desde: str  # ISO date
    fecha_hasta: str  # ISO date
    estado: str
    cliente_nombre: Optional[str] = None
    meta: dict = {}

    class Config:
        from_attributes = True


class CalendarResponse(BaseModel):
    """Respuesta del calendario"""
    from_date: str
    to_date: str
    blocks: List[CalendarBlock]
    rooms: List[dict]


class CreateReservationRequest(BaseModel):
    """Request para crear reserva"""
    cliente_id: Optional[int] = None
    empresa_id: Optional[int] = None
    nombre_temporal: Optional[str] = None
    fecha_checkin: str  # YYYY-MM-DD
    fecha_checkout: str  # YYYY-MM-DD
    room_ids: List[int] = Field(..., min_items=1)
    estado: str = "confirmada"
    origen: Optional[str] = None
    notas: Optional[str] = None
    huespedes: List[dict] = []  # [{cliente_id, rol}]


class UpdateReservationRequest(BaseModel):
    """Request para actualizar reserva"""
    estado: Optional[str] = None
    notas: Optional[str] = None
    fecha_checkin: Optional[str] = None
    fecha_checkout: Optional[str] = None


class MoveBlockRequest(BaseModel):
    """Request para mover/resize bloque"""
    kind: str  # "reservation" | "stay"
    reservation_id: Optional[int] = None
    stay_id: Optional[int] = None
    occupancy_id: Optional[int] = None
    room_id: int
    fecha_checkin: Optional[str] = None  # Para reservations
    fecha_checkout: Optional[str] = None
    desde: Optional[str] = None  # Para stay occupancy (ISO datetime)
    hasta: Optional[str] = None
    motivo: Optional[str] = None


class CheckinRequest(BaseModel):
    """Request para check-in desde reserva"""
    notas: Optional[str] = None
    huespedes: List[dict] = []  # Si vacío, usa los de la reserva


class CheckoutRequest(BaseModel):
    """Request para check-out"""
    notas: Optional[str] = None
    pago_monto: Optional[float] = None
    pago_metodo: Optional[str] = None


class ChargeRequest(BaseModel):
    """Request para agregar cargo"""
    tipo: str  # "night" | "product" | "service" | "fee" | "discount"
    descripcion: str
    cantidad: float = 1.0
    monto_unitario: float
    monto_total: float


class PaymentRequest(BaseModel):
    """Request para registrar pago"""
    monto: float = Field(..., gt=0, description="Monto del pago (> 0)")
    metodo: str = "efectivo"  # "efectivo" | "tarjeta" | "transferencia" | etc
    referencia: Optional[str] = None  # Número de operación, comprobante, etc


class InvoiceLineItem(BaseModel):
    """Línea de factura"""
    line_type: str  # "room" | "charge" | "tax" | "discount" | "payment"
    description: str
    quantity: float = 1.0
    unit_price: float = 0.0
    total: float = 0.0
    metadata: dict = {}  # Para info adicional (fecha, tipo de cargo, etc.)


class InvoicePeriod(BaseModel):
    """Período de la estadía"""
    checkin_real: str  # ISO datetime
    checkout_candidate: str  # ISO date (puede ser hoy, fecha planeada, o override)
    checkout_planned: str  # ISO date de la reserva


class InvoiceNights(BaseModel):
    """Desglose de noches"""
    planned: int  # Según reserva
    calculated: int  # Según checkin_real y checkout_candidate
    suggested_to_charge: int  # Lógica de negocio (mínimo 1)
    override_applied: bool = False
    override_value: Optional[int] = None


class InvoiceRoom(BaseModel):
    """Información de habitación"""
    room_id: int
    numero: str
    room_type_name: str
    nightly_rate: float
    rate_source: str  # "stay" | "room_type" | "default" | "missing"


class InvoiceTotals(BaseModel):
    """Totales de factura"""
    room_subtotal: float
    charges_total: float
    taxes_total: float
    discounts_total: float
    grand_total: float
    payments_total: float
    balance: float


class InvoiceWarning(BaseModel):
    """Warning para UX"""
    code: str
    message: str
    severity: str = "warning"  # "info" | "warning" | "error"


class InvoicePreviewResponse(BaseModel):
    """Preview profesional de factura para check-out"""
    # Identificación
    stay_id: int
    reservation_id: int
    cliente_nombre: Optional[str] = None
    currency: str = "ARS"
    
    # Período y noches
    period: InvoicePeriod
    nights: InvoiceNights
    room: InvoiceRoom
    
    # Líneas detalladas (opcional)
    breakdown_lines: List[InvoiceLineItem] = []
    
    # Totales
    totals: InvoiceTotals
    
    # Pagos (opcional)
    payments: List[dict] = []
    
    # Warnings/Alertas
    warnings: List[InvoiceWarning] = []
    
    # Metadata
    readonly: bool = False  # True si la estadía ya está cerrada
    generated_at: str  # Timestamp del preview


# ========================================================================
# HELPERS
# ========================================================================

def parse_to_date(value: Union[str, date, datetime]) -> date:
    """
    Convierte string / datetime / date a date.
    Lanza error claro si no puede.
    """
    if value is None:
        raise ValueError("Date value is None")

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            # ISO completo (con o sin Z)
            return datetime.fromisoformat(value.replace('Z', '+00:00')).date()
        except ValueError:
            try:
                return datetime.strptime(value, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError(f"Invalid date format: {value}")

    raise TypeError(f"Unsupported date type: {type(value)}")

def parse_to_datetime(value: Union[str, datetime]) -> datetime:
    """
    Convierte string a datetime (timezone-aware si viene con Z).
    """
    if value is None:
        raise ValueError("Datetime value is None")

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            for fmt in (
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M',
                '%Y-%m-%d'
            ):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue

        raise ValueError(f"Invalid datetime format: {value}")

    raise TypeError(f"Unsupported datetime type: {type(value)}")


def _check_room_availability(
    db: Session,
    room_id: int,
    fecha_desde: date,
    fecha_hasta: date,
    exclude_reservation_id: Optional[int] = None,
    exclude_stay_id: Optional[int] = None
) -> bool:
    """Verificar disponibilidad de habitación en rango de fechas"""
    
    # Verificar conflictos en reservas confirmadas
    reservations_query = (
        db.query(Reservation)
        .join(ReservationRoom)
        .filter(
            ReservationRoom.room_id == room_id,
            Reservation.estado.in_(["confirmada", "convertida"]),
            Reservation.fecha_checkin < fecha_hasta,
            Reservation.fecha_checkout > fecha_desde
        )
    )
    
    if exclude_reservation_id:
        reservations_query = reservations_query.filter(Reservation.id != exclude_reservation_id)
    
    if reservations_query.first():
        return False
    
    # Verificar conflictos en ocupaciones reales
    occupancies_query = (
        db.query(StayRoomOccupancy)
        .join(Stay)
        .filter(
            StayRoomOccupancy.room_id == room_id,
            Stay.estado.in_(["pendiente_checkin", "ocupada", "pendiente_checkout"]),
            StayRoomOccupancy.desde < fecha_hasta,
            or_(
                StayRoomOccupancy.hasta.is_(None),
                StayRoomOccupancy.hasta > fecha_desde
            )
        )
    )
    
    if exclude_stay_id:
        occupancies_query = occupancies_query.filter(Stay.id != exclude_stay_id)
    
    if occupancies_query.first():
        return False
    
    return True


# ========================================================================
# ENDPOINTS: CALENDAR
# ========================================================================

@router.get("/calendar", response_model=CalendarResponse)
def get_calendar(
    from_date: str = Query(..., alias="from", description="YYYY-MM-DD"),
    to_date: str = Query(..., alias="to", description="YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    """
    Obtener vista del calendario con todas las reservas y estadías
    """
    fecha_desde = parse_to_date(from_date)
    fecha_hasta = parse_to_date(to_date)
    
    blocks = []
    
    # 1. Cargar reservas confirmadas
    reservations = (
        db.query(Reservation)
        .options(
            joinedload(Reservation.rooms).joinedload(ReservationRoom.room),
            joinedload(Reservation.cliente),
            joinedload(Reservation.empresa)
        )
        .filter(
            Reservation.estado.in_(["confirmada", "convertida"]),
            Reservation.fecha_checkin < fecha_hasta,
            Reservation.fecha_checkout > fecha_desde
        )
        .all()
    )
    
    for res in reservations:
        cliente_nombre = None
        if res.cliente:
            cliente_nombre = f"{res.cliente.nombre} {res.cliente.apellido}"
        elif res.empresa:
            cliente_nombre = res.empresa.nombre
        else:
            cliente_nombre = res.nombre_temporal
        
        for res_room in res.rooms:
            blocks.append(CalendarBlock(
                id=res.id,
                kind="reservation",
                room_id=res_room.room.id,
                room_numero=res_room.room.numero,
                fecha_desde=res.fecha_checkin.isoformat(),
                fecha_hasta=res.fecha_checkout.isoformat(),
                estado=res.estado,
                cliente_nombre=cliente_nombre,
                meta={
                    "origen": res.origen,
                    "notas": res.notas
                }
            ))
    
    # 2. Cargar estadías activas
    stays = (
        db.query(Stay)
        .options(
            joinedload(Stay.reservation).joinedload(Reservation.cliente),
            joinedload(Stay.reservation).joinedload(Reservation.empresa),
            joinedload(Stay.occupancies).joinedload(StayRoomOccupancy.room)
        )
        .filter(
            Stay.estado.in_(["pendiente_checkin", "ocupada", "pendiente_checkout"])
        )
        .all()
    )
    
    for stay in stays:
        res = stay.reservation
        cliente_nombre = None
        if res.cliente:
            cliente_nombre = f"{res.cliente.nombre} {res.cliente.apellido}"
        elif res.empresa:
            cliente_nombre = res.empresa.nombre
        else:
            cliente_nombre = res.nombre_temporal
        
        for occ in stay.occupancies:
            # Filtrar por rango de fechas
            occ_desde = occ.desde.date() if isinstance(occ.desde, datetime) else occ.desde
            occ_hasta = occ.hasta.date() if occ.hasta and isinstance(occ.hasta, datetime) else (occ.hasta if occ.hasta else fecha_hasta)
            
            if occ_desde < fecha_hasta and (not occ_hasta or occ_hasta > fecha_desde):
                blocks.append(CalendarBlock(
                    id=stay.id,
                    kind="stay",
                    room_id=occ.room.id,
                    room_numero=occ.room.numero,
                    fecha_desde=occ_desde.isoformat(),
                    fecha_hasta=occ_hasta.isoformat() if occ_hasta else fecha_hasta.isoformat(),
                    estado=stay.estado,
                    cliente_nombre=cliente_nombre,
                    meta={
                        "occupancy_id": occ.id,
                        "checkin_real": stay.checkin_real.isoformat() if stay.checkin_real else None
                    }
                ))
    
    # 3. Cargar información de habitaciones
    rooms = db.query(Room).filter(Room.activo == True).all()
    rooms_data = [
        {
            "id": r.id,
            "numero": r.numero,
            "piso": r.piso,
            "room_type_id": r.room_type_id,
            "estado_operativo": r.estado_operativo
        }
        for r in rooms
    ]
    
    log_event("calendar", "usuario", "Ver calendario", f"from={from_date} to={to_date} blocks={len(blocks)}")
    
    return CalendarResponse(
        from_date=from_date,
        to_date=to_date,
        blocks=blocks,
        rooms=rooms_data
    )


# ========================================================================
# ENDPOINTS: RESERVATIONS
# ========================================================================

@router.post("/reservations", status_code=status.HTTP_201_CREATED)
def create_reservation(
    req: CreateReservationRequest,
    db: Session = Depends(get_db)
):
    """
    Crear nueva reserva
    """
    fecha_checkin = _parse_date(req.fecha_checkin)
    fecha_checkout = _parse_date(req.fecha_checkout)
    
    if fecha_checkout <= fecha_checkin:
        raise HTTPException(400, "La fecha de checkout debe ser posterior al checkin")
    
    # Validar habitaciones
    rooms = db.query(Room).filter(Room.id.in_(req.room_ids)).all()
    if len(rooms) != len(req.room_ids):
        raise HTTPException(404, "Una o más habitaciones no encontradas")
    
    # Verificar disponibilidad
    for room in rooms:
        if not _check_room_availability(db, room.id, fecha_checkin, fecha_checkout):
            raise HTTPException(
                409,
                f"Habitación {room.numero} no disponible en las fechas seleccionadas"
            )
    
    # Validar cliente/empresa si se proporciona
    if req.cliente_id:
        cliente = db.query(Cliente).filter(Cliente.id == req.cliente_id).first()
        if not cliente:
            raise HTTPException(404, "Cliente no encontrado")
    
    if req.empresa_id:
        empresa = db.query(Empresa).filter(Empresa.id == req.empresa_id).first()
        if not empresa:
            raise HTTPException(404, "Empresa no encontrada")
    
    # Crear reserva
    reservation = Reservation(
        cliente_id=req.cliente_id,
        empresa_id=req.empresa_id,
        nombre_temporal=req.nombre_temporal,
        fecha_checkin=fecha_checkin,
        fecha_checkout=fecha_checkout,
        estado=req.estado,
        origen=req.origen,
        notas=req.notas
    )
    
    db.add(reservation)
    db.flush()
    
    # Asignar habitaciones
    for room_id in req.room_ids:
        res_room = ReservationRoom(
            reservation_id=reservation.id,
            room_id=room_id
        )
        db.add(res_room)
    
    # Asignar huéspedes si se proporcionan
    for guest_data in req.huespedes:
        res_guest = ReservationGuest(
            reservation_id=reservation.id,
            cliente_id=guest_data.get("cliente_id"),
            rol=guest_data.get("rol", "adulto")
        )
        db.add(res_guest)
    
    # Auditoría
    audit = AuditEvent(
        entity_type="reservation",
        entity_id=reservation.id,
        action="CREATE",
        usuario="sistema",
        descripcion=f"Reserva creada para {fecha_checkin} - {fecha_checkout}",
        payload={"room_ids": req.room_ids}
    )
    db.add(audit)
    
    db.commit()
    db.refresh(reservation)
    
    log_event("reservations", "usuario", "Crear reserva", f"id={reservation.id}")
    
    return {
        "id": reservation.id,
        "estado": reservation.estado,
        "fecha_checkin": reservation.fecha_checkin.isoformat(),
        "fecha_checkout": reservation.fecha_checkout.isoformat()
    }


@router.patch("/reservations/{reservation_id}")
def update_reservation(
    reservation_id: int = Path(..., gt=0),
    req: UpdateReservationRequest = ...,
    db: Session = Depends(get_db)
):
    """
    Actualizar reserva existente
    """
    reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(404, "Reserva no encontrada")
    
    cambios = []
    
    if req.estado is not None:
        reservation.estado = req.estado
        cambios.append(f"estado={req.estado}")
    
    if req.notas is not None:
        reservation.notas = req.notas
        cambios.append("notas actualizadas")
    
    if req.fecha_checkin or req.fecha_checkout:
        nueva_checkin = _parse_date(req.fecha_checkin) if req.fecha_checkin else reservation.fecha_checkin
        nueva_checkout = _parse_date(req.fecha_checkout) if req.fecha_checkout else reservation.fecha_checkout
        
        if nueva_checkout <= nueva_checkin:
            raise HTTPException(400, "Fechas inválidas")
        
        # Verificar disponibilidad para las nuevas fechas
        for res_room in reservation.rooms:
            if not _check_room_availability(
                db, res_room.room_id, nueva_checkin, nueva_checkout,
                exclude_reservation_id=reservation_id
            ):
                raise HTTPException(409, f"Habitación {res_room.room.numero} no disponible")
        
        reservation.fecha_checkin = nueva_checkin
        reservation.fecha_checkout = nueva_checkout
        cambios.append(f"fechas={nueva_checkin} a {nueva_checkout}")
    
    reservation.updated_at = datetime.utcnow()
    
    # Auditoría
    audit = AuditEvent(
        entity_type="reservation",
        entity_id=reservation.id,
        action="UPDATE",
        usuario="sistema",
        descripcion=f"Reserva actualizada: {', '.join(cambios)}"
    )
    db.add(audit)
    
    db.commit()
    db.refresh(reservation)
    
    log_event("reservations", "usuario", "Actualizar reserva", f"id={reservation_id}")
    
    return {
        "id": reservation.id,
        "estado": reservation.estado,
        "updated_at": reservation.updated_at.isoformat()
    }


# ========================================================================
# ENDPOINTS: BLOCK MOVE
# ========================================================================

@router.patch("/calendar/blocks/move")
def move_block(
    req: MoveBlockRequest,
    db: Session = Depends(get_db)
):
    """
    Mover o redimensionar bloque (reserva o estadía)
    """
    if req.kind == "reservation":
        if not req.reservation_id:
            raise HTTPException(400, "reservation_id requerido")
        
        reservation = db.query(Reservation).filter(Reservation.id == req.reservation_id).first()
        if not reservation:
            raise HTTPException(404, "Reserva no encontrada")
        
        nueva_checkin = _parse_date(req.fecha_checkin) if req.fecha_checkin else reservation.fecha_checkin
        nueva_checkout = _parse_date(req.fecha_checkout) if req.fecha_checkout else reservation.fecha_checkout
        
        # Verificar disponibilidad
        if not _check_room_availability(
            db, req.room_id, nueva_checkin, nueva_checkout,
            exclude_reservation_id=req.reservation_id
        ):
            raise HTTPException(409, "Habitación no disponible en las nuevas fechas")
        
        # Actualizar fechas
        reservation.fecha_checkin = nueva_checkin
        reservation.fecha_checkout = nueva_checkout
        
        # Si cambió de habitación, actualizar
        res_room = reservation.rooms[0] if reservation.rooms else None
        if res_room and res_room.room_id != req.room_id:
            res_room.room_id = req.room_id
        
        reservation.updated_at = datetime.utcnow()
        
        audit = AuditEvent(
            entity_type="reservation",
            entity_id=reservation.id,
            action="MOVE",
            usuario="sistema",
            descripcion=f"Reserva movida a habitación {req.room_id}"
        )
        db.add(audit)
        
        db.commit()
        
        return {"success": True, "reservation_id": reservation.id}
    
    elif req.kind == "stay":
        if not req.occupancy_id:
            raise HTTPException(400, "occupancy_id requerido para mover estadía")
        
        occupancy = db.query(StayRoomOccupancy).filter(StayRoomOccupancy.id == req.occupancy_id).first()
        if not occupancy:
            raise HTTPException(404, "Ocupación no encontrada")
        
        stay = occupancy.stay
        
        # Si cambió de habitación, crear nueva ocupación y cerrar la anterior
        if occupancy.room_id != req.room_id:
            # Cerrar ocupación actual
            occupancy.hasta = datetime.utcnow()
            
            # Crear nueva ocupación
            nueva_occ = StayRoomOccupancy(
                stay_id=stay.id,
                room_id=req.room_id,
                desde=datetime.utcnow(),
                hasta=None,
                motivo=req.motivo or "Cambio de habitación",
                creado_por="sistema"
            )
            db.add(nueva_occ)
            
            # Actualizar estado de habitaciones
            room_anterior = db.query(Room).filter(Room.id == occupancy.room_id).first()
            if room_anterior:
                room_anterior.estado_operativo = "disponible"
            
            room_nueva = db.query(Room).filter(Room.id == req.room_id).first()
            if room_nueva:
                room_nueva.estado_operativo = "ocupada"
        
        # Si cambió fechas (resize)
        if req.desde:
            occupancy.desde = _parse_datetime(req.desde)
        if req.hasta:
            occupancy.hasta = _parse_datetime(req.hasta)
        
        audit = AuditEvent(
            entity_type="stay",
            entity_id=stay.id,
            action="ROOM_MOVE",
            usuario="sistema",
            descripcion=f"Estadía movida a habitación {req.room_id}"
        )
        db.add(audit)
        
        db.commit()
        
        return {"success": True, "stay_id": stay.id}
    
    else:
        raise HTTPException(400, f"kind inválido: {req.kind}")


# ========================================================================
# ENDPOINTS: CHECK-IN / CHECK-OUT
# ========================================================================

@router.post("/stays/from-reservation/{reservation_id}/checkin", status_code=status.HTTP_201_CREATED)
def checkin_from_reservation(
    reservation_id: int = Path(..., gt=0),
    req: CheckinRequest = ...,
    db: Session = Depends(get_db)
):
    """
    Realizar check-in creando una estadía desde una reserva
    """
    reservation = (
        db.query(Reservation)
        .options(
            joinedload(Reservation.rooms),
            joinedload(Reservation.guests)
        )
        .filter(Reservation.id == reservation_id)
        .first()
    )
    
    if not reservation:
        raise HTTPException(404, "Reserva no encontrada")
    
    if reservation.estado not in ["confirmada", "draft"]:
        raise HTTPException(409, f"Reserva en estado {reservation.estado} no puede hacer check-in")
    
    # Verificar si ya existe estadía
    existing_stay = db.query(Stay).filter(Stay.reservation_id == reservation_id).first()
    if existing_stay:
        raise HTTPException(409, "Ya existe una estadía para esta reserva")
    
    # Crear estadía
    stay = Stay(
        reservation_id=reservation.id,
        estado="ocupada",
        checkin_real=datetime.utcnow(),
        notas_internas=req.notas
    )
    db.add(stay)
    db.flush()
    
    # Crear ocupaciones para cada habitación
    for res_room in reservation.rooms:
        occupancy = StayRoomOccupancy(
            stay_id=stay.id,
            room_id=res_room.room_id,
            desde=datetime.utcnow(),
            hasta=None,  # Sigue ocupando
            motivo="Check-in inicial",
            creado_por="sistema"
        )
        db.add(occupancy)
        
        # Actualizar estado de la habitación
        room = db.query(Room).filter(Room.id == res_room.room_id).first()
        if room:
            room.estado_operativo = "ocupada"
    
    # Marcar reserva como convertida
    reservation.estado = "convertida"
    
    # Auditoría
    audit = AuditEvent(
        entity_type="stay",
        entity_id=stay.id,
        action="CHECKIN",
        usuario="sistema",
        descripcion=f"Check-in realizado desde reserva {reservation_id}",
        payload={
            "reservation_id": reservation_id,
            "rooms": [r.room_id for r in reservation.rooms]
        }
    )
    db.add(audit)
    
    db.commit()
    db.refresh(stay)
    
    log_event("stays", "usuario", "Check-in", f"stay_id={stay.id} reservation_id={reservation_id}")
    
    return {
        "id": stay.id,
        "reservation_id": reservation.id,
        "estado": stay.estado,
        "checkin_real": stay.checkin_real.isoformat()
    }


@router.post("/stays/{stay_id}/checkout")
def checkout_stay(
    stay_id: int = Path(..., gt=0),
    req: CheckoutRequest = ...,
    db: Session = Depends(get_db)
):
    """
    Realizar check-out de una estadía
    """
    stay = (
        db.query(Stay)
        .options(
            joinedload(Stay.occupancies),
            joinedload(Stay.charges),
            joinedload(Stay.payments)
        )
        .filter(Stay.id == stay_id)
        .first()
    )
    
    if not stay:
        raise HTTPException(404, "Estadía no encontrada")
    
    if stay.estado not in ["ocupada", "pendiente_checkout"]:
        raise HTTPException(409, f"Estadía en estado {stay.estado} no puede hacer check-out")
    
    # Cerrar todas las ocupaciones activas
    ahora = datetime.utcnow()
    for occ in stay.occupancies:
        if not occ.hasta:
            occ.hasta = ahora
            
            # Actualizar estado de la habitación a disponible (o limpieza si se implementa)
            room = db.query(Room).filter(Room.id == occ.room_id).first()
            if room:
                room.estado_operativo = "disponible"  # Podría ser "limpieza" según lógica
    
    # Registrar pago si se proporciona
    if req.pago_monto and req.pago_monto > 0:
        payment = StayPayment(
            stay_id=stay.id,
            monto=Decimal(str(req.pago_monto)),
            metodo=req.pago_metodo or "efectivo",
            usuario="sistema",
            notas="Pago en checkout"
        )
        db.add(payment)
    
    # Actualizar estadía
    stay.estado = "cerrada"
    stay.checkout_real = ahora
    if req.notas:
        stay.notas_internas = (stay.notas_internas or "") + "\n" + req.notas
    stay.updated_at = ahora
    
    # Calcular totales
    total_charges = sum(Decimal(str(c.monto_total)) for c in stay.charges)
    total_payments = sum(Decimal(str(p.monto)) for p in stay.payments if not p.es_reverso)
    saldo = total_charges - total_payments
    
    # Auditoría
    audit = AuditEvent(
        entity_type="stay",
        entity_id=stay.id,
        action="CHECKOUT",
        usuario="sistema",
        descripcion=f"Check-out realizado",
        payload={
            "total_charges": float(total_charges),
            "total_payments": float(total_payments),
            "saldo": float(saldo)
        }
    )
    db.add(audit)
    
    db.commit()
    db.refresh(stay)
    
    log_event("stays", "usuario", "Check-out", f"stay_id={stay_id} saldo={float(saldo)}")
    
    return {
        "id": stay.id,
        "estado": stay.estado,
        "checkout_real": stay.checkout_real.isoformat(),
        "total_charges": float(total_charges),
        "total_payments": float(total_payments),
        "saldo": float(saldo)
    }


# ========================================================================
# ENDPOINTS: CHARGES
# ========================================================================

@router.get("/stays/{stay_id}/charges")
def list_charges(
    stay_id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Listar cargos de una estadía
    """
    stay = db.query(Stay).filter(Stay.id == stay_id).first()
    if not stay:
        raise HTTPException(404, "Estadía no encontrada")
    
    charges = db.query(StayCharge).filter(StayCharge.stay_id == stay_id).all()
    
    return {
        "stay_id": stay_id,
        "charges": [
            {
                "id": c.id,
                "tipo": c.tipo,
                "descripcion": c.descripcion,
                "cantidad": float(c.cantidad),
                "monto_unitario": float(c.monto_unitario),
                "monto_total": float(c.monto_total),
                "created_at": c.created_at.isoformat()
            }
            for c in charges
        ],
        "total": float(sum(c.monto_total for c in charges))
    }


@router.post("/stays/{stay_id}/charges", status_code=status.HTTP_201_CREATED)
def add_charge(
    stay_id: int = Path(..., gt=0),
    req: ChargeRequest = ...,
    db: Session = Depends(get_db)
):
    """
    Agregar cargo a una estadía
    """
    stay = db.query(Stay).filter(Stay.id == stay_id).first()
    if not stay:
        raise HTTPException(404, "Estadía no encontrada")
    
    if stay.estado == "cerrada":
        raise HTTPException(409, "No se pueden agregar cargos a una estadía cerrada")
    
    charge = StayCharge(
        stay_id=stay_id,
        tipo=req.tipo,
        descripcion=req.descripcion,
        cantidad=Decimal(str(req.cantidad)),
        monto_unitario=Decimal(str(req.monto_unitario)),
        monto_total=Decimal(str(req.monto_total)),
        creado_por="sistema"
    )
    
    db.add(charge)
    
    # Auditoría
    audit = AuditEvent(
        entity_type="stay",
        entity_id=stay_id,
        action="ADD_CHARGE",
        usuario="sistema",
        descripcion=f"Cargo agregado: {req.descripcion}",
        payload={
            "tipo": req.tipo,
            "monto": req.monto_total
        }
    )
    db.add(audit)
    
    db.commit()
    db.refresh(charge)
    
    log_event("stays", "usuario", "Agregar cargo", f"stay_id={stay_id} tipo={req.tipo} monto={req.monto_total}")
    
    return {
        "id": charge.id,
        "tipo": charge.tipo,
        "monto_total": float(charge.monto_total),
        "created_at": charge.created_at.isoformat()
    }


@router.post("/stays/{stay_id}/payments", status_code=status.HTTP_201_CREATED)
def add_payment(
    stay_id: int = Path(..., gt=0),
    req: PaymentRequest = ...,
    db: Session = Depends(get_db)
):
    """
    Registrar pago para una estadía
    
    - Crea un StayPayment en la BD
    - NO genera comprobante ni modifica la reserva
    - El frontend es responsable de actualizar invoicePreview después
    """
    stay = db.query(Stay).filter(Stay.id == stay_id).first()
    if not stay:
        raise HTTPException(404, "Estadía no encontrada")
    
    if stay.estado == "cerrada":
        raise HTTPException(409, "No se pueden agregar pagos a una estadía cerrada")
    
    payment = StayPayment(
        stay_id=stay_id,
        monto=Decimal(str(req.monto)),
        metodo=req.metodo,
        referencia=req.referencia or "",
        notas="Pago registrado desde checkout",
        es_reverso=False
    )
    
    db.add(payment)
    
    # Auditoría
    audit = AuditEvent(
        entity_type="stay",
        entity_id=stay_id,
        action="ADD_PAYMENT",
        usuario="sistema",
        descripcion=f"Pago registrado: {req.metodo} ${req.monto}",
        payload={
            "metodo": req.metodo,
            "monto": req.monto,
            "referencia": req.referencia
        }
    )
    db.add(audit)
    
    db.commit()
    db.refresh(payment)
    
    log_event("stays", "usuario", "Registrar pago", f"stay_id={stay_id} metodo={req.metodo} monto={req.monto}")
    
    return {
        "id": payment.id,
        "monto": float(payment.monto),
        "metodo": payment.metodo,
        "referencia": payment.referencia,
        "timestamp": payment.timestamp.isoformat()
    }

IVA_RATE_DEFAULT = 0.21


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _today_date() -> date:
    # Si más adelante querés timezone local, lo cambiás acá y no en todo el endpoint.
    return date.today()

@router.get("/stays/{stay_id}/invoice-preview", response_model=InvoicePreviewResponse)
def get_invoice_preview(
    stay_id: int = Path(..., gt=0),
    checkout_date: Optional[str] = Query(None, description="Fecha candidata de checkout (YYYY-MM-DD o ISO)"),
    nights_override: Optional[int] = Query(None, ge=1, description="Override de noches a cobrar (>= 1)"),
    tarifa_override: Optional[float] = Query(None, ge=0, description="Override de tarifa por noche"),
    discount_override_pct: Optional[float] = Query(None, ge=0, le=100, description="Descuento adicional en %"),
    tax_override_mode: Optional[str] = Query(None, description="Modo: 'normal'|'exento'|'custom'"),
    tax_override_value: Optional[float] = Query(None, ge=0, description="Impuesto personalizado"),
    include_items: bool = Query(True, description="Incluir líneas detalladas"),
    db: Session = Depends(get_db),
):
    """
    🧾 INVOICE PREVIEW (Checkout Wizard)

    - NO modifica DB (solo preview)
    - El backend es la fuente de verdad:
      noches, tarifa, impuestos, descuentos, pagos, total y saldo.
    """

    # =====================================================================
    # 1) CARGA Y VALIDACIÓN
    # =====================================================================
    stay = (
        db.query(Stay)
        .filter(Stay.id == stay_id)
        .options(
            joinedload(Stay.reservation).joinedload(Reservation.cliente),
            joinedload(Stay.reservation).joinedload(Reservation.empresa),
            joinedload(Stay.occupancies).joinedload(StayRoomOccupancy.room).joinedload(Room.tipo),
            joinedload(Stay.charges),
            joinedload(Stay.payments),
        )
        .first()
    )

    if not stay:
        raise HTTPException(status_code=404, detail=f"Stay {stay_id} no encontrado")

    reservation = stay.reservation
    if not reservation:
        raise HTTPException(status_code=400, detail="Stay sin reserva asociada")

    readonly = (stay.estado == "cerrada")

    # =====================================================================
    # 2) CLIENTE (DISPLAY)
    # =====================================================================
    cliente_nombre = None
    if reservation.cliente:
        cliente_nombre = f"{reservation.cliente.nombre} {reservation.cliente.apellido}".strip()
    elif reservation.empresa:
        cliente_nombre = (reservation.empresa.nombre or "").strip()
    elif getattr(reservation, "nombre_temporal", None):
        cliente_nombre = (reservation.nombre_temporal or "").strip()

    cliente_nombre = cliente_nombre or f"Stay #{stay_id}"

    # =====================================================================
    # 3) OCUPACIÓN PRINCIPAL + HABITACIÓN + TIPO
    # =====================================================================
    occupancy = None
    if stay.occupancies:
        active = [o for o in stay.occupancies if not o.hasta]
        occupancy = active[0] if active else stay.occupancies[-1]

    if not occupancy or not occupancy.room:
        raise HTTPException(status_code=400, detail="Stay sin ocupación/habitación registrada")

    room = occupancy.room
    room_type = getattr(room, "tipo", None)

    # =====================================================================
    # 4) TARIFA (rate snapshot recomendado, fallback a room_type.base_price, soporte para override)
    # =====================================================================
    nightly_rate = 0.0
    rate_source = "missing"
    tarifa_override_applied = False

    # Si tarifa_override viene en parámetros, úsalo directamente
    if tarifa_override is not None and tarifa_override >= 0:
        nightly_rate = _safe_float(tarifa_override, 0.0)
        rate_source = "override"
        tarifa_override_applied = True
    # Si más adelante agregás stay.nightly_rate_snapshot, va primero:
    elif (stay_rate := getattr(stay, "nightly_rate", None) or getattr(stay, "nightly_rate_snapshot", None)):
        nightly_rate = _safe_float(stay_rate, 0.0)
        rate_source = "stay_snapshot"
    elif room_type and getattr(room_type, "precio_base", None):
        nightly_rate = _safe_float(room_type.precio_base, 0.0)
        rate_source = "room_type"
    else:
        nightly_rate = 0.0
        rate_source = "missing"

    invoice_room = InvoiceRoom(
        room_id=room.id,
        numero=str(room.numero),
        room_type_name=(getattr(room_type, "nombre", None) or "No especificado"),
        nightly_rate=nightly_rate,
        rate_source=rate_source,
    )

    # =====================================================================
    # 5) FECHAS + NOCHES (SIEMPRE DATE)
    # =====================================================================
    # Check-in real: stay.checkin_real o occupancy.desde
    raw_checkin = stay.checkin_real or occupancy.desde
    if not raw_checkin:
        raise HTTPException(status_code=400, detail="Stay sin fecha de check-in (real)")

    try:
        checkin_date = parse_to_date(raw_checkin)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Check-in inválido: {e}")

    # Checkout planned (plan): preferí stay.checkout_planned si existe; sino reserva
    raw_checkout_planned = getattr(stay, "checkout_planned", None) or reservation.fecha_checkout
    if not raw_checkout_planned:
        raise HTTPException(status_code=400, detail="No existe checkout planificado")

    try:
        checkout_planned_date = parse_to_date(raw_checkout_planned)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Checkout planificado inválido: {e}")

    # Checkout candidato:
    # - si viene query => usarla
    # - si la estadía ya cerró y hay checkout_real => usarlo
    # - si está abierta => hoy (default UX pro)
    if checkout_date:
        try:
            checkout_candidate_date = parse_to_date(checkout_date)
        except Exception:
            raise HTTPException(status_code=400, detail=f"checkout_date inválido: {checkout_date}")
    elif readonly and stay.checkout_real:
        checkout_candidate_date = parse_to_date(stay.checkout_real)
    else:
        checkout_candidate_date = _today_date()

    if checkout_candidate_date < checkin_date:
        raise HTTPException(
            status_code=400,
            detail=f"checkout_date ({checkout_candidate_date}) no puede ser anterior a checkin ({checkin_date})",
        )

    # Planned nights: usar fechas del plan (si fecha_checkin existe)
    raw_plan_checkin = getattr(stay, "checkin_planned", None) or reservation.fecha_checkin
    try:
        plan_checkin_date = parse_to_date(raw_plan_checkin) if raw_plan_checkin else checkin_date
    except Exception:
        plan_checkin_date = checkin_date

    planned_nights = max(0, (checkout_planned_date - plan_checkin_date).days)

    # Calculated nights (cobrables): mínimo 1 si la estadía está activa o si candidate==checkin
    raw_diff = (checkout_candidate_date - checkin_date).days
    calculated_nights = max(1, raw_diff) if not readonly else max(0, raw_diff)

    suggested_to_charge = max(1, calculated_nights) if not readonly else max(0, calculated_nights)

    override_applied = nights_override is not None
    final_nights = int(nights_override) if override_applied else int(suggested_to_charge)

    invoice_nights = InvoiceNights(
        planned=planned_nights,
        calculated=calculated_nights,
        suggested_to_charge=suggested_to_charge,
        override_applied=override_applied,
        override_value=nights_override,
    )

    invoice_period = InvoicePeriod(
        checkin_real=(stay.checkin_real.isoformat() if stay.checkin_real else datetime.combine(checkin_date, datetime.min.time()).isoformat()),
        checkout_candidate=checkout_candidate_date.isoformat(),
        checkout_planned=checkout_planned_date.isoformat(),
    )

    # =====================================================================
    # 6) LÍNEAS + TOTALES
    # =====================================================================
    breakdown_lines: List[InvoiceLineItem] = []
    warnings: List[InvoiceWarning] = []

    # --- Alojamiento ---
    room_subtotal = nightly_rate * final_nights

    if include_items:
        breakdown_lines.append(
            InvoiceLineItem(
                line_type="room",
                description=f"Alojamiento - {invoice_room.room_type_name} #{invoice_room.numero}",
                quantity=float(final_nights),
                unit_price=nightly_rate,
                total=room_subtotal,
                metadata={
                    "nights": final_nights,
                    "room_id": room.id,
                    "rate_source": rate_source,
                    "checkin_date": checkin_date.isoformat(),
                    "checkout_candidate": checkout_candidate_date.isoformat(),
                },
            )
        )

    # --- Cargos / Consumos ---
    charges_total = 0.0
    discount_total_from_charges = 0.0
    fee_total_from_charges = 0.0

    for charge in (stay.charges or []):
        c_type = getattr(charge, "tipo", None) or "charge"
        c_desc = getattr(charge, "descripcion", None) or f"Cargo {c_type}"
        c_total = _safe_float(getattr(charge, "monto_total", None), 0.0)
        c_qty = _safe_float(getattr(charge, "cantidad", None), 1.0)
        c_unit = _safe_float(getattr(charge, "monto_unitario", None), c_total)

        # Clasificación
        if c_type == "discount":
            discount_total_from_charges += abs(c_total)
            if include_items:
                breakdown_lines.append(
                    InvoiceLineItem(
                        line_type="discount",
                        description=c_desc,
                        quantity=1.0,
                        unit_price=-abs(c_total),
                        total=-abs(c_total),
                        metadata={"charge_id": charge.id, "tipo": "discount"},
                    )
                )
            continue

        if c_type == "fee":
            fee_total_from_charges += c_total
            if include_items:
                breakdown_lines.append(
                    InvoiceLineItem(
                        line_type="tax",
                        description=c_desc,
                        quantity=1.0,
                        unit_price=c_total,
                        total=c_total,
                        metadata={"charge_id": charge.id, "tipo": "fee"},
                    )
                )
            continue

        # Normal charges
        charges_total += c_total

        if include_items:
            breakdown_lines.append(
                InvoiceLineItem(
                    line_type="charge",
                    description=c_desc,
                    quantity=float(c_qty),
                    unit_price=float(c_unit),
                    total=float(c_total),
                    metadata={
                        "charge_id": charge.id,
                        "tipo": c_type,
                        "created_at": (charge.created_at.isoformat() if getattr(charge, "created_at", None) else None),
                    },
                )
            )

        if c_total == 0:
            warnings.append(
                InvoiceWarning(
                    code="UNPRICED_CHARGE",
                    message=f"Cargo sin precio: {c_desc}",
                    severity="warning",
                )
            )

    # --- Impuestos (con soporte para overrides) ---
    taxes_total = 0.0

    # 1) Fees explícitos
    taxes_total += fee_total_from_charges

    # 2) IVA automático (con soporte para override)
    should_apply_auto_iva = True
    if any((getattr(c, "tipo", None) == "fee" and "iva" in (getattr(c, "descripcion", "") or "").lower()) for c in (stay.charges or [])):
        should_apply_auto_iva = False

    # Determinar modo de impuesto
    iva_rate = 0.0
    iva_alojamiento = 0.0
    tax_override_applied = False
    tax_override_reason = None

    if tax_override_mode:
        tax_override_applied = True
        if tax_override_mode.lower() == "exento":
            iva_rate = 0.0
            iva_alojamiento = 0.0
            tax_override_reason = "Operación exenta"
        elif tax_override_mode.lower() == "normal":
            iva_rate = IVA_RATE_DEFAULT
            iva_alojamiento = (room_subtotal * iva_rate) if should_apply_auto_iva else 0.0
            tax_override_reason = "IVA normal 21%"
        elif tax_override_mode.lower() == "custom" and tax_override_value is not None:
            iva_alojamiento = _safe_float(tax_override_value, 0.0)
            tax_override_reason = f"Impuesto personalizado: ${iva_alojamiento:.2f}"
    else:
        # Comportamiento por defecto
        iva_rate = IVA_RATE_DEFAULT
        iva_alojamiento = (room_subtotal * iva_rate) if should_apply_auto_iva else 0.0

    taxes_total += iva_alojamiento

    if include_items and iva_alojamiento > 0:
        breakdown_lines.append(
            InvoiceLineItem(
                line_type="tax",
                description=f"{'IVA' if not tax_override_applied else 'Impuesto'} {int((iva_alojamiento / room_subtotal * 100) if room_subtotal > 0 else 0)}% sobre alojamiento",
                quantity=1.0,
                unit_price=iva_alojamiento,
                total=iva_alojamiento,
                metadata={
                    "tax_type": "iva",
                    "rate": iva_rate,
                    "base": room_subtotal,
                    "override_applied": tax_override_applied,
                    "override_reason": tax_override_reason,
                },
            )
        )

    # --- Descuentos (con soporte para override en %) ---
    discounts_total = discount_total_from_charges
    discount_override_applied = False
    discount_override_amount = 0.0

    if discount_override_pct is not None and discount_override_pct > 0:
        discount_override_applied = True
        # Calcular descuento en % sobre el subtotal
        discount_override_amount = room_subtotal * (discount_override_pct / 100.0)
        discounts_total += discount_override_amount

        if include_items:
            breakdown_lines.append(
                InvoiceLineItem(
                    line_type="discount",
                    description=f"Descuento {discount_override_pct}% sobre alojamiento",
                    quantity=1.0,
                    unit_price=-discount_override_amount,
                    total=-discount_override_amount,
                    metadata={
                        "discount_type": "percentage_override",
                        "percentage": discount_override_pct,
                        "base": room_subtotal,
                    },
                )
            )

    # --- Total ---
    grand_total = room_subtotal + charges_total + taxes_total - discounts_total

    # --- Pagos ---
    payments_total = 0.0
    payments_list: List[Dict[str, Any]] = []

    for pago in (stay.payments or []):
        if getattr(pago, "es_reverso", False):
            continue

        amount = _safe_float(getattr(pago, "monto", None), 0.0)
        if amount <= 0:
            continue

        payments_total += amount

        payments_list.append(
            {
                "id": pago.id,
                "monto": amount,
                "metodo": getattr(pago, "metodo", "") or "desconocido",
                "referencia": getattr(pago, "referencia", "") or "",
                "timestamp": (pago.timestamp.isoformat() if getattr(pago, "timestamp", None) else None),
                "usuario": getattr(pago, "usuario", None),
            }
        )

        if include_items:
            breakdown_lines.append(
                InvoiceLineItem(
                    line_type="payment",
                    description=f"Pago ({getattr(pago, 'metodo', 'desconocido')})",
                    quantity=1.0,
                    unit_price=-amount,
                    total=-amount,
                    metadata={"payment_id": pago.id, "metodo": getattr(pago, "metodo", None), "referencia": getattr(pago, "referencia", None)},
                )
            )

    balance = grand_total - payments_total

    # =====================================================================
    # 7) WARNINGS (UX)
    # =====================================================================
    if rate_source == "missing" or nightly_rate <= 0:
        warnings.append(
            InvoiceWarning(
                code="MISSING_RATE",
                message=f"No hay tarifa configurada para {invoice_room.room_type_name}",
                severity="error",
            )
        )

    if tarifa_override_applied:
        warnings.append(
            InvoiceWarning(
                code="TARIFA_OVERRIDE",
                message=f"Tarifa modificada: ${nightly_rate:.2f}/noche",
                severity="info",
            )
        )

    if override_applied:
        warnings.append(
            InvoiceWarning(
                code="NIGHTS_OVERRIDE",
                message=f"Override de noches aplicado: {final_nights} (calculado: {calculated_nights})",
                severity="info",
            )
        )

    if discount_override_applied:
        warnings.append(
            InvoiceWarning(
                code="DISCOUNT_OVERRIDE",
                message=f"Descuento aplicado: {discount_override_pct}% = ${discount_override_amount:.2f}",
                severity="info",
            )
        )

    if tax_override_applied:
        warnings.append(
            InvoiceWarning(
                code="TAX_OVERRIDE",
                message=f"Régimen de impuesto modificado: {tax_override_reason}",
                severity="info",
            )
        )

    if planned_nights != calculated_nights and planned_nights > 0:
        warnings.append(
            InvoiceWarning(
                code="NIGHTS_DIFFER",
                message=f"Noches calculadas ({calculated_nights}) difieren de planificadas ({planned_nights})",
                severity="warning",
            )
        )

    if not readonly and raw_diff == 0:
        warnings.append(
            InvoiceWarning(
                code="SAME_DAY_CANDIDATE",
                message="Checkout candidato el mismo día del check-in. Se sugiere cobrar mínimo 1 noche.",
                severity="info",
            )
        )

    if balance > 0:
        warnings.append(
            InvoiceWarning(
                code="BALANCE_DUE",
                message=f"Saldo pendiente: {balance:.2f}",
                severity="warning",
            )
        )
    elif balance < 0:
        warnings.append(
            InvoiceWarning(
                code="OVERPAYMENT",
                message=f"Sobrepago: {abs(balance):.2f}",
                severity="info",
            )
        )

    if payments_total > grand_total and grand_total > 0:
        warnings.append(
            InvoiceWarning(
                code="PAYMENTS_EXCEED_TOTAL",
                message=f"Los pagos ({payments_total:.2f}) superan el total ({grand_total:.2f})",
                severity="warning",
            )
        )

    # =====================================================================
    # 8) RESPUESTA
    # =====================================================================
    totals = InvoiceTotals(
        room_subtotal=round(room_subtotal, 2),
        charges_total=round(charges_total, 2),
        taxes_total=round(taxes_total, 2),
        discounts_total=round(discounts_total, 2),
        grand_total=round(grand_total, 2),
        payments_total=round(payments_total, 2),
        balance=round(balance, 2),
    )

    return InvoicePreviewResponse(
        stay_id=stay_id,
        reservation_id=reservation.id,
        cliente_nombre=cliente_nombre,
        currency="ARS",
        period=invoice_period,
        nights=invoice_nights,
        room=invoice_room,
        breakdown_lines=breakdown_lines if include_items else [],
        totals=totals,
        payments=payments_list if include_items else [],
        warnings=warnings,
        readonly=readonly,
        generated_at=datetime.utcnow().isoformat(),
    )


# ========================================================================
# ENDPOINTS: PRODUCTOS/SERVICIOS (opcional)
# ========================================================================

@router.get("/productos-servicios")
def list_productos_servicios(db: Session = Depends(get_db)):
    """
    Listar productos y servicios disponibles (placeholder)
    """
    # Esto debería venir de una tabla Productos/Servicios
    # Por ahora devolvemos ejemplos hardcoded
    return [
        {"id": 1, "tipo": "product", "nombre": "Minibar - Agua", "precio": 5.00},
        {"id": 2, "tipo": "product", "nombre": "Minibar - Gaseosa", "precio": 8.00},
        {"id": 3, "tipo": "service", "nombre": "Lavandería", "precio": 50.00},
        {"id": 4, "tipo": "service", "nombre": "Desayuno", "precio": 25.00},
    ]
