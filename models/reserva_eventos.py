"""
Modelos SQLAlchemy para la nueva arquitectura Check-in/Check-out
Incluye: ReservaHuesped, ReservaEvento, ReservaPago, ReservaRoomMove
Actualización: Modelo Reserva con nuevos campos de estado y auditoría
"""

from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey,
    Text, CheckConstraint, UniqueConstraint, Index, Enum as SQLEnum,
    ForeignKeyConstraint, Sequence
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from database.conexion import Base


class EstadoReserva(str, Enum):
    """Estados permitidos para reservas"""
    PENDIENTE_CHECKIN = "pendiente_checkin"
    OCUPADA = "ocupada"
    PENDIENTE_CHECKOUT = "pendiente_checkout"
    CERRADA = "cerrada"


class RolHuesped(str, Enum):
    """Roles de huéspedes en una reserva"""
    PRINCIPAL = "principal"
    ADULTO = "adulto"
    MENOR = "menor"


class TipoEvento(str, Enum):
    """Tipos de eventos para auditoría"""
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


class MetodoPago(str, Enum):
    """Métodos de pago permitidos"""
    EFECTIVO = "efectivo"
    TARJETA = "tarjeta"
    TRANSFERENCIA = "transferencia"
    OTRO = "otro"


class EstadoHabitacion(str, Enum):
    """Estados de limpieza de habitación"""
    LIMPIA = "limpia"
    REVISAR = "revisar"
    EN_USO = "en_uso"
    SUCIA = "sucia"


class ReservaHuesped(Base):
    """
    Relación N:N entre Reservas y Clientes.
    Permite múltiples huéspedes por reserva con roles específicos y asignaciones de habitación.
    """
    __tablename__ = "reservas_huespedes"
    __table_args__ = (
        UniqueConstraint('reserva_id', 'cliente_id', name='uq_reserva_cliente'),
        UniqueConstraint('reserva_id', 'orden_registro', name='uq_reserva_orden'),
        Index('idx_reserva_huesped_reserva', 'reserva_id'),
        Index('idx_reserva_huesped_cliente', 'cliente_id'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    reserva_id = Column(Integer, ForeignKey('reservas.id', ondelete='CASCADE'), nullable=False)
    cliente_id = Column(Integer, ForeignKey('clientes.id', ondelete='SET NULL'), nullable=True)
    rol = Column(SQLEnum(RolHuesped), nullable=False)
    habitacion_id = Column(Integer, ForeignKey('habitaciones.id', ondelete='SET NULL'), nullable=True)
    orden_registro = Column(Integer, nullable=False)  # Orden temporal de registro
    fecha_agregado = Column(DateTime, default=datetime.utcnow)
    creado_por = Column(String(50), nullable=False)

    # Relationships
    reserva = relationship("Reserva", back_populates="huespedes")
    cliente = relationship("Cliente")
    habitacion = relationship("Habitacion")


class ReservaEvento(Base):
    """
    Auditoría inmutable de todos los eventos en una reserva.
    Permite reconstruir histórico, detectar cambios, y hacer rollback.
    """
    __tablename__ = "reserva_eventos"
    __table_args__ = (
        UniqueConstraint('reserva_id', 'timestamp', name='uq_reserva_evento_timestamp'),
        Index('idx_reserva_evento_reserva', 'reserva_id'),
        Index('idx_reserva_evento_timestamp', 'timestamp'),
        Index('idx_reserva_evento_tipo', 'tipo_evento'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    reserva_id = Column(Integer, ForeignKey('reservas.id', ondelete='CASCADE'), nullable=False)
    tipo_evento = Column(SQLEnum(TipoEvento), nullable=False)
    usuario = Column(String(50), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    payload = Column(JSONB, nullable=True)  # Contenido completo del cambio
    cambios_anteriores = Column(JSONB, nullable=True)  # Para rollback
    ip_address = Column(String(45), nullable=True)
    descripcion = Column(Text, nullable=True)  # Resumen legible

    # Relationships
    reserva = relationship("Reserva", back_populates="eventos")

    def to_dict(self):
        """Convertir evento a diccionario para respuesta"""
        return {
            'id': self.id,
            'tipo': self.tipo_evento.value,
            'usuario': self.usuario,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'descripcion': self.descripcion,
            'payload': self.payload,
        }


class ReservaPago(Base):
    """
    Transacciones de dinero por reserva.
    Permite pagos parciales, reversas, y auditoría completa de dinero.
    """
    __tablename__ = "reserva_pagos"
    __table_args__ = (
        Index('idx_reserva_pago_reserva', 'reserva_id'),
        Index('idx_reserva_pago_timestamp', 'timestamp'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    reserva_id = Column(Integer, ForeignKey('reservas.id', ondelete='CASCADE'), nullable=False)
    monto = Column(Numeric(12, 2), nullable=False)
    metodo = Column(SQLEnum(MetodoPago), nullable=False)
    referencia = Column(String(100), nullable=True)  # Ticket, cheque, referencia bancaria
    timestamp = Column(DateTime, default=datetime.utcnow)
    usuario = Column(String(50), nullable=False)
    notas = Column(Text, nullable=True)
    es_reverso = Column(Boolean, default=False)  # Para devoluciones
    creado_en = Column(DateTime, default=datetime.utcnow)

    # Relationships
    reserva = relationship("Reserva", back_populates="pagos")


class ReservaRoomMove(Base):
    """
    Historial de cambios de habitación dentro de una reserva.
    Permite tracking de movimientos y optimización de capacidad.
    """
    __tablename__ = "reserva_room_moves"
    __table_args__ = (
        UniqueConstraint('reserva_id', 'timestamp', name='uq_reserva_move_timestamp'),
        Index('idx_reserva_move_reserva', 'reserva_id'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    reserva_id = Column(Integer, ForeignKey('reservas.id', ondelete='CASCADE'), nullable=False)
    habitacion_anterior_id = Column(Integer, ForeignKey('habitaciones.id', ondelete='SET NULL'), nullable=True)
    habitacion_nueva_id = Column(Integer, ForeignKey('habitaciones.id', ondelete='RESTRICT'), nullable=False)
    razon = Column(String(200), nullable=False)  # upgrade, queja, error, mantenimiento
    timestamp = Column(DateTime, default=datetime.utcnow)
    usuario = Column(String(50), nullable=False)

    # Relationships
    reserva = relationship("Reserva", back_populates="room_moves")
    habitacion_anterior = relationship("Habitacion", foreign_keys=[habitacion_anterior_id])
    habitacion_nueva = relationship("Habitacion", foreign_keys=[habitacion_nueva_id])


# ========================================================================
# ACTUALIZACIÓN AL MODELO RESERVA EXISTENTE
# (Asumir que existe como models/reserva.py)
# 
# Agregar estas líneas al modelo Reserva:
# ========================================================================
"""
from sqlalchemy import String, DateTime, Numeric
from enum import Enum

# En la clase Reserva, agregar campos:

class Reserva(Base):
    __tablename__ = "reservas"
    
    # ... campos existentes ...
    
    # NUEVOS CAMPOS PARA ARQUITECTURA
    estado = Column(
        SQLEnum(EstadoReserva),
        default=EstadoReserva.PENDIENTE_CHECKIN,
        nullable=False
    )
    fecha_checkin_real = Column(DateTime, nullable=True)
    fecha_checkout_real = Column(DateTime, nullable=True)
    monto_pagado = Column(Numeric(12, 2), default=0.00)
    saldo_pendiente = Column(Numeric(12, 2), default=0.00)
    estado_habitacion = Column(
        SQLEnum(EstadoHabitacion),
        nullable=True
    )
    usuario_actual = Column(String(50), nullable=True)
    notas_internas = Column(Text, nullable=True)
    actualizado_por = Column(String(50), nullable=True)
    
    # RELATIONSHIPS
    huespedes = relationship(
        "ReservaHuesped",
        back_populates="reserva",
        cascade="all, delete-orphan"
    )
    eventos = relationship(
        "ReservaEvento",
        back_populates="reserva",
        cascade="all, delete-orphan"
    )
    pagos = relationship(
        "ReservaPago",
        back_populates="reserva",
        cascade="all, delete-orphan"
    )
    room_moves = relationship(
        "ReservaRoomMove",
        back_populates="reserva",
        cascade="all, delete-orphan"
    )
    
    def agregar_evento(self, tipo: TipoEvento, usuario: str, 
                      descripcion: str = None, payload: dict = None,
                      cambios_anteriores: dict = None, ip_address: str = None):
        '''Helper para crear eventos de forma segura'''
        evento = ReservaEvento(
            reserva_id=self.id,
            tipo_evento=tipo,
            usuario=usuario,
            descripcion=descripcion,
            payload=payload,
            cambios_anteriores=cambios_anteriores,
            ip_address=ip_address
        )
        self.eventos.append(evento)
        return evento
    
    @property
    def total_huespedes(self) -> int:
        return len(self.huespedes)
    
    @property
    def total_pagado(self) -> float:
        return float(self.monto_pagado or 0)
    
    @property
    def saldo(self) -> float:
        return float(self.saldo_pendiente or 0)
"""

# ========================================================================
# FIN DE ACTUALIZACIONES
# ========================================================================
