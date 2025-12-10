"""
Modelos mejorados de Reserva
Incluye: Estados tipados, detalles financieros, auditoría completa, historial detallado
"""

from sqlalchemy import (
    Column, Integer, String, ForeignKey, Date, DateTime, Boolean, Numeric, Text,
    Index
)
from sqlalchemy.orm import relationship
from database.conexion import Base
from datetime import datetime


# ----------- RESERVA -----------
class Reserva(Base):
    __tablename__ = "reservas"
    __table_args__ = (
        Index('idx_reserva_cliente', 'cliente_id'),
        Index('idx_reserva_empresa', 'empresa_id'),
        Index('idx_reserva_estado', 'estado'),
        Index('idx_reserva_fechas', 'fecha_checkin', 'fecha_checkout'),
    )

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=True)
    nombre_temporal = Column(String(100), nullable=True)  # Para reservas sin asignar
    
    # Fechas
    fecha_checkin = Column(Date, nullable=False)
    fecha_checkout = Column(Date, nullable=False)
    
    # Ocupantes
    cantidad_adultos = Column(Integer, default=1)
    cantidad_menores = Column(Integer, default=0)
    
    # Estados
    estado = Column(String(20), nullable=False, default="pendiente")  # pendiente, confirmada, activa, finalizada, cancelada
    
    # Financiero (breakdown)
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    descuento = Column(Numeric(12, 2), nullable=False, default=0)
    impuestos = Column(Numeric(12, 2), nullable=False, default=0)
    total = Column(Numeric(12, 2), nullable=False, default=0)
    
    # Control
    deleted = Column(Boolean, default=False)
    notas = Column(Text, nullable=True)
    
    # Auditoría
    creado_en = Column(DateTime, default=datetime.utcnow)
    creado_por = Column(String(50), nullable=True)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    actualizado_por = Column(String(50), nullable=True)
    
    # Relaciones
    cliente = relationship("Cliente", back_populates="reservas")
    empresa = relationship("Empresa", back_populates="reservas")
    habitaciones = relationship("ReservaHabitacion", back_populates="reserva", cascade="all, delete-orphan")
    items = relationship("ReservaItem", back_populates="reserva", cascade="all, delete-orphan")
    historial = relationship("HistorialReserva", back_populates="reserva", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Reserva(id={self.id}, cliente_id={self.cliente_id}, estado='{self.estado}')>"


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