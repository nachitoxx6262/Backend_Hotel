from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime

from database.conexion import Base


class Rol(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(50), unique=True, nullable=False, index=True)
    descripcion = Column(String(255), nullable=True)
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    permisos = relationship("RolPermiso", back_populates="rol", cascade="all, delete-orphan")
    usuarios = relationship("UsuarioRol", back_populates="rol", cascade="all, delete-orphan")


class Permiso(Base):
    __tablename__ = "permisos"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(100), unique=True, nullable=False, index=True)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(String(255), nullable=True)
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    roles = relationship("RolPermiso", back_populates="permiso", cascade="all, delete-orphan")


class RolPermiso(Base):
    __tablename__ = "roles_permisos"

    id = Column(Integer, primary_key=True)
    rol_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permiso_id = Column(Integer, ForeignKey("permisos.id", ondelete="CASCADE"), nullable=False)

    rol = relationship("Rol", back_populates="permisos")
    permiso = relationship("Permiso", back_populates="roles")

    __table_args__ = (
        UniqueConstraint("rol_id", "permiso_id", name="uq_rol_permiso"),
    )


class UsuarioRol(Base):
    __tablename__ = "usuarios_roles"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    rol_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)

    rol = relationship("Rol", back_populates="usuarios")
    usuario = relationship("Usuario", back_populates="usuario_roles")

    __table_args__ = (
        UniqueConstraint("usuario_id", "rol_id", name="uq_usuario_rol"),
    )
