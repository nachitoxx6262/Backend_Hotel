"""
PMS BACKEND - ENDPOINTS PROFESIONALES PARA SCHEDULER
Diseño Senior: Single Source of Truth, sin duplicidades, sin hacks
"""

from datetime import datetime, date, timedelta
from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
from pydantic import BaseModel, Field

from database.conexion import get_db
from models.core import (
    Reservation, ReservationRoom, ReservationGuest, Room, RoomType,
    Stay, StayRoomOccupancy, StayCharge, StayPayment,
    DailyRate, RatePlan, HKCycle, HKTemplate, AuditEvent, Cliente, Empresa
)
from utils.logging_utils import log_event


router = APIRouter(prefix="/api/pms", tags=["PMS Professional"])


# ========================================================================
# 🧩 SCHEMAS
# ========================================================================

class BlockUI(BaseModel):
    """Bloque para renderizar en scheduler (Reserva o Estadía)"""
    id: str  # "res-55" o "stay-90-occ-12"
    kind: str  # "reservation" | "stay"
    reservation_id: Optional[int] = None
    stay_id: Optional[int] = None
    occupancy_id: Optional[int] = None
    room_id: int
    fecha_checkin: str  # ISO date (para reservas)
    fecha_checkout: str  # ISO date (para reservas)
    desde: Optional[str] = None  # ISO date (para stays)
    hasta: Optional[str] = None  # ISO date (para stays)
    guest_label: str
    ui_status: str  # "reservada" | "ocupada" | "pendiente_checkout" | "finalizada"
    can_move: bool
    can_resize: bool
    can_checkin: Optional[bool] = None
    can_checkout: Optional[bool] = None


class RoomUI(BaseModel):
    """Habitación para scheduler"""
    id: int
    numero: str
    room_type_name: str
    estado: str


class CalendarResponse(BaseModel):
    """Response de calendario - TODO para renderizar scheduler"""
    from_date: str
    to_date: str
    rooms: List[RoomUI]
    blocks: List[BlockUI]
    conflicts: List[dict] = []


class MoveBlockRequest(BaseModel):
    """Mover o redimensionar bloque"""
    kind: str  # "reservation" | "stay"
    reservation_id: Optional[int] = None
    stay_id: Optional[int] = None
    occupancy_id: Optional[int] = None  # requerido para move de stays
    room_id: int
    fecha_checkin: Optional[str] = None  # Para reservation/resize
    fecha_checkout: Optional[str] = None
    desde: Optional[str] = None  # Para stay (ISO datetime)
    hasta: Optional[str] = None
    motivo: str = "user_action"


class CreateReservationRequest(BaseModel):
    """QuickBook: creación rápida"""
    nombre_temporal: str
    fecha_checkin: str  # YYYY-MM-DD
    fecha_checkout: str
    room_ids: List[int] = Field(..., min_items=1)
    estado: str = "confirmada"
    cliente_id: Optional[int] = None
    empresa_id: Optional[int] = None
    notas: Optional[str] = None


class CheckinPreviewResponse(BaseModel):
    """Preview para el wizard de check-in"""
    reservation_id: int
    room: dict
    fecha_checkin: str
    fecha_checkout: str
    nights_planned: int
    deposit_suggestion: dict


class CheckinRequest(BaseModel):
    """Confirmar check-in → crear Stay"""
    notas: Optional[str] = None
    huespedes: List[dict]  # [{nombre, apellido, documento, rol}]
    deposito: Optional[dict] = None  # {monto, metodo}


class AddChargeRequest(BaseModel):
    """Agregar consumo"""
    tipo: str  # "product" | "service" | "minibar" | "fee"
    descripcion: str
    cantidad: float = 1.0
    monto_unitario: float
    monto_total: Optional[float] = None


class PaymentRequest(BaseModel):
    """Registrar pago"""
    monto: float
    metodo: str  # "efectivo" | "tarjeta" | "transferencia"
    ref: Optional[str] = None


class InvoicePreviewResponse(BaseModel):
    """Factura en preview - TODO para checkout"""
    nights: dict  # {planned, to_charge}
    pricing: dict
    charges_total: float
    payments_total: float
    total: float
    balance: float


class CheckoutRequest(BaseModel):
    """Confirmar checkout"""
    checkout_real: Optional[str] = None  # ISO datetime
    allow_close_with_debt: bool = False
    notas: Optional[str] = None
    housekeeping: bool = True


# ========================================================================
# 1️⃣ CALENDARIO (CORE)
# ========================================================================

def _parse_date(date_str: str) -> date:
    """Convertir string ISO a date"""
    if isinstance(date_str, str):
        return datetime.fromisoformat(date_str.split('T')[0]).date()
    return date_str


def _format_date(d: date) -> str:
    """Convertir date a ISO string"""
    return d.isoformat()


def _can_move_block(block_kind: str, block_status: str) -> bool:
    """Validar si un bloque puede moverse"""
    if block_kind == "reservation":
        return block_status not in ["cancelada", "no_show", "convertida"]
    elif block_kind == "stay":
        return block_status not in ["cerrada"]
    return False


def _can_resize_block(block_kind: str, block_status: str) -> bool:
    """Validar si un bloque puede redimensionarse"""
    return _can_move_block(block_kind, block_status)


def _get_ui_status(kind: str, state: str) -> str:
    """Mapear estado DB a estado UI"""
    if kind == "reservation":
        return state if state in ["confirmada", "cancelada"] else "reservada"
    elif kind == "stay":
        if state == "pendiente_checkin":
            return "pendiente_checkin"
        elif state == "ocupada":
            return "ocupada"
        elif state == "pendiente_checkout":
            return "pendiente_checkout"
        else:
            return "finalizada"
    return state


def _build_blocks(db: Session, from_date: date, to_date: date) -> List[BlockUI]:
    """Construir lista de bloques (reservas + stays)"""
    blocks = []

    # 1. Reservas confirmadas/draft
    reservations = (
        db.query(Reservation)
        .options(
            joinedload(Reservation.rooms).joinedload(ReservationRoom.room),
            joinedload(Reservation.cliente),
            joinedload(Reservation.empresa)
        )
        .filter(
            Reservation.estado.in_(["confirmada", "draft", "convertida"]),
            Reservation.fecha_checkin < to_date,
            Reservation.fecha_checkout > from_date
        )
        .all()
    )

    for res in reservations:
        for res_room in res.rooms:
            guest_label = None
            if res.cliente:
                guest_label = f"{res.cliente.nombre} {res.cliente.apellido}"
            elif res.empresa:
                guest_label = res.empresa.nombre
            else:
                guest_label = res.nombre_temporal

            ui_status = _get_ui_status("reservation", res.estado)
            can_move = _can_move_block("reservation", res.estado)
            can_resize = _can_resize_block("reservation", res.estado)

            blocks.append(BlockUI(
                id=f"res-{res.id}",
                kind="reservation",
                reservation_id=res.id,
                room_id=res_room.room.id,
                fecha_checkin=_format_date(res.fecha_checkin),
                fecha_checkout=_format_date(res.fecha_checkout),
                guest_label=guest_label or "Sin nombre",
                ui_status=ui_status,
                can_move=can_move,
                can_resize=can_resize,
                can_checkin=(res.estado in ["confirmada", "draft"] and not res.deleted)
            ))

    # 2. Stays activos (ocupaciones reales)
    stays = (
        db.query(Stay)
        .options(
            joinedload(Stay.occupancies).joinedload(StayRoomOccupancy.room),
            joinedload(Stay.reservation).joinedload(Reservation.cliente),
            joinedload(Stay.reservation).joinedload(Reservation.empresa)
        )
        .filter(
            Stay.estado.in_(["pendiente_checkin", "ocupada", "pendiente_checkout"])
        )
        .all()
    )

    for stay in stays:
        res = stay.reservation
        guest_label = None
        if res.cliente:
            guest_label = f"{res.cliente.nombre} {res.cliente.apellido}"
        elif res.empresa:
            guest_label = res.empresa.nombre
        else:
            guest_label = res.nombre_temporal

        for occ in stay.occupancies:
            occ_desde = occ.desde.date() if isinstance(occ.desde, datetime) else occ.desde
            occ_hasta = occ.hasta.date() if occ.hasta and isinstance(occ.hasta, datetime) else occ.hasta

            # Filtrar por rango visible
            if not (occ_desde < to_date and (not occ_hasta or occ_hasta > from_date)):
                continue

            ui_status = _get_ui_status("stay", stay.estado)
            can_move = _can_move_block("stay", stay.estado)
            can_resize = _can_resize_block("stay", stay.estado)

            blocks.append(BlockUI(
                id=f"stay-{stay.id}-occ-{occ.id}",
                kind="stay",
                stay_id=stay.id,
                occupancy_id=occ.id,
                room_id=occ.room.id,
                desde=_format_date(occ_desde),
                hasta=_format_date(occ_hasta) if occ_hasta else _format_date(to_date),
                guest_label=guest_label or "Sin nombre",
                ui_status=ui_status,
                can_move=can_move,
                can_resize=can_resize,
                can_checkout=(stay.estado in ["ocupada", "pendiente_checkout"])
            ))

    return blocks


@router.get("/calendar", response_model=CalendarResponse)
def get_calendar(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    """
    🗓️ CALENDARIO: TODO para renderizar scheduler
    
    - Bloque = Reservation o Stay
    - Valida can_move, can_resize automáticamente
    - Frontend NO calcula, solo renderiza
    """
    desde = _parse_date(from_date)
    hasta = _parse_date(to_date)

    if hasta <= desde:
        raise HTTPException(400, "Rango de fechas inválido")

    # Habitaciones activas
    rooms = (
        db.query(Room)
        .options(joinedload(Room.tipo))
        .filter(Room.activo == True)
        .all()
    )

    rooms_ui = [
        RoomUI(
            id=r.id,
            numero=r.numero,
            room_type_name=r.tipo.nombre if r.tipo else "N/A",
            estado=r.estado_operativo
        )
        for r in rooms
    ]

    # Bloques (reservas + stays)
    blocks = _build_blocks(db, desde, hasta)

    log_event("calendar", "usuario", "Ver calendario", f"{from_date} a {to_date}")

    return CalendarResponse(
        from_date=from_date,
        to_date=to_date,
        rooms=rooms_ui,
        blocks=blocks
    )


# ========================================================================
# 2️⃣ MOVER / REDIMENSIONAR BLOQUES (ÚNICO ENDPOINT)
# ========================================================================

def _check_availability(
    db: Session,
    room_id: int,
    from_date: date,
    to_date: date,
    exclude_reservation_id: Optional[int] = None,
    exclude_occupancy_id: Optional[int] = None
) -> bool:
    """Verificar disponibilidad sin solapamientos"""

    # Verificar conflicto con reservas confirmadas
    conflicting_res = (
        db.query(Reservation)
        .join(ReservationRoom)
        .filter(
            ReservationRoom.room_id == room_id,
            Reservation.estado.in_(["confirmada", "convertida"]),
            Reservation.fecha_checkin < to_date,
            Reservation.fecha_checkout > from_date,
            Reservation.id != (exclude_reservation_id or -1)
        )
        .first()
    )

    if conflicting_res:
        return False

    # Verificar conflicto con ocupaciones activas
    conflicting_occ = (
        db.query(StayRoomOccupancy)
        .join(Stay)
        .filter(
            StayRoomOccupancy.room_id == room_id,
            Stay.estado.in_(["pendiente_checkin", "ocupada", "pendiente_checkout"]),
            StayRoomOccupancy.desde < to_date,
            or_(
                StayRoomOccupancy.hasta.is_(None),
                StayRoomOccupancy.hasta > from_date
            ),
            StayRoomOccupancy.id != (exclude_occupancy_id or -1)
        )
        .first()
    )

    if conflicting_occ:
        return False

    return True


@router.patch("/calendar/blocks/move")
def move_block(
    req: MoveBlockRequest,
    db: Session = Depends(get_db)
):
    """
    🔄 MOVER / REDIMENSIONAR BLOQUE
    
    Kind:
    - "reservation": mover reserva confirmada
    - "stay": mover ocupación real
    
    El backend decide qué es válido. Frontend NO valida.
    """

    if req.kind == "reservation":
        # ===== MOVER RESERVA =====
        if not req.reservation_id:
            raise HTTPException(400, "reservation_id requerido")

        res = db.query(Reservation).filter(Reservation.id == req.reservation_id).first()
        if not res:
            raise HTTPException(404, "Reserva no encontrada")

        if not _can_move_block("reservation", res.estado):
            raise HTTPException(409, f"Reserva en estado {res.estado} no puede moverse")

        # Parsear nuevas fechas
        nueva_checkin = _parse_date(req.fecha_checkin) if req.fecha_checkin else res.fecha_checkin
        nueva_checkout = _parse_date(req.fecha_checkout) if req.fecha_checkout else res.fecha_checkout

        if nueva_checkout <= nueva_checkin:
            raise HTTPException(400, "Fechas inválidas")

        # Validar disponibilidad para TODAS las habitaciones de la reserva
        for res_room in res.rooms:
            if not _check_availability(
                db, res_room.room_id, nueva_checkin, nueva_checkout,
                exclude_reservation_id=req.reservation_id
            ):
                raise HTTPException(409, f"Habitación no disponible en nuevas fechas")

        # Actualizar fechas
        res.fecha_checkin = nueva_checkin
        res.fecha_checkout = nueva_checkout
        res.updated_at = datetime.utcnow()

        # Si cambió de habitación (solo primera)
        if req.room_id and res.rooms and res.rooms[0].room_id != req.room_id:
            res.rooms[0].room_id = req.room_id

        audit = AuditEvent(
            entity_type="reservation",
            entity_id=res.id,
            action="MOVE",
            usuario="sistema",
            descripcion=f"Movida a {nueva_checkin} - {nueva_checkout}",
            payload={"room_id": req.room_id, "motivo": req.motivo}
        )
        db.add(audit)
        db.commit()

        log_event("calendar", "usuario", "Mover reserva", f"id={req.reservation_id}")

        return {"success": True, "reservation_id": res.id}

    elif req.kind == "stay":
        # ===== MOVER OCUPACIÓN REAL =====
        if not req.occupancy_id:
            raise HTTPException(400, "occupancy_id requerido para stay")

        occ = db.query(StayRoomOccupancy).filter(StayRoomOccupancy.id == req.occupancy_id).first()
        if not occ:
            raise HTTPException(404, "Ocupación no encontrada")

        stay = occ.stay
        if not _can_move_block("stay", stay.estado):
            raise HTTPException(409, f"Stay en estado {stay.estado} no puede moverse")

        # Si cambió de habitación: cerrar ocupación anterior, crear nueva
        if occ.room_id != req.room_id:
            if not _check_availability(db, req.room_id, occ.desde, occ.hasta or datetime.utcnow(), exclude_occupancy_id=req.occupancy_id):
                raise HTTPException(409, "Habitación destino no disponible")

            # Cerrar ocupación actual
            occ.hasta = datetime.utcnow()

            # Crear nueva
            nueva_occ = StayRoomOccupancy(
                stay_id=stay.id,
                room_id=req.room_id,
                desde=datetime.utcnow(),
                hasta=None,
                motivo=f"Move: {req.motivo}",
                creado_por="sistema"
            )
            db.add(nueva_occ)

            # Actualizar estado de habitaciones
            old_room = db.query(Room).filter(Room.id == occ.room_id).first()
            if old_room:
                old_room.estado_operativo = "disponible"

            new_room = db.query(Room).filter(Room.id == req.room_id).first()
            if new_room:
                new_room.estado_operativo = "ocupada"

        # Resize (cambiar desde/hasta)
        if req.desde:
            occ.desde = datetime.fromisoformat(req.desde)
        if req.hasta:
            occ.hasta = datetime.fromisoformat(req.hasta)

        audit = AuditEvent(
            entity_type="stay",
            entity_id=stay.id,
            action="MOVE",
            usuario="sistema",
            descripcion=f"Moved to room {req.room_id}",
            payload={"occupancy_id": req.occupancy_id}
        )
        db.add(audit)
        db.commit()

        log_event("calendar", "usuario", "Mover stay", f"id={stay.id}")

        return {"success": True, "stay_id": stay.id}

    else:
        raise HTTPException(400, f"kind inválido: {req.kind}")


# ========================================================================
# 3️⃣ RESERVAS
# ========================================================================

@router.post("/reservations", status_code=status.HTTP_201_CREATED)
def create_reservation(
    req: CreateReservationRequest,
    db: Session = Depends(get_db)
):
    """
    Crear reserva (QuickBook)
    """
    desde = _parse_date(req.fecha_checkin)
    hasta = _parse_date(req.fecha_checkout)

    if hasta <= desde:
        raise HTTPException(400, "Fechas inválidas")

    # Verificar habitaciones
    rooms = db.query(Room).filter(Room.id.in_(req.room_ids)).all()
    if len(rooms) != len(req.room_ids):
        raise HTTPException(404, "Una o más habitaciones no encontradas")

    # Verificar disponibilidad
    for room in rooms:
        if not _check_availability(db, room.id, desde, hasta):
            raise HTTPException(409, f"Habitación {room.numero} no disponible")

    # Crear reserva
    res = Reservation(
        cliente_id=req.cliente_id,
        empresa_id=req.empresa_id,
        nombre_temporal=req.nombre_temporal,
        fecha_checkin=desde,
        fecha_checkout=hasta,
        estado=req.estado,
        notas=req.notas
    )
    db.add(res)
    db.flush()

    # Asignar habitaciones
    for room_id in req.room_ids:
        res_room = ReservationRoom(
            reservation_id=res.id,
            room_id=room_id
        )
        db.add(res_room)

    audit = AuditEvent(
        entity_type="reservation",
        entity_id=res.id,
        action="CREATE",
        usuario="sistema",
        descripcion=f"Reserva creada {desde} - {hasta}"
    )
    db.add(audit)

    db.commit()
    db.refresh(res)

    log_event("reservations", "usuario", "Crear reserva", f"id={res.id}")

    return {
        "id": res.id,
        "estado": res.estado,
        "fecha_checkin": _format_date(res.fecha_checkin),
        "fecha_checkout": _format_date(res.fecha_checkout)
    }


@router.get("/reservations/{id}")
def get_reservation(
    id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """Detalle de reserva"""
    res = db.query(Reservation).filter(Reservation.id == id).first()
    if not res:
        raise HTTPException(404, "Reserva no encontrada")

    return {
        "id": res.id,
        "estado": res.estado,
        "fecha_checkin": _format_date(res.fecha_checkin),
        "fecha_checkout": _format_date(res.fecha_checkout),
        "nombre": res.nombre_temporal,
        "rooms": [{"id": rr.room_id, "numero": rr.room.numero} for rr in res.rooms]
    }


# ========================================================================
# 4️⃣ CHECK-IN (WIZARD)
# ========================================================================

@router.get("/reservations/{id}/checkin-preview", response_model=CheckinPreviewResponse)
def checkin_preview(
    id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """
    Preview para el wizard de check-in
    """
    res = db.query(Reservation).filter(Reservation.id == id).first()
    if not res:
        raise HTTPException(404, "Reserva no encontrada")

    if res.estado not in ["confirmada", "draft"]:
        raise HTTPException(409, f"Reserva en estado {res.estado} no puede hacer check-in")

    nights = (res.fecha_checkout - res.fecha_checkin).days
    room = res.rooms[0].room if res.rooms else None

    return CheckinPreviewResponse(
        reservation_id=res.id,
        room={"id": room.id, "numero": room.numero} if room else {},
        fecha_checkin=_format_date(res.fecha_checkin),
        fecha_checkout=_format_date(res.fecha_checkout),
        nights_planned=nights,
        deposit_suggestion={"monto": 0, "metodo": "efectivo"}
    )


@router.post("/stays/from-reservation/{id}/checkin", status_code=status.HTTP_201_CREATED)
def checkin_from_reservation(
    id: int = Path(..., gt=0),
    req: CheckinRequest = ...,
    db: Session = Depends(get_db)
):
    """
    ✅ CHECK-IN: Convertir reserva → estadía
    """
    res = db.query(Reservation).options(
        joinedload(Reservation.rooms),
        joinedload(Reservation.guests)
    ).filter(Reservation.id == id).first()

    if not res:
        raise HTTPException(404, "Reserva no encontrada")

    if res.estado not in ["confirmada", "draft"]:
        raise HTTPException(409, f"Reserva no puede hacer check-in en estado {res.estado}")

    # Verificar si ya existe stay
    existing_stay = db.query(Stay).filter(Stay.reservation_id == id).first()
    if existing_stay:
        raise HTTPException(409, "Ya existe estadía para esta reserva")

    # Crear Stay
    stay = Stay(
        reservation_id=res.id,
        estado="ocupada",
        checkin_real=datetime.utcnow(),
        notas_internas=req.notas
    )
    db.add(stay)
    db.flush()

    # Crear ocupaciones
    for res_room in res.rooms:
        occ = StayRoomOccupancy(
            stay_id=stay.id,
            room_id=res_room.room_id,
            desde=datetime.utcnow(),
            hasta=None,
            motivo="Check-in inicial",
            creado_por="sistema"
        )
        db.add(occ)

        # Actualizar estado habitación
        room = res_room.room
        room.estado_operativo = "ocupada"

    # Marcar reserva como convertida
    res.estado = "convertida"

    # Registrar huéspedes
    for huesped_data in req.huespedes:
        guest = ReservationGuest(
            reservation_id=res.id,
            rol=huesped_data.get("rol", "adulto")
        )
        db.add(guest)

    # Registrar depósito si hay
    if req.deposito and req.deposito.get("monto"):
        pago = StayPayment(
            stay_id=stay.id,
            monto=Decimal(str(req.deposito["monto"])),
            metodo=req.deposito.get("metodo", "efectivo"),
            usuario="sistema",
            notas="Depósito check-in"
        )
        db.add(pago)

    audit = AuditEvent(
        entity_type="stay",
        entity_id=stay.id,
        action="CHECKIN",
        usuario="sistema",
        descripcion=f"Check-in desde reserva {id}"
    )
    db.add(audit)

    db.commit()
    db.refresh(stay)

    log_event("stays", "usuario", "Check-in", f"stay_id={stay.id}")

    return {
        "id": stay.id,
        "reservation_id": res.id,
        "estado": stay.estado,
        "checkin_real": stay.checkin_real.isoformat()
    }


# ========================================================================
# 5️⃣ CONSUMOS (CHARGES)
# ========================================================================

@router.get("/stays/{id}/charges")
def list_charges(
    id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """Listar consumos de una estadía"""
    stay = db.query(Stay).filter(Stay.id == id).first()
    if not stay:
        raise HTTPException(404, "Estadía no encontrada")

    charges = db.query(StayCharge).filter(StayCharge.stay_id == id).all()

    return {
        "stay_id": id,
        "charges": [
            {
                "id": c.id,
                "tipo": c.tipo,
                "descripcion": c.descripcion,
                "cantidad": float(c.cantidad),
                "monto_unitario": float(c.monto_unitario),
                "monto_total": float(c.monto_total)
            }
            for c in charges
        ],
        "total": float(sum(c.monto_total for c in charges))
    }


@router.post("/stays/{id}/charges", status_code=status.HTTP_201_CREATED)
def add_charge(
    id: int = Path(..., gt=0),
    req: AddChargeRequest = ...,
    db: Session = Depends(get_db)
):
    """Agregar consumo"""
    stay = db.query(Stay).filter(Stay.id == id).first()
    if not stay:
        raise HTTPException(404, "Estadía no encontrada")

    if stay.estado == "cerrada":
        raise HTTPException(409, "No se pueden agregar cargos a estadía cerrada")

    monto_total = req.monto_total if req.monto_total else (req.cantidad * req.monto_unitario)

    charge = StayCharge(
        stay_id=id,
        tipo=req.tipo,
        descripcion=req.descripcion,
        cantidad=Decimal(str(req.cantidad)),
        monto_unitario=Decimal(str(req.monto_unitario)),
        monto_total=Decimal(str(monto_total)),
        creado_por="sistema"
    )
    db.add(charge)

    audit = AuditEvent(
        entity_type="stay",
        entity_id=id,
        action="ADD_CHARGE",
        usuario="sistema",
        descripcion=f"Cargo: {req.descripcion}",
        payload={"monto": float(monto_total)}
    )
    db.add(audit)

    db.commit()
    db.refresh(charge)

    log_event("stays", "usuario", "Agregar cargo", f"stay_id={id} monto={monto_total}")

    return {
        "id": charge.id,
        "monto_total": float(charge.monto_total)
    }


# ========================================================================
# 6️⃣ PAGOS
# ========================================================================

@router.get("/stays/{id}/payments")
def list_payments(
    id: int = Path(..., gt=0),
    db: Session = Depends(get_db)
):
    """Listar pagos de una estadía"""
    stay = db.query(Stay).filter(Stay.id == id).first()
    if not stay:
        raise HTTPException(404, "Estadía no encontrada")

    payments = db.query(StayPayment).filter(StayPayment.stay_id == id).all()

    return {
        "stay_id": id,
        "payments": [
            {
                "id": p.id,
                "monto": float(p.monto),
                "metodo": p.metodo,
                "ref": p.referencia,
                "timestamp": p.timestamp.isoformat()
            }
            for p in payments
        ],
        "total": float(sum(p.monto for p in payments if not p.es_reverso))
    }


@router.post("/stays/{id}/payments", status_code=status.HTTP_201_CREATED)
def add_payment(
    id: int = Path(..., gt=0),
    req: PaymentRequest = ...,
    db: Session = Depends(get_db)
):
    """Registrar pago"""
    stay = db.query(Stay).filter(Stay.id == id).first()
    if not stay:
        raise HTTPException(404, "Estadía no encontrada")

    payment = StayPayment(
        stay_id=id,
        monto=Decimal(str(req.monto)),
        metodo=req.metodo,
        referencia=req.ref,
        usuario="sistema",
        es_reverso=False
    )
    db.add(payment)

    audit = AuditEvent(
        entity_type="stay",
        entity_id=id,
        action="PAYMENT",
        usuario="sistema",
        descripcion=f"Pago {req.metodo} {req.monto}",
        payload={"ref": req.ref}
    )
    db.add(audit)

    db.commit()

    log_event("stays", "usuario", "Registrar pago", f"stay_id={id} monto={req.monto}")

    return {
        "id": payment.id,
        "monto": float(payment.monto),
        "metodo": payment.metodo
    }


# ========================================================================
# 7️⃣ FACTURA (CHECKOUT PREVIEW)
# ========================================================================

@router.get("/stays/{id}/invoice-preview", response_model=InvoicePreviewResponse)
def invoice_preview(
    id: int = Path(..., gt=0),
    nights_to_charge: int = Query(None),
    nightly_rate: float = Query(None),
    db: Session = Depends(get_db)
):
    """
    SINGLE SOURCE OF TRUTH: Backend calcula TODO
    
    Frontend pasa sugerencias, backend valida y retorna valores finales.
    """
    stay = db.query(Stay).options(
        joinedload(Stay.charges),
        joinedload(Stay.payments)
    ).filter(Stay.id == id).first()

    if not stay:
        raise HTTPException(404, "Estadía no encontrada")

    # Calcular noches
    nights_planned = (stay.reservation.fecha_checkout - stay.reservation.fecha_checkin).days
    nights_charge = nights_to_charge if nights_to_charge else nights_planned

    # Tarifa por noche (sugerencia del frontend, validada)
    rate = nightly_rate if nightly_rate else 20000  # Default

    # Subtotal noches
    subtotal_noches = Decimal(str(nights_charge * rate))

    # Cargos (consumos)
    charges_total = sum(c.monto_total for c in stay.charges)

    # Taxes & discounts (hardcoded por ahora, luego configurables)
    tax_pct = 0.21  # IVA 21%
    taxes = (subtotal_noches + charges_total) * Decimal(str(tax_pct))

    # Total
    total = subtotal_noches + charges_total + taxes

    # Pagos
    payments_total = sum(p.monto for p in stay.payments if not p.es_reverso)

    # Saldo
    balance = total - payments_total

    return InvoicePreviewResponse(
        nights={
            "planned": nights_planned,
            "to_charge": nights_charge
        },
        pricing={
            "nightly_rate": float(rate),
            "subtotal": float(subtotal_noches),
            "taxes": [{"name": "IVA 21%", "amount": float(taxes)}],
            "discounts": []
        },
        charges_total=float(charges_total),
        payments_total=float(payments_total),
        total=float(total),
        balance=float(balance)
    )


# ========================================================================
# 8️⃣ CHECKOUT (CIERRE DEFINITIVO)
# ========================================================================

@router.post("/stays/{id}/checkout")
def checkout_stay(
    id: int = Path(..., gt=0),
    req: CheckoutRequest = ...,
    db: Session = Depends(get_db)
):
    """
    🚪 CHECK-OUT: Cierre definitivo + housekeeping automático
    """
    stay = db.query(Stay).options(
        joinedload(Stay.occupancies),
        joinedload(Stay.charges),
        joinedload(Stay.payments)
    ).filter(Stay.id == id).first()

    if not stay:
        raise HTTPException(404, "Estadía no encontrada")

    if stay.estado not in ["ocupada", "pendiente_checkout"]:
        raise HTTPException(409, f"No puede hacer checkout en estado {stay.estado}")

    # Validar si puede cerrar con deuda
    charges_total = sum(c.monto_total for c in stay.charges)
    payments_total = sum(p.monto for p in stay.payments if not p.es_reverso)
    balance = charges_total - payments_total

    if balance > 0 and not req.allow_close_with_debt:
        raise HTTPException(409, f"Saldo pendiente: {balance}. Habilita cerrar con deuda.")

    # Cerrar ocupaciones
    ahora = datetime.utcnow()
    for occ in stay.occupancies:
        if not occ.hasta:
            occ.hasta = ahora

            # Marcar habitación como disponible (o "limpieza" si housekeeping)
            room = occ.room
            room.estado_operativo = "limpieza" if req.housekeeping else "disponible"

    # Actualizar stay
    stay.estado = "cerrada"
    stay.checkout_real = datetime.fromisoformat(req.checkout_real) if req.checkout_real else ahora
    if req.notas:
        stay.notas_internas = (stay.notas_internas or "") + "\n" + req.notas
    stay.updated_at = ahora

    # Crear ciclo de housekeeping si se solicita
    if req.housekeeping and stay.occupancies:
        primary_room = stay.occupancies[0].room
        hk_cycle = HKCycle(
            room_id=primary_room.id,
            stay_id=stay.id,
            estado="pending",
            motivo=f"Limpieza post-checkout stay {id}",
            creado_por="sistema"
        )
        db.add(hk_cycle)

    # Auditoría
    audit = AuditEvent(
        entity_type="stay",
        entity_id=stay.id,
        action="CHECKOUT",
        usuario="sistema",
        descripcion="Check-out realizado",
        payload={
            "charges": float(charges_total),
            "payments": float(payments_total),
            "balance": float(balance)
        }
    )
    db.add(audit)

    db.commit()
    db.refresh(stay)

    log_event("stays", "usuario", "Check-out", f"stay_id={id} balance={balance}")

    return {
        "id": stay.id,
        "estado": stay.estado,
        "checkout_real": stay.checkout_real.isoformat(),
        "total": float(charges_total),
        "paid": float(payments_total),
        "balance": float(balance)
    }


# ========================================================================
# 9️⃣ DISPONIBILIDAD (VALIDACIÓN PREVIA)
# ========================================================================

@router.get("/availability/check")
def check_availability(
    room_id: int = Query(..., gt=0),
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    """Validar disponibilidad antes de mover"""
    desde = _parse_date(from_date)
    hasta = _parse_date(to_date)

    if hasta <= desde:
        return {"available": False, "reason": "invalid_dates"}

    if _check_availability(db, room_id, desde, hasta):
        return {"available": True, "reason": "ok"}
    else:
        return {"available": False, "reason": "overlap"}
