"""
Modelo mejorado de ProductoServicio
Incluye: Tipos categorizados, control de activos, auditoría
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Numeric, Text, Index
)
from sqlalchemy.orm import relationship
from database.conexion import Base
from datetime import datetime


# ----------- PRODUCTO / SERVICIO / DESCUENTO -----------
class ProductoServicio(Base):
    __tablename__ = "productos_servicios"
    __table_args__ = (
        Index('idx_producto_tipo', 'tipo'),
        Index('idx_producto_activo', 'activo'),
    )

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    tipo = Column(String(20), nullable=False)  # producto, servicio, descuento, extra
    descripcion = Column(Text, nullable=True)
    precio_unitario = Column(Numeric(10, 2), nullable=False)
    
    # Control
    activo = Column(Boolean, default=True)
    
    # Auditoría
    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    actualizado_por = Column(String(50), nullable=True)
    
    # Relaciones
    reserva_items = relationship("ReservaItem", back_populates="producto")

    def __repr__(self):
        return f"<ProductoServicio(id={self.id}, nombre='{self.nombre}', tipo='{self.tipo}')>"


