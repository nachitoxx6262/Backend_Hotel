from sqlalchemy import (
    Column, Integer, String, ForeignKey, Date, Boolean, Numeric, Text
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from database.conexion import Base

# ----------- PRODUCTO / SERVICIO / DESCUENTO -----------
class ProductoServicio(Base):
    __tablename__ = "productos_servicios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    tipo = Column(String(20), nullable=False)  # producto, servicio, descuento
    descripcion = Column(Text)
    precio_unitario = Column(Numeric(10, 2), nullable=False)

    reserva_items = relationship("ReservaItem", back_populates="producto")


