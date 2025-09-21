from sqlalchemy import (
    Column, Integer, String, ForeignKey, Date, Boolean, Numeric, Text
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from database.conexion import Base 

# ----------- HABITACION -----------
class Habitacion(Base):
    __tablename__ = "habitaciones"

    id = Column(Integer, primary_key=True, index=True)
    numero = Column(Integer, nullable=False, unique=True)
    tipo = Column(String(30), nullable=False)  # simple, doble, suite, etc.
    estado = Column(String(30), nullable=False)  # libre, ocupada, mantenimiento
    mantenimiento = Column(Boolean, default=False)
    observaciones = Column(Text)

    reserva_habitaciones = relationship("ReservaHabitacion", back_populates="habitacion")


