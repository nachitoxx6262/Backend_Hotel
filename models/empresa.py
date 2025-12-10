"""
Modelo mejorado de Empresa
Incluye: Información completa, términos comerciales, auditoría
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Numeric, Text,
    UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from database.conexion import Base
from datetime import datetime


class Empresa(Base):
    __tablename__ = "empresas"
    __table_args__ = (
        UniqueConstraint('cuit', name='uq_empresa_cuit'),
        Index('idx_empresa_nombre', 'nombre'),
        Index('idx_empresa_blacklist', 'blacklist'),
    )

    id = Column(Integer, primary_key=True, index=True)
    
    # Información general
    nombre = Column(String(150), nullable=False)
    cuit = Column(String(20), nullable=False, unique=True)
    tipo_empresa = Column(String(50), nullable=False)  # Tipo de empresa
    
    # Contacto principal
    contacto_principal_nombre = Column(String(100), nullable=False)
    contacto_principal_titulo = Column(String(100), nullable=True)
    contacto_principal_email = Column(String(100), nullable=False)
    contacto_principal_telefono = Column(String(30), nullable=False)
    contacto_principal_celular = Column(String(30), nullable=True)
    
    # Dirección
    direccion = Column(String(200), nullable=False)
    ciudad = Column(String(100), nullable=False)
    provincia = Column(String(100), nullable=True)
    codigo_postal = Column(String(20), nullable=True)
    
    # Términos comerciales
    dias_credito = Column(Integer, default=30)
    limite_credito = Column(Numeric(12, 2), default=0)
    tasa_descuento = Column(Numeric(5, 2), default=0)  # Descuento porcentual
    
    # Control
    activo = Column(Boolean, default=True)
    deleted = Column(Boolean, default=False, nullable=False)
    blacklist = Column(Boolean, default=False, nullable=False)
    motivo_blacklist = Column(Text, nullable=True)
    nota_interna = Column(Text, nullable=True)
    
    # Auditoría
    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    actualizado_por = Column(String(50), nullable=True)
    
    # Relaciones
    clientes = relationship("Cliente", back_populates="empresa")
    reservas = relationship("Reserva", back_populates="empresa")

    def __repr__(self):
        return f"<Empresa(id={self.id}, nombre='{self.nombre}')>"
