from datetime import datetime, date
from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    Boolean,
    ForeignKey,
    Text,
    UniqueConstraint,
    Index,
    Numeric,
    JSON,
    CheckConstraint,
    text,
)
from sqlalchemy.orm import relationship
from database.conexion import Base
from sqlalchemy.dialects.postgresql import JSONB

class Empresa(Base):
    __tablename__ = "empresas"
    __table_args__ = (
        UniqueConstraint("cuit", name="uq_empresa_cuit"),
        Index("idx_empresa_nombre", "nombre"),
    )

    id = Column(Integer, primary_key=True)
    nombre = Column(String(150), nullable=False)
    cuit = Column(String(20), nullable=False)
    tipo_empresa = Column(String(50), nullable=True)

    contacto_nombre = Column(String(100), nullable=True)
    contacto_email = Column(String(100), nullable=True)
    contacto_telefono = Column(String(30), nullable=True)

    direccion = Column(String(200), nullable=True)
    ciudad = Column(String(100), nullable=True)
    provincia = Column(String(100), nullable=True)

    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    clientes = relationship("Cliente", back_populates="empresa")


class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = (
        UniqueConstraint("tipo_documento", "numero_documento", name="uq_doc"),
        Index("idx_cliente_email", "email"),
        Index("idx_cliente_telefono", "telefono"),
    )

    id = Column(Integer, primary_key=True)
    nombre = Column(String(60), nullable=False)
    apellido = Column(String(60), nullable=False)
    tipo_documento = Column(String(20), nullable=False, default="DNI")
    numero_documento = Column(String(40), nullable=False)

    fecha_nacimiento = Column(Date, nullable=True)
    nacionalidad = Column(String(60), nullable=True)

    email = Column(String(100), nullable=True)
    telefono = Column(String(30), nullable=True)

    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=True)
    nota_interna = Column(Text, nullable=True)

    blacklist = Column(Boolean, default=False, nullable=False)
    motivo_blacklist = Column(Text, nullable=True)

    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    empresa = relationship("Empresa", back_populates="clientes")

class RoomType(Base):
    __tablename__ = "room_types"
    __table_args__ = (UniqueConstraint("nombre", name="uq_roomtype_nombre"),)

    id = Column(Integer, primary_key=True)
    nombre = Column(String(60), nullable=False)
    descripcion = Column(Text, nullable=True)
    capacidad = Column(Integer, nullable=False, default=1)
    precio_base = Column(Numeric(12, 2), nullable=True)  # Tarifa nocturna base
    amenidades = Column(JSONB, nullable=True)  # ["wifi","tv",...]
    activo = Column(Boolean, default=True, nullable=False)


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        UniqueConstraint("numero", name="uq_room_numero"),
        Index("idx_room_tipo", "room_type_id"),
        Index("idx_room_estado_operativo", "estado_operativo"),
    )

    id = Column(Integer, primary_key=True)
    numero = Column(String(10), nullable=False)   # "101", "PB1" si algún día te pintan letras
    piso = Column(Integer, nullable=True)
    room_type_id = Column(Integer, ForeignKey("room_types.id"), nullable=False)

    # Estado OPERATIVO (venta)
    # disponible | ocupada | bloqueada | fuera_servicio
    estado_operativo = Column(String(20), nullable=False, default="disponible")

    notas = Column(Text, nullable=True)
    particularidades = Column(JSONB, nullable=True)  # {"jacuzzi":true,...}
    activo = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tipo = relationship("RoomType")


class RatePlan(Base):
    __tablename__ = "rate_plans"
    __table_args__ = (Index("idx_rateplan_activo", "activo"),)

    id = Column(Integer, primary_key=True)
    nombre = Column(String(80), nullable=False)
    descripcion = Column(Text, nullable=True)

    # Reglas: cancelación, desayuno, etc.
    reglas = Column(JSONB, nullable=True)

    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class DailyRate(Base):
    """
    Tarifa por día y tipo de habitación (y opcionalmente por rate plan).
    Te permite temporadas / yield / feriados sin inventarte 20 columnas.
    """
    __tablename__ = "daily_rates"
    __table_args__ = (
        UniqueConstraint("room_type_id", "fecha", "rate_plan_id", name="uq_rate_day"),
        Index("idx_rate_fecha", "fecha"),
    )

    id = Column(Integer, primary_key=True)
    room_type_id = Column(Integer, ForeignKey("room_types.id"), nullable=False)
    rate_plan_id = Column(Integer, ForeignKey("rate_plans.id"), nullable=True)

    fecha = Column(DateTime, nullable=False)  # guardá date si querés; DateTime también sirve
    precio = Column(Numeric(12, 2), nullable=False)

    room_type = relationship("RoomType")
    rate_plan = relationship("RatePlan")

class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        Index("idx_res_fechas", "fecha_checkin", "fecha_checkout"),
        Index("idx_res_estado", "estado"),
    )

    id = Column(Integer, primary_key=True)

    # Titular (puede ser null si es "nombre temporal")
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=True)
    nombre_temporal = Column(String(120), nullable=True)

    fecha_checkin = Column(Date, nullable=False)
    fecha_checkout = Column(Date, nullable=False)

    # Estado de reserva (negocio)
    # draft | confirmada | ocupada | cancelada | no_show | cerrada
    estado = Column(String(20), nullable=False, default="confirmada")

    origen = Column(String(30), nullable=True)  # walkin, whatsapp, booking, etc.
    notas = Column(Text, nullable=True)
    
    # Cancelación (soft delete)
    cancel_reason = Column(Text, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(Integer, nullable=True)  # ID del usuario que canceló

    # Snapshot opcional: datos para reconstruir rápido sin 50 joins
    meta = Column(JSONB, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cliente = relationship("Cliente")
    empresa = relationship("Empresa")
    rooms = relationship("ReservationRoom", back_populates="reservation", cascade="all, delete-orphan")
    guests = relationship("ReservationGuest", back_populates="reservation", cascade="all, delete-orphan")

    def can_checkin(self):
        """Verifica si la reserva puede hacer check-in"""
        invalid_states = ["cancelada", "no_show", "cerrada"]
        return self.estado not in invalid_states

    def is_editable(self):
        """Verifica si la reserva puede ser editada"""
        # Una reserva no se puede editar si está ocupada (tiene Stay activo), cerrada, cancelada o no-show
        non_editable_states = ["ocupada", "cerrada", "cancelada", "no_show"]
        return self.estado not in non_editable_states

    def is_cancelled_or_noshow(self):
        """Verifica si está cancelada o no-show"""
        return self.estado in ["cancelada", "no_show"]

    def is_draft_or_confirmed(self):
        """Verifica si está en draft o confirmada (puede hacer checkin)"""
        return self.estado in ["draft", "confirmada"]


class ReservationRoom(Base):
    """
    Asignación de habitaciones planificada (reserva) – NO la ocupación real.
    """
    __tablename__ = "reservation_rooms"
    __table_args__ = (
        UniqueConstraint("reservation_id", "room_id", name="uq_res_room"),
        Index("idx_resroom_room", "room_id"),
    )

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)

    reservation = relationship("Reservation", back_populates="rooms")
    room = relationship("Room")


class ReservationGuest(Base):
    """
    Huéspedes en la reserva (roles), sin meter checkin acá.
    """
    __tablename__ = "reservation_guests"
    __table_args__ = (
        UniqueConstraint("reservation_id", "cliente_id", name="uq_res_guest"),
        Index("idx_resguest_res", "reservation_id"),
    )

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False)
    cliente_id = Column(Integer, ForeignKey("clientes.id", ondelete="SET NULL"), nullable=True)

    # principal | adulto | menor
    rol = Column(String(20), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    reservation = relationship("Reservation", back_populates="guests")
    cliente = relationship("Cliente")

class Stay(Base):
    __tablename__ = "stays"
    __table_args__ = (
        UniqueConstraint("reservation_id", name="uq_stay_reservation"),
        Index("idx_stay_estado", "estado"),
    )

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id", ondelete="RESTRICT"), nullable=False)

    # Estados operacionales (vida real)
    # pendiente_checkin | ocupada | pendiente_checkout | cerrada
    estado = Column(String(30), nullable=False, default="pendiente_checkin")

    checkin_real = Column(DateTime, nullable=True)
    checkout_real = Column(DateTime, nullable=True)

    notas_internas = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    reservation = relationship("Reservation")
    occupancies = relationship("StayRoomOccupancy", back_populates="stay", cascade="all, delete-orphan")
    charges = relationship("StayCharge", back_populates="stay", cascade="all, delete-orphan")
    payments = relationship("StayPayment", back_populates="stay", cascade="all, delete-orphan")

    def get_active_occupancy(self):
        """Retorna la ocupación activa (hasta IS NULL), o None"""
        if self.occupancies:
            active = [o for o in self.occupancies if o.hasta is None]
            return active[0] if active else None
        return None

    def has_active_occupancy(self):
        """Verifica si hay ocupación activa"""
        return self.get_active_occupancy() is not None

    def calculate_total_charges(self):
        """Calcula total de cargos"""
        from decimal import Decimal
        return sum(Decimal(str(c.monto_total)) for c in self.charges) if self.charges else Decimal("0")

    def calculate_total_payments(self):
        """Calcula total de pagos (excluyendo reversos)"""
        from decimal import Decimal
        return sum(
            Decimal(str(p.monto)) for p in self.payments 
            if self.payments and not p.es_reverso
        ) if self.payments else Decimal("0")

    def calculate_balance(self):
        """Calcula saldo pendiente (cargos - pagos)"""
        total_charges = self.calculate_total_charges()
        total_payments = self.calculate_total_payments()
        return total_charges - total_payments

    def is_closed(self):
        """Verifica si Stay está cerrada"""
        return self.estado == "cerrada"

    def is_active(self):
        """Verifica si Stay está activa (no cerrada, no pendiente)"""
        return self.estado in ["ocupada", "pendiente_checkout"]


class StayRoomOccupancy(Base):
    """
    Ocupación REAL por habitación y período.
    Esto resuelve:
    - cambio de habitación
    - extensión
    - solapes
    """
    __tablename__ = "stay_room_occupancies"
    __table_args__ = (
        Index("idx_occ_room", "room_id"),
        Index("idx_occ_fechas", "desde", "hasta"),
    )

    id = Column(Integer, primary_key=True)
    stay_id = Column(Integer, ForeignKey("stays.id", ondelete="CASCADE"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False)

    desde = Column(DateTime, nullable=False)
    hasta = Column(DateTime, nullable=True)  # null = sigue ocupando

    motivo = Column(String(120), nullable=True)  # upgrade, mantenimiento, error, etc.
    creado_por = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    stay = relationship("Stay", back_populates="occupancies")
    room = relationship("Room")

class StayCharge(Base):
    """
    Cargos: noches, minibar, lavandería, penalidad, descuento (negativo), etc.
    """
    __tablename__ = "stay_charges"
    __table_args__ = (
        Index("idx_charge_stay", "stay_id"),
        Index("idx_charge_tipo", "tipo"),
    )

    id = Column(Integer, primary_key=True)
    stay_id = Column(Integer, ForeignKey("stays.id", ondelete="CASCADE"), nullable=False)

    # night | product | service | fee | discount
    tipo = Column(String(20), nullable=False)
    descripcion = Column(String(200), nullable=True)

    cantidad = Column(Numeric(12, 2), nullable=False, default=1)
    monto_unitario = Column(Numeric(12, 2), nullable=False)
    monto_total = Column(Numeric(12, 2), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    creado_por = Column(String(50), nullable=True)

    stay = relationship("Stay", back_populates="charges")


class StayPayment(Base):
    """
    Pagos: parciales, reversos, etc.
    """
    __tablename__ = "stay_payments"
    __table_args__ = (
        Index("idx_payment_stay", "stay_id"),
        Index("idx_payment_fecha", "timestamp"),
    )

    id = Column(Integer, primary_key=True)
    stay_id = Column(Integer, ForeignKey("stays.id", ondelete="CASCADE"), nullable=False)

    monto = Column(Numeric(12, 2), nullable=False)
    metodo = Column(String(20), nullable=False)  # efectivo/tarjeta/transferencia/otro
    referencia = Column(String(120), nullable=True)
    es_reverso = Column(Boolean, default=False, nullable=False)

    timestamp = Column(DateTime, default=datetime.utcnow)
    usuario = Column(String(50), nullable=True)
    notas = Column(Text, nullable=True)

    stay = relationship("Stay", back_populates="payments")


class HKTemplate(Base):
    __tablename__ = "hk_templates"
    __table_args__ = (Index("idx_hkt_name", "nombre"),)

    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False, unique=True)
    checklist = Column(JSON, nullable=False, default=list)  # [{"nombre":"Baño", "orden":1}, ...]
    minibar_default = Column(JSON, nullable=True)

    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class HousekeepingTask(Base):
    __tablename__ = "housekeeping_tasks"
    __table_args__ = (
        Index("idx_hk_task_room_date", "room_id", "task_date"),
        Index("idx_hk_task_status_date", "status", "task_date"),
        # Una sola limpieza diaria por habitación y día
        UniqueConstraint("room_id", "task_date", "task_type", name="uq_hk_task_daily"),
        # Una sola limpieza de checkout por estadía
        Index(
            "uq_hk_task_checkout_stay",
            "stay_id",
            unique=True,
            postgresql_where=text("task_type = 'checkout'"),
        ),
        # Constraints removidos para flexibilidad: task_type y status son libres
    )

    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False)
    stay_id = Column(Integer, ForeignKey("stays.id", ondelete="SET NULL"), nullable=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id", ondelete="SET NULL"), nullable=True)

    task_date = Column(Date, nullable=False)
    task_type = Column(String(50), nullable=False)  # Liberado de 20 a 50
    status = Column(String(30), nullable=False, default="pending")  # Liberado de 20 a 30
    priority = Column(String(20), nullable=False, default="media")  # baja | media | alta | urgente

    assigned_to_user_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    started_at = Column(DateTime, nullable=True) # Para métricas de tiempo
    done_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    meta = Column(JSONB, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    room = relationship("Room")
    stay = relationship("Stay")
    reservation = relationship("Reservation")


class HKCycle(Base):
    """
    Reemplaza CleaningCycle + HousekeepingTarea en un solo flujo.
    """
    __tablename__ = "hk_cycles"
    __table_args__ = (
        Index("idx_hk_room", "room_id"),
        Index("idx_hk_estado", "estado"),
        Index("idx_hk_stay", "stay_id"),
    )

    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False)
    stay_id = Column(Integer, ForeignKey("stays.id", ondelete="SET NULL"), nullable=True)  # puede existir limpieza sin stay

    template_id = Column(Integer, ForeignKey("hk_templates.id"), nullable=True)

    # pending | in_progress | review | done | maintenance_required
    estado = Column(String(30), nullable=False, default="pending")

    asignado_a = Column(String(100), nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    checklist_result = Column(JSON, nullable=True)
    minibar_snapshot = Column(JSON, nullable=True)
    notas = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    room = relationship("Room")
    stay = relationship("Stay")
    template = relationship("HKTemplate")
    incidents = relationship("HKIncident", back_populates="cycle", cascade="all, delete-orphan")
    lost_items = relationship("HKLostItem", back_populates="cycle", cascade="all, delete-orphan")


class HKIncident(Base):
    __tablename__ = "hk_incidents"
    __table_args__ = (Index("idx_hkinc_cycle", "cycle_id"),)

    id = Column(Integer, primary_key=True)
    cycle_id = Column(Integer, ForeignKey("hk_cycles.id", ondelete="CASCADE"), nullable=False)

    tipo = Column(String(50), nullable=False)
    gravedad = Column(String(10), nullable=False, default="media")
    descripcion = Column(Text, nullable=False)
    fotos_url = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100), nullable=True)

    cycle = relationship("HKCycle", back_populates="incidents")


class HKLostItem(Base):
    __tablename__ = "hk_lost_items"
    __table_args__ = (Index("idx_hklost_cycle", "cycle_id"),)

    id = Column(Integer, primary_key=True)
    cycle_id = Column(Integer, ForeignKey("hk_cycles.id", ondelete="CASCADE"), nullable=False)

    descripcion = Column(Text, nullable=False)
    lugar = Column(String(150), nullable=True)
    entregado_a = Column(String(120), nullable=True)
    fecha_hallazgo = Column(DateTime, default=datetime.utcnow)

    created_by = Column(String(100), nullable=True)

    cycle = relationship("HKCycle", back_populates="lost_items")

class MaintenanceTicket(Base):
    __tablename__ = "maintenance_tickets"
    __table_args__ = (
        Index("idx_mt_room", "room_id"),
        Index("idx_mt_estado", "estado"),
    )

    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False)

    # abierto | en_progreso | resuelto | cancelado
    estado = Column(String(20), nullable=False, default="abierto")
    prioridad = Column(String(10), nullable=False, default="media")

    tipo = Column(String(50), nullable=True)  # aire, plomería, eléctrico...
    descripcion = Column(Text, nullable=False)

    bloquea_room = Column(Boolean, default=False, nullable=False)

    creado_por = Column(String(50), nullable=True)
    asignado_a = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    room = relationship("Room")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("idx_audit_entity", "entity_type", "entity_id"),
        Index("idx_audit_time", "timestamp"),
        Index("idx_audit_action", "action"),
    )

    id = Column(Integer, primary_key=True)

    # "reservation" | "stay" | "hk_cycle" | "maintenance" | "cash"
    entity_type = Column(String(30), nullable=False)
    entity_id = Column(Integer, nullable=False)

    action = Column(String(50), nullable=False)  # CHECKIN, CHECKOUT, ROOM_MOVE, PAYMENT, UPDATE...
    usuario = Column(String(50), nullable=True)

    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    descripcion = Column(Text, nullable=True)
    payload = Column(JSONB, nullable=True)
    ip_address = Column(String(45), nullable=True)


class DailyCleanLog(Base):
    """
    Registro ligero de limpieza diaria completada.
    No crea tareas persistidas, solo audita cuándo y por quién se realizó.
    """
    __tablename__ = "daily_clean_logs"
    __table_args__ = (
        UniqueConstraint("room_id", "date", name="uq_daily_clean_room_date"),
        Index("idx_daily_clean_room", "room_id"),
        Index("idx_daily_clean_date", "date"),
    )

    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False)
    date = Column(Date, nullable=False)
    user_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    completed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    notes = Column(Text, nullable=True)

    room = relationship("Room")