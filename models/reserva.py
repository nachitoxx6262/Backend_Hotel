from sqlalchemy import (
    Column, Integer, String, ForeignKey, Date, Boolean, Numeric, Text, DateTime
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from database.conexion import Base  
from datetime import datetime


# ----------- RESERVA -----------
class Reserva(Base):
    __tablename__ = "reservas"

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=True)
    fecha_checkin = Column(Date, nullable=False)
    fecha_checkout = Column(Date, nullable=False)
    estado = Column(String(20), nullable=False)  # activa, finalizada, cancelada
    total = Column(Numeric(12, 2), nullable=True)
    deleted = Column(Boolean, default=False)
    notas = Column(Text, nullable=True)

    cliente = relationship("Cliente", back_populates="reservas")
    empresa = relationship("Empresa", back_populates="reservas")
    habitaciones = relationship("ReservaHabitacion", back_populates="reserva")
    items = relationship("ReservaItem", back_populates="reserva")
    historial = relationship("HistorialReserva", back_populates="reserva")


# ----------- RESERVA ITEM -----------
class ReservaItem(Base):
    __tablename__ = "reserva_items"

    id = Column(Integer, primary_key=True, index=True)
    reserva_id = Column(Integer, ForeignKey("reservas.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos_servicios.id"), nullable=True)
    descripcion = Column(String(200))  # Solo para items personalizados
    cantidad = Column(Integer, default=1, nullable=False)
    monto_total = Column(Numeric(12, 2), nullable=False)
    tipo_item = Column(String(20), nullable=False)  # producto, servicio, descuento

    reserva = relationship("Reserva", back_populates="items")
    producto = relationship("ProductoServicio", back_populates="reserva_items")


# ----------- RESERVA HABITACION (Tabla intermedia) -----------
class ReservaHabitacion(Base):
    __tablename__ = "reserva_habitaciones"

    id = Column(Integer, primary_key=True, index=True)
    reserva_id = Column(Integer, ForeignKey("reservas.id"), nullable=False)
    habitacion_id = Column(Integer, ForeignKey("habitaciones.id"), nullable=False)
    precio_noche = Column(Numeric(10, 2), nullable=False)

    reserva = relationship("Reserva", back_populates="habitaciones")
    habitacion = relationship("Habitacion", back_populates="reserva_habitaciones")



class HistorialReserva(Base):
    __tablename__ = "historial_reservas"

    id = Column(Integer, primary_key=True, index=True)
    reserva_id = Column(Integer, ForeignKey("reservas.id"), nullable=False)
    estado = Column(String(20), nullable=False)
    usuario = Column(String(50), nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)

    reserva = relationship("Reserva", back_populates="historial")