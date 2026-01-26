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
    DailyRate, RatePlan, AuditEvent, Cliente, Empresa,
    HousekeepingTask
)
from models import Usuario
from utils.logging_utils import log_event
from utils.invoice_engine import compute_invoice


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
# 🧽 HOUSEKEEPING ENDPOINTS
# ========================================================================

class HousekeepingTaskPatchRequest(BaseModel):
    status: Optional[str] = None  # pending | in_progress | done | skipped
    assigned_to_user_id: Optional[int] = None
    notes: Optional[str] = None
    meta: Optional[dict] = None

class HousekeepingTaskCreateRequest(BaseModel):
    room_id: int
    task_date: Optional[str] = None  # YYYY-MM-DD
    task_names: List[str]  # Lista de tareas (ej: ["Cambiar sábanas", "Minibar"])
    description: Optional[str] = None
    priority: str = "media" # baja | media | alta | urgente
    status: str = "pending"
    assigned_to_user_id: Optional[int] = None
    meta: Optional[dict] = None
    block_room: bool = True  # If true, set room state to 'limpieza'

class IncidentReportRequest(BaseModel):
    room_id: int
    task_id: Optional[int] = None
    tipo: str # rotura, falla_electrica, plomeria, etc.
    descripcion: str
    gravedad: str = "media" # baja, media, alta

class LostItemReportRequest(BaseModel):
    room_id: int
    task_id: Optional[int] = None
    descripcion: str
    lugar: Optional[str] = None

@router.post("/housekeeping/tasks", status_code=status.HTTP_201_CREATED)
def create_housekeeping_task(
    req: HousekeepingTaskCreateRequest,
    db: Session = Depends(get_db)
):
    """Crear una tarea agrupada (un registro) con lista de sub-tareas en meta.task_list."""
    room = db.query(Room).filter(Room.id == req.room_id).first()
    if not room:
        raise HTTPException(404, "Habitación no encontrada")

    if not req.task_names:
        raise HTTPException(400, "Se requiere al menos una tarea")

    task_date = datetime.fromisoformat(req.task_date).date() if req.task_date else datetime.utcnow().date()

    meta = req.meta or {}
    meta["task_list"] = req.task_names
    if req.description:
        meta["description"] = req.description
    meta.setdefault("source", "supervisor_manual")

    # Siempre un solo registro por request: título amigable
    title = req.task_names[0] if len(req.task_names) == 1 else f"{len(req.task_names)} tareas programadas"

    new_task = HousekeepingTask(
        room_id=req.room_id,
        task_date=task_date,
        task_type=title,
        status=req.status,
        priority=req.priority,
        assigned_to_user_id=req.assigned_to_user_id,
        notes=req.description,
        meta=meta
    )
    db.add(new_task)

    if req.block_room and room.estado_operativo == "disponible":
        room.estado_operativo = "limpieza"
        room.updated_at = datetime.utcnow()

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error al guardar tareas: {str(e)}")
    
    return {
        "id": new_task.id,
        "task_name": new_task.task_type,
        "priority": new_task.priority,
        "status": new_task.status,
        "room_id": new_task.room_id,
        "room_numero": room.numero,
        "task_list": meta.get("task_list", [])
    }

# Configuración: Hora de generación de limpieza diaria (ej: 10 AM)
HOUSEKEEPING_DAILY_GEN_HOUR = 10

def _get_is_high_priority(db: Session, room_id: int, target_date: date) -> bool:
    """Detecta si hay un check-in pendiente para hoy en esta habitación"""
    incoming = (
        db.query(Reservation)
        .join(ReservationRoom)
        .filter(
            ReservationRoom.room_id == room_id,
            Reservation.fecha_checkin == target_date,
            Reservation.estado.in_(["confirmada", "draft"])
        )
        .first()
    )
    return incoming is not None

def _auto_generate_daily_tasks(db: Session, target_date: date):
    """Lógica interna para generar tareas diarias faltantes para habitaciones ocupadas"""
    now = datetime.utcnow()
    # Solo generar si ya pasamos la hora configurada (o si se fuerza, pero aquí automatizamos)
    # if now.hour < HOUSEKEEPING_DAILY_GEN_HOUR: return

    occ_rooms = (
        db.query(StayRoomOccupancy.room_id, Stay.id.label("stay_id"), Stay.reservation_id)
        .join(Stay, Stay.id == StayRoomOccupancy.stay_id)
        .filter(
            Stay.estado.in_(["ocupada", "pendiente_checkout"]),
            StayRoomOccupancy.desde < datetime.combine(target_date + timedelta(days=1), datetime.min.time()),
            or_(StayRoomOccupancy.hasta.is_(None), StayRoomOccupancy.hasta > datetime.combine(target_date, datetime.min.time()))
        )
        .distinct()
        .all()
    )

    for rid, sid, resid in occ_rooms:
        # Lógica mejorada: Si es checkout hoy, generar tarea de CHECKOUT
        res = db.query(Reservation).filter(Reservation.id == resid).first()
        
        if res and res.fecha_checkout <= target_date:
            # Generar tarea de checkout anticipada (para que housekeeping sepa que hoy se van)
            stay_obj = db.query(Stay).get(sid)
            room_obj = db.query(Room).get(rid)
            if stay_obj and room_obj:
                upsert_checkout_task(db, stay_obj, room_obj)
            continue

        existing = (
            db.query(HousekeepingTask)
            .filter(
                HousekeepingTask.task_type == "daily",
                HousekeepingTask.room_id == rid,
                HousekeepingTask.task_date == target_date,
            )
            .first()
        )
        if not existing:
            priority = "alta" if _get_is_high_priority(db, rid, target_date) else "media"
            new_task = HousekeepingTask(
                room_id=rid,
                stay_id=sid,
                reservation_id=resid,
                task_date=target_date,
                task_type="daily",
                priority=priority,
                status="pending",
                meta={"source": "auto-generation"},
            )
            db.add(new_task)
    db.commit()


@router.post("/housekeeping/generate-daily")
def generate_daily_tasks_endpoint(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    target_date = datetime.utcnow().date() if not date else datetime.fromisoformat(date).date()
    _auto_generate_daily_tasks(db, target_date)
    return {"message": "Tareas generadas", "date": target_date.isoformat()}


@router.get("/housekeeping/board")
def housekeeping_board(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    include_done: bool = Query(False),
    type: str = Query("all", description="All tasks, or specific type"),
    db: Session = Depends(get_db)
):
    target_date = datetime.utcnow().date() if not date else datetime.fromisoformat(date).date()
    
    # Automatización: generar diarias para el día consultado si es hoy o futuro cercano
    if target_date >= datetime.utcnow().date():
        _auto_generate_daily_tasks(db, target_date)

    # Optimización: Eager load de Room para evitar N+1
    q = db.query(HousekeepingTask, Room).join(Room, Room.id == HousekeepingTask.room_id)

    clauses = []

    # Daily tasks for the selected date
    if type in ("all", "daily"):
        daily_clause = and_(HousekeepingTask.task_type == "daily", HousekeepingTask.task_date == target_date)
        if not include_done:
            daily_clause = and_(daily_clause, HousekeepingTask.status != "done")
        clauses.append(daily_clause)

    # Checkout tasks (no date filter because checkout tasks can be open without task_date)
    if type in ("all", "checkout"):
        checkout_clause = (HousekeepingTask.task_type == "checkout")
        if not include_done:
            checkout_clause = and_(checkout_clause, HousekeepingTask.status.in_(["pending", "in_progress"]))
        clauses.append(checkout_clause)

    # Manual/other tasks created by supervisor: include them by task_date for the selected day
    if type in ("all", "manual", "other"):
        manual_clause = and_(
            HousekeepingTask.task_type.notin_(["daily", "checkout"]),
            HousekeepingTask.task_date == target_date,
        )
        if not include_done:
            manual_clause = and_(manual_clause, HousekeepingTask.status != "done")
        clauses.append(manual_clause)

    if not clauses:
        return {"date": target_date.isoformat(), "summary": {"checkout_pending": 0, "daily_pending": 0, "in_progress": 0, "done": 0}, "tasks": []}

    results = q.filter(or_(*clauses)).all()

    # Map assigned users in batch
    user_ids = [t.assigned_to_user_id for t, r in results if t.assigned_to_user_id]
    users = {}
    if user_ids:
        for u in db.query(Usuario).filter(Usuario.id.in_(list(set(user_ids)))).all():
            users[u.id] = {"id": u.id, "username": u.username}

    # Build summary
    checkout_pending = sum(1 for t, r in results if t.task_type == "checkout" and t.status == "pending")
    daily_pending = sum(1 for t, r in results if t.task_type == "daily" and t.status == "pending")
    # Include manual tasks in the aggregates to reflect real workload
    in_progress = sum(1 for t, r in results if t.status == "in_progress")
    done = sum(1 for t, r in results if t.status == "done")

    def serialize_task(t: HousekeepingTask, room: Room):
        meta = t.meta or {}
        if t.task_type == "checkout" and not meta.get("procedure"):
            meta = {**meta, "procedure": [
                "Retirar ropa de cama y toallas",
                "Vaciar y limpiar minibar",
                "Revisar olvidos en placard, caja fuerte y baño",
                "Pasar aspiradora y paño húmedo",
                "Reposición de amenities",
                "Dejar habitación en estado 'disponible'"
            ]}
        return {
            "id": t.id,
            "task_type": t.task_type,
            "status": t.status,
            "priority": t.priority,
            "task_date": t.task_date.isoformat() if t.task_date else None,
            "room": {"id": room.id, "numero": room.numero, "estado_operativo": room.estado_operativo} if room else None,
            "assigned_to": users.get(t.assigned_to_user_id) if t.assigned_to_user_id else None,
            "stay_id": t.stay_id,
            "reservation_id": t.reservation_id,
            "notes": t.notes,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "done_at": t.done_at.isoformat() if t.done_at else None,
            "meta": meta,
            "has_incident": bool(meta.get("has_incident") or meta.get("incidents")),
            "has_lost_item": bool(meta.get("has_lost_item") or meta.get("lost_items")),
            "incidents": meta.get("incidents", []),
            "lost_items": meta.get("lost_items", []),
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }

    return {
        "date": target_date.isoformat(),
        "summary": {
            "checkout_pending": checkout_pending,
            "daily_pending": daily_pending,
            "in_progress": in_progress,
            "done": done,
        },
        "tasks": [serialize_task(t, r) for t, r in results],
    }

@router.post("/housekeeping/tasks/{task_id}/start")
def housekeeping_start_task(
    task_id: int,
    db: Session = Depends(get_db)
):
    """Registra el inicio de una limpieza para métricas."""
    task = db.query(HousekeepingTask).filter(HousekeepingTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Tarea no encontrada")
    
    task.status = "in_progress"
    task.started_at = datetime.utcnow()
    db.commit()
    return {"status": "in_progress", "started_at": task.started_at}

@router.post("/housekeeping/incidents")
def housekeeping_report_incident(
    req: IncidentReportRequest,
    db: Session = Depends(get_db)
):
    """Reportar incidencia vinculada a habitación y anclarla a la tarea."""
    task = None
    if req.task_id:
        task = db.query(HousekeepingTask).filter(HousekeepingTask.id == req.task_id).first()
        if not task:
            raise HTTPException(404, "Tarea no encontrada para la incidencia")

        meta = task.meta or {}
        incidents = meta.get("incidents", [])
        incidents.append({
            "tipo": req.tipo,
            "descripcion": req.descripcion,
            "gravedad": req.gravedad,
            "fecha": datetime.utcnow().isoformat(),
            "room_id": req.room_id,
        })
        meta["incidents"] = incidents
        meta["has_incident"] = True
        task.meta = meta
        task.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(task)

    return {"status": "reported", "room_id": req.room_id, "task_id": task.id if task else None}


@router.post("/housekeeping/lost-items")
def housekeeping_report_lost_item(
    req: LostItemReportRequest,
    db: Session = Depends(get_db)
):
    """Reportar objeto perdido y anclarlo a la tarea."""
    task = None
    if req.task_id:
        task = db.query(HousekeepingTask).filter(HousekeepingTask.id == req.task_id).first()
        if not task:
            raise HTTPException(404, "Tarea no encontrada para el objeto extraviado")

        meta = task.meta or {}
        lost_items = meta.get("lost_items", [])
        lost_items.append({
            "descripcion": req.descripcion,
            "lugar": req.lugar,
            "fecha": datetime.utcnow().isoformat(),
            "room_id": req.room_id,
        })
        meta["lost_items"] = lost_items
        meta["has_lost_item"] = True
        task.meta = meta
        task.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(task)

    return {"status": "reported", "room_id": req.room_id, "task_id": task.id if task else None}


@router.patch("/housekeeping/tasks/{task_id}")
def housekeeping_patch_task(
    task_id: int = Path(..., gt=0),
    req: HousekeepingTaskPatchRequest = ...,
    db: Session = Depends(get_db)
):
    """Patch housekeeping task. If status goes to done, mark room disponible and set done_at."""
    task = db.query(HousekeepingTask).filter(HousekeepingTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task no encontrada")

    if req.status:
        if req.status not in ["pending", "in_progress", "done", "skipped"]:
            raise HTTPException(400, "Estado inválido")
        task.status = req.status

    if req.assigned_to_user_id is not None:
        task.assigned_to_user_id = req.assigned_to_user_id

    if req.notes:
        task.notes = (task.notes or "") + f"\n{req.notes}"

    if req.meta is not None:
        # merge meta
        current_meta = task.meta or {}
        current_meta.update(req.meta)
        task.meta = current_meta

    # Validate skipped reason
    if task.status == "skipped":
        if not task.meta or not task.meta.get("skip_reason"):
            raise HTTPException(400, "skip_reason requerido para estado skipped")

    task.updated_at = datetime.utcnow()

    # If completed a checkout task, unlock room
    if task.status == "done":
        if getattr(task, "done_at", None) is None:
            task.done_at = datetime.utcnow()
        room = db.query(Room).filter(Room.id == task.room_id).first()
        if room and room.estado_operativo == "limpieza":
            room.estado_operativo = "disponible"
            room.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(task)
    return {
        "id": task.id,
        "status": task.status,
        "room_id": task.room_id,
    }


class HousekeepingClaimRequest(BaseModel):
    assigned_to_user_id: int


@router.post("/housekeeping/tasks/{task_id}/claim")
def housekeeping_claim_task(
    task_id: int = Path(..., gt=0),
    req: HousekeepingClaimRequest = ...,
    db: Session = Depends(get_db)
):
    task = db.query(HousekeepingTask).filter(HousekeepingTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task no encontrada")

    task.assigned_to_user_id = req.assigned_to_user_id
    task.status = "in_progress"
    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return {"id": task.id, "status": task.status, "assigned_to_user_id": task.assigned_to_user_id}


@router.get("/housekeeping/daily")
def housekeeping_daily(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    """
    Derived daily tasks for a given date.
    Returns automatically for rooms with active stays (checkin_real <= date < checkout_real).
    Includes completion status from daily_clean_logs (no persistent tasks created).
    """
    from models.core import DailyCleanLog
    
    target_date = datetime.utcnow().date() if not date else datetime.fromisoformat(date).date()

    day_start = datetime.combine(target_date, datetime.min.time())
    next_day = target_date + timedelta(days=1)
    day_end = datetime.combine(next_day, datetime.min.time())

    # Rooms with active occupancies on that date
    occ_results = (
        db.query(
            StayRoomOccupancy.room_id,
            Room.numero,
            Room.estado_operativo
        )
        .join(Room, Room.id == StayRoomOccupancy.room_id)
        .join(Stay, Stay.id == StayRoomOccupancy.stay_id)
        .filter(
            Stay.estado.in_(["ocupada", "pendiente_checkout"]),
            StayRoomOccupancy.desde < day_end,
            or_(StayRoomOccupancy.hasta.is_(None), StayRoomOccupancy.hasta > day_start)
        )
        .all()
    )

    # Check if each was logged as completed
    room_ids = [r[0] for r in occ_results]
    logs = {}
    if room_ids:
        for log in db.query(DailyCleanLog).filter(
            DailyCleanLog.room_id.in_(room_ids),
            DailyCleanLog.date == target_date
        ).all():
            logs[log.room_id] = {
                "user_id": log.user_id,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                "notes": log.notes,
            }

    tasks = [
        {
            "id": f"daily-{r[0]}-{target_date.isoformat()}",  # Virtual ID
            "task_type": "daily",
            "room": {"id": r[0], "numero": r[1], "estado_operativo": r[2]},
            "task_date": target_date.isoformat(),
            "status": "done" if r[0] in logs else "pending",
            "log": logs.get(r[0]),
        }
        for r in occ_results
    ]

    return {
        "date": target_date.isoformat(),
        "tasks": tasks,
    }


class DailyCleanLogRequest(BaseModel):
    room_id: int
    date: str  # YYYY-MM-DD
    user_id: int
    notes: Optional[str] = None


@router.post("/housekeeping/daily/log")
def housekeeping_daily_log(
    req: DailyCleanLogRequest,
    db: Session = Depends(get_db)
):
    """Register daily cleaning completion. Upserts a DailyCleanLog entry."""
    from models.core import DailyCleanLog
    
    target_date = datetime.fromisoformat(req.date).date()

    log = (
        db.query(DailyCleanLog)
        .filter(
            DailyCleanLog.room_id == req.room_id,
            DailyCleanLog.date == target_date
        )
        .first()
    )

    if log:
        log.user_id = req.user_id
        log.completed_at = datetime.utcnow()
        log.notes = req.notes
    else:
        log = DailyCleanLog(
            room_id=req.room_id,
            date=target_date,
            user_id=req.user_id,
            completed_at=datetime.utcnow(),
            notes=req.notes,
        )
        db.add(log)

    db.commit()
    db.refresh(log)
    return {
        "id": log.id,
        "room_id": log.room_id,
        "date": log.date.isoformat(),
        "completed_at": log.completed_at.isoformat(),
    }


# ========================================================================
# 1️⃣ CALENDARIO (CORE)
# ========================================================================

def parse_to_date(date_str: str) -> date:
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
        return block_status not in ["cancelada", "no_show", "ocupada"]
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
            Reservation.estado.in_(["confirmada", "draft"]),  # Excluir ocupada (ya tiene Stay)
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
    desde = parse_to_date(from_date)
    hasta = parse_to_date(to_date)

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

    room = db.query(Room).filter(Room.id == room_id).first()
    if not room or room.estado_operativo == "limpieza":
        return False

    # Verificar conflicto con reservas confirmadas
    conflicting_res = (
        db.query(Reservation)
        .join(ReservationRoom)
        .filter(
            ReservationRoom.room_id == room_id,
            Reservation.estado.in_(["confirmada", "draft"]),  # No ocupada (su ocupación está en Stays)
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


def upsert_checkout_task(db: Session, stay: Stay, room: Room) -> HousekeepingTask:
    """Crea o devuelve la tarea de checkout para la estadía (idempotente)."""
    today = datetime.utcnow().date()

    # Check for existing task by the unique constraint: (room_id, task_date, task_type)
    existing = (
        db.query(HousekeepingTask)
        .filter(
            HousekeepingTask.room_id == room.id,
            HousekeepingTask.task_date == today,
            HousekeepingTask.task_type == "checkout",
        )
        .first()
    )

    if existing:
        # Update the stay and reservation references if they changed
        updated = False
        if existing.stay_id != stay.id:
            existing.stay_id = stay.id
            updated = True
        if existing.reservation_id != stay.reservation_id:
            existing.reservation_id = stay.reservation_id
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
        nueva_checkin = parse_to_date(req.fecha_checkin) if req.fecha_checkin else res.fecha_checkin
        nueva_checkout = parse_to_date(req.fecha_checkout) if req.fecha_checkout else res.fecha_checkout

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
    desde = parse_to_date(req.fecha_checkin)
    hasta = parse_to_date(req.fecha_checkout)

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

    # Validar que la fecha actual esté dentro del período de reserva
    from datetime import date as date_class
    today = date_class.today()
    if today < res.fecha_checkin or today >= res.fecha_checkout:
        raise HTTPException(
            409, 
            f"El check-in solo se puede realizar entre el {res.fecha_checkin} y el {res.fecha_checkout}."
        )

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

    # Marcar reserva como ocupada (check-in realizado)
    res.estado = "ocupada"

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
    REFACTORIZADO: Usa motor compartido (invoice_engine.compute_invoice)
    
    SINGLE SOURCE OF TRUTH: Backend calcula TODO
    Frontend pasa sugerencias, backend valida y retorna valores finales.
    """
    stay = db.query(Stay).options(
        joinedload(Stay.reservation).joinedload(Reservation.cliente),
        joinedload(Stay.reservation).joinedload(Reservation.empresa),
        joinedload(Stay.occupancies).joinedload(StayRoomOccupancy.room).joinedload(Room.tipo),
        joinedload(Stay.charges),
        joinedload(Stay.payments)
    ).filter(Stay.id == id).first()

    if not stay:
        raise HTTPException(404, "Estadía no encontrada")

    # Calcular usando motor compartido
    try:
        calc = compute_invoice(
            stay=stay,
            db=db,
            nights_override=nights_to_charge,
            tarifa_override=nightly_rate,
        )
    except Exception as e:
        log_event("invoice_preview", "sistema", "Error de cálculo", f"stay_id={id} error={str(e)}")
        raise HTTPException(
            500,
            f"Error al calcular invoice: {str(e)}"
        )

    # Retornar en formato compatible
    return InvoicePreviewResponse(
        nights={
            "planned": calc.planned_nights,
            "to_charge": calc.final_nights
        },
        pricing={
            "nightly_rate": float(calc.nightly_rate),
            "subtotal": float(calc.room_subtotal),
            "taxes": [{"name": "Impuestos", "amount": float(calc.taxes_total)}],
            "discounts": []
        },
        charges_total=float(calc.charges_total),
        payments_total=float(calc.payments_total),
        total=float(calc.grand_total),
        balance=float(calc.balance)
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
    🚪 CHECK-OUT PROFESIONAL
    
    REFACTORIZADO: Usa motor compartido (invoice_engine.compute_invoice)
    - Actualiza Reservation a "finalizada"
    - Usa cálculo financiero consistente
    - Maneja housekeeping
    - Idempotencia completa
    """
    # =====================================================================
    # 1) CARGAR STAY
    # =====================================================================
    stay = db.query(Stay).options(
        joinedload(Stay.reservation).joinedload(Reservation.cliente),
        joinedload(Stay.reservation).joinedload(Reservation.empresa),
        joinedload(Stay.occupancies).joinedload(StayRoomOccupancy.room).joinedload(Room.tipo),
        joinedload(Stay.charges),
        joinedload(Stay.payments)
    ).filter(Stay.id == id).first()

    if not stay:
        raise HTTPException(404, "Estadía no encontrada")

    reservation = stay.reservation
    if not reservation:
        raise HTTPException(400, "Stay sin reserva asociada")

    # =====================================================================
    # 2) IDEMPOTENCIA
    # =====================================================================
    if stay.estado == "cerrada":
        hk_task = (
            db.query(HousekeepingTask)
            .filter(
                HousekeepingTask.task_type == "checkout",
                HousekeepingTask.stay_id == stay.id,
            )
            .first()
        )

        try:
            calc = compute_invoice(stay, db)
            log_event("stays", "sistema", "Check-out - Idempotencia", f"stay_id={id} ya cerrada")
            
            return {
                "id": stay.id,
                "estado": "cerrada",
                "checkout_real": stay.checkout_real.isoformat() if stay.checkout_real else None,
                "reservation_estado": reservation.estado,
                "total": float(calc.grand_total),
                "paid": float(calc.payments_total),
                "balance": float(calc.balance),
                "message": "Stay ya estaba cerrada",
                "housekeeping_task_id": hk_task.id if hk_task else None,
            }
        except Exception as e:
            log_event("stays", "sistema", "Check-out - Idempotencia (calc error)", f"stay_id={id} error={str(e)}")
            return {
                "id": stay.id,
                "estado": "cerrada",
                "message": "Stay ya estaba cerrada",
                "housekeeping_task_id": hk_task.id if hk_task else None,
            }

    # =====================================================================
    # 3) VALIDACIONES
    # =====================================================================
    if stay.estado not in ["ocupada", "pendiente_checkout"]:
        raise HTTPException(
            409,
            f"No puede hacer checkout en estado {stay.estado}. Estados válidos: ocupada, pendiente_checkout"
        )

    # =====================================================================
    # 4) CÁLCULO FINANCIERO (motor compartido)
    # =====================================================================
    try:
        calc = compute_invoice(
            stay=stay,
            db=db,
            checkout_date_override=req.checkout_real if hasattr(req, "checkout_real") and req.checkout_real else None,
        )
    except Exception as e:
        log_event("stays", "sistema", "Check-out - Error de cálculo", f"stay_id={id} error={str(e)}")
        raise HTTPException(
            500,
            f"Error al calcular totales: {str(e)}"
        )

    # =====================================================================
    # 5) VALIDAR SALDO
    # =====================================================================
    if calc.balance > 0 and not req.allow_close_with_debt:
        raise HTTPException(
            409,
            f"Saldo pendiente: ${float(calc.balance):.2f}. Habilita allow_close_with_debt=true"
        )

    # =====================================================================
    # 6) CERRAR OCUPACIONES
    # =====================================================================
    ahora = datetime.utcnow()
    closed_rooms = []

    for occ in stay.occupancies:
        if not occ.hasta:  # Ocupación activa
            occ.hasta = ahora

            # Actualizar estado de habitación
            room = db.query(Room).filter(Room.id == occ.room_id).first()
            if room:
                # Checkout siempre deja la habitación en limpieza hasta que housekeeping cierre la tarea
                room.estado_operativo = "limpieza"
                room.updated_at = ahora
                closed_rooms.append({
                    "room_id": room.id,
                    "numero": room.numero,
                    "estado_nuevo": room.estado_operativo
                })

    # =====================================================================
    # 7) ACTUALIZAR STAY
    # =====================================================================
    stay.estado = "cerrada"
    stay.checkout_real = datetime.fromisoformat(req.checkout_real) if req.checkout_real else ahora

    if req.notas:
        stay.notas_internas = (stay.notas_internas or "") + f"\n[Checkout {ahora.date()}] {req.notas}"

    stay.updated_at = ahora

    # =====================================================================
    # 8) ACTUALIZAR RESERVATION A "FINALIZADA"
    # =====================================================================
    if reservation.estado == "ocupada":
        reservation.estado = "finalizada"
        reservation.updated_at = ahora
        log_event("reservations", "sistema", "Reservation finalizada por checkout", f"reservation_id={reservation.id}")

    # =====================================================================
    # 9) CREAR / ACTUALIZAR TAREA DE HOUSEKEEPING (CHECKOUT)
    # =====================================================================
    housekeeping_task_id = None
    if stay.occupancies:
        primary_room = stay.occupancies[0].room
        if primary_room:
            hk_task = upsert_checkout_task(db, stay, primary_room)
            housekeeping_task_id = hk_task.id
            log_event(
                "housekeeping",
                "sistema",
                "Housekeeping task checkout",
                f"stay_id={id} room_id={primary_room.id} task_id={housekeeping_task_id}"
            )

    # =====================================================================
    # 10) AUDITORÍA
    # =====================================================================
    audit = AuditEvent(
        entity_type="stay",
        entity_id=stay.id,
        action="CHECKOUT",
        usuario="sistema",
        descripcion="Check-out completado",
        payload={
            "reservation_id": reservation.id,
            "reservation_estado_nuevo": reservation.estado,
            "charges": float(calc.charges_total),
            "payments": float(calc.payments_total),
            "balance": float(calc.balance),
            "housekeeping_task_id": housekeeping_task_id,
            "closed_rooms": closed_rooms,
        }
    )
    db.add(audit)

    # =====================================================================
    # 11) COMMIT
    # =====================================================================
    db.commit()
    db.refresh(stay)
    db.refresh(reservation)

    log_event("stays", "usuario", "Check-out exitoso", f"stay_id={id} balance={float(calc.balance):.2f}")

    # =====================================================================
    # 12) RESPUESTA
    # =====================================================================
    return {
        "id": stay.id,
        "estado": stay.estado,
        "checkout_real": stay.checkout_real.isoformat(),
        "reservation_id": reservation.id,
        "reservation_estado": reservation.estado,
        "total": float(calc.grand_total),
        "paid": float(calc.payments_total),
        "balance": float(calc.balance),
        "housekeeping_task_id": housekeeping_task_id,
        "closed_rooms": closed_rooms,
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
    desde = parse_to_date(from_date)
    hasta = parse_to_date(to_date)

    if hasta <= desde:
        return {"available": False, "reason": "invalid_dates"}

    if _check_availability(db, room_id, desde, hasta):
        return {"available": True, "reason": "ok"}
    else:
        return {"available": False, "reason": "overlap"}
