"""
Schemas Pydantic para Check-in/Check-out y Gestión de Huéspedes
Define request/response models para todos los endpoints.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, EmailStr, validator
from enum import Enum


# ========================================================================
# ENUMS
# ========================================================================

class EstadoReservaEnum(str, Enum):
    PENDIENTE_CHECKIN = "pendiente_checkin"
    OCUPADA = "ocupada"
    PENDIENTE_CHECKOUT = "pendiente_checkout"
    CERRADA = "cerrada"


class RolHuespedEnum(str, Enum):
    PRINCIPAL = "principal"
    ADULTO = "adulto"
    MENOR = "menor"


class TipoEventoEnum(str, Enum):
    CHECKIN = "CHECKIN"
    ADD_GUEST = "ADD_GUEST"
    UPDATE_GUEST = "UPDATE_GUEST"
    DELETE_GUEST = "DELETE_GUEST"
    ROOM_MOVE = "ROOM_MOVE"
    EXTEND_STAY = "EXTEND_STAY"
    PAYMENT = "PAYMENT"
    CHECKOUT = "CHECKOUT"
    NOTE = "NOTE"
    STATE_CHANGE = "STATE_CHANGE"
    CORRECTION = "CORRECTION"
    PAYMENT_REVERSAL = "PAYMENT_REVERSAL"


class MetodoPagoEnum(str, Enum):
    EFECTIVO = "efectivo"
    TARJETA = "tarjeta"
    TRANSFERENCIA = "transferencia"
    OTRO = "otro"


class EstadoHabitacionEnum(str, Enum):
    LIMPIA = "limpia"
    REVISAR = "revisar"
    EN_USO = "en_uso"
    SUCIA = "sucia"


# ========================================================================
# SCHEMAS PARA HUÉSPEDES
# ========================================================================

class HuespedBase(BaseModel):
    """Base para datos de huésped"""
    nombre: str = Field(..., min_length=1, max_length=60)
    apellido: str = Field(..., min_length=1, max_length=60)
    tipo_documento: str = Field(default="DNI", max_length=20)
    documento: str = Field(..., min_length=1, max_length=40)
    telefono: Optional[str] = Field(None, max_length=30)
    email: Optional[EmailStr] = None
    nacionalidad: Optional[str] = Field(None, max_length=60)
    fecha_nacimiento: Optional[str] = None  # ISO format: YYYY-MM-DD
    genero: Optional[str] = Field(None, max_length=10)
    direccion: Optional[str] = Field(None, max_length=200)


class HuespedCheckinRequest(HuespedBase):
    """Datos de huésped durante check-in"""
    rol: RolHuespedEnum = RolHuespedEnum.ADULTO
    habitacion_id: Optional[int] = None  # Si no, asignar habitación principal
    
    @validator('telefono', 'email', 'nacionalidad', 'direccion')
    def empty_str_to_none(cls, v):
        """Convertir string vacío a None"""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


class HuespedResponse(HuespedBase):
    """Respuesta de huésped desde API"""
    id: int
    cliente_id: int
    rol: RolHuespedEnum
    habitacion_id: Optional[int] = None
    fecha_agregado: datetime
    creado_por: str

    class Config:
        from_attributes = True


# ========================================================================
# SCHEMAS PARA CHECK-IN
# ========================================================================

class CheckinHuespedRequest(BaseModel):
    """Huésped durante check-in (puede ser nuevo o existente)"""
    cliente_id: Optional[int] = None
    rol: RolHuespedEnum
    habitacion_id: Optional[int] = None
    nombre: str = Field(..., min_length=1, max_length=60)
    apellido: str = Field(..., min_length=1, max_length=60)
    documento: str = Field(..., min_length=1, max_length=40)
    tipo_documento: str = Field(default="DNI", max_length=20)
    email: Optional[str] = None
    telefono: Optional[str] = None
    nacionalidad: Optional[str] = None
    fecha_nacimiento: Optional[str] = None
    genero: Optional[str] = None
    direccion: Optional[str] = None
    
    @validator('email', 'telefono', 'nacionalidad', 'direccion')
    def empty_str_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


class CheckinRequest(BaseModel):
    """Request para POST /reservas/{id}/checkin"""
    usuario: str = Field(..., min_length=1)
    fecha_checkin_real: Optional[datetime] = None  # Default a ahora
    notas_internas: Optional[str] = None
    huespedes: List[CheckinHuespedRequest] = Field(..., min_items=1)


class CheckinResponse(BaseModel):
    """Response para POST /reservas/{id}/checkin"""
    id: int
    estado: EstadoReservaEnum
    fecha_checkin_real: datetime
    huespedes: List[HuespedResponse]
    evento_id: int
    timestamp: datetime


# ========================================================================
# SCHEMAS PARA GESTIÓN DE HUÉSPEDES
# ========================================================================

class UpdateHuespedRequest(BaseModel):
    """Request para PUT /reservas/{id}/huespedes/{huesped_id}"""
    usuario: str
    razon: Optional[str] = None
    rol: Optional[RolHuespedEnum] = None
    habitacion_id: Optional[int] = None
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    documento: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    nacionalidad: Optional[str] = None


class DeleteHuespedRequest(BaseModel):
    """Request para DELETE /reservas/{id}/huespedes/{huesped_id}"""
    usuario: str
    razon: str


class DeleteHuespedResponse(BaseModel):
    """Response para DELETE"""
    eliminado: bool
    huesped_anterior: Dict[str, Any]
    evento_id: int


# ========================================================================
# SCHEMAS PARA PAGOS
# ========================================================================

class PagoRequest(BaseModel):
    """Request para POST /reservas/{id}/pagos"""
    usuario: str
    monto: float = Field(..., gt=0)
    metodo: MetodoPagoEnum
    referencia: Optional[str] = None
    notas: Optional[str] = None


class PagoResponse(BaseModel):
    """Response para POST /pagos"""
    pago_id: int
    monto: float
    total_pagado: float
    saldo_pendiente: float
    evento_id: int
    timestamp: datetime


# ========================================================================
# SCHEMAS PARA MOVIMIENTOS DE HABITACIÓN
# ========================================================================

class RoomMoveRequest(BaseModel):
    """Request para mover huésped a otra habitación"""
    usuario: str
    huesped_id: int
    habitacion_anterior_id: int
    habitacion_nueva_id: int
    razon: str = Field(..., max_length=200)
    notas: Optional[str] = None


class RoomMoveResponse(BaseModel):
    """Response para room move"""
    id: int
    reserva_id: int
    habitacion_anterior_id: int
    habitacion_nueva_id: int
    razon: str
    timestamp: datetime
    usuario: str


# ========================================================================
# SCHEMAS PARA EXTENSIÓN DE ESTADÍA
# ========================================================================

class ExtenderEstadiaRequest(BaseModel):
    """Request para extender fecha de checkout"""
    usuario: str
    fecha_checkout_nueva: str  # ISO format: YYYY-MM-DD
    razon: Optional[str] = None
    notas: Optional[str] = None


class ExtenderEstadiaResponse(BaseModel):
    """Response para extensión"""
    reserva_id: int
    fecha_checkout_anterior: str
    fecha_checkout_nueva: str
    noches_adicionales: int
    monto_adicional: float
    evento_id: int


# ========================================================================
# SCHEMAS PARA CHECK-OUT
# ========================================================================

class DanoReportado(BaseModel):
    """Daño reportado durante checkout"""
    descripcion: str
    costo: float = Field(default=0, ge=0)
    foto_url: Optional[str] = None


class CheckoutRequest(BaseModel):
    """Request para POST /reservas/{id}/checkout"""
    usuario: str
    fecha_checkout_real: Optional[datetime] = None
    pago_final: Optional[PagoRequest] = None
    estado_habitacion: EstadoHabitacionEnum
    notas_limpieza: Optional[str] = None
    daños_reportados: Optional[List[DanoReportado]] = None
    autorizar_deuda: bool = False


class ResumenCheckout(BaseModel):
    """Resumen financiero de checkout"""
    fecha_entrada: str
    fecha_salida: str
    total_noches: int
    monto_total: float
    pagos_registrados: float
    saldo_final: float
    estado_habitacion: str
    daños: List[DanoReportado] = []
    monto_daños_total: float = 0


class CheckoutResponse(BaseModel):
    """Response para POST /reservas/{id}/checkout"""
    id: int
    estado: EstadoReservaEnum
    resumen: ResumenCheckout
    recibo_id: str
    evento_id: int


# ========================================================================
# SCHEMAS PARA REVERSIÓN DE CHECKOUT
# ========================================================================

class RevertirCheckoutRequest(BaseModel):
    """Request para revertir checkout (solo admin)"""
    usuario: str
    razon: str


class RevertirCheckoutResponse(BaseModel):
    """Response para reversión"""
    reserva_id: int
    estado_anterior: EstadoReservaEnum
    estado_nuevo: EstadoReservaEnum
    evento_id: int
    timestamp: datetime


# ========================================================================
# SCHEMAS PARA AUDITORÍA Y EVENTOS
# ========================================================================

class EventoResponse(BaseModel):
    """Evento para timeline"""
    id: int
    tipo: TipoEventoEnum
    usuario: str
    timestamp: datetime
    descripcion: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class EventosListResponse(BaseModel):
    """Lista de eventos con paginación"""
    reserva_id: int
    total_eventos: int
    eventos: List[EventoResponse]


# ========================================================================
# SCHEMAS PARA ESTADO DE RESERVA
# ========================================================================

class ReservaEstadoResponse(BaseModel):
    """Estado actual de una reserva"""
    id: int
    estado: EstadoReservaEnum
    fecha_checkin: str
    fecha_checkout: str
    fecha_checkin_real: Optional[str] = None
    fecha_checkout_real: Optional[str] = None
    total_huespedes: int
    monto_total: float
    monto_pagado: float
    saldo_pendiente: float
    habitaciones: List[str]  # ["Hab 45", "Hab 46"]
    ultimo_evento: Optional[str] = None


# ========================================================================
# SCHEMAS PARA CUENTAS ABIERTAS (PARA FRONTEND)
# ========================================================================

class CuentaAbiertaResponse(BaseModel):
    """Información de cuenta abierta para recepción"""
    reserva_id: int
    cliente_principal: str  # "Juan Pérez"
    monto_original: float
    pagado: float
    pendiente: float
    metodo_pago_preferido: Optional[str] = None
    ultima_actualizacion: datetime


# ========================================================================
# SCHEMAS PARA LISTA DE HUÉSPEDES (OCCUPANCY DISPLAY)
# ========================================================================

class HuespedOccupancyResponse(BaseModel):
    """Huésped para display de ocupación"""
    id: int
    nombre: str
    apellido: str
    rol: RolHuespedEnum
    documento: str
    habitacion_numero: int
    email: Optional[str] = None
    telefono: Optional[str] = None


class OccupancyListResponse(BaseModel):
    """Lista de ocupación por habitación"""
    habitacion_id: int
    habitacion_numero: int
    estado: str  # "ocupada", "limpia", "mantenimiento"
    huespedes: List[HuespedOccupancyResponse]
    reserva_id: int
    fecha_checkout: str


# ========================================================================
# SCHEMAS DE VALIDACIÓN
# ========================================================================

class DuplicadoAdvertencia(BaseModel):
    """Advertencia de documento duplicado"""
    duplicado: bool
    reservas_activas: List[Dict[str, Any]] = []
    mensaje: str


class CapacidadAdvertencia(BaseModel):
    """Advertencia de capacidad excedida"""
    supera_capacidad: bool
    capacidad_max: int
    personas_actuales: int
    diferencia: int


# ========================================================================
# SCHEMAS PARA DATOS AGREGADOS (ADMIN/REPORTS)
# ========================================================================

class CheckinCheckoutStats(BaseModel):
    """Estadísticas de check-in/checkout"""
    total_checkins_hoy: int
    total_checkouts_hoy: int
    reservas_ocupadas: int
    reservas_pendientes_checkout: int
    saldo_pendiente_total: float
    tasa_ocupacion: float  # 0.0 - 1.0


class RevisionHuesped(BaseModel):
    """Revisión de documento de huésped (antecedentes)"""
    cliente_id: int
    nombre: str
    total_reservas: int
    noches_totales: int
    gasto_total: float
    ultima_reserva: Optional[str] = None
    flags: List[str] = []  # ['vip', 'problema', 'preferente']
