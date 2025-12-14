"""
Modelos mejorados de Reserva
Incluye: Estados tipados, detalles financieros, auditoría completa, historial detallado
Arquitectura Check-in/Check-out: Nuevos campos de estado operacional y auditoría
"""

from sqlalchemy import (
    Column, Integer, String, ForeignKey, Date, DateTime, Boolean, Numeric, Text,
    Index, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from database.conexion import Base
from datetime import datetime
from enum import Enum


# ========================================================================
# ENUMS
# ========================================================================

class EstadoReservaEnum(str, Enum):
    """Estados de reserva en ciclo operacional"""
    PENDIENTE_CHECKIN = "pendiente_checkin"
    OCUPADA = "ocupada"
    PENDIENTE_CHECKOUT = "pendiente_checkout"
    CERRADA = "cerrada"


class EstadoHabitacionEnum(str, Enum):
    """Estados de limpieza de habitación"""
    LIMPIA = "limpia"
    REVISAR = "revisar"
    EN_USO = "en_uso"
    SUCIA = "sucia"


# ----------- RESERVA -----------
class Reserva(Base):
    __tablename__ = "reservas"
    __table_args__ = (
        Index('idx_reserva_cliente', 'cliente_id'),
        Index('idx_reserva_empresa', 'empresa_id'),
        Index('idx_reserva_estado', 'estado'),
        Index('idx_reserva_fechas', 'fecha_checkin', 'fecha_checkout'),
        Index('idx_reserva_estado_operacional', 'estado_operacional'),
    )

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=True)
    nombre_temporal = Column(String(100), nullable=True)  # Para reservas sin asignar
    
    # Fechas
    fecha_checkin = Column(Date, nullable=False)
    fecha_checkout = Column(Date, nullable=False)
    fecha_checkin_real = Column(DateTime, nullable=True)  # Cuándo realmente llegó
    fecha_checkout_real = Column(DateTime, nullable=True)  # Cuándo realmente se fue
    
    # Ocupantes
    cantidad_adultos = Column(Integer, default=1)
    cantidad_menores = Column(Integer, default=0)
    
    # Estados: Clásico + Operacional
    estado = Column(String(20), nullable=False, default="pendiente")  # Compatibilidad backwards
    estado_operacional = Column(
        SQLEnum(EstadoReservaEnum),
        default=EstadoReservaEnum.PENDIENTE_CHECKIN,
        nullable=False
    )  # NEW: pendiente_checkin, ocupada, pendiente_checkout, cerrada
    
    # Financiero (breakdown)
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    descuento = Column(Numeric(12, 2), nullable=False, default=0)
    impuestos = Column(Numeric(12, 2), nullable=False, default=0)
    total = Column(Numeric(12, 2), nullable=False, default=0)
    
    # NEW: Detalles de pago
    monto_pagado = Column(Numeric(12, 2), default=0.00)
    saldo_pendiente = Column(Numeric(12, 2), default=0.00)
    
    # NEW: Estado de limpieza
    estado_habitacion = Column(
        SQLEnum(EstadoHabitacionEnum),
        nullable=True
    )  # limpia, revisar, en_uso, sucia
    
    # NEW: Gestión operacional
    usuario_actual = Column(String(50), nullable=True)  # Quién está atendiendo
    notas_internas = Column(Text, nullable=True)  # Para staff
    
    # Control
    deleted = Column(Boolean, default=False)
    notas = Column(Text, nullable=True)
    
    # Auditoría
    creado_en = Column(DateTime, default=datetime.utcnow)
    creado_por = Column(String(50), nullable=True)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    actualizado_por = Column(String(50), nullable=True)
    
    # Relaciones: Existentes
    cliente = relationship("Cliente", back_populates="reservas")
    empresa = relationship("Empresa", back_populates="reservas")
    habitaciones = relationship("ReservaHabitacion", back_populates="reserva", cascade="all, delete-orphan")
    items = relationship("ReservaItem", back_populates="reserva", cascade="all, delete-orphan")
    historial = relationship("HistorialReserva", back_populates="reserva", cascade="all, delete-orphan")
    
    # Relaciones: NEW (Arquitectura check-in)
    huespedes = relationship("ReservaHuesped", back_populates="reserva", cascade="all, delete-orphan")
    eventos = relationship("ReservaEvento", back_populates="reserva", cascade="all, delete-orphan")
    pagos = relationship("ReservaPago", back_populates="reserva", cascade="all, delete-orphan")
    room_moves = relationship("ReservaRoomMove", back_populates="reserva", cascade="all, delete-orphan")
    
    # Helper methods
    def agregar_evento(self, tipo, usuario, descripcion=None, payload=None):
        """Helper para crear evento (se usa desde endpoints)"""
        from models.reserva_eventos import ReservaEvento
        evento = ReservaEvento(
            reserva_id=self.id,
            tipo_evento=tipo,
            usuario=usuario,
            descripcion=descripcion,
            payload=payload
        )
        return evento
    
    @property
    def total_huespedes(self):
        """Cantidad total de huéspedes"""
        if hasattr(self, 'huespedes'):
            return len(self.huespedes)
        return 0
    
    @property
    def saldo(self):
        """Saldo pendiente (cantidad)"""
        return float(self.saldo_pendiente or 0)
    
    @property
    def total_pagado(self):
        """Total pagado (cantidad)"""
        return float(self.monto_pagado or 0)

    def __repr__(self):
        return f"<Reserva(id={self.id}, cliente_id={self.cliente_id}, estado='{self.estado_operacional}')>"


# ----------- RESERVA HABITACION (Tabla intermedia) -----------
class ReservaHabitacion(Base):
    __tablename__ = "reserva_habitaciones"
    __table_args__ = (
        Index('idx_resv_hab_reserva', 'reserva_id'),
        Index('idx_resv_hab_habitacion', 'habitacion_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    reserva_id = Column(Integer, ForeignKey("reservas.id", ondelete="CASCADE"), nullable=False)
    habitacion_id = Column(Integer, ForeignKey("habitaciones.id"), nullable=False)
    
    # Pricing
    precio_noche = Column(Numeric(10, 2), nullable=False)
    cantidad_noches = Column(Integer, default=1)
    subtotal_habitacion = Column(Numeric(12, 2), nullable=False)
    
    # Auditoría
    creado_en = Column(DateTime, default=datetime.utcnow)
    
    # Relaciones
    reserva = relationship("Reserva", back_populates="habitaciones")
    habitacion = relationship("Habitacion", back_populates="reserva_habitaciones")

    def __repr__(self):
        return f"<ReservaHabitacion(reserva_id={self.reserva_id}, habitacion_id={self.habitacion_id})>"


# ----------- RESERVA ITEM -----------
class ReservaItem(Base):
    __tablename__ = "reserva_items"
    __table_args__ = (
        Index('idx_resv_item_reserva', 'reserva_id'),
        Index('idx_resv_item_producto', 'producto_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    reserva_id = Column(Integer, ForeignKey("reservas.id", ondelete="CASCADE"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos_servicios.id"), nullable=True)
    
    # Descripción (para items personalizados)
    descripcion = Column(String(200))
    cantidad = Column(Integer, default=1, nullable=False)
    monto_unitario = Column(Numeric(10, 2), nullable=False)
    monto_total = Column(Numeric(12, 2), nullable=False)
    tipo_item = Column(String(20), nullable=False)  # producto, servicio, descuento, extra
    
    # Auditoría
    creado_en = Column(DateTime, default=datetime.utcnow)
    
    # Relaciones
    reserva = relationship("Reserva", back_populates="items")
    producto = relationship("ProductoServicio", back_populates="reserva_items")

    def __repr__(self):
        return f"<ReservaItem(reserva_id={self.reserva_id}, tipo='{self.tipo_item}')>"


# ----------- HISTORIAL RESERVA -----------
class HistorialReserva(Base):
    __tablename__ = "historial_reservas"
    __table_args__ = (
        Index('idx_hist_resv_reserva', 'reserva_id'),
        Index('idx_hist_resv_fecha', 'fecha'),
    )

    id = Column(Integer, primary_key=True, index=True)
    reserva_id = Column(Integer, ForeignKey("reservas.id", ondelete="CASCADE"), nullable=False)
    
    # Estados
    estado_anterior = Column(String(20), nullable=True)
    estado_nuevo = Column(String(20), nullable=False)
    
    # Auditoría
    usuario = Column(String(50), nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow, index=True)
    motivo = Column(Text, nullable=True)
    
    # Relaciones
    reserva = relationship("Reserva", back_populates="historial")

    def __repr__(self):
        return f"<HistorialReserva(reserva_id={self.reserva_id}, estado='{self.estado_nuevo}')>"