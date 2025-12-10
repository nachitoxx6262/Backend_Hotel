from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Boolean, Index
from sqlalchemy.orm import relationship
from database.conexion import Base


class CleaningCycle(Base):
    __tablename__ = "cleaning_cycles"
    __table_args__ = (
        Index("idx_clean_cycle_estado", "estado"),
        Index("idx_clean_cycle_habitacion", "habitacion_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    habitacion_id = Column(Integer, ForeignKey("habitaciones.id"), nullable=False)
    reserva_id = Column(Integer, ForeignKey("reservas.id"), nullable=True)
    estado = Column(String(20), nullable=False, default="pending")  # pending|in_progress|review|done|maintenance
    responsable_inicio = Column(String(120), nullable=True)
    responsable_fin = Column(String(120), nullable=True)
    fecha_inicio = Column(DateTime, nullable=True)
    fecha_fin = Column(DateTime, nullable=True)
    observaciones_finales = Column(Text, nullable=True)
    minibar_snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    checklist_items = relationship("CleaningChecklistItem", back_populates="cycle", cascade="all, delete-orphan")
    events = relationship("CleaningEvent", back_populates="cycle", cascade="all, delete-orphan")
    lost_items = relationship("CleaningLostItem", back_populates="cycle", cascade="all, delete-orphan")
    incidents = relationship("CleaningIncident", back_populates="cycle", cascade="all, delete-orphan")


class CleaningChecklistItem(Base):
    __tablename__ = "cleaning_checklist_items"
    __table_args__ = (
        Index("idx_checklist_cycle", "cycle_id"),
        Index("idx_checklist_done", "done"),
    )

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(Integer, ForeignKey("cleaning_cycles.id", ondelete="CASCADE"), nullable=False)
    nombre = Column(String(150), nullable=False)
    descripcion = Column(Text, nullable=True)
    orden = Column(Integer, default=0)
    done = Column(Boolean, default=False)
    observaciones = Column(Text, nullable=True)
    parent_id = Column(Integer, ForeignKey("cleaning_checklist_items.id"), nullable=True)
    extra = Column(JSON, nullable=True)

    cycle = relationship("CleaningCycle", back_populates="checklist_items")
    subtareas = relationship("CleaningChecklistItem", remote_side=[id])


class CleaningEvent(Base):
    __tablename__ = "cleaning_events"
    __table_args__ = (
        Index("idx_event_cycle", "cycle_id"),
        Index("idx_event_tipo", "tipo_evento"),
    )

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(Integer, ForeignKey("cleaning_cycles.id", ondelete="CASCADE"), nullable=False)
    tipo_evento = Column(String(50), nullable=False)
    descripcion = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    extra_json = Column(JSON, nullable=True)
    responsable = Column(String(120), nullable=True)

    cycle = relationship("CleaningCycle", back_populates="events")


class CleaningLostItem(Base):
    __tablename__ = "cleaning_lost_items"
    __table_args__ = (
        Index("idx_lost_cycle", "cycle_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(Integer, ForeignKey("cleaning_cycles.id", ondelete="CASCADE"), nullable=False)
    descripcion = Column(Text, nullable=False)
    lugar = Column(String(150), nullable=True)
    entregado_a = Column(String(150), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    responsable = Column(String(120), nullable=True)

    cycle = relationship("CleaningCycle", back_populates="lost_items")


class CleaningIncident(Base):
    __tablename__ = "cleaning_incidents"
    __table_args__ = (
        Index("idx_incident_cycle", "cycle_id"),
        Index("idx_incident_tipo", "tipo"),
    )

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(Integer, ForeignKey("cleaning_cycles.id", ondelete="CASCADE"), nullable=False)
    tipo = Column(String(50), nullable=False)
    gravedad = Column(String(20), nullable=False, default="media")
    descripcion = Column(Text, nullable=False)
    fotos_url = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    responsable = Column(String(120), nullable=True)

    cycle = relationship("CleaningCycle", back_populates="incidents")
