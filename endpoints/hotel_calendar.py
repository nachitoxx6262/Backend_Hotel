"""
Hotel Calendar Endpoints
Endpoints para el nuevo sistema de calendario con Reservations y Stays separados
"""

from datetime import datetime, date, timedelta, time
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
    Room, RoomType, Cliente, ClienteCorporativo, AuditEvent, HousekeepingTask, HotelSettings
)
from models.servicios import ProductoServicio
from utils.logging_utils import log_event
from utils.dependencies import get_current_user_optional, get_current_user
from utils.invoice_engine import compute_invoice
from utils.timezone import get_hotel_now, HOTEL_TZ, to_hotel_time
from utils.overstay_engine import check_overstay_status, OVERSTAY_DETECTED
from utils.housekeeping_engine import generate_checkout_tasks


router = APIRouter(prefix="/api/calendar", tags=["Hotel Calendar"])


# ========================================================================
# SCHEMAS
# ========================================================================

class CalendarBlock(BaseModel):
    """Bloque en el calendario (reserva o estadía)"""
    id: int
    block_type: str  # "reservation" | "stay"
    kind: str  # DEPRECATED: usar block_type (mantener para backward compatibility)
    room_id: int
    room_numero: str
    start_date: str  # ISO date (YYYY-MM-DD)
    end_date: str  # ISO date (YYYY-MM-DD)
    fecha_desde: str  # DEPRECATED: usar start_date
    fecha_hasta: str  # DEPRECATED: usar end_date
    status: str  # estado del stay/reservation
    estado: str  # DEPRECATED: usar status
    title: Optional[str] = None  # cliente/empresa/nombre_temporal
    cliente_nombre: Optional[str] = None  # DEPRECATED: usar title
    is_historical: bool = False  # true si stay.estado == 'cerrada'
    color_hint: Optional[str] = None  # hint para UI
    meta: dict = {}
    pax: int = 1  # Cantidad de huespedes
    
    # New Fields (Strict Date vs Timestamp)
    planned_checkin: Optional[str] = None  # YYYY-MM-DD
    planned_checkout: Optional[str] = None  # YYYY-MM-DD
    actual_checkin_at: Optional[str] = None  # ISO Timestamp
    actual_checkin_at: Optional[str] = None  # ISO Timestamp
    actual_checkout_at: Optional[str] = None  # ISO Timestamp
    
    # Flags (Phase 2)
    flags: List[str] = []  # ["overstay_detected", "critical"]

    # Render helpers (clipped blocks)
    render_start_date: Optional[str] = None  # start date clamped to requested range
    render_end_date: Optional[str] = None  # end date clamped to requested range
    clipped_left: bool = False  # true si el bloque inicia antes del rango solicitado
    clipped_right: bool = False  # true si el bloque termina después del rango solicitado

    class Config:
        from_attributes = True


class CalendarMeta(BaseModel):
    hotel_timezone: str
    server_time: str
    focus_date: str
    coverage: dict  # { from, to }

class CalendarResponse(BaseModel):
    """Respuesta del calendario"""
    from_date: str
    to_date: str
    meta: CalendarMeta
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


class CancelReservationRequest(BaseModel):
    """Request para cancelar reserva"""
    reason: Optional[str] = "Cancelada por cliente"


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
    """Request para checkout (preview y confirm)"""
    # Overrides para cálculo de factura
    nights_override: Optional[int] = Field(None, ge=1, description="Override de noches a cobrar")
    tarifa_override: Optional[float] = Field(None, ge=0, description="Override de tarifa por noche")
    discount_override_pct: Optional[float] = Field(None, ge=0, le=100, description="Descuento adicional %")
    tax_override_mode: Optional[str] = Field(None, description="normal|exento|custom")
    tax_override_value: Optional[float] = Field(None, ge=0, description="Impuesto manual si mode=custom")
    surcharge_amount: Optional[float] = Field(None, ge=0, description="Recargo adicional (ej. por forma de pago)")

    # Opciones de Confirmación
    housekeeping: bool = Field(False, description="Generar tarea de limpieza")
    allow_close_with_debt: bool = Field(False, description="Permitir cerrar con saldo pendiente")
    debt_reason: Optional[str] = Field(None, description="Motivo de deuda (obligatorio si hay deuda)")
    notes: Optional[str] = Field(None, description="Notas finales del checkout")

    # Idempotencia (opcional, por ahora no persistida pero buen hook)
    idempotency_key: Optional[str] = None
    
    # Retroactive Checkout (Phase 3)
    retroactive_time: Optional[str] = Field(None, description="Fecha/hora retroactiva (ISO)")
    audit_reason: Optional[str] = Field(None, description="Motivo de checkout retroactivo")

    # Empresa opcional al cerrar
    empresa_id: Optional[int] = Field(
        None,
        gt=0,
        description="Asociar la reserva a una empresa durante el checkout (opcional)",
    )


class CheckoutResult(BaseModel):
    """Resultado del checkout confirmado"""
    success: bool
    message: str
    stay_id: int
    stay_status: str
    reservation_status: str
    invoice: "InvoicePreviewResponse"
    housekeeping_task_id: Optional[int] = None




class ProductoServicioBase(BaseModel):
    nombre: str
    tipo: str
    descripcion: Optional[str] = None
    precio_unitario: float
    activo: Optional[bool] = True


class ProductoServicioCreate(ProductoServicioBase):
    pass


class ProductoServicioUpdate(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    descripcion: Optional[str] = None
    precio_unitario: Optional[float] = None
    activo: Optional[bool] = None


class ProductoServicioResponse(ProductoServicioBase):
    id: int
    creado_en: datetime
    actualizado_en: datetime
    actualizado_por: Optional[str] = None

    class Config:
        from_attributes = True


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
    
    # Overstay information
    is_overstay: bool = False
    overstay_nights: int = 0
    overstay_charge: float = 0.0


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


class EmpresaContactInfo(BaseModel):
    """Contacto básico de la empresa"""
    nombre: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None


class InvoicePreviewResponse(BaseModel):
    """Preview profesional de factura para check-out"""
    # Identificación
    stay_id: int
    reservation_id: int
    cliente_nombre: Optional[str] = None
    empresa_id: Optional[int] = None
    empresa_nombre: Optional[str] = None
    empresa_contacto: Optional[EmpresaContactInfo] = None
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


def localize_hotel_date(value: date) -> datetime:
    """Localize a date at midnight in hotel timezone."""
    if value is None:
        raise ValueError("Date value is None")
    return HOTEL_TZ.localize(datetime.combine(value, time.min))


def normalize_hotel_dt(value: Union[date, datetime]) -> datetime:
    """Normalize date/datetime to hotel timezone (aware)."""
    if isinstance(value, datetime):
        return to_hotel_time(value)
    if isinstance(value, date):
        return localize_hotel_date(value)
    raise TypeError(f"Unsupported datetime type: {type(value)}")


def _get_active_empresa_or_404(
    db: Session,
    empresa_id: int,
    tenant_id: int
) -> ClienteCorporativo:
    """Obtiene empresa activa del tenant o lanza 404 si no existe o está inactiva."""
    empresa = (
        db.query(ClienteCorporativo)
        .filter(
            ClienteCorporativo.id == empresa_id,
            ClienteCorporativo.empresa_usuario_id == tenant_id,
            ClienteCorporativo.activo == True  # noqa: E712
        )
        .first()
    )
    if not empresa:
        raise HTTPException(404, "Empresa no encontrada o inactiva")
    return empresa


def compute_render_window(start: date, end: date, view_start: date, view_end: date):
    """
    Calcula el segmento visible de un bloque respecto al rango solicitado.
    No altera las fechas reales; se usa para que el front pueda anclar y mostrar
    reservas largas que empiezan antes (o terminan después) del rango visible.
    """
    # Clamp dates to view boundaries
    clamped_start = start if start >= view_start else view_start
    clamped_end = end if end <= view_end else view_end

    return {
        "render_start_date": clamped_start.isoformat(),
        "render_end_date": clamped_end.isoformat(),
        "clipped_left": start < view_start,
        "clipped_right": end > view_end,
    }


def _check_room_availability(
    db: Session,
    tenant_id: int,
    room_id: int,
    fecha_desde: date,
    fecha_hasta: date,
    exclude_reservation_id: Optional[int] = None,
    exclude_stay_id: Optional[int] = None
) -> bool:
    """Verificar disponibilidad de habitación en rango de fechas"""

    room = db.query(Room).filter(
        Room.id == room_id,
        Room.empresa_usuario_id == tenant_id
    ).first()
    # Si no existe, no permitir asignaciones
    if not room:
        return False
    
    # Verificar conflictos en reservas confirmadas
    reservations_query = (
        db.query(Reservation)
        .join(ReservationRoom)
        .filter(
            ReservationRoom.room_id == room_id,
            Reservation.empresa_usuario_id == tenant_id,
            Reservation.estado.in_(["draft", "confirmada"]),  # No ocupada (ya tiene Stay con occupancies)
            Reservation.fecha_checkin < fecha_hasta,
            Reservation.fecha_checkout > fecha_desde
        )
    )
    
    if exclude_reservation_id:
        reservations_query = reservations_query.filter(Reservation.id != exclude_reservation_id)
    
    conflicting_reservation = reservations_query.first()
    if conflicting_reservation:
        return False
    
    # Verificar conflictos en ocupaciones reales
    # NOTA: Las ocupaciones sin checkout (hasta=None) solo bloquean si se superponen con el rango solicitado
    # considerando que la estadía abierta podría continuar indefinidamente
    occupancies = (
        db.query(StayRoomOccupancy)
        .join(Stay)
        .filter(
            StayRoomOccupancy.room_id == room_id,
            Stay.empresa_usuario_id == tenant_id,
            Stay.estado.in_(["pendiente_checkin", "ocupada", "pendiente_checkout"]),
        )
    ).all()
    
    if exclude_stay_id:
        occupancies = [occ for occ in occupancies if occ.stay_id != exclude_stay_id]
    
    for occ in occupancies:
        # Convertir desde a date para comparación
        occ_desde = occ.desde.date() if isinstance(occ.desde, datetime) else occ.desde
        occ_hasta = occ.hasta.date() if occ.hasta and isinstance(occ.hasta, datetime) else occ.hasta
        
        # Si la ocupación tiene hasta definido, verificar overlap normal
        if occ_hasta:
            # Overlap: desde < fecha_hasta AND hasta > fecha_desde
            if occ_desde < fecha_hasta and occ_hasta > fecha_desde:
                return False
        else:
            # Ocupación sin checkout (abierta): solo bloquear si el checkin solicitado 
            # está en la fecha de inicio de la ocupación o antes de la fecha actual
            # Permitir reservas futuras
            if fecha_desde <= occ_desde:
                # La reserva quiere empezar antes o en la fecha de la ocupación actual
                return False
    
    return True


def upsert_checkout_task(db: Session, stay: Stay, room: Room) -> HousekeepingTask:
    """Crea o devuelve la tarea de checkout para la estadía (idempotente)."""
    today = datetime.utcnow().date()

    existing = (
        db.query(HousekeepingTask)
        .filter(
            HousekeepingTask.task_type == "checkout",
            HousekeepingTask.stay_id == stay.id,
        )
        .first()
    )

    if existing:
        # Asegurar datos básicos actualizados sin cambiar status/done_at
        updated = False
        if existing.room_id != room.id:
            existing.room_id = room.id
            updated = True
        if existing.reservation_id != stay.reservation_id:
            existing.reservation_id = stay.reservation_id
            updated = True
        if existing.task_date is None:
            existing.task_date = today
            updated = True
        if updated:
            existing.updated_at = datetime.utcnow()
        return existing

    task = HousekeepingTask(
        room_id=room.id,
        stay_id=stay.id,
        reservation_id=stay.reservation_id,
        task_date=today,
        task_type="checkout",
        status="pending",
        meta={"source": "checkout"},
    )
    db.add(task)
    db.flush()
    return task


# ========================================================================
# ENDPOINTS: CALENDAR
# ========================================================================

@router.get("/calendar", response_model=CalendarResponse)
def get_calendar(
    from_date: str = Query(..., alias="from", description="YYYY-MM-DD"),
    to_date: str = Query(..., alias="to", description="YYYY-MM-DD"),
    include_history: bool = Query(True, description="Incluir stays cerradas (histórico)"),
    include_cancelled: bool = Query(False, description="Incluir reservas canceladas"),
    include_no_show: bool = Query(False, description="Incluir reservas no-show"),
    room_id: Optional[int] = Query(None, description="Filtrar por habitación específica"),
    view: str = Query("all", description="Vista: all | stays | reservations"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_optional)
):
    """
    📅 CALENDARIO UNIFICADO - Reservas futuras + Ocupaciones actuales + Histórico
    
    Regla anti-duplicado:
    - Si una Reservation tiene un Stay en el rango solicitado, se muestra SOLO el Stay
    - Solo se muestra Reservation cuando NO existe stay en el rango
    
    Query params:
    - include_history: Incluir stays cerradas (default: True)
    - include_cancelled: Incluir reservas canceladas (default: False)
    - include_no_show: Incluir reservas no-show (default: False)
    - room_id: Filtrar por habitación específica (opcional)
    - view: "all" | "stays" | "reservations" (default: "all")
    """
    # Validar rango de fechas
    fecha_desde = parse_to_date(from_date)
    fecha_hasta = parse_to_date(to_date)
    
    if fecha_hasta <= fecha_desde:
        raise HTTPException(400, "La fecha 'to' debe ser posterior a 'from'")
    
    # Validar rango máximo (120 días)
    days_diff = (fecha_hasta - fecha_desde).days
    if days_diff > 120:
        log_event("calendar", "warning", "Rango amplio", f"from={from_date} to={to_date} days={days_diff}")
    
    # Obtener tenant_id del usuario autenticado
    tenant_id = current_user.empresa_usuario_id if current_user else None
    if not tenant_id:
        raise HTTPException(401, "Usuario no autenticado o sin tenant asociado")
    
    # Convertir a datetime para overlap (from inclusivo, to exclusivo) en horario del hotel
    from_dt = localize_hotel_date(fecha_desde)
    to_dt = localize_hotel_date(fecha_hasta) + timedelta(days=1)  # to exclusivo
    
    blocks = []
    reservation_ids_with_stay = set()
    
    # ========================================================================
    # 0️⃣ OBTENER CONTEXTO GENERAL
    # ========================================================================
    
    # Cargar configuración del hotel para Overstay Check
    hotel_settings = db.query(HotelSettings).first()

    # ========================================================================
    # 1️⃣ QUERY DE STAYS (incluye histórico si include_history=True)
    # ========================================================================
    
    if view in ("all", "stays"):
        # Construir filtro de estados
        stay_estados = ["pendiente_checkin", "ocupada", "pendiente_checkout"]
        if include_history:
            stay_estados.append("cerrada")
        
        # Query base de stays
        # OPTIMIZADO: Eagerly load ALL relationships to prevent N+1 queries
        stays_query = (
            db.query(Stay)
            .options(
                joinedload(Stay.reservation).joinedload(Reservation.cliente),
                joinedload(Stay.reservation).joinedload(Reservation.empresa),
                joinedload(Stay.reservation).joinedload(Reservation.rooms).joinedload(ReservationRoom.room).joinedload(Room.tipo),
                joinedload(Stay.reservation).joinedload(Reservation.guests),  # Include guests for pax count
                joinedload(Stay.occupancies).joinedload(StayRoomOccupancy.room).joinedload(Room.tipo),
                joinedload(Stay.charges),
                joinedload(Stay.payments)
            )
            .filter(
                Stay.empresa_usuario_id == tenant_id,
                Stay.estado.in_(stay_estados)
            )
        )
        
        # NO filtrar por overlap en la query SQL (lo haremos en Python)
        # Esto permite manejar correctamente stays con checkout el mismo día
        stays = stays_query.all()
        
        log_event("calendar", "debug", "stays_loaded", f"count={len(stays)} from={from_date} to={to_date} include_history={include_history}")
        
        for stay in stays:
            res = stay.reservation
            
            # Determinar start/end datetime usando coalesce logic
            stay_start_dt = None
            stay_end_dt = None
            
            if stay.checkin_real:
                stay_start_dt = normalize_hotel_dt(stay.checkin_real)
            elif stay.occupancies and stay.occupancies[0].desde:
                occ_desde = stay.occupancies[0].desde
                stay_start_dt = normalize_hotel_dt(occ_desde)
            elif res and res.fecha_checkin:
                stay_start_dt = normalize_hotel_dt(res.fecha_checkin)
            else:
                stay_start_dt = from_dt
            
            if stay.checkout_real:
                stay_end_dt = normalize_hotel_dt(stay.checkout_real)
            elif res and res.fecha_checkout:
                stay_end_dt = normalize_hotel_dt(res.fecha_checkout)
            else:
                stay_end_dt = to_dt
            
            # --- AUTO-EXTEND LOGIC ---
            # IMPORTANT: Apply BEFORE intersection check so extended stays are included
            # Si el stay está ACTIVO (ocupada/pendiente_checkout) y su fecha de fin ya pasó (o es hoy),
            # forzamos que visualmente termine "Mañana" para que ocupe el slot de hoy.
            if stay.estado in ["ocupada", "pendiente_checkout"]:
                now = get_hotel_now()
                # Definir "Mañana" a las 00:00 como límite mínimo para que bloquee el día de hoy
                tomorrow_min = localize_hotel_date(now.date()) + timedelta(days=1)
                
                if stay_end_dt < tomorrow_min:
                    stay_end_dt = tomorrow_min
            
            # CRITICAL: Check intersection (overlap) - correct logic for semi-open ranges
            # Intersection condition: stay_start < to_dt AND stay_end > from_dt
            if stay_start_dt >= to_dt or stay_end_dt <= from_dt:
                # No intersection - skip this stay
                continue

            # Convertir a date para display
            start_date = stay_start_dt.date()
            end_date = stay_end_dt.date()
            
            # Si checkout es mismo día que checkin, forzar mínimo 1 día de duración para render
            if end_date <= start_date:
                end_date = start_date + timedelta(days=1)
            
            # Marcar reservation_id para evitar duplicados
            if res:
                reservation_ids_with_stay.add(res.id)

            render_window = compute_render_window(start_date, end_date, fecha_desde, fecha_hasta)
            
            # SAFETY CHECK: Validate render_window has valid dates (render_start <= render_end)
            if render_window["clipped_left"] or render_window["clipped_right"]:
                try:
                    render_start = parse_to_date(render_window["render_start_date"])
                    render_end = parse_to_date(render_window["render_end_date"])
                    if render_start >= render_end:
                        # Invalid render window - skip this stay
                        log_event("calendar", "warning", "Invalid render_window", 
                                  f"stay_id={stay.id} actual={start_date}-{end_date} render={render_start}-{render_end}")
                        continue
                except Exception as e:
                    log_event("calendar", "error", "render_window parse error", str(e))
                    continue
            
            # Construir title (cliente/empresa/nombre_temporal)
            title = None
            if res:
                if res.cliente:
                    title = f"{res.cliente.nombre} {res.cliente.apellido}"
                elif res.empresa:
                    title = res.empresa.nombre
                else:
                    title = res.nombre_temporal
            
            # Determinar si es histórico
            is_historical = (stay.estado == "cerrada")
            
            # Determinar color_hint
            color_hint = None
            if is_historical:
                color_hint = "historical"
            elif stay.estado == "ocupada":
                color_hint = "active"
            elif stay.estado == "pendiente_checkin":
                color_hint = "pending"
            elif stay.estado == "pendiente_checkout":
                color_hint = "checkout_pending"
            
            # Calcular Pax
            pax = len(res.guests) if (res and res.guests) else 1

            # Si hay occupancies, crear un bloque por cada habitación ocupada
            if stay.occupancies:
                for occ in stay.occupancies:
                    # Filtrar por room_id si se especificó
                    if room_id and occ.room_id != room_id:
                        continue
                    
                    # Metadata extendida
                    meta_data = {
                        "occupancy_id": occ.id,
                        "reservation_id": res.id if res else None,
                        "checkin_real": stay.checkin_real.isoformat() if stay.checkin_real else None,
                        "checkout_real": stay.checkout_real.isoformat() if stay.checkout_real else None,
                        "source": "stay_occupancy"
                    }

                    # Overstay Process
                    ov_result = check_overstay_status(stay, hotel_settings)
                    block_flags = ov_result.get("flags", [])
                    if ov_result.get("status") == OVERSTAY_DETECTED:
                        meta_data["overstay_info"] = ov_result.get("meta")
                        # Override status for UI if strictly needed, or just let UI handle flags
                        # stay.estado is "ocupada" usually.
                        pass
                    
                    blocks.append(CalendarBlock(
                        id=stay.id,
                        block_type="stay",
                        kind="stay",  # backward compatibility
                        room_id=occ.room.id,
                        room_numero=occ.room.numero,
                        start_date=start_date.isoformat(),
                        end_date=end_date.isoformat(),
                        fecha_desde=start_date.isoformat(),  # backward compatibility
                        fecha_hasta=end_date.isoformat(),  # backward compatibility
                        status=stay.estado,
                        estado=stay.estado,  # backward compatibility
                        title=title,
                        cliente_nombre=title,  # backward compatibility
                        is_historical=is_historical,
                        color_hint=color_hint,
                        meta=meta_data,
                        pax=pax,
                        planned_checkin=stay.reservation.fecha_checkin.isoformat() if stay.reservation else None,
                        planned_checkout=stay.reservation.fecha_checkout.isoformat() if stay.reservation else None,
                        actual_checkin_at=stay.checkin_real.isoformat() if stay.checkin_real else None,
                        actual_checkout_at=stay.checkout_real.isoformat() if stay.checkout_real else None,
                        flags=block_flags,
                        render_start_date=render_window["render_start_date"],
                        render_end_date=render_window["render_end_date"],
                        clipped_left=render_window["clipped_left"],
                        clipped_right=render_window["clipped_right"],
                    ))
            else:
                # Si no hay occupancies, usar las habitaciones de la reserva (fallback)
                if res and res.rooms:
                    for res_room in res.rooms:
                        # Filtrar por room_id si se especificó
                        if room_id and res_room.room_id != room_id:
                            continue
                        
                        meta_data = {
                            "reservation_id": res.id,
                            "checkin_real": stay.checkin_real.isoformat() if stay.checkin_real else None,
                            "checkout_real": stay.checkout_real.isoformat() if stay.checkout_real else None,
                            "source": "stay_no_occupancy_fallback"
                        }
                        
                        # Overstay Process (Fallback path)
                        ov_result = check_overstay_status(stay, hotel_settings)
                        block_flags = ov_result.get("flags", [])
                        if ov_result.get("status") == OVERSTAY_DETECTED:
                            meta_data["overstay_info"] = ov_result.get("meta")

                        blocks.append(CalendarBlock(
                            id=stay.id,
                            block_type="stay",
                            kind="stay",
                            room_id=res_room.room.id,
                            room_numero=res_room.room.numero,
                            start_date=start_date.isoformat(),
                            end_date=end_date.isoformat(),
                            fecha_desde=start_date.isoformat(),
                            fecha_hasta=end_date.isoformat(),
                            status=stay.estado,
                            estado=stay.estado,
                            title=title,
                            cliente_nombre=title,
                            is_historical=is_historical,
                            color_hint=color_hint,
                            meta=meta_data,
                            pax=pax,
                            planned_checkin=stay.reservation.fecha_checkin.isoformat() if stay.reservation else None,
                            planned_checkout=stay.reservation.fecha_checkout.isoformat() if stay.reservation else None,
                            actual_checkin_at=stay.checkin_real.isoformat() if stay.checkin_real else None,
                            actual_checkout_at=stay.checkout_real.isoformat() if stay.checkout_real else None,
                            flags=block_flags,
                            render_start_date=render_window["render_start_date"],
                            render_end_date=render_window["render_end_date"],
                            clipped_left=render_window["clipped_left"],
                            clipped_right=render_window["clipped_right"],
                        ))
    
    # ========================================================================
    # 2️⃣ QUERY DE RESERVATIONS (futuras / planificadas)
    # ========================================================================
    
    if view in ("all", "reservations"):
        # Construir filtro de estados
        # Por defecto: draft, confirmada
        # Excluir: finalizada (siempre), cancelada (si include_cancelled=False), no_show (si include_no_show=False)
        reservation_estados = ["draft", "confirmada"]
        
        # Incluir 'ocupada' SOLO si no tiene Stay asociado (se filtra después)
        # Esto permite mostrar reservas que fueron marcadas como ocupadas manualmente pero sin stay creado
        
        if include_cancelled:
            reservation_estados.append("cancelada")
        
        if include_no_show:
            reservation_estados.append("no_show")
        
        # Query base de reservations
        # OPTIMIZADO: Eagerly load ALL relationships including Room.tipo
        reservations_query = (
            db.query(Reservation)
            .options(
                joinedload(Reservation.rooms).joinedload(ReservationRoom.room).joinedload(Room.tipo),
                joinedload(Reservation.cliente),
                joinedload(Reservation.empresa),
                joinedload(Reservation.guests)  # Include guests for pax count
            )
            .filter(
                Reservation.empresa_usuario_id == tenant_id,
                Reservation.estado.in_(reservation_estados + ["ocupada"]),  # incluir ocupada para filtrar después
                Reservation.fecha_checkin < fecha_hasta,
                Reservation.fecha_checkout > fecha_desde
            )
        )
        
        # IMPORTANTE: Excluir reservations que ya tienen stay en el rango (anti-duplicado)
        if reservation_ids_with_stay:
            reservations_query = reservations_query.filter(
                Reservation.id.notin_(reservation_ids_with_stay)
            )
        
        reservations = reservations_query.all()
        
        log_event("calendar", "debug", "reservations_loaded", f"count={len(reservations)} from={from_date} to={to_date}")
        
        for res in reservations:
            # Filtrar reservations con estado 'ocupada' que tienen Stay
            # (ya fueron excluidas en la query, pero por si acaso)
            if res.estado == "ocupada":
                stay_exists = db.query(Stay.id).filter(Stay.reservation_id == res.id).first()
                if stay_exists:
                    continue
            
            # Excluir estados no deseados (por si acaso)
            if res.estado == "finalizada":
                continue
            
            if res.estado == "cancelada" and not include_cancelled:
                continue
            
            if res.estado == "no_show" and not include_no_show:
                continue
            
            # Construir title
            title = None
            if res.cliente:
                title = f"{res.cliente.nombre} {res.cliente.apellido}"
            elif res.empresa:
                title = res.empresa.nombre
            else:
                title = res.nombre_temporal
            
            # Determinar color_hint
            color_hint = None
            if res.estado == "draft":
                color_hint = "draft"
            elif res.estado == "confirmada":
                color_hint = "confirmed"
            elif res.estado == "ocupada":
                color_hint = "occupied_no_stay"
            elif res.estado == "cancelada":
                color_hint = "cancelled"
            elif res.estado == "no_show":
                color_hint = "no_show"
            
            # Calcular Pax
            pax = len(res.guests) if res.guests else 1

            render_window = compute_render_window(
                res.fecha_checkin,
                res.fecha_checkout,
                fecha_desde,
                fecha_hasta
            )
            
            # Crear un bloque por cada habitación de la reserva
            for res_room in res.rooms:
                # Filtrar por room_id si se especificó
                if room_id and res_room.room_id != room_id:
                    continue
                
                meta_data = {
                    "reservation_id": res.id,
                    "origen": res.origen,
                    "notas": res.notas,
                    "source": "reservation"
                }
                
                blocks.append(CalendarBlock(
                    id=res.id,
                    block_type="reservation",
                    kind="reservation",
                    room_id=res_room.room.id,
                    room_numero=res_room.room.numero,
                    start_date=res.fecha_checkin.isoformat(),
                    end_date=res.fecha_checkout.isoformat(),
                    fecha_desde=res.fecha_checkin.isoformat(),
                    fecha_hasta=res.fecha_checkout.isoformat(),
                    status=res.estado,
                    estado=res.estado,
                    title=title,
                    cliente_nombre=title,
                    is_historical=False,
                    color_hint=color_hint,
                    meta=meta_data,
                    pax=pax,
                    planned_checkin=res.fecha_checkin.isoformat(),
                    planned_checkout=res.fecha_checkout.isoformat(),
                    actual_checkin_at=None,
                    actual_checkout_at=None,
                    flags=[],
                    render_start_date=render_window["render_start_date"],
                    render_end_date=render_window["render_end_date"],
                    clipped_left=render_window["clipped_left"],
                    clipped_right=render_window["clipped_right"],
                ))
    
    # ========================================================================
    # 3️⃣ CARGAR INFORMACIÓN DE HABITACIONES
    # ========================================================================
    
    rooms_query = (
        db.query(Room)
        .options(joinedload(Room.tipo))
        .filter(
            Room.activo == True,
            Room.empresa_usuario_id == tenant_id
        )
    )
    
    if room_id:
        rooms_query = rooms_query.filter(Room.id == room_id)
    
    rooms = rooms_query.all()
    rooms_data = [
        {
            "id": r.id,
            "numero": r.numero,
            "piso": r.piso,
            "room_type_id": r.room_type_id,
            "room_type_nombre": r.tipo.nombre if r.tipo else None,
            "capacidad": r.tipo.capacidad if r.tipo else None,
            "estado_operativo": r.estado_operativo
        }
        for r in rooms
    ]
    
    log_event("calendar", "usuario", "Ver calendario", 
              f"from={from_date} to={to_date} blocks={len(blocks)} history={include_history} cancelled={include_cancelled} no_show={include_no_show}")
    
    from utils.timezone import get_hotel_now, HOTEL_TIMEZONE_STR
    hotel_now = get_hotel_now()

    return CalendarResponse(
        from_date=from_date,
        to_date=to_date,
        meta=CalendarMeta(
            hotel_timezone=HOTEL_TIMEZONE_STR,
            server_time=hotel_now.isoformat(),
            focus_date=hotel_now.date().isoformat(),
            coverage={"from": from_date, "to": to_date}
        ),
        blocks=blocks,
        rooms=rooms_data
    )


# ========================================================================
# ENDPOINTS: RESERVATIONS
# ========================================================================

@router.post("/reservations", status_code=status.HTTP_201_CREATED)
def create_reservation(
    req: CreateReservationRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Crear nueva reserva
    """
    tenant_id = current_user.empresa_usuario_id
    
    fecha_checkin = parse_to_date(req.fecha_checkin)
    fecha_checkout = parse_to_date(req.fecha_checkout)
    
    if fecha_checkout <= fecha_checkin:
        raise HTTPException(400, "La fecha de checkout debe ser posterior al checkin")
    
    # Validar habitaciones (deben pertenecer al tenant)
    rooms = db.query(Room).filter(
        Room.id.in_(req.room_ids),
        Room.empresa_usuario_id == tenant_id
    ).all()
    if len(rooms) != len(req.room_ids):
        raise HTTPException(404, "Una o más habitaciones no encontradas o no pertenecen a tu empresa")
    
    # Verificar disponibilidad
    for room in rooms:
        if not _check_room_availability(db, tenant_id, room.id, fecha_checkin, fecha_checkout):
            raise HTTPException(
                409,
                f"Habitación {room.numero} no disponible en las fechas seleccionadas"
            )
    
    # Validar cliente/empresa si se proporciona (deben pertenecer al tenant)
    if req.cliente_id:
        cliente = db.query(Cliente).filter(
            Cliente.id == req.cliente_id,
            Cliente.empresa_usuario_id == tenant_id
        ).first()
        if not cliente:
            raise HTTPException(404, "Cliente no encontrado o no pertenece a tu empresa")
    
    if req.empresa_id:
        empresa = db.query(ClienteCorporativo).filter(
            ClienteCorporativo.id == req.empresa_id,
            ClienteCorporativo.empresa_usuario_id == tenant_id
        ).first()
        if not empresa:
            raise HTTPException(404, "Empresa no encontrada o no pertenece a tu empresa")
    
    # Crear reserva con empresa_usuario_id
    reservation = Reservation(
        cliente_id=req.cliente_id,
        empresa_id=req.empresa_id,
        empresa_usuario_id=tenant_id,
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
    
    # Asignar huéspedes si se proporcionan (validar pertenencia al tenant)
    guest_ids = [g.get("cliente_id") for g in req.huespedes if g.get("cliente_id")]
    if guest_ids:
        unique_guest_ids = list(set(guest_ids))
        valid_guest_ids = {
            row[0]
            for row in db.query(Cliente.id)
            .filter(
                Cliente.id.in_(unique_guest_ids),
                Cliente.empresa_usuario_id == tenant_id
            )
            .all()
        }
        if len(valid_guest_ids) != len(unique_guest_ids):
            raise HTTPException(404, "Uno o más huéspedes no pertenecen a tu empresa")

    for guest_data in req.huespedes:
        cliente_id = guest_data.get("cliente_id")
        if not cliente_id:
            continue
        res_guest = ReservationGuest(
            reservation_id=reservation.id,
            cliente_id=cliente_id,
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
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Actualizar reserva existente.
    
    Validaciones:
    - No se puede editar si está convertida (tiene Stay activo)
    - No se puede editar si está cerrada
    - Cambios de fechas requieren verificar disponibilidad
    """
    tenant_id = current_user.empresa_usuario_id
    
    reservation = db.query(Reservation).filter(
        Reservation.id == reservation_id,
        Reservation.empresa_usuario_id == tenant_id
    ).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reserva no encontrada o no pertenece a tu empresa")
    
    # VALIDACIÓN 1: No editar si está ocupada (tiene Stay activa)
    if reservation.estado == "ocupada":
        raise HTTPException(
            status_code=409,
            detail="No se puede editar una reserva con estadía activa. Edita la estadía directamente"
        )
    
    # VALIDACIÓN 2: No editar si está cerrada
    if reservation.estado == "cerrada":
        raise HTTPException(
            status_code=409,
            detail="No se puede editar una reserva cerrada"
        )
    
    cambios = []
    
    if req.estado is not None:
        # VALIDACIÓN 3: Validar transición de estado
        estado_actual = reservation.estado
        estado_nuevo = req.estado
        
        # Estados finales (no se pueden cambiar desde estos)
        if estado_actual in ["cerrada", "cancelada", "no_show"]:
            raise HTTPException(
                status_code=409,
                detail=f"No se puede cambiar estado desde '{estado_actual}' - estado final"
            )
        
        # Transiciones inválidas
        if estado_actual == "ocupada":
            raise HTTPException(
                status_code=409,
                detail="No se puede cambiar estado de una reserva con estadía activa"
            )
        
        reservation.estado = estado_nuevo
        cambios.append(f"estado={estado_nuevo}")
    
    if req.notas is not None:
        reservation.notas = req.notas
        cambios.append("notas actualizadas")
    
    if req.fecha_checkin or req.fecha_checkout:
        nueva_checkin = parse_to_date(req.fecha_checkin) if req.fecha_checkin else reservation.fecha_checkin
        nueva_checkout = parse_to_date(req.fecha_checkout) if req.fecha_checkout else reservation.fecha_checkout
        
        if nueva_checkout <= nueva_checkin:
            raise HTTPException(400, "Fechas inválidas")
        
        # Verificar disponibilidad para las nuevas fechas
        for res_room in reservation.rooms:
            if not _check_room_availability(
                db, tenant_id, res_room.room_id, nueva_checkin, nueva_checkout,
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


@router.patch("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: int = Path(..., gt=0),
    req: CancelReservationRequest = ...,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Cancelar reserva (soft delete).
    
    Validaciones:
    - Reserva debe existir
    - NO se puede cancelar si tiene Stay activo (estado != 'cerrada')
    - Si ya está cancelada: idempotente (retorna OK)
    
    Persiste:
    - estado = 'cancelada'
    - cancel_reason
    - cancelled_at
    - cancelled_by
    """
    tenant_id = current_user.empresa_usuario_id
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Usuario no autenticado o sin tenant asociado")

    reservation = (
        db.query(Reservation)
        .options(joinedload(Reservation.rooms))
        .filter(
            Reservation.id == reservation_id,
            Reservation.empresa_usuario_id == tenant_id
        )
        .first()
    )
    
    if not reservation:
        raise HTTPException(status_code=404, detail="Reserva no encontrada o no pertenece a tu empresa")
    
    # IDEMPOTENCIA: Si ya está cancelada, retornar OK
    if reservation.estado == "cancelada":
        log_event("reservations", "sistema", "Cancel - Idempotencia", f"reservation_id={reservation_id} ya cancelada")
        return {
            "id": reservation.id,
            "estado": "cancelada",
            "message": "Reserva ya estaba cancelada"
        }
    
    # VALIDACIÓN 1: No permitir cancelar si tiene Stay activo
    existing_stay = db.query(Stay).filter(
        Stay.reservation_id == reservation_id,
        Stay.empresa_usuario_id == tenant_id,
        Stay.estado != "cerrada"
    ).first()
    
    if existing_stay:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede cancelar: la reserva tiene una estadía activa (Stay #{existing_stay.id}). Debe hacer checkout primero."
        )
    
    # Soft delete: marcar como cancelada
    reservation.estado = "cancelada"
    reservation.cancel_reason = req.reason
    reservation.cancelled_at = datetime.utcnow()
    reservation.cancelled_by = current_user.id
    reservation.updated_at = datetime.utcnow()
    
    # Liberar habitaciones (estado_operativo)
    for res_room in reservation.rooms:
        room = db.query(Room).filter(
            Room.id == res_room.room_id,
            Room.empresa_usuario_id == tenant_id
        ).first()
        if room and room.estado_operativo == "reservada":
            room.estado_operativo = "disponible"
    
    # Auditoría
    username = current_user.username
    audit = AuditEvent(
        entity_type="reservation",
        entity_id=reservation.id,
        action="CANCEL",
        usuario=username,
        descripcion=f"Reserva cancelada: {req.reason}"
    )
    db.add(audit)
    
    db.commit()
    db.refresh(reservation)
    
    log_event("reservations", username, "Cancelar reserva", f"id={reservation_id} reason={req.reason}")
    
    return {
        "id": reservation.id,
        "estado": "cancelada",
        "cancelled_at": reservation.cancelled_at.isoformat(),
        "cancel_reason": reservation.cancel_reason
    }


# ========================================================================
# ENDPOINTS: BLOCK MOVE
# ========================================================================

@router.patch("/calendar/blocks/move")
def move_block(
    req: MoveBlockRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Mover o redimensionar bloque (reserva o estadía).
    
    Validaciones:
    - Para RESERVA: no puede estar cancelada/no_show/convertida
    - Para STAY: no puede estar cerrada
    - Verificar solapamiento de habitaciones
    - Validar dates lógicas (checkin < checkout)
    """
    tenant_id = current_user.empresa_usuario_id
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Usuario no autenticado o sin tenant asociado")

    if req.kind == "reservation":
        if not req.reservation_id:
            raise HTTPException(status_code=400, detail="reservation_id requerido")
        
        reservation = db.query(Reservation).filter(
            Reservation.id == req.reservation_id,
            Reservation.empresa_usuario_id == tenant_id
        ).first()
        if not reservation:
            raise HTTPException(status_code=404, detail="Reserva no encontrada")
        
        # VALIDACIÓN 1: No mover reserva cancelada/no_show/convertida
        if reservation.estado == "cancelada":
            raise HTTPException(
                status_code=409,
                detail="No se puede mover una reserva cancelada"
            )
        if reservation.estado == "no_show":
            raise HTTPException(
                status_code=409,
                detail="No se puede mover una reserva no-show"
            )
        if reservation.estado == "ocupada":
            raise HTTPException(
                status_code=409,
                detail="No se puede mover una reserva con estadía activa. Edita la estadía directamente"
            )
        
        nueva_checkin = parse_to_date(req.fecha_checkin) if req.fecha_checkin else reservation.fecha_checkin
        nueva_checkout = parse_to_date(req.fecha_checkout) if req.fecha_checkout else reservation.fecha_checkout
        
        # VALIDACIÓN 2: Fechas lógicas
        if nueva_checkout <= nueva_checkin:
            raise HTTPException(
                status_code=400,
                detail="Fecha de checkout debe ser posterior a check-in"
            )
        
        # Verificar disponibilidad
        availability_result = _check_room_availability(
            db, tenant_id, req.room_id, nueva_checkin, nueva_checkout,
            exclude_reservation_id=req.reservation_id
        )
        if not availability_result:
            # Obtener habitación para mensaje más específico
            target_room = db.query(Room).filter(
                Room.id == req.room_id,
                Room.empresa_usuario_id == tenant_id
            ).first()
            room_label = target_room.numero if target_room else str(req.room_id)
            
            raise HTTPException(409, f"Habitación {room_label} no disponible en las fechas solicitadas")
        else:
            target_room = db.query(Room).filter(
                Room.id == req.room_id,
                Room.empresa_usuario_id == tenant_id
            ).first()
            if not target_room:
                raise HTTPException(status_code=404, detail="Habitación no encontrada o no pertenece a tu empresa")
        
        # Advertencia si hay estadía activa (sin bloquear)
        active_stay_warning = (
            db.query(StayRoomOccupancy)
            .join(Stay)
            .filter(
                StayRoomOccupancy.room_id == req.room_id,
                Stay.empresa_usuario_id == tenant_id,
                Stay.estado.in_(["pendiente_checkin", "ocupada", "pendiente_checkout"]),
                StayRoomOccupancy.hasta.is_(None)  # Sin checkout
            )
            .first()
        )
        # Esta advertencia se podría loggear o retornar en metadata, pero por ahora solo permitimos la reserva
        
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
        # ========================================================================
        # NUEVA LÓGICA: Resolver occupancy_id faltante
        # ========================================================================
        occupancy = None
        stay = None
        
        # 1. Intentar cargar occupancy por ID si fue proporcionado
        if req.occupancy_id:
            occupancy = db.query(StayRoomOccupancy).filter(StayRoomOccupancy.id == req.occupancy_id).first()
            if not occupancy:
                raise HTTPException(status_code=404, detail="Ocupación no encontrada")
            stay = occupancy.stay
            if stay and stay.empresa_usuario_id != tenant_id:
                raise HTTPException(status_code=404, detail="Ocupación no encontrada")
        
        # 2. Si no hay occupancy_id pero hay stay_id, intentar recuperar
        elif req.stay_id:
            stay = db.query(Stay).filter(
                Stay.id == req.stay_id,
                Stay.empresa_usuario_id == tenant_id
            ).first()
            if not stay:
                raise HTTPException(status_code=404, detail="Estadía no encontrada")
            
            # Buscar la occupancy activa (until=NULL) en ese stay
            active_occupancies = [occ for occ in stay.occupancies if occ.hasta is None]
            
            if not active_occupancies:
                # No hay occupancy activa - ERROR
                raise HTTPException(
                    status_code=409,
                    detail="La estadía no tiene ocupación activa. No se puede mover una estadía cerrada o sin asignación de habitación"
                )
            
            if len(active_occupancies) > 1:
                # Múltiples ocupaciones activas - usar la más reciente
                occupancy = max(active_occupancies, key=lambda o: o.desde)
                log_event("stays", "warning", "Multiple active occupancies", f"stay_id={stay.id}, usando la más reciente")
            else:
                occupancy = active_occupancies[0]
            
            log_event("stays", "info", "Recovered occupancy", f"stay_id={stay.id}, occupancy_id={occupancy.id}")
        
        # 3. Si aún no hay occupancy, error
        if not occupancy or not stay:
            raise HTTPException(
                status_code=400,
                detail="occupancy_id o stay_id requerido para mover estadía. No se puede identificar la ocupación actual"
            )
        
        # VALIDACIÓN 1: Stay cerrada no se puede mover
        if stay.is_closed():
            raise HTTPException(
                status_code=409,
                detail="No se puede mover una estadía cerrada"
            )
        
        # VALIDACIÓN 2: Stay en estado pendiente_checkout - permitir con warning
        if stay.estado == "pendiente_checkout":
            log_event("stays", "sistema", "Move Stay - Advertencia estado", f"stay_id={stay.id} pendiente_checkout")
        
        # VALIDACIÓN 3: Ocupación debe estar activa (hasta IS NULL)
        if occupancy.hasta is not None:
            raise HTTPException(
                status_code=400,
                detail="Solo se pueden mover ocupaciones activas (sin hasta). Esta ocupación ya fue cerrada"
            )
        
        # Si cambió de habitación, crear nueva ocupación y cerrar la anterior
        if occupancy.room_id != req.room_id:
            # Cerrar ocupación actual
            occupancy.hasta = datetime.utcnow()
            
            # Crear nueva ocupación
            room_nueva = db.query(Room).filter(
                Room.id == req.room_id,
                Room.empresa_usuario_id == tenant_id
            ).first()
            if not room_nueva:
                raise HTTPException(status_code=404, detail="Habitación no encontrada o no pertenece a tu empresa")

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
            room_anterior = db.query(Room).filter(
                Room.id == occupancy.room_id,
                Room.empresa_usuario_id == tenant_id
            ).first()
            if room_anterior:
                room_anterior.estado_operativo = "disponible"
            
            room_nueva = db.query(Room).filter(
                Room.id == req.room_id,
                Room.empresa_usuario_id == tenant_id
            ).first()
            if room_nueva:
                room_nueva.estado_operativo = "ocupada"
        
        # Si cambió fechas (resize)
        if req.desde:
            occupancy.desde = parse_to_datetime(req.desde)
        if req.hasta:
            occupancy.hasta = parse_to_datetime(req.hasta)
        
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
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Realizar check-in creando una estadía desde una reserva.
    
    Validaciones:
    - Reserva debe estar en draft o confirmada
    - Reserva NO debe estar cancelada, no_show o cerrada
    - NO debe existir Stay activo para esa reserva
    - Fecha de checkin debe estar en rango (o con warning)
    
    Idempotencia: Si Stay ya existe, retorna 200 OK con Stay existente
    """
    tenant_id = current_user.empresa_usuario_id
    
    reservation = (
        db.query(Reservation)
        .options(
            joinedload(Reservation.rooms),
            joinedload(Reservation.guests)
        )
        .filter(
            Reservation.id == reservation_id,
            Reservation.empresa_usuario_id == tenant_id
        )
        .first()
    )
    
    if not reservation:
        raise HTTPException(status_code=404, detail="Reserva no encontrada o no pertenece a tu empresa")
    
    # VALIDACIÓN 1: Reserva debe ser candidata a check-in
    if not reservation.is_draft_or_confirmed():
        error_msg = f"Reserva en estado '{reservation.estado}' no puede hacer check-in"
        if reservation.is_cancelled_or_noshow():
            raise HTTPException(
                status_code=409, 
                detail=f"{error_msg} - Reserva cancelada o no-show"
            )
        else:
            raise HTTPException(status_code=409, detail=error_msg)
    
    # VALIDACIÓN 2: No debe existir Stay activo/abierto para esa reserva
    existing_stay = db.query(Stay).filter(
        Stay.reservation_id == reservation_id,
        Stay.estado != "cerrada"
    ).first()
    
    if existing_stay:
        # IDEMPOTENCIA: Si ya existe un Stay activo, retornar 200 OK con el Stay existente
        log_event("stays", "sistema", "Check-in - Idempotencia", f"stay_id={existing_stay.id} ya existe")
        return {
            "id": existing_stay.id,
            "reservation_id": reservation.id,
            "estado": existing_stay.estado,
            "checkin_real": existing_stay.checkin_real.isoformat() if existing_stay.checkin_real else None,
            "message": "Stay ya existe para esta reserva"
        }
    
    # VALIDACIÓN 3: Check-in no debe estar fuera de rango (warning)
    # Permitir con warning, no bloquear
    today = datetime.utcnow().date()
    fecha_checkin = reservation.fecha_checkin
    fecha_checkout = reservation.fecha_checkout
    
    warnings = []
    if today > fecha_checkin:
        warnings.append(f"Check-in tardío: se programó para {fecha_checkin} pero es {today}")
    if today >= fecha_checkout:
        raise HTTPException(
            status_code=400,
            detail=f"Check-in fuera de rango: fecha_checkout ({fecha_checkout}) ya pasó o es hoy"
        )
    
    # === AUTO-CREACIÓN DE CLIENTES ===
    # Procesar la lista de huéspedes enviada en el request
    
    processed_guests = []
    
    for h in req.huespedes:
        nombre = h.get("nombre", "").strip()
        apellido = h.get("apellido", "").strip()
        # Aceptar ambos formatos: documento o numero_documento
        documento = h.get("documento") or h.get("numero_documento", "")
        documento = documento.strip() if documento else ""
        tipo_doc = h.get("tipo_documento", "DNI")
        rol = h.get("rol", "adulto")
        
        if not documento:
            continue
            
        # Buscar cliente existente
        cliente = db.query(Cliente).filter(
            Cliente.numero_documento == documento,
            Cliente.tipo_documento == tipo_doc,
            Cliente.empresa_usuario_id == tenant_id
        ).first()
        
        if not cliente:
            # Crear nuevo
            cliente = Cliente(
                empresa_usuario_id=tenant_id,
                nombre=nombre,
                apellido=apellido,
                tipo_documento=tipo_doc,
                numero_documento=documento,
                telefono=h.get("telefono"),
                email=h.get("email"),
                activo=True
            )
            db.add(cliente)
            db.flush()
            log_event("clientes", "sistema", "Auto-creación en Check-in", f"id={cliente.id} doc={documento}")
            
        processed_guests.append({"cliente_id": cliente.id, "rol": rol})
        
        # Si es el principal, actualizar reserva SIEMPRE (incluso si tenía nombre_temporal)
        if rol == 'principal':
            reservation.cliente_id = cliente.id

    # Actualizar ReservationGuests si hay datos nuevos
    if req.huespedes:
        db.query(ReservationGuest).filter(ReservationGuest.reservation_id == reservation.id).delete()
        for pg in processed_guests:
            rg = ReservationGuest(
                reservation_id=reservation.id,
                cliente_id=pg["cliente_id"],
                rol=pg["rol"]
            )
            db.add(rg)

    # Crear estadía
    stay = Stay(
        empresa_usuario_id=tenant_id,
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
    
    # Marcar reserva como ocupada (check-in realizado)
    reservation.estado = "ocupada"
    
    # Auditoría
    audit = AuditEvent(
        entity_type="stay",
        entity_id=stay.id,
        action="CHECKIN",
        usuario="sistema",
        descripcion=f"Check-in realizado desde reserva {reservation_id}",
        payload={
            "reservation_id": reservation_id,
            "rooms": [r.room_id for r in reservation.rooms],
            "guests_count": len(processed_guests)
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
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    🚪 CHECK-OUT PROFESIONAL
    
    Cierre definitivo de estadía con:
    - Cálculo financiero usando motor compartido (invoice_engine)
    - Actualización de estado de Stay y Reservation asociada
    - Cierre de ocupaciones activas
    - Gestión de housekeeping (opcional)
    - Registro de pagos finales
    - Auditoría completa
    - Idempotencia (si ya está cerrada, retorna 200 OK)
    
    Validaciones:
    - Stay debe existir
    - Stay debe estar en estado válido para checkout: ["ocupada", "pendiente_checkout"]
    - Stay NO debe estar ya cerrada (salvo idempotencia)
    - Debe tener al menos 1 ocupación activa
    - Validación de saldo (warning o bloqueo según configuración)
    
    Estados finales:
    - Stay: "cerrada"
    - Reservation: "finalizada" (si estaba "ocupada")
    - Room: "limpieza" hasta que housekeeping cierre la tarea de checkout
    """
    tenant_id = current_user.empresa_usuario_id
    
    # =====================================================================
    # 1) CARGAR STAY CON RELACIONES
    # =====================================================================
    stay = (
        db.query(Stay)
        .options(
            joinedload(Stay.reservation).joinedload(Reservation.cliente),
            joinedload(Stay.reservation).joinedload(Reservation.empresa),
            joinedload(Stay.occupancies).joinedload(StayRoomOccupancy.room).joinedload(Room.tipo),
            joinedload(Stay.charges),
            joinedload(Stay.payments),
        )
        .filter(
            Stay.id == stay_id,
            Stay.empresa_usuario_id == tenant_id
        )
        .first()
    )
    
    if not stay:
        raise HTTPException(404, "Estadía no encontrada o no pertenece a tu empresa")
    
    reservation = stay.reservation
    if not reservation:
        raise HTTPException(status_code=400, detail="Stay sin reserva asociada")

    if req.empresa_id is not None:
        empresa = _get_active_empresa_or_404(db, req.empresa_id, tenant_id)
        reservation.empresa_id = empresa.id
        reservation.empresa = empresa
        reservation.updated_at = datetime.utcnow()
    
    # =====================================================================
    # 2) IDEMPOTENCIA: Si ya está cerrada, retornar datos sin modificar
    # =====================================================================
    if stay.estado == "cerrada":
        existing_task = (
            db.query(HousekeepingTask)
            .filter(
                HousekeepingTask.task_type == "checkout",
                HousekeepingTask.stay_id == stay.id,
            )
            .first()
        )
        hk_task_id = existing_task.id if existing_task else None
        try:
            calc = compute_invoice(stay, db)
            log_event("stays", "sistema", "Check-out - Idempotencia", f"stay_id={stay_id} ya cerrada")
            
            return {
                "id": stay.id,
                "estado": stay.estado,
                "checkout_real": stay.checkout_real.isoformat() if stay.checkout_real else None,
                "reservation_estado": reservation.estado,
                "totals": {
                    "room_subtotal": float(calc.room_subtotal),
                    "charges_total": float(calc.charges_total),
                    "taxes_total": float(calc.taxes_total),
                    "discounts_total": float(calc.discounts_total),
                    "grand_total": float(calc.grand_total),
                    "payments_total": float(calc.payments_total),
                    "balance": float(calc.balance),
                },
                "housekeeping_task_id": hk_task_id,
                "message": "Stay ya estaba cerrada (idempotencia)",
            }
        except Exception as e:
            # Si falla el cálculo, igual retornar success (ya está cerrada)
            log_event("stays", "sistema", "Check-out - Idempotencia (calc error)", f"stay_id={stay_id} error={str(e)}")
            return {
                "id": stay.id,
                "estado": "cerrada",
                "checkout_real": stay.checkout_real.isoformat() if stay.checkout_real else None,
                "housekeeping_task_id": hk_task_id,
                "message": "Stay ya estaba cerrada",
            }
    
    # =====================================================================
    # 3) VALIDACIONES DE ESTADO
    # =====================================================================
    if stay.estado not in ["ocupada", "pendiente_checkout"]:
        raise HTTPException(
            status_code=409,
            detail=f"Stay en estado '{stay.estado}' no puede hacer check-out. Estados válidos: ocupada, pendiente_checkout"
        )
    
    # Validar que tenga ocupación activa
    if not stay.has_active_occupancy():
        raise HTTPException(
            status_code=400,
            detail="No hay ocupación activa. No se puede hacer checkout sin habitación asignada"
        )

    active_occ = stay.get_active_occupancy()
    primary_room = active_occ.room if active_occ else (stay.occupancies[0].room if stay.occupancies else None)
    
    # =====================================================================
    # 4) CÁLCULO FINANCIERO (usando motor compartido)
    # =====================================================================
    try:
        calc = compute_invoice(
            stay=stay,
            db=db,
            checkout_date_override=req.checkout_real if hasattr(req, "checkout_real") and req.checkout_real else None,
            nights_override=getattr(req, "nights_override", None),
            tarifa_override=getattr(req, "tarifa_override", None),
            discount_pct_override=getattr(req, "discount_pct", None),
            tax_mode_override=getattr(req, "tax_mode", None),
            tax_value_override=getattr(req, "tax_value", None),
        )
    except Exception as e:
        log_event("stays", "sistema", "Check-out - Error de cálculo", f"stay_id={stay_id} error={str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al calcular totales: {str(e)}"
        )
    
    # =====================================================================
    # 5) VALIDACIÓN DE SALDO (si está configurado el bloqueo)
    # =====================================================================
    allow_debt = getattr(req, "allow_close_with_debt", False)
    
    if calc.balance > 0 and not allow_debt:
        raise HTTPException(
            status_code=409,
            detail=f"Saldo pendiente: ${float(calc.balance):.2f}. Para cerrar con deuda, envía allow_close_with_debt=true"
        )
    
    # =====================================================================
    # 6) REGISTRAR PAGO FINAL (si viene en el request)
    # =====================================================================
    if req.pago_monto and req.pago_monto > 0:
        payment = StayPayment(
            stay_id=stay.id,
            monto=Decimal(str(req.pago_monto)),
            metodo=req.pago_metodo or "efectivo",
            referencia=getattr(req, "pago_referencia", None),
            usuario="sistema",
            notas="Pago en checkout",
            timestamp=datetime.utcnow()
        )
        db.add(payment)
        db.flush()
        
        # Recalcular balance con el nuevo pago
        calc.payments_total += Decimal(str(req.pago_monto))
        calc.balance = calc.grand_total - calc.payments_total
    
    # =====================================================================
    # 7) CERRAR OCUPACIONES ACTIVAS
    # =====================================================================
    ahora = datetime.utcnow()
    closed_rooms = []
    
    for occ in stay.occupancies:
        if not occ.hasta:  # Ocupación activa
            occ.hasta = ahora
            
            # Actualizar estado de la habitación
            room = db.query(Room).filter(Room.id == occ.room_id).first()
            if room:
                room.estado_operativo = "limpieza"
                room.updated_at = ahora
                closed_rooms.append({
                    "room_id": room.id,
                    "numero": room.numero,
                    "estado_nuevo": room.estado_operativo
                })
    
    # =====================================================================
    # 8) ACTUALIZAR STAY
    # =====================================================================
    stay.estado = "cerrada"
    stay.checkout_real = ahora
    
    if req.notas:
        stay.notas_internas = (stay.notas_internas or "") + f"\n[Checkout {ahora.date()}] {req.notas}"
    
    stay.updated_at = ahora
    
    # =====================================================================
    # 9) ACTUALIZAR RESERVATION A ESTADO FINAL
    # =====================================================================
    # Si la reserva estaba en "ocupada", pasarla a "finalizada"
    # (Estado final único para reservas que completaron su ciclo)
    if reservation.estado == "ocupada":
        reservation.estado = "finalizada"
        reservation.updated_at = ahora
        log_event("reservations", "sistema", "Reservation finalizada por checkout", f"reservation_id={reservation.id}")
    
    # =====================================================================
    # 10) CREAR TAREA DE HOUSEKEEPING (CHECKOUT) - IDEMPOTENTE
    # =====================================================================
    hk_task_id = None
    if primary_room:
        hk_task = upsert_checkout_task(db, stay, primary_room)
        hk_task_id = hk_task.id
    
    # =====================================================================
    # 11) AUDITORÍA
    # =====================================================================
    audit = AuditEvent(
        entity_type="stay",
        entity_id=stay.id,
        action="CHECKOUT",
        usuario="sistema",
        descripcion=f"Check-out completado",
        payload={
            "reservation_id": reservation.id,
            "reservation_estado_nuevo": reservation.estado,
            "room_subtotal": float(calc.room_subtotal),
            "charges_total": float(calc.charges_total),
            "taxes_total": float(calc.taxes_total),
            "discounts_total": float(calc.discounts_total),
            "grand_total": float(calc.grand_total),
            "payments_total": float(calc.payments_total),
            "balance": float(calc.balance),
            "final_nights": calc.final_nights,
            "housekeeping_task_id": hk_task_id,
            "closed_rooms": closed_rooms,
        }
    )
    db.add(audit)
    
    # =====================================================================
    # 12) COMMIT
    # =====================================================================
    db.commit()
    db.refresh(stay)
    db.refresh(reservation)
    
    log_event("stays", "usuario", "Check-out exitoso", 
              f"stay_id={stay_id} balance={float(calc.balance):.2f} reservation_estado={reservation.estado}")
    
    # =====================================================================
    # 13) RESPUESTA
    # =====================================================================
    return {
        "id": stay.id,
        "estado": stay.estado,
        "checkout_real": stay.checkout_real.isoformat(),
        "reservation_id": reservation.id,
        "reservation_estado": reservation.estado,
        "cliente_nombre": calc.cliente_nombre,
        "totals": {
            "room_subtotal": float(calc.room_subtotal),
            "charges_total": float(calc.charges_total),
            "taxes_total": float(calc.taxes_total),
            "discounts_total": float(calc.discounts_total),
            "grand_total": float(calc.grand_total),
            "payments_total": float(calc.payments_total),
            "balance": float(calc.balance),
        },
        "nights_charged": calc.final_nights,
        "housekeeping_task_id": hk_task_id,
        "warnings": calc.warnings,
        "closed_rooms": closed_rooms,
    }


@router.get("/stays/{stay_id}/summary")
def get_stay_summary(
    stay_id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Obtener resumen completo de una estadía (especialmente para cerradas).
    
    Retorna:
    - Información de la reserva original
    - Fechas (planificadas vs reales)
    - Huéspedes
    - Cargos y pagos
    - Totales
    """
    tenant_id = current_user.empresa_usuario_id
    
    stay = (
        db.query(Stay)
        .options(
            joinedload(Stay.reservation).joinedload(Reservation.guests),
            joinedload(Stay.reservation).joinedload(Reservation.cliente),
            joinedload(Stay.reservation).joinedload(Reservation.empresa),
            joinedload(Stay.occupancies).joinedload(StayRoomOccupancy.room),
            joinedload(Stay.charges),
            joinedload(Stay.payments)
        )
        .filter(
            Stay.id == stay_id,
            Stay.empresa_usuario_id == tenant_id
        )
        .first()
    )
    
    if not stay:
        raise HTTPException(404, "Estadía no encontrada o no pertenece a tu empresa")
        raise HTTPException(status_code=404, detail="Estadía no encontrada")
    
    reservation = stay.reservation
    
    # Información del cliente
    cliente_info = None
    if reservation:
        if reservation.cliente:
            cliente_info = {
                "tipo": "cliente",
                "nombre": f"{reservation.cliente.nombre} {reservation.cliente.apellido}",
                "email": reservation.cliente.email,
                "telefono": reservation.cliente.telefono
            }
        elif reservation.empresa:
            cliente_info = {
                "tipo": "empresa",
                "nombre": reservation.empresa.nombre,
                "cuit": reservation.empresa.cuit,
                "email": reservation.empresa.contacto_email,
                "telefono": reservation.empresa.contacto_telefono
            }
        else:
            cliente_info = {
                "tipo": "temporal",
                "nombre": reservation.nombre_temporal
            }
    
    # Huéspedes
    huespedes = []
    if reservation and reservation.guests:
        huespedes = [
            {
                "nombre": f"{g.nombre} {g.apellido}",
                "documento": g.documento,
                "tipo_documento": g.tipo_documento,
                "rol": g.rol
            }
            for g in reservation.guests
        ]
    
    # Habitaciones
    habitaciones = []
    for occ in stay.occupancies:
        habitaciones.append({
            "numero": occ.room.numero,
            "desde": occ.desde.isoformat() if occ.desde else None,
            "hasta": occ.hasta.isoformat() if occ.hasta else None,
            "motivo": occ.motivo
        })
    
    # Cargos
    cargos = [
        {
            "id": c.id,
            "tipo": c.tipo,
            "descripcion": c.descripcion,
            "cantidad": float(c.cantidad),
            "monto_unitario": float(c.monto_unitario),
            "monto_total": float(c.monto_total),
            "created_at": c.created_at.isoformat() if c.created_at else None
        }
        for c in stay.charges
    ]
    
    # Pagos
    pagos = [
        {
            "id": p.id,
            "monto": float(p.monto),
            "metodo": p.metodo,
            "notas": p.notas,
            "es_reverso": p.es_reverso,
            # Los pagos usan la columna timestamp (no created_at) para el momento de registro
            "created_at": p.timestamp.isoformat() if getattr(p, "timestamp", None) else None
        }
        for p in stay.payments
    ]
    
    # Totales
    total_charges = sum(Decimal(str(c.monto_total)) for c in stay.charges)
    total_payments = sum(Decimal(str(p.monto)) for p in stay.payments if not p.es_reverso)
    saldo = total_charges - total_payments
    
    # Calcular noches
    noches_planificadas = None
    noches_reales = None
    
    if reservation:
        noches_planificadas = (reservation.fecha_checkout - reservation.fecha_checkin).days
    
    if stay.checkin_real and stay.checkout_real:
        noches_reales = (stay.checkout_real.date() - stay.checkin_real.date()).days
    
    return {
        "stay_id": stay.id,
        "estado": stay.estado,
        "cliente": cliente_info,
        "huespedes": huespedes,
        "habitaciones": habitaciones,
        "fechas": {
            "checkin_planificado": reservation.fecha_checkin.isoformat() if reservation else None,
            "checkout_planificado": reservation.fecha_checkout.isoformat() if reservation else None,
            "checkin_real": stay.checkin_real.isoformat() if stay.checkin_real else None,
            "checkout_real": stay.checkout_real.isoformat() if stay.checkout_real else None,
            "noches_planificadas": noches_planificadas,
            "noches_reales": noches_reales
        },
        "financiero": {
            "cargos": cargos,
            "pagos": pagos,
            "total_cargos": float(total_charges),
            "total_pagos": float(total_payments),
            "saldo": float(saldo)
        },
        "notas": stay.notas_internas,
        "reservation_id": reservation.id if reservation else None
    }


# ========================================================================
# ENDPOINTS: CHARGES
# ========================================================================

@router.get("/stays/{stay_id}/charges")
def list_charges(
    stay_id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Listar cargos de una estadía
    """
    tenant_id = current_user.empresa_usuario_id
    
    stay = db.query(Stay).filter(
        Stay.id == stay_id,
        Stay.empresa_usuario_id == tenant_id
    ).first()
    if not stay:
        raise HTTPException(404, "Estadía no encontrada o no pertenece a tu empresa")
    
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
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Agregar cargo a una estadía
    """
    tenant_id = current_user.empresa_usuario_id
    
    stay = db.query(Stay).filter(
        Stay.id == stay_id,
        Stay.empresa_usuario_id == tenant_id
    ).first()
    if not stay:
        raise HTTPException(404, "Estadía no encontrada o no pertenece a tu empresa")
    
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


@router.delete("/stays/{stay_id}/charges/{charge_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_charge(
    stay_id: int = Path(..., gt=0),
    charge_id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Eliminar un cargo (Hard Delete).
    Solo si la estadía NO está cerrada.
    """
    tenant_id = current_user.empresa_usuario_id
    
    stay = db.query(Stay).filter(
        Stay.id == stay_id,
        Stay.empresa_usuario_id == tenant_id
    ).first()
    if not stay:
        raise HTTPException(404, "Estadía no encontrada o no pertenece a tu empresa")
    
    if stay.estado == "cerrada":
        raise HTTPException(409, "No se pueden eliminar cargos de una estadía cerrada")
    
    charge = db.query(StayCharge).filter(StayCharge.id == charge_id, StayCharge.stay_id == stay_id).first()
    if not charge:
        raise HTTPException(404, "Cargo no encontrado")
    
    # Auditoría antes de borrar
    audit = AuditEvent(
        entity_type="stay",
        entity_id=stay_id,
        action="DELETE_CHARGE",
        usuario="sistema",
        descripcion=f"Cargo eliminado: {charge.descripcion}",
        payload={
            "charge_id": charge_id,
            "tipo": charge.tipo,
            "monto": float(charge.monto_total)
        }
    )
    db.add(audit)
    
    db.delete(charge)
    db.commit()
    
    log_event("stays", "sistema", "Eliminar cargo", f"stay_id={stay_id} charge_id={charge_id}")
    return None


@router.post("/stays/{stay_id}/payments", status_code=status.HTTP_201_CREATED)
def add_payment(
    stay_id: int = Path(..., gt=0),
    req: PaymentRequest = ...,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Registrar pago para una estadía
    
    - Crea un StayPayment en la BD
    - NO genera comprobante ni modifica la reserva
    - El frontend es responsable de actualizar invoicePreview después
    """
    tenant_id = current_user.empresa_usuario_id
    
    stay = db.query(Stay).filter(
        Stay.id == stay_id,
        Stay.empresa_usuario_id == tenant_id
    ).first()
    if not stay:
        raise HTTPException(404, "Estadía no encontrada o no pertenece a tu empresa")
    
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

@router.post("/stays/{stay_id}/checkout/preview", response_model=InvoicePreviewResponse)
def preview_checkout_post(
    stay_id: int = Path(..., gt=0),
    req: CheckoutRequest = ...,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    🧾 POST INVOICE PREVIEW (Body params)
    
    Versión POST para aceptar overrides complejos en el body.
    """
    tenant_id = current_user.empresa_usuario_id
    
    # Validar que el stay pertenece al tenant
    stay = db.query(Stay).filter(
        Stay.id == stay_id,
        Stay.empresa_usuario_id == tenant_id
    ).first()
    if not stay:
        raise HTTPException(404, "Estadía no encontrada o no pertenece a tu empresa")
    
    return get_invoice_preview(
        stay_id=stay_id,
        checkout_date=None, # O extraer de req se existe
        nights_override=req.nights_override,
        tarifa_override=req.tarifa_override,
        discount_override_pct=req.discount_override_pct,
        tax_override_mode=req.tax_override_mode,
        tax_override_value=req.tax_override_value,
        surcharge_amount=req.surcharge_amount,
        include_items=True,
        db=db,
        current_user=current_user
    )

@router.get("/stays/{stay_id}/invoice-preview", response_model=InvoicePreviewResponse)
def get_invoice_preview(
    stay_id: int = Path(..., gt=0),
    checkout_date: Optional[str] = Query(None, description="Fecha candidata de checkout (YYYY-MM-DD o ISO)"),
    nights_override: Optional[int] = Query(None, ge=1, description="Override de noches a cobrar (>= 1)"),
    tarifa_override: Optional[float] = Query(None, ge=0, description="Override de tarifa por noche"),
    discount_override_pct: Optional[float] = Query(None, ge=0, le=100, description="Descuento adicional en %"),
    tax_override_mode: Optional[str] = Query(None, description="Modo: 'normal'|'exento'|'custom'"),
    tax_override_value: Optional[float] = Query(None, ge=0, description="Impuesto personalizado"),
    surcharge_amount: Optional[float] = Query(None, ge=0, description="Recargo adicional (ej. forma de pago)"),
    include_items: bool = Query(True, description="Incluir líneas detalladas"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    🧾 INVOICE PREVIEW (Checkout Wizard)
    
    REFACTORIZADO: Usa motor compartido (invoice_engine.compute_invoice)
    
    - NO modifica DB (solo preview)
    - El backend es la fuente de verdad:
      noches, tarifa, impuestos, descuentos, pagos, total y saldo.
    - Retorna estructura completa para el frontend del checkout wizard
    """
    tenant_id = current_user.empresa_usuario_id
    
    # =====================================================================
    # 1) CARGAR STAY
    # =====================================================================
    stay = (
        db.query(Stay)
        .filter(
            Stay.id == stay_id,
            Stay.empresa_usuario_id == tenant_id
        )
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
    
    # =====================================================================
    # 2) CALCULAR USANDO MOTOR COMPARTIDO
    # =====================================================================
    try:
        calc = compute_invoice(
            stay=stay,
            db=db,
            checkout_date_override=checkout_date,
            nights_override=nights_override,
            tarifa_override=tarifa_override,
            discount_pct_override=discount_override_pct,
            tax_mode_override=tax_override_mode,
            tax_value_override=tax_override_value,
        )
    except Exception as e:
        log_event("invoice_preview", "sistema", "Error de cálculo", f"stay_id={stay_id} error={str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al calcular invoice: {str(e)}"
        )
    
    # =====================================================================
    # 3) CONSTRUIR LÍNEAS DETALLADAS (si se solicita)
    # =====================================================================
    breakdown_lines: List[InvoiceLineItem] = []
    
    if include_items:
        # Alojamiento
        breakdown_lines.append(
            InvoiceLineItem(
                line_type="room",
                description=f"Alojamiento - {calc.room_type_name} #{calc.room_numero}",
                quantity=float(calc.final_nights),
                unit_price=float(calc.nightly_rate),
                total=float(calc.room_subtotal),
                metadata={
                    "nights": calc.final_nights,
                    "room_id": calc.room_id,
                    "rate_source": calc.rate_source,
                    "checkin_date": calc.checkin_date.isoformat() if calc.checkin_date else None,
                    "checkout_candidate": calc.checkout_candidate_date.isoformat() if calc.checkout_candidate_date else None,
                },
            )
        )
        
        # Cargos/Consumos
        for charge_item in calc.charges_breakdown:
            breakdown_lines.append(
                InvoiceLineItem(
                    line_type=charge_item["type"],
                    description=charge_item["description"],
                    quantity=charge_item["quantity"],
                    unit_price=charge_item["unit_price"],
                    total=charge_item["total"],
                    metadata={"charge_id": charge_item.get("charge_id")},
                )
            )
        
        # Impuestos (si hay)
        if calc.taxes_total > 0:
            breakdown_lines.append(
                InvoiceLineItem(
                    line_type="tax",
                    description="Impuestos (IVA/fees)",
                    quantity=1.0,
                    unit_price=float(calc.taxes_total),
                    total=float(calc.taxes_total),
                    metadata={"tax_mode": tax_override_mode or "auto"},
                )
            )
        
        # Descuentos (si hay)
        if calc.discounts_total > 0:
            breakdown_lines.append(
                InvoiceLineItem(
                    line_type="discount",
                    description="Descuentos aplicados",
                    quantity=1.0,
                    unit_price=-float(calc.discounts_total),
                    total=-float(calc.discounts_total),
                    metadata={"discount_pct": discount_override_pct},
                )
            )
        
        # Recargos (si hay)
        if surcharge_amount and surcharge_amount > 0:
            breakdown_lines.append(
                InvoiceLineItem(
                    line_type="surcharge",
                    description="Recargo (forma de pago, cuotas, etc.)",
                    quantity=1.0,
                    unit_price=float(surcharge_amount),
                    total=float(surcharge_amount),
                    metadata={"surcharge_applied": True},
                )
            )
        
        # Pagos
        for payment_item in calc.payments_breakdown:
            breakdown_lines.append(
                InvoiceLineItem(
                    line_type="payment",
                    description=f"Pago ({payment_item['metodo']})",
                    quantity=1.0,
                    unit_price=-payment_item['monto'],
                    total=-payment_item['monto'],
                    metadata={
                        "payment_id": payment_item.get("id"),
                        "referencia": payment_item.get("referencia"),
                    },
                )
            )
    
    # =====================================================================
    # 4) CONSTRUIR WARNINGS PARA UI
    # =====================================================================
    warnings_list = []
    for w in calc.warnings:
        warnings_list.append(
            InvoiceWarning(
                code=w["code"],
                message=w["message"],
                severity=w["severity"],
            )
        )
    
    # =====================================================================
    # 5) RESPUESTA
    # =====================================================================
    return InvoicePreviewResponse(
        stay_id=stay_id,
        reservation_id=reservation.id,
        cliente_nombre=calc.cliente_nombre,
        currency="ARS",
        period=InvoicePeriod(
            checkin_real=(stay.checkin_real.isoformat() if stay.checkin_real else 
                         datetime.combine(calc.checkin_date, datetime.min.time()).isoformat()),
            checkout_candidate=calc.checkout_candidate_date.isoformat(),
            checkout_planned=calc.checkout_planned_date.isoformat(),
        ),
        nights=InvoiceNights(
            planned=calc.planned_nights,
            calculated=calc.calculated_nights,
            suggested_to_charge=max(1, calc.calculated_nights) if not calc.readonly else max(0, calc.calculated_nights),
            override_applied=calc.nights_override_applied,
            override_value=nights_override,
        ),
        room=InvoiceRoom(
            room_id=calc.room_id,
            numero=calc.room_numero,
            room_type_name=calc.room_type_name,
            nightly_rate=float(calc.nightly_rate),
            rate_source=calc.rate_source,
            is_overstay=calc.is_overstay,
            overstay_nights=calc.overstay_nights,
            overstay_charge=round(float(calc.overstay_charge), 2),
        ),
        breakdown_lines=breakdown_lines,
        totals=InvoiceTotals(
            room_subtotal=round(float(calc.room_subtotal), 2),
            charges_total=round(float(calc.charges_total), 2),
            taxes_total=round(float(calc.taxes_total), 2),
            discounts_total=round(float(calc.discounts_total), 2),
            grand_total=round(float(calc.grand_total + Decimal(str(surcharge_amount or 0))), 2),
            payments_total=round(float(calc.payments_total), 2),
            balance=round(float(calc.balance + Decimal(str(surcharge_amount or 0))), 2),
        ),
        payments=calc.payments_breakdown if include_items else [],
        warnings=warnings_list,
        readonly=calc.readonly,
        generated_at=datetime.utcnow().isoformat(),
    )


@router.post("/stays/{stay_id}/checkout/confirm", response_model=CheckoutResult)
def confirm_checkout(
    stay_id: int = Path(..., gt=0),
    req: CheckoutRequest = ...,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    ✅ CONFIRMAR CHECKOUT
    """
    tenant_id = current_user.empresa_usuario_id
    
    # 1. Validar Stay
    stay = db.query(Stay).filter(
        Stay.id == stay_id,
        Stay.empresa_usuario_id == tenant_id
    ).first()
    if not stay:
        raise HTTPException(404, "Stay no encontrado o no pertenece a tu empresa")
        
    if stay.estado == "cerrada":
        raise HTTPException(409, "Estadía ya cerrada")

    reservation = stay.reservation
    if not reservation:
        raise HTTPException(400, "Stay sin reserva asociada")

    if req.empresa_id is not None:
        empresa = _get_active_empresa_or_404(db, req.empresa_id, tenant_id)
        reservation.empresa_id = empresa.id
        reservation.empresa = empresa
        reservation.updated_at = datetime.utcnow()

    # 2. Validar Retroactive Time
    actual_checkout_at = datetime.now() # Default server time
    audit_notes = ""
    
    if req.retroactive_time:
        try:
            retro_dt = datetime.fromisoformat(req.retroactive_time.replace("Z", "+00:00"))
            # Validate not in future (allow 5 min drift)
            if retro_dt > datetime.now() + timedelta(minutes=5):
                 raise HTTPException(400, "La fecha retroactiva no puede ser futura")
            
            actual_checkout_at = retro_dt
            
            if not req.audit_reason:
                 raise HTTPException(400, "Debe especificar un motivo para checkout retroactivo")
            
            audit_notes = f" [RETROACTIVO: {req.retroactive_time} | Motivo: {req.audit_reason}]"
            
        except ValueError:
             raise HTTPException(400, "Formato de fecha invalido")

    # 3. Calcular Invoice Final (Persistir overrides)
    try:
        calc = compute_invoice(
            stay=stay,
            db=db,
            checkout_date_override=req.retroactive_time, # Pass override to engine
            nights_override=req.nights_override,
            tarifa_override=req.tarifa_override,
            discount_pct_override=req.discount_override_pct,
            tax_mode_override=req.tax_override_mode,
            tax_value_override=req.tax_override_value,
        )
    except Exception as e:
        raise HTTPException(500, f"Error cálculo final: {e}")

    # 4. Aplicar recargo adicional si existe
    surcharge_amount = Decimal(str(req.surcharge_amount)) if req.surcharge_amount else Decimal('0')
    final_grand_total = calc.grand_total + surcharge_amount
    final_balance = calc.balance + surcharge_amount
    
    # 5. Validar Deuda
    if final_balance > 0.01 and not req.allow_close_with_debt:
        raise HTTPException(409, f"No se puede cerrar con saldo pendiente ({final_balance}). Registre pago o autorice deuda.")
    
    if final_balance > 0.01 and req.allow_close_with_debt and not req.debt_reason:
        raise HTTPException(400, "Debe especificar motivo de deuda")

    # 6. ACTUALIZAR STAY (Cerrar)
    stay.checkout_real = actual_checkout_at
    stay.estado = "cerrada"
    stay.updated_at = datetime.now()
    
    # 6. Guardar Invoice Snapshot / Charges (Si el engine no lo hiciera, pero aqui asumimos que compute_invoice es solo calc)
    # Debemos persistir los cargos CALCULADOS si son dinámicos (e.g. Alojamiento)
    # En este sistema, los cargos de alojamiento se generan dinamicamente o se deben materializar al cierre.
    # Asumimos que debemos MATERIALIZAR el cargo de habitacion final.
    
    # Buscar si ya existe cargo de habitacion, si no, crearlo.
    # ... (Simplificacion: Asumimos que compute_invoice retorna lo que deberia haber. 
    # Lo correcto es upsert del cargo de alojamiento)
    
    # -> Materializar Cargo Alojamiento Final
    room_charge = db.query(StayCharge).filter(StayCharge.stay_id == stay.id, StayCharge.tipo == "room_revenue").first()
    if not room_charge:
        room_charge = StayCharge(
            stay_id=stay.id,
            tipo="room_revenue",
            descripcion=f"Alojamiento {calc.final_nights} noches",
            cantidad=calc.final_nights,
            monto_unitario=calc.nightly_rate,
            monto_total=calc.room_subtotal,
            creado_por="sistema_checkout"
        )
        db.add(room_charge)
    else:
        # Actualizar existente
        room_charge.cantidad = calc.final_nights
        room_charge.monto_unitario = calc.nightly_rate
        room_charge.monto_total = calc.room_subtotal
        room_charge.descripcion = f"Alojamiento {calc.final_nights} noches"

    # Agregar recargo adicional como cargo si existe
    if surcharge_amount > 0:
        surcharge_charge = db.query(StayCharge).filter(
            StayCharge.stay_id == stay.id, 
            StayCharge.tipo == "surcharge"
        ).first()
        
        if not surcharge_charge:
            surcharge_charge = StayCharge(
                stay_id=stay.id,
                tipo="surcharge",
                descripcion="Recargo adicional (forma de pago)",
                cantidad=1,
                monto_unitario=surcharge_amount,
                monto_total=surcharge_amount,
                creado_por="sistema_checkout"
            )
            db.add(surcharge_charge)
        else:
            surcharge_charge.monto_unitario = surcharge_amount
            surcharge_charge.monto_total = surcharge_amount

    # Persistir descuentos/impuestos como items si es necesario (omitido por brevedad, asumimos engine simple)

    # 7. Generar Auditoría
    audit = AuditEvent(
        entity_type="stay",
        entity_id=stay_id,
        action="CHECKOUT_CONFIRMED" if not req.retroactive_time else "RETROACTIVE_CHECKOUT",
        usuario="sistema", # TODO: Get user
        descripcion=f"Checkout completado.{audit_notes}",
        payload={
            "checkout_real": actual_checkout_at.isoformat(),
            "grand_total": float(final_grand_total),
            "surcharge": float(surcharge_amount),
            "balance": float(final_balance),
            "overrides": req.dict(exclude_none=True)
        }
    )
    db.add(audit)
    
    # 8. Housekeeping + Estado de habitaciones
    ahora = datetime.utcnow()
    for occ in stay.occupancies:
        if occ.room:
            if req.housekeeping:
                # Marcar habitación como "limpieza" (pendiente de housekeeping)
                occ.room.estado_operativo = "limpieza"
            else:
                # Sin housekeeping: marcar como disponible
                occ.room.estado_operativo = "disponible"
            occ.room.updated_at = ahora
    
    # Generar tarea de housekeeping si está habilitada
    if req.housekeeping:
        try:
            generate_checkout_tasks(stay, db)
            db.flush()  # Forzar escritura para capturar UniqueViolation aquí
        except Exception as e:
            # Si ya existe la tarea (checkout duplicado), continuar
            if "uq_hk_task_daily" in str(e) or "UniqueViolation" in str(e):
                db.rollback()  # Revertir solo esta operación
                log_event("checkout", current_user.username, 
                         "Tarea housekeeping ya existe", 
                         f"stay_id={stay_id}, ignorando duplicado")
            else:
                # Otro error, re-lanzar
                raise
    
    # 9. CREAR TRANSACCIONES EN CAJA (una por cada pago realizado)
    # Buscar o crear categoría "Venta de Habitación"
    from models.core import TransactionCategory, Transaction, TransactionType, PaymentMethod
    
    categoria_venta = db.query(TransactionCategory).filter(
        TransactionCategory.empresa_usuario_id == tenant_id,
        TransactionCategory.nombre == "Venta de Habitación",
        TransactionCategory.tipo == TransactionType.INGRESO.value
    ).first()
    
    if not categoria_venta:
        # Crear categoría del sistema si no existe
        categoria_venta = TransactionCategory(
            empresa_usuario_id=tenant_id,
            nombre="Venta de Habitación",
            tipo=TransactionType.INGRESO.value,
            descripcion="Ingresos por alojamiento",
            activo=True,
            es_sistema=True
        )
        db.add(categoria_venta)
        db.flush()
    
    # Mapeo de métodos de pago de StayPayment a Transaction
    metodo_map = {
        "efectivo": PaymentMethod.EFECTIVO.value,
        "tarjeta": PaymentMethod.TARJETA.value,
        "tarjeta_credito": PaymentMethod.TARJETA_CREDITO.value,
        "tarjeta_debito": PaymentMethod.TARJETA_DEBITO.value,
        "transferencia": PaymentMethod.TRANSFERENCIA.value,
        "qr": PaymentMethod.QR.value,
        "cheque": PaymentMethod.CHEQUE.value
    }
    
    # Preparar breakdown compartido para todas las transacciones
    breakdown = [
        {"description": f"Alojamiento - {calc.final_nights} noches", "amount": float(calc.room_subtotal)},
    ]
    
    # Agregar cargos
    if calc.charges_total > 0:
        breakdown.append({"description": "Consumos y cargos", "amount": float(calc.charges_total)})
    
    # Agregar descuentos
    if calc.discounts_total > 0:
        breakdown.append({"description": "Descuentos", "amount": -float(calc.discounts_total)})
    
    # Agregar recargo
    if surcharge_amount and surcharge_amount > 0:
        breakdown.append({"description": "Recargo (pago, cuotas, etc.)", "amount": float(surcharge_amount)})
    
    # Agregar impuestos
    if calc.taxes_total > 0:
        breakdown.append({"description": "Impuestos", "amount": float(calc.taxes_total)})
    
    # Crear una transacción por cada pago realizado
    if stay.payments:
        for payment in stay.payments:
            if payment.es_reverso:
                continue  # Saltar pagos revertidos
            
            metodo_pago = metodo_map.get(payment.metodo, "otro")
            
            ingreso_transaction = Transaction(
                empresa_usuario_id=tenant_id,
                tipo=TransactionType.INGRESO.value,
                category_id=categoria_venta.id,
                monto=payment.monto,
                metodo_pago=metodo_pago,
                referencia=payment.referencia or f"Stay #{stay.id} - Reserva #{reservation.id}",
                fecha=actual_checkout_at,
                usuario_id=current_user.id,
                stay_id=stay.id,
                cliente_id=reservation.cliente_id,
                notas=f"Pago {metodo_pago} - Checkout Stay #{stay.id}" + (f" - {payment.notas}" if payment.notas else ""),
                es_automatica=True,
                metadata_json={
                    "breakdown": breakdown,
                    "payment_id": payment.id,
                    "is_partial": len([p for p in stay.payments if not p.es_reverso]) > 1
                }
            )
            db.add(ingreso_transaction)
    else:
        # Si no hay pagos registrados, crear transacción por el total (efectivo por defecto)
        ingreso_transaction = Transaction(
            empresa_usuario_id=tenant_id,
            tipo=TransactionType.INGRESO.value,
            category_id=categoria_venta.id,
            monto=final_grand_total,
            metodo_pago=PaymentMethod.EFECTIVO.value,
            referencia=f"Stay #{stay.id} - Reserva #{reservation.id}",
            fecha=actual_checkout_at,
            usuario_id=current_user.id,
            stay_id=stay.id,
            cliente_id=reservation.cliente_id,
            notas=f"Ingreso automático por checkout: {calc.final_nights} noches a {calc.nightly_rate}/noche" + (f" + recargo ${surcharge_amount}" if surcharge_amount > 0 else ""),
            es_automatica=True,
            metadata_json={"breakdown": breakdown}
        )
        db.add(ingreso_transaction)

    db.commit()
    
    # Convert InvoiceCalculation to InvoicePreviewResponse
    breakdown_lines = [
        InvoiceLineItem(
            line_type="charge",
            description=charge.get("descripcion", ""),
            quantity=charge.get("cantidad", 1),
            unit_price=charge.get("monto_unitario", 0),
            total=charge.get("monto_total", 0)
        )
        for charge in calc.charges_breakdown
    ]
    
    warnings_list = [
        InvoiceWarning(
            code=w.get("code", "generic_warning"),
            message=w.get("message", ""),
            severity=w.get("severity", "warning"),
        )
        for w in calc.warnings
    ]
    
    nights_override = None
    if calc.nights_override_applied:
        nights_override = calc.final_nights
    
    invoice_response = InvoicePreviewResponse(
        stay_id=stay_id,
        reservation_id=reservation.id,
        cliente_nombre=calc.cliente_nombre,
        empresa_id=req.empresa_id,
        empresa_nombre=None,
        empresa_contacto=None,
        currency="ARS",
        period=InvoicePeriod(
            checkin_real=(stay.checkin_real.isoformat() if stay.checkin_real else 
                         datetime.combine(calc.checkin_date, datetime.min.time()).isoformat()),
            checkout_candidate=calc.checkout_candidate_date.isoformat(),
            checkout_planned=calc.checkout_planned_date.isoformat(),
        ),
        nights=InvoiceNights(
            planned=calc.planned_nights,
            calculated=calc.calculated_nights,
            suggested_to_charge=max(1, calc.calculated_nights),
            override_applied=calc.nights_override_applied,
            override_value=nights_override,
        ),
        room=InvoiceRoom(
            room_id=calc.room_id,
            numero=calc.room_numero,
            room_type_name=calc.room_type_name,
            nightly_rate=float(calc.nightly_rate),
            rate_source=calc.rate_source,
            is_overstay=calc.is_overstay,
            overstay_nights=calc.overstay_nights,
            overstay_charge=round(float(calc.overstay_charge), 2),
        ),
        breakdown_lines=breakdown_lines,
        totals=InvoiceTotals(
            room_subtotal=round(float(calc.room_subtotal), 2),
            charges_total=round(float(calc.charges_total), 2),
            taxes_total=round(float(calc.taxes_total), 2),
            discounts_total=round(float(calc.discounts_total), 2),
            grand_total=round(float(final_grand_total), 2),
            payments_total=round(float(calc.payments_total), 2),
            balance=round(float(final_balance), 2),
        ),
        payments=calc.payments_breakdown,
        warnings=warnings_list,
        readonly=True,
        generated_at=datetime.utcnow().isoformat(),
    )
    
    return CheckoutResult(
        success=True,
        message="Checkout exitoso",
        stay_id=stay.id,
        stay_status="cerrada",
        reservation_status="finalizada",
        invoice=invoice_response
    )


@router.post("/stays/{stay_id}/checkout/stay", response_model=CheckoutResult)
def checkout_stay(
    stay_id: int = Path(..., gt=0),
    req: CheckoutRequest = ...,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    📝 CHECKOUT DE ESTADÍA (Sin confirmar)
    Retorna preview del cierre sin persistir cambios.
    """
    tenant_id = current_user.empresa_usuario_id
    
    stay = (
        db.query(Stay)
        .filter(
            Stay.id == stay_id,
            Stay.empresa_usuario_id == tenant_id
        )
        .options(
            joinedload(Stay.reservation),
            joinedload(Stay.occupancies).joinedload(StayRoomOccupancy.room).joinedload(Room.tipo),
            joinedload(Stay.charges),
            joinedload(Stay.payments),
        )
        .first()
    )
    if not stay:
        raise HTTPException(404, "Stay no encontrado o no pertenece a tu empresa")

    # 1. Idempotencia
    if stay.estado == "cerrada":
        calc = compute_invoice(stay, db)
        invoice = _build_preview_response(stay, calc, None, None)
        return CheckoutResult(
            success=True,
            message="La estadía ya estaba cerrada.",
            stay_id=stay.id,
            stay_status=stay.estado,
            reservation_status=stay.reservation.estado if stay.reservation else "desconocido",
            invoice=invoice
        )
    
    # 2. Validación de Estado
    if stay.estado not in ["ocupada", "pendiente_checkout"]:
        raise HTTPException(409, f"No se puede hacer checkout de estadía en estado '{stay.estado}'")

    # 3. Recalculo con Overrides
    try:
        calc = compute_invoice(
            stay=stay,
            db=db,
            nights_override=req.nights_override,
            tarifa_override=req.tarifa_override,
            discount_pct_override=req.discount_override_pct,
            tax_mode_override=req.tax_override_mode,
            tax_value_override=req.tax_override_value,
        )
    except Exception as e:
        raise HTTPException(500, f"Error calculando totales: {e}")

    # 4. Validar Warnings Bloqueantes
    blocking = [w for w in calc.warnings if w["severity"] == "error"]
    if blocking:
        raise HTTPException(409, f"No se puede cerrar por errores: {blocking[0]['message']}")

    # 5. Regla de Deuda (con tolerancia)
    balance = float(calc.balance)
    if balance > 0.01:
        if not req.allow_close_with_debt:
            raise HTTPException(409, f"Saldo pendiente de ${balance:.2f}. Debe pagar o autorizar cierre con deuda.")
        if not req.debt_reason:
            raise HTTPException(422, "Debe especificar 'debt_reason' para cerrar con deuda.")

    # 6. COMMIT
    ahora = datetime.utcnow()
    
    # Stay
    stay.estado = "cerrada"
    stay.checkout_real = ahora
    if req.notes:
        stay.notas_internas = (stay.notas_internas or "") + f"\n[Checkout Confirmado] {req.notes}"
    stay.updated_at = ahora

    # Ocupaciones
    closed_rooms_info = []
    for occ in stay.occupancies:
        if not occ.hasta:
            occ.hasta = ahora
            if occ.room:
                occ.room.estado_operativo = "limpieza"
                occ.room.updated_at = ahora
                closed_rooms_info.append(occ.room.numero)

    # Reserva
    if stay.reservation:
        stay.reservation.estado = "finalizada"
        stay.reservation.updated_at = ahora
    
    # Housekeeping
    hk_task_id = None
    if req.housekeeping and closed_rooms_info:
        # Tarea manual simple
        primary_occ = stay.occupancies[0] if stay.occupancies else None
        if primary_occ:
            new_task = HousekeepingTask(
                room_id=primary_occ.room_id,
                stay_id=stay.id,
                task_date=ahora.date(),
                task_type="checkout",
                status="pending",
                priority="alta"
            )
            db.add(new_task)
            db.flush()
            hk_task_id = new_task.id

    # Auditoría
    audit = AuditEvent(
        entity_type="stay",
        entity_id=stay.id,
        action="CHECKOUT_CONFIRM",
        usuario="sistema",
        descripcion="Checkout confirmado",
        payload={
            "balance": balance,
            "closed_with_debt": balance > 0.01,
            "debt_reason": req.debt_reason,
            "overrides": {
                "nights": req.nights_override,
                "rate": req.tarifa_override,
                "discount": req.discount_override_pct
            }
        }
    )
    db.add(audit)

    db.commit()
    db.refresh(stay)

    final_invoice = _build_preview_response(stay, calc, req.discount_override_pct, req.tax_override_mode)
    
    return CheckoutResult(
        success=True,
        message="Checkout realizado correctamente.",
        stay_id=stay.id,
        stay_status=stay.estado,
        reservation_status=stay.reservation.estado if stay.reservation else "unknown",
        invoice=final_invoice,
        housekeeping_task_id=hk_task_id
    )


def _build_preview_response(stay, calc, discount_override_pct, tax_override_mode) -> InvoicePreviewResponse:
    # Helper simple para no duplicar toda la lógica de construcción de respuesta
    breakdown_lines = []

    # Empresa asociada (si existe)
    reservation = getattr(stay, "reservation", None)
    empresa = getattr(reservation, "empresa", None)
    empresa_contacto = None
    if empresa:
        empresa_contacto = EmpresaContactInfo(
            nombre=empresa.contacto_nombre,
            email=empresa.contacto_email,
            telefono=empresa.contacto_telefono,
        )
    
    # Room
    breakdown_lines.append(InvoiceLineItem(
        line_type="room",
        description=f"Alojamiento - {calc.room_type_name} #{calc.room_numero}",
        quantity=float(calc.final_nights),
        unit_price=float(calc.nightly_rate),
        total=float(calc.room_subtotal),
        metadata={
            "nights": calc.final_nights, 
            "room_id": calc.room_id,
            "rate_source": calc.rate_source
        }
    ))
    
    # Charges
    for charge in calc.charges_breakdown:
        breakdown_lines.append(InvoiceLineItem(
            line_type=charge["type"],
            description=charge["description"],
            quantity=charge["quantity"],
            unit_price=charge["unit_price"],
            total=charge["total"],
            metadata={"charge_id": charge.get("charge_id")}
        ))
        
    # Taxes
    if calc.taxes_total > 0:
        breakdown_lines.append(InvoiceLineItem(
            line_type="tax",
            description="Impuestos",
            quantity=1.0,
            unit_price=float(calc.taxes_total),
            total=float(calc.taxes_total),
            metadata={"tax_mode": tax_override_mode or "auto"}
        ))
        
    # Discounts
    if calc.discounts_total > 0:
        breakdown_lines.append(InvoiceLineItem(
            line_type="discount",
            description="Descuentos",
            quantity=1.0,
            unit_price=-float(calc.discounts_total),
            total=-float(calc.discounts_total),
            metadata={"discount_pct": discount_override_pct}
        ))
        
    # Payments
    for p in calc.payments_breakdown:
        breakdown_lines.append(InvoiceLineItem(
            line_type="payment",
            description=f"Pago ({p['metodo']})",
            quantity=1.0,
            unit_price=-p['monto'],
            total=-p['monto'],
            metadata={"payment_id": p.get("id"), "referencia": p.get("referencia")}
        ))
        
    warnings_list = [
        InvoiceWarning(code=w["code"], message=w["message"], severity=w["severity"])
        for w in calc.warnings
    ]
    
    return InvoicePreviewResponse(
        stay_id=stay.id,
        reservation_id=stay.reservation_id,
        cliente_nombre=calc.cliente_nombre,
        empresa_id=empresa.id if empresa else None,
        empresa_nombre=empresa.nombre if empresa else None,
        empresa_contacto=empresa_contacto,
        currency="ARS",
        period=InvoicePeriod(
            checkin_real=stay.checkin_real.isoformat() if stay.checkin_real else datetime.utcnow().isoformat(),
            checkout_candidate=calc.checkout_candidate_date.isoformat(),
            checkout_planned=calc.checkout_planned_date.isoformat()
        ),
        nights=InvoiceNights(
            planned=calc.planned_nights,
            calculated=calc.calculated_nights,
            suggested_to_charge=max(1, calc.calculated_nights) if not calc.readonly else max(0, calc.calculated_nights),
            override_applied=calc.nights_override_applied,
            override_value=None 
        ),
        room=InvoiceRoom(
            room_id=calc.room_id,
            numero=calc.room_numero,
            room_type_name=calc.room_type_name,
            nightly_rate=float(calc.nightly_rate),
            rate_source=calc.rate_source,
            is_overstay=calc.is_overstay,
            overstay_nights=calc.overstay_nights,
            overstay_charge=round(float(calc.overstay_charge), 2),
        ),
        breakdown_lines=breakdown_lines,
        totals=InvoiceTotals(
            room_subtotal=round(float(calc.room_subtotal), 2),
            charges_total=round(float(calc.charges_total), 2),
            taxes_total=round(float(calc.taxes_total), 2),
            discounts_total=round(float(calc.discounts_total), 2),
            grand_total=round(float(calc.grand_total), 2),
            payments_total=round(float(calc.payments_total), 2),
            balance=round(float(calc.balance), 2)
        ),
        payments=calc.payments_breakdown,
        warnings=warnings_list,
        readonly=calc.readonly,
        generated_at=datetime.utcnow().isoformat()
    )


# ========================================================================
# ENDPOINTS: PRODUCTOS/SERVICIOS (opcional)
# ========================================================================

@router.get("/productos-servicios", response_model=List[ProductoServicioResponse])
def list_productos_servicios(
    include_inactive: bool = Query(False, description="Incluir inactivos"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    tenant_id = current_user.empresa_usuario_id
    
    query = db.query(ProductoServicio).filter(
        ProductoServicio.empresa_usuario_id == tenant_id
    ).order_by(ProductoServicio.actualizado_en.desc())
    if not include_inactive:
        query = query.filter(ProductoServicio.activo.is_(True))
    return query.all()


@router.post("/productos-servicios", response_model=ProductoServicioResponse, status_code=status.HTTP_201_CREATED)
def create_producto_servicio(
    payload: ProductoServicioCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    tenant_id = current_user.empresa_usuario_id
    
    nuevo = ProductoServicio(
        nombre=payload.nombre,
        tipo=payload.tipo,
        descripcion=payload.descripcion,
        precio_unitario=payload.precio_unitario,
        activo=payload.activo if payload.activo is not None else True,
        actualizado_por=getattr(current_user, "username", None),
        empresa_usuario_id=tenant_id
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    username = getattr(current_user, "username", "sistema")
    log_event("PRODUCTOS", username, "Crear producto/servicio", f"id={nuevo.id} nombre={nuevo.nombre}")
    return nuevo


@router.put("/productos-servicios/{producto_id}", response_model=ProductoServicioResponse)
def update_producto_servicio(
    producto_id: int = Path(..., gt=0),
    payload: ProductoServicioUpdate = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    tenant_id = current_user.empresa_usuario_id
    
    producto = db.query(ProductoServicio).filter(
        ProductoServicio.id == producto_id,
        ProductoServicio.empresa_usuario_id == tenant_id
    ).first()
    if not producto:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto/servicio no encontrado o no pertenece a tu empresa")

    data = payload.dict(exclude_unset=True)
    for key, value in data.items():
        setattr(producto, key, value)
    producto.actualizado_por = getattr(current_user, "username", None)

    db.commit()
    db.refresh(producto)
    username = getattr(current_user, "username", "sistema")
    log_event("PRODUCTOS", username, "Actualizar producto/servicio", f"id={producto.id}")
    return producto


@router.delete("/productos-servicios/{producto_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_producto_servicio(
    producto_id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    tenant_id = current_user.empresa_usuario_id
    
    producto = db.query(ProductoServicio).filter(
        ProductoServicio.id == producto_id,
        ProductoServicio.empresa_usuario_id == tenant_id
    ).first()
    if not producto:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto/servicio no encontrado o no pertenece a tu empresa")

    producto.activo = False
    producto.actualizado_por = getattr(current_user, "username", None)
    db.commit()
    username = getattr(current_user, "username", "sistema")
    log_event("PRODUCTOS", username, "Eliminar producto/servicio", f"id={producto.id}")
    return None


@router.get("/clients/search-by-doc")
def search_client_by_doc(
    doc: str = Query(..., min_length=3),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Buscar un cliente por documento.
    """
    tenant_id = current_user.empresa_usuario_id

    cliente = db.query(Cliente).filter(
        Cliente.numero_documento == doc,
        Cliente.empresa_usuario_id == tenant_id
    ).first()
    
    if not cliente:
        return None 
        
    stays_count = (
        db.query(func.count(Stay.id))
        .join(Reservation, Reservation.id == Stay.reservation_id)
        .filter(
            Reservation.cliente_id == cliente.id,
            Reservation.empresa_usuario_id == tenant_id,
            Stay.estado == 'cerrada'
        )
        .scalar()
    )
    
    last_stay = (
        db.query(Stay)
        .join(Reservation, Reservation.id == Stay.reservation_id)
        .filter(
            Reservation.cliente_id == cliente.id,
            Reservation.empresa_usuario_id == tenant_id,
            Stay.estado == 'cerrada'
        )
        .order_by(Stay.checkout_real.desc())
        .first()
    )

    return {
        "found": True,
        "id": cliente.id,
        "nombre": cliente.nombre,
        "apellido": cliente.apellido,
        "documento": cliente.numero_documento,
        "tipo_documento": cliente.tipo_documento,
        "history": {
            "total_stays": stays_count or 0,
            "last_stay_date": last_stay.checkout_real.isoformat() if last_stay and last_stay.checkout_real else None,
            "blacklist": cliente.blacklist,
            "motivo_blacklist": cliente.motivo_blacklist
        }
    }

