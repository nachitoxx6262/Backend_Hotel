from sqlalchemy import (
    Column, Integer, String, Boolean, UniqueConstraint
)
from sqlalchemy.orm import relationship
from database.conexion import Base  

class Empresa(Base):
    __tablename__ = "empresas"
    __table_args__ = (
        UniqueConstraint('cuit', name='uq_empresa_cuit'),
    )
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    cuit = Column(String(20), nullable=False, unique=True)
    email = Column(String(100), nullable=False)
    telefono = Column(String(30), nullable=False)
    direccion = Column(String(200))
    deleted = Column(Boolean, default=False, nullable=False)  # 🔥 Baja lógica
    blacklist = Column(Boolean, default=False, nullable=False)  # 🔥 Lista negra

    clientes = relationship("Cliente", back_populates="empresa")
    reservas = relationship("Reserva", back_populates="empresa")
