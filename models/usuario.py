"""
Modelos de Usuario para autenticación y autorización
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from database.conexion import Base
from .rol import Rol, UsuarioRol


class Usuario(Base):
    """Tabla de usuarios del sistema"""
    __tablename__ = "usuarios"
    __table_args__ = (
        Index('idx_usuario_username', 'username'),
        Index('idx_usuario_email', 'email'),
        Index('idx_usuario_activo', 'activo'),
    )

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    nombre = Column(String(60), nullable=True)
    apellido = Column(String(60), nullable=True)

    # Empresa a la que pertenece el usuario (tenant)
    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="SET NULL"), nullable=True)
    
    # Rol principal (para compatibilidad)
    rol = Column(String(20), nullable=False, default="readonly")
    
    # Control de estado
    activo = Column(Boolean, default=True, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    
    # Auditoría
    fecha_creacion = Column(DateTime, default=datetime.utcnow, nullable=False)
    fecha_ultima_modificacion = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ultimo_login = Column(DateTime, nullable=True)
    
    # Seguridad
    intentos_fallidos = Column(Integer, default=0, nullable=False)
    bloqueado_hasta = Column(DateTime, nullable=True)
    
    # Relaciones
    usuario_roles = relationship("UsuarioRol", back_populates="usuario", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Usuario(id={self.id}, username='{self.username}', rol='{self.rol}')>"
