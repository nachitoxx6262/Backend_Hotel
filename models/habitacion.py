"""
Modelo mejorado de Habitación
Incluye: Categorías, historial de mantenimiento, auditoría completa
"""

from sqlalchemy import (
    Column, Integer, String, ForeignKey, Date, DateTime, Boolean, 
    Numeric, Text, Index, JSON
)
from sqlalchemy.orm import relationship
from database.conexion import Base
from datetime import datetime
import enum


class CategoriaHabitacion(Base):
    """
    Tabla para categorizar tipos de habitaciones
    Ejemplo: Simple, Doble, Triple, Suite, etc.
    """
    __tablename__ = "categorias_habitaciones"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(50), nullable=False, unique=True, index=True)
    descripcion = Column(Text, nullable=True)
    capacidad_personas = Column(Integer, nullable=False, default=1)
    precio_base_noche = Column(Numeric(10, 2), nullable=False)
    amenidades = Column(JSON, nullable=True, default=[])  # Array de amenidades
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    habitaciones = relationship("Habitacion", back_populates="categoria")

    __table_args__ = (
        Index('idx_categoria_nombre', 'nombre'),
    )


class Habitacion(Base):
    """
    Modelo mejorado de Habitación
    - Vinculada a categoría
    - Sin campo mantenimiento booleano (usa tabla de historial)
    - Auditoría completa
    """
    __tablename__ = "habitaciones"

    id = Column(Integer, primary_key=True, index=True)
    numero = Column(Integer, nullable=False, unique=True, index=True)
    categoria_id = Column(Integer, ForeignKey("categorias_habitaciones.id"), nullable=False)
    estado = Column(String(30), nullable=False, default="disponible")
    
    # Información adicional
    piso = Column(Integer, nullable=True)
    observaciones = Column(Text, nullable=True)
    fotos_url = Column(Text, nullable=True)  # JSON con URLs de fotos
    
    # Información de camas y particularidades
    num_camas = Column(Integer, default=1)  # Número total de camas
    tipo_camas = Column(String(100), nullable=True)  # Ej: "2 simples", "1 doble", "1 doble + 2 simples"
    particularidades = Column(JSON, nullable=True, default={})  # {"tiene_jacuzzi": true, "terraza": true, etc}
    
    # Template de tareas personalizado
    template_tareas_id = Column(Integer, ForeignKey("housekeeping_tareas_templates.id"), nullable=True)
    
    # Auditoría
    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    actualizado_por = Column(String(50), nullable=True)  # Usuario que realizó el cambio
    
    # Control
    activo = Column(Boolean, default=True)
    deleted = Column(Boolean, default=False, nullable=False)

    # Relaciones
    categoria = relationship("CategoriaHabitacion", back_populates="habitaciones")
    reserva_habitaciones = relationship("ReservaHabitacion", back_populates="habitacion")
    mantenimientos = relationship("MantenimientoHabitacion", back_populates="habitacion")
    template_tareas = relationship("HousekeepingTareaTemplate", foreign_keys=[template_tareas_id], back_populates="habitaciones")


    __table_args__ = (
        Index('idx_habitacion_numero', 'numero'),
        Index('idx_habitacion_estado', 'estado'),
        Index('idx_habitacion_categoria', 'categoria_id'),
    )


class MantenimientoHabitacion(Base):
    """
    Historial de mantenimientos de cada habitación
    Proporciona trazabilidad completa de trabajos realizados
    """
    __tablename__ = "mantenimientos_habitaciones"

    id = Column(Integer, primary_key=True, index=True)
    habitacion_id = Column(Integer, ForeignKey("habitaciones.id"), nullable=False)
    
    # Información del mantenimiento
    tipo = Column(String(30), nullable=False)  # preventivo, correctivo, urgente, limpieza, etc.
    estado = Column(String(30), nullable=False, default="programado")
    descripcion = Column(Text, nullable=False)
    observaciones = Column(Text, nullable=True)
    
    # Fechas
    fecha_programada = Column(Date, nullable=False)
    fecha_inicio = Column(DateTime, nullable=True)
    fecha_fin = Column(DateTime, nullable=True)
    
    # Personal
    responsable = Column(String(100), nullable=True)  # Nombre de quién realizó el trabajo
    supervisor = Column(String(100), nullable=True)   # Quién supervisó
    
    # Costos
    costo_estimado = Column(Numeric(10, 2), nullable=True)
    costo_real = Column(Numeric(10, 2), nullable=True)
    
    # Auditoría
    creado_en = Column(DateTime, default=datetime.utcnow)
    creado_por = Column(String(50), nullable=True)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    actualizado_por = Column(String(50), nullable=True)

    # Relación
    habitacion = relationship("Habitacion", back_populates="mantenimientos")

    __table_args__ = (
        Index('idx_mant_habitacion', 'habitacion_id'),
        Index('idx_mant_estado', 'estado'),
        Index('idx_mant_fecha_programada', 'fecha_programada'),
    )



