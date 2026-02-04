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
    Enum,
)
from sqlalchemy.orm import relationship
from database.conexion import Base
from sqlalchemy.dialects.postgresql import JSONB
import enum


# ============================================================================
# ENUMS MULTI-TENANT
# ============================================================================

class PlanType(str, enum.Enum):
    DEMO = "demo"
    BASICO = "basico"
    PREMIUM = "premium"


class SubscriptionStatus(str, enum.Enum):
    ACTIVO = "activo"
    VENCIDO = "vencido"
    CANCELADO = "cancelado"
    BLOQUEADO = "bloqueado"


class PaymentStatus(str, enum.Enum):
    PENDIENTE = "pendiente"
    EXITOSO = "exitoso"
    FALLIDO = "fallido"


class PaymentProvider(str, enum.Enum):
    DUMMY = "dummy"
    MERCADO_PAGO = "mercado_pago"
    STRIPE = "stripe"


# ============================================================================
# MULTI-TENANT CORE MODELS
# ============================================================================

class Plan(Base):
    """Planes disponibles en el SaaS"""
    __tablename__ = "planes"
    __table_args__ = (
        UniqueConstraint("nombre", name="uq_plan_nombre"),
        Index("idx_plan_nombre", "nombre"),
    )

    id = Column(Integer, primary_key=True)
    nombre = Column(Enum(PlanType, values_callable=lambda obj: [e.value for e in obj]), nullable=False, unique=True)
    descripcion = Column(Text, nullable=True)
    precio_mensual = Column(Numeric(12, 2), nullable=False)
    max_habitaciones = Column(Integer, nullable=False, default=10)
    max_usuarios = Column(Integer, nullable=False, default=5)
    caracteristicas = Column(JSONB, nullable=True)  # {"feature1": true, "feature2": false}
    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="plan")


class EmpresaUsuario(Base):
    """Tenants SaaS - Hoteles que contratan Cuenus Hotel"""
    __tablename__ = "empresa_usuarios"
    __table_args__ = (
        UniqueConstraint("cuit", name="uq_empresa_usuario_cuit"),
        Index("idx_empresa_usuario_nombre", "nombre_hotel"),
        Index("idx_empresa_usuario_estado", "activa"),
    )

    id = Column(Integer, primary_key=True)
    nombre_hotel = Column(String(150), nullable=False)
    cuit = Column(String(20), nullable=False)
    
    contacto_nombre = Column(String(100), nullable=True)
    contacto_email = Column(String(100), nullable=True)
    contacto_telefono = Column(String(30), nullable=True)
    
    direccion = Column(String(200), nullable=True)
    ciudad = Column(String(100), nullable=True)
    provincia = Column(String(100), nullable=True)

    plan_tipo = Column(Enum(PlanType, values_callable=lambda obj: [e.value for e in obj]), default=PlanType.DEMO, nullable=False)
    
    # Trial: solo para plan DEMO
    fecha_inicio_demo = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=True)
    fecha_fin_demo = Column(DateTime(timezone=True), nullable=True)  # Seteado a hoy + 10 días en registro
    
    # Control de acceso
    activa = Column(Boolean, default=True, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    usuarios = relationship("Usuario", back_populates="empresa_usuario")
    clientes = relationship("Cliente", back_populates="empresa_usuario")
    clientes_corporativos = relationship("ClienteCorporativo", back_populates="empresa_usuario")
    habitaciones = relationship("Room", back_populates="empresa_usuario")
    reservas = relationship("Reservation", back_populates="empresa_usuario")
    stays = relationship("Stay", back_populates="empresa_usuario")
    daily_rates = relationship("DailyRate", back_populates="empresa_usuario")
    housekeeping_tasks = relationship("HousekeepingTask", back_populates="empresa_usuario")
    roles = relationship("Rol", back_populates="empresa_usuario")
    subscription = relationship("Subscription", back_populates="empresa_usuario", uselist=False)
    hotel_settings = relationship("HotelSettings", back_populates="empresa_usuario", uselist=False)
    transaction_categories = relationship("TransactionCategory", back_populates="empresa_usuario")
    transactions = relationship("Transaction", back_populates="empresa_usuario")
    cash_closings = relationship("CashClosing", back_populates="empresa_usuario")


class Subscription(Base):
    """Suscripciones activas por tenant"""
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("empresa_usuario_id", name="uq_subscription_empresa_usuario"),
        Index("idx_subscription_estado", "estado"),
    )

    id = Column(Integer, primary_key=True)
    empresa_usuario_id = Column(Integer, ForeignKey("empresa_usuarios.id"), nullable=False, unique=True)
    plan_id = Column(Integer, ForeignKey("planes.id"), nullable=False)
    
    estado = Column(Enum(SubscriptionStatus, values_callable=lambda obj: [e.value for e in obj]), default=SubscriptionStatus.ACTIVO, nullable=False)
    fecha_proxima_renovacion = Column(DateTime(timezone=True), nullable=True)
    
    metadata_json = Column(JSONB, nullable=True)  # {last_payment_id, billing_email, etc}
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    empresa_usuario = relationship("EmpresaUsuario", back_populates="subscription")
    plan = relationship("Plan", back_populates="subscriptions")
    payment_attempts = relationship("PaymentAttempt", back_populates="subscription")
    transactions = relationship("Transaction", back_populates="subscription")


class PaymentAttempt(Base):
    """Intentos de pago - tabla de auditoría"""
    __tablename__ = "payment_attempts"
    __table_args__ = (
        Index("idx_payment_subscription", "subscription_id"),
        Index("idx_payment_estado", "estado"),
    )

    id = Column(Integer, primary_key=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=False)
    
    monto = Column(Numeric(12, 2), nullable=False)
    estado = Column(Enum(PaymentStatus), default=PaymentStatus.PENDIENTE, nullable=False)
    proveedor = Column(Enum(PaymentProvider), default=PaymentProvider.DUMMY, nullable=False)
    
    external_id = Column(String(255), nullable=True)  # ID del proveedor de pago
    webhook_url = Column(String(500), nullable=True)
    response_json = Column(JSONB, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    subscription = relationship("Subscription", back_populates="payment_attempts")


# ============================================================================
# RENOMBRADA: Empresa → ClienteCorporativo (Clientes que reservan)
# ============================================================================

class ClienteCorporativo(Base):
    """Empresas clientes que reservan en el hotel (ej: Coca Cola, Mercedes)"""
    __tablename__ = "cliente_corporativo"
    __table_args__ = (
        UniqueConstraint("cuit", name="uq_cliente_corporativo_cuit"),
        Index("idx_cliente_corporativo_nombre", "nombre"),
        Index("idx_cliente_corporativo_empresa_usuario", "empresa_usuario_id"),
    )

    id = Column(Integer, primary_key=True)
    empresa_usuario_id = Column(Integer, ForeignKey("empresa_usuarios.id"), nullable=False)
    
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
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    empresa_usuario = relationship("EmpresaUsuario", back_populates="clientes_corporativos")
    clientes = relationship("Cliente", back_populates="cliente_corporativo")


class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = (
        UniqueConstraint("tipo_documento", "numero_documento", name="uq_doc"),
        Index("idx_cliente_email", "email"),
        Index("idx_cliente_telefono", "telefono"),
        Index("idx_cliente_empresa", "empresa_usuario_id"),
        Index("idx_cliente_corporativo", "empresa_id"),
    )

    id = Column(Integer, primary_key=True)
    empresa_usuario_id = Column(Integer, ForeignKey("empresa_usuarios.id", ondelete="CASCADE"), nullable=False)
    nombre = Column(String(60), nullable=False)
    apellido = Column(String(60), nullable=False)
    tipo_documento = Column(String(20), nullable=False, default="DNI")
    numero_documento = Column(String(40), nullable=False)

    fecha_nacimiento = Column(Date, nullable=True)
    nacionalidad = Column(String(60), nullable=True)

    email = Column(String(100), nullable=True)
    telefono = Column(String(30), nullable=True)

    empresa_id = Column(Integer, ForeignKey("cliente_corporativo.id"), nullable=True)
    nota_interna = Column(Text, nullable=True)

    blacklist = Column(Boolean, default=False, nullable=False)
    motivo_blacklist = Column(Text, nullable=True)

    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    empresa_usuario = relationship("EmpresaUsuario", back_populates="clientes")
    cliente_corporativo = relationship("ClienteCorporativo", back_populates="clientes")
    transactions = relationship("Transaction", back_populates="cliente")

class RoomType(Base):
    __tablename__ = "room_types"
    __table_args__ = (
        UniqueConstraint("empresa_usuario_id", "nombre", name="uq_roomtype_empresa_nombre"),
        Index("idx_roomtype_empresa", "empresa_usuario_id"),
    )

    id = Column(Integer, primary_key=True)
    empresa_usuario_id = Column(Integer, ForeignKey("empresa_usuarios.id", ondelete="CASCADE"), nullable=False)
    nombre = Column(String(60), nullable=False)
    descripcion = Column(Text, nullable=True)
    capacidad = Column(Integer, nullable=False, default=1)
    precio_base = Column(Numeric(12, 2), nullable=True)  # Tarifa nocturna base
    amenidades = Column(JSONB, nullable=True)  # ["wifi","tv",...]
    activo = Column(Boolean, default=True, nullable=False)


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        UniqueConstraint("empresa_usuario_id", "numero", name="uq_room_empresa_numero"),
        Index("idx_room_tipo", "room_type_id"),
        Index("idx_room_estado_operativo", "estado_operativo"),
        Index("idx_room_empresa", "empresa_usuario_id"),
    )

    id = Column(Integer, primary_key=True)
    empresa_usuario_id = Column(Integer, ForeignKey("empresa_usuarios.id", ondelete="CASCADE"), nullable=False)
    numero = Column(String(10), nullable=False)   # "101", "PB1" si algún día te pintan letras
    piso = Column(Integer, nullable=True)
    room_type_id = Column(Integer, ForeignKey("room_types.id"), nullable=False)

    # Estado OPERATIVO (venta)
    # disponible | ocupada | bloqueada | fuera_servicio
    estado_operativo = Column(String(20), nullable=False, default="disponible")

    notas = Column(Text, nullable=True)
    particularidades = Column(JSONB, nullable=True)  # {"jacuzzi":true,...}
    activo = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    tipo = relationship("RoomType")
    empresa_usuario = relationship("EmpresaUsuario", back_populates="habitaciones")


class RatePlan(Base):
    __tablename__ = "rate_plans"
    __table_args__ = (Index("idx_rateplan_activo", "activo"),)

    id = Column(Integer, primary_key=True)
    nombre = Column(String(80), nullable=False)
    descripcion = Column(Text, nullable=True)

    # Reglas: cancelación, desayuno, etc.
    reglas = Column(JSONB, nullable=True)

    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class DailyRate(Base):
    """
    Tarifa por día y tipo de habitación (y opcionalmente por rate plan).
    Te permite temporadas / yield / feriados sin inventarte 20 columnas.
    """
    __tablename__ = "daily_rates"
    __table_args__ = (
        UniqueConstraint("empresa_usuario_id", "room_type_id", "fecha", "rate_plan_id", name="uq_rate_day_empresa"),
        Index("idx_rate_fecha", "fecha"),
        Index("idx_rate_empresa", "empresa_usuario_id"),
    )

    id = Column(Integer, primary_key=True)
    empresa_usuario_id = Column(Integer, ForeignKey("empresa_usuarios.id", ondelete="CASCADE"), nullable=False)
    room_type_id = Column(Integer, ForeignKey("room_types.id"), nullable=False)
    rate_plan_id = Column(Integer, ForeignKey("rate_plans.id"), nullable=True)

    fecha = Column(DateTime(timezone=True), nullable=False)  # guardá date si querés; DateTime también sirve
    precio = Column(Numeric(12, 2), nullable=False)

    room_type = relationship("RoomType")
    rate_plan = relationship("RatePlan")
    empresa_usuario = relationship("EmpresaUsuario", back_populates="daily_rates")

class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        Index("idx_res_fechas", "fecha_checkin", "fecha_checkout"),
        Index("idx_res_estado", "estado"),
        Index("idx_res_empresa", "empresa_usuario_id"),
    )

    id = Column(Integer, primary_key=True)
    empresa_usuario_id = Column(Integer, ForeignKey("empresa_usuarios.id", ondelete="CASCADE"), nullable=False)

    # Titular (puede ser null si es "nombre temporal")
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    empresa_id = Column(Integer, ForeignKey("cliente_corporativo.id"), nullable=True)
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
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(Integer, nullable=True)  # ID del usuario que canceló

    # Snapshot opcional: datos para reconstruir rápido sin 50 joins
    meta = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    cliente = relationship("Cliente")
    empresa = relationship("ClienteCorporativo", foreign_keys=[empresa_id])
    empresa_usuario = relationship("EmpresaUsuario", back_populates="reservas")
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

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    reservation = relationship("Reservation", back_populates="guests")
    cliente = relationship("Cliente")

class Stay(Base):
    __tablename__ = "stays"
    __table_args__ = (
        UniqueConstraint("reservation_id", name="uq_stay_reservation"),
        Index("idx_stay_estado", "estado"),
        Index("idx_stay_empresa", "empresa_usuario_id"),
    )

    id = Column(Integer, primary_key=True)
    empresa_usuario_id = Column(Integer, ForeignKey("empresa_usuarios.id", ondelete="CASCADE"), nullable=False)
    reservation_id = Column(Integer, ForeignKey("reservations.id", ondelete="RESTRICT"), nullable=False)

    # Estados operacionales (vida real)
    # pendiente_checkin | ocupada | pendiente_checkout | cerrada
    estado = Column(String(30), nullable=False, default="pendiente_checkin")

    checkin_real = Column(DateTime(timezone=True), nullable=True)
    checkout_real = Column(DateTime(timezone=True), nullable=True)

    notas_internas = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    reservation = relationship("Reservation")
    empresa_usuario = relationship("EmpresaUsuario", back_populates="stays")
    occupancies = relationship("StayRoomOccupancy", back_populates="stay", cascade="all, delete-orphan")
    charges = relationship("StayCharge", back_populates="stay", cascade="all, delete-orphan")
    payments = relationship("StayPayment", back_populates="stay", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="stay")

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

    desde = Column(DateTime(timezone=True), nullable=False)
    hasta = Column(DateTime(timezone=True), nullable=True)  # null = sigue ocupando

    motivo = Column(String(120), nullable=True)  # upgrade, mantenimiento, error, etc.
    creado_por = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

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

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
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

    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow)
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
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class HousekeepingTask(Base):
    __tablename__ = "housekeeping_tasks"
    __table_args__ = (
        Index("idx_hk_task_room_date", "room_id", "task_date"),
        Index("idx_hk_task_status_date", "status", "task_date"),
        Index("idx_hk_task_empresa", "empresa_usuario_id"),
        # Una sola limpieza diaria por habitación y día
        UniqueConstraint("room_id", "task_date", "task_type", name="uq_hk_task_daily"),
        # Una sola limpieza de checkout por estadía
        Index(
            "uq_hk_task_checkout_stay",
            "stay_id",
            unique=True,
            postgresql_where=text("task_type = 'checkout'"),
        ),
    )

    id = Column(Integer, primary_key=True)
    empresa_usuario_id = Column(Integer, ForeignKey("empresa_usuarios.id", ondelete="CASCADE"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False)
    stay_id = Column(Integer, ForeignKey("stays.id", ondelete="SET NULL"), nullable=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id", ondelete="SET NULL"), nullable=True)

    task_date = Column(Date, nullable=False)
    task_type = Column(String(50), nullable=False)  # Liberado de 20 a 50
    status = Column(String(30), nullable=False, default="pending")  # Liberado de 20 a 30
    priority = Column(String(20), nullable=False, default="media")  # baja | media | alta | urgente

    assigned_to_user_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True) # Para métricas de tiempo
    done_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    meta = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    room = relationship("Room")
    stay = relationship("Stay")
    reservation = relationship("Reservation")
    empresa_usuario = relationship("EmpresaUsuario", back_populates="housekeeping_tasks")


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
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    checklist_result = Column(JSON, nullable=True)
    minibar_snapshot = Column(JSON, nullable=True)
    notas = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

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

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
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
    fecha_hallazgo = Column(DateTime(timezone=True), default=datetime.utcnow)

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

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    closed_at = Column(DateTime(timezone=True), nullable=True)

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

    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
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
    completed_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    notes = Column(Text, nullable=True)

    room = relationship("Room")


class HotelSettings(Base):
    __tablename__ = "hotel_settings"
    __table_args__ = (
        UniqueConstraint("empresa_usuario_id", name="uq_hotel_settings_empresa_usuario"),
        Index("idx_hotel_settings_empresa", "empresa_usuario_id"),
    )

    id = Column(Integer, primary_key=True)
    empresa_usuario_id = Column(Integer, ForeignKey("empresa_usuarios.id", ondelete="CASCADE"), nullable=False, unique=True)
    checkout_hour = Column(Integer, default=12, nullable=False)
    checkout_minute = Column(Integer, default=0, nullable=False)
    cleaning_start_hour = Column(Integer, default=10, nullable=False)
    cleaning_end_hour = Column(Integer, default=12, nullable=False)
    auto_extend_stays = Column(Boolean, default=True, nullable=False)
    timezone = Column(String(50), default="America/Argentina/Buenos_Aires", nullable=False)
    overstay_price = Column(Numeric(10, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    empresa_usuario = relationship("EmpresaUsuario", back_populates="hotel_settings")


# ============================================================================
# SISTEMA DE CAJA - INGRESOS Y EGRESOS
# ============================================================================

class TransactionType(str, enum.Enum):
    """Tipo de transacción"""
    INGRESO = "ingreso"
    EGRESO = "egreso"


class PaymentMethod(str, enum.Enum):
    """Métodos de pago para transacciones de caja"""
    EFECTIVO = "efectivo"
    TRANSFERENCIA = "transferencia"
    TARJETA = "tarjeta"
    TARJETA_CREDITO = "tarjeta_credito"
    TARJETA_DEBITO = "tarjeta_debito"
    CHEQUE = "cheque"
    QR = "qr"
    OTRO = "otro"


class TransactionCategory(Base):
    """Categorías de ingresos y egresos"""
    __tablename__ = "transaction_categories"
    __table_args__ = (
        UniqueConstraint("empresa_usuario_id", "nombre", "tipo", name="uq_category_nombre_tipo"),
        Index("idx_category_empresa", "empresa_usuario_id"),
        Index("idx_category_tipo", "tipo"),
    )

    id = Column(Integer, primary_key=True)
    empresa_usuario_id = Column(Integer, ForeignKey("empresa_usuarios.id", ondelete="CASCADE"), nullable=False)
    nombre = Column(String(100), nullable=False)  # Ej: "Sueldos", "Proveedores", "Venta de Habitación"
    tipo = Column(Enum(TransactionType, name='transaction_type', values_callable=lambda obj: [e.value for e in obj]), nullable=False)  # ingreso o egreso
    descripcion = Column(Text, nullable=True)
    activo = Column(Boolean, default=True, nullable=False)
    es_sistema = Column(Boolean, default=False, nullable=False)  # No editable/eliminable si es True
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    empresa_usuario = relationship("EmpresaUsuario", back_populates="transaction_categories")
    transactions = relationship("Transaction", back_populates="category")


class Transaction(Base):
    """Registro de ingresos y egresos"""
    __tablename__ = "transactions"
    __table_args__ = (
        Index("idx_transaction_empresa", "empresa_usuario_id"),
        Index("idx_transaction_tipo", "tipo"),
        Index("idx_transaction_fecha", "fecha"),
        Index("idx_transaction_usuario", "usuario_id"),
        Index("idx_transaction_stay", "stay_id"),
        Index("idx_transaction_subscription", "subscription_id"),
        Index("idx_transaction_anulada", "anulada"),
    )

    id = Column(Integer, primary_key=True)
    empresa_usuario_id = Column(Integer, ForeignKey("empresa_usuarios.id", ondelete="CASCADE"), nullable=False)
    tipo = Column(Enum(TransactionType, name='transaction_type', values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    category_id = Column(Integer, ForeignKey("transaction_categories.id", ondelete="RESTRICT"), nullable=False)
    
    monto = Column(Numeric(12, 2), nullable=False)
    metodo_pago = Column(Enum(PaymentMethod, name='payment_method', values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    referencia = Column(String(255), nullable=True)  # Nro de comprobante, transferencia, etc.
    
    fecha = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    
    # Relaciones opcionales con entidades del sistema
    stay_id = Column(Integer, ForeignKey("stays.id", ondelete="SET NULL"), nullable=True)  # Si es ingreso de estadía
    subscription_id = Column(Integer, ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)  # Si es pago de suscripción
    cliente_id = Column(Integer, ForeignKey("clientes.id", ondelete="SET NULL"), nullable=True)  # Cliente asociado
    
    # Control de anulaciones (no se permite edición, solo anulación)
    anulada = Column(Boolean, default=False, nullable=False)
    anulada_por_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    anulada_fecha = Column(DateTime(timezone=True), nullable=True)
    motivo_anulacion = Column(Text, nullable=True)
    transaction_anulacion_id = Column(Integer, ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True)  # Referencia a la transacción que anula esta
    
    notas = Column(Text, nullable=True)
    es_automatica = Column(Boolean, default=False, nullable=False)  # True si fue generada por checkout/stripe
    metadata_json = Column(JSONB, nullable=True)  # {breakdown: [...], invoice_details, etc}
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    empresa_usuario = relationship("EmpresaUsuario", back_populates="transactions")
    category = relationship("TransactionCategory", back_populates="transactions")
    usuario = relationship("Usuario", foreign_keys=[usuario_id], back_populates="transactions_creadas")
    anulada_por = relationship("Usuario", foreign_keys=[anulada_por_id], back_populates="transactions_anuladas")
    stay = relationship("Stay", back_populates="transactions")
    subscription = relationship("Subscription", back_populates="transactions")
    cliente = relationship("Cliente", back_populates="transactions")
    transaction_anulacion = relationship("Transaction", remote_side=[id], uselist=False)


class CashClosing(Base):
    """Cierre de caja por turno"""
    __tablename__ = "cash_closings"
    __table_args__ = (
        Index("idx_cash_closing_empresa", "empresa_usuario_id"),
        Index("idx_cash_closing_usuario", "usuario_id"),
        Index("idx_cash_closing_fecha", "fecha_cierre"),
    )

    id = Column(Integer, primary_key=True)
    empresa_usuario_id = Column(Integer, ForeignKey("empresa_usuarios.id", ondelete="CASCADE"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    
    fecha_apertura = Column(DateTime(timezone=True), nullable=False)
    fecha_cierre = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    
    # Montos calculados por el sistema
    ingresos_sistema = Column(Numeric(12, 2), nullable=False, default=0)
    egresos_sistema = Column(Numeric(12, 2), nullable=False, default=0)
    saldo_sistema = Column(Numeric(12, 2), nullable=False, default=0)
    
    # Montos declarados por el usuario
    efectivo_declarado = Column(Numeric(12, 2), nullable=False)
    diferencia = Column(Numeric(12, 2), nullable=False)  # efectivo_declarado - saldo_sistema
    
    notas = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    empresa_usuario = relationship("EmpresaUsuario", back_populates="cash_closings")
    usuario = relationship("Usuario", back_populates="cash_closings")
