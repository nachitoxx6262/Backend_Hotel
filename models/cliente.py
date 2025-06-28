from sqlalchemy import (
    Column, Integer, String, ForeignKey, Boolean, UniqueConstraint
)
from sqlalchemy.orm import relationship
from database.conexion import Base

class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = (
        UniqueConstraint('tipo_documento', 'numero_documento', name='uq_tipo_numero_doc'),
    )
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(60), nullable=False)
    apellido = Column(String(60), nullable=False)
    tipo_documento = Column(String(20), nullable=False)
    numero_documento = Column(String(40), nullable=False)
    nacionalidad = Column(String(60), nullable=False)
    email = Column(String(100), nullable=False)
    telefono = Column(String(30), nullable=False)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=True)
    deleted = Column(Boolean, default=False, nullable=False)  # 🟢 Baja lógica

    empresa = relationship("Empresa", back_populates="clientes")
    reservas = relationship("Reserva", back_populates="cliente")
