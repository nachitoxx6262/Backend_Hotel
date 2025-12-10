"""
Modelo mejorado de Cliente
Incluye: Más campos de información, preferencias, auditoría completa
"""

from sqlalchemy import (
    Column, Integer, String, ForeignKey, Date, DateTime, Boolean, 
    Numeric, Text, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from database.conexion import Base
from datetime import datetime


class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = (
        UniqueConstraint('tipo_documento', 'numero_documento', name='uq_tipo_numero_doc'),
        Index('idx_cliente_email', 'email'),
        Index('idx_cliente_tipo_doc', 'tipo_documento'),
        Index('idx_cliente_blacklist', 'blacklist'),
    )

    id = Column(Integer, primary_key=True, index=True)
    
    # Información personal
    nombre = Column(String(60), nullable=False)
    apellido = Column(String(60), nullable=False)
    tipo_documento = Column(String(20), nullable=False)
    numero_documento = Column(String(40), nullable=False)
    fecha_nacimiento = Column(Date, nullable=True)
    nacionalidad = Column(String(60), nullable=False)
    genero = Column(String(10), nullable=True)  # M, F, O
    
    # Contacto
    email = Column(String(100), nullable=False)
    telefono = Column(String(30), nullable=False)
    telefono_alternativo = Column(String(30), nullable=True)
    
    # Dirección
    direccion = Column(String(200), nullable=True)
    ciudad = Column(String(100), nullable=True)
    provincia = Column(String(100), nullable=True)
    codigo_postal = Column(String(20), nullable=True)
    
    # Relación empresarial
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=True)
    tipo_cliente = Column(String(20), nullable=False, default="individual")  # individual, corporativo, vip
    
    # Preferencias
    preferencias = Column(Text, nullable=True)  # JSON con preferencias (tipo habitación, piso, etc.)
    nota_interna = Column(Text, nullable=True)
    
    # Control
    activo = Column(Boolean, default=True)
    deleted = Column(Boolean, default=False, nullable=False)
    blacklist = Column(Boolean, default=False, nullable=False)
    motivo_blacklist = Column(Text, nullable=True)
    
    # Auditoría
    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    actualizado_por = Column(String(50), nullable=True)
    
    # Relaciones
    empresa = relationship("Empresa", back_populates="clientes")
    reservas = relationship("Reserva", back_populates="cliente")

    def __repr__(self):
        return f"<Cliente(id={self.id}, nombre='{self.nombre} {self.apellido}')>"
