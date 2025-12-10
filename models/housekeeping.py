from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Index, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database.conexion import Base


class HousekeepingTareaTemplate(Base):
    """
    Template reutilizable de tareas de limpieza
    Permite personalizar tareas por tipo de habitación
    """
    __tablename__ = "housekeeping_tareas_templates"
    __table_args__ = (
        Index('idx_hk_template_nombre', 'nombre'),
    )

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False, unique=True)  # Ej: "Suite Estándar", "Habitación Doble Ejecutiva"
    descripcion = Column(Text, nullable=True)
    
    # Tareas que se incluyen en este template
    tareas = Column(JSON, nullable=False, default=[])  # Ej: [{"nombre": "Limpiar baño", "orden": 1, "subtareas": [...]}, ...]
    
    # Checklist estándar para este tipo
    checklist_default = Column(JSON, nullable=True, default={})  # {"cama": true, "bano": true, "amenities": true}
    
    # Minibar reposición default
    minibar_default = Column(JSON, nullable=True, default={})  # {"aguas": 2, "gaseosas": 2, "snacks": 3}
    
    # Particularidades a considerar
    particularidades_especiales = Column(JSON, nullable=True, default=[])  # ["jacuzzi", "terraza", "sauna", etc]
    
    # Control
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    habitaciones = relationship("Habitacion", foreign_keys="Habitacion.template_tareas_id", back_populates="template_tareas")


class HousekeepingTarea(Base):
    __tablename__ = "housekeeping_tareas"
    __table_args__ = (
        Index('idx_hk_habitacion', 'habitacion_id'),
        Index('idx_hk_estado', 'estado'),
        Index('idx_hk_asignado', 'asignado_a'),
    )

    id = Column(Integer, primary_key=True, index=True)
    habitacion_id = Column(Integer, ForeignKey("habitaciones.id"), nullable=False)
    template_id = Column(Integer, ForeignKey("housekeeping_tareas_templates.id"), nullable=True)  # Plantilla usada
    
    # Campo para subtareas (si esta tarea es una tarea padre)
    es_padre = Column(Boolean, default=False)  # True si agrupa múltiples subtareas
    tarea_padre_id = Column(Integer, ForeignKey("housekeeping_tareas.id"), nullable=True)  # Referencia a tarea padre
    
    estado = Column(String(20), nullable=False, default="pendiente")  # pendiente, en_curso, pausada, lista_revision, finalizada
    prioridad = Column(String(10), nullable=False, default="media")  # alta, media, baja
    asignado_a = Column(String(100), nullable=True)
    ultimo_huesped = Column(String(120), nullable=True)
    notas = Column(Text, nullable=True)
    checklist_result = Column(JSON, nullable=True)
    minibar = Column(JSON, nullable=True)
    cleaning_started_at = Column(DateTime, nullable=True)
    cleaning_finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    incidencias = relationship("HousekeepingIncidencia", back_populates="tarea", cascade="all, delete-orphan")
    objetos_perdidos = relationship("HousekeepingObjetoPerdido", back_populates="tarea", cascade="all, delete-orphan")
    subtareas = relationship("HousekeepingTarea", remote_side=[id], foreign_keys=[tarea_padre_id], back_populates="tarea_padre")
    tarea_padre = relationship("HousekeepingTarea", remote_side=[tarea_padre_id], foreign_keys=[tarea_padre_id], back_populates="subtareas")


class HousekeepingIncidencia(Base):
    __tablename__ = "housekeeping_incidencias"
    __table_args__ = (
        Index('idx_hk_inc_tarea', 'tarea_id'),
        Index('idx_hk_inc_habitacion', 'habitacion_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    tarea_id = Column(Integer, ForeignKey("housekeeping_tareas.id", ondelete="CASCADE"), nullable=False)
    habitacion_id = Column(Integer, ForeignKey("habitaciones.id"), nullable=False)
    tipo = Column(String(30), nullable=False)
    gravedad = Column(String(10), nullable=False, default="media")
    descripcion = Column(Text, nullable=False)
    fotos_url = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100), nullable=True)

    tarea = relationship("HousekeepingTarea", back_populates="incidencias")


class HousekeepingObjetoPerdido(Base):
    __tablename__ = "housekeeping_objetos_perdidos"
    __table_args__ = (
        Index('idx_hk_obj_tarea', 'tarea_id'),
        Index('idx_hk_obj_habitacion', 'habitacion_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    tarea_id = Column(Integer, ForeignKey("housekeeping_tareas.id", ondelete="CASCADE"), nullable=False)
    habitacion_id = Column(Integer, ForeignKey("habitaciones.id"), nullable=False)
    descripcion = Column(Text, nullable=False)
    lugar = Column(String(150), nullable=True)
    fecha_hallazgo = Column(DateTime, default=datetime.utcnow)
    entregado_a = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100), nullable=True)

    tarea = relationship("HousekeepingTarea", back_populates="objetos_perdidos")
