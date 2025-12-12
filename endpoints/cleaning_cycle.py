from datetime import datetime
from itertools import cycle
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session, joinedload

from database import conexion
from models.habitacion import Habitacion
from models.housekeeping import HousekeepingTareaTemplate
from models.cleaning_cycle import (
    CleaningCycle,
    CleaningChecklistItem,
    CleaningEvent,
    CleaningLostItem,
    CleaningIncident,
)
from schemas.cleaning_cycle import (
    CleaningCycleCreate,
    CleaningCycleList,
    CleaningCycleDetail,
    CleaningCycleStart,
    CleaningCycleFinish,
    CleaningCyclePauseResume,
    CleaningChecklistToggle,
    CleaningEventCreate,
    CleaningIncidentCreate,
    CleaningLostItemCreate,
)

router = APIRouter(prefix="/cleaning-cycles", tags=["CleaningCycles"])


# Helpers

def _get_cycle(db: Session, cycle_id: int) -> CleaningCycle:
    cycle = (
        db.query(CleaningCycle)
        .options(
            joinedload(CleaningCycle.checklist_items),
            joinedload(CleaningCycle.events),
            joinedload(CleaningCycle.lost_items),
            joinedload(CleaningCycle.incidents),
        )
        .filter(CleaningCycle.id == cycle_id)
        .first()
    )
    if not cycle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CleaningCycle no encontrado")
    return cycle


def _append_event(db: Session, cycle: CleaningCycle, tipo: str, descripcion: Optional[str], extra: Optional[dict], responsable: Optional[str]):
    evt = CleaningEvent(
        cycle_id=cycle.id,
        tipo_evento=tipo,
        descripcion=descripcion,
        extra_json=extra,
        responsable=responsable,
        timestamp=datetime.utcnow(),
    )
    db.add(evt)


def _build_checklist_from_template(db: Session, cycle: CleaningCycle, template: HousekeepingTareaTemplate):
    if not template or not template.tareas:
        return
    for idx, tarea in enumerate(template.tareas, 1):
        item = CleaningChecklistItem(
            cycle_id=cycle.id,
            nombre=tarea.get("nombre", f"Tarea {idx}"),
            descripcion=tarea.get("descripcion"),
            orden=tarea.get("orden", idx),
            extra={"template_id": template.id},
        )
        db.add(item)
        db.flush()  # ensure parent id exists for subtasks
        # Subtareas
        for sidx, sub in enumerate(tarea.get("subtareas", []), 1):
            sub_item = CleaningChecklistItem(
                cycle_id=cycle.id,
                nombre=sub.get("nombre", f"Subtarea {idx}.{sidx}"),
                descripcion=sub.get("descripcion"),
                orden=sub.get("orden", sidx),
                parent_id=item.id,
                extra={"template_id": template.id},
            )
            db.add(sub_item)


# Endpoints

@router.post("", response_model=CleaningCycleDetail, status_code=status.HTTP_201_CREATED)
def crear_cycle(payload: CleaningCycleCreate, db: Session = Depends(conexion.get_db)):
    habitacion = db.query(Habitacion).filter(Habitacion.id == payload.habitacion_id).first()
    if not habitacion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Habitación no encontrada")

    cycle = CleaningCycle(
        habitacion_id=habitacion.id,
        reserva_id=payload.reserva_id,
        estado="pending",
        minibar_snapshot=habitacion.particularidades or {},
    )
    db.add(cycle)
    db.flush()

    template = None
    if habitacion.template_tareas_id:
        template = db.query(HousekeepingTareaTemplate).filter(HousekeepingTareaTemplate.id == habitacion.template_tareas_id).first()
    _build_checklist_from_template(db, cycle, template)

    _append_event(db, cycle, "cycle_created", "Cycle creado por checkout", None, payload.responsable)
    db.commit()
    db.refresh(cycle)
    return _get_cycle(db, cycle.id)


@router.get("", response_model=list[CleaningCycleList])
def listar_cycles(
    estado: Optional[str] = Query(None),
    habitacion_id: Optional[int] = Query(None),
    piso: Optional[int] = Query(None),
    db: Session = Depends(conexion.get_db),
):
    query = db.query(CleaningCycle)
    if estado:
        query = query.filter(CleaningCycle.estado == estado)
    if habitacion_id:
        query = query.filter(CleaningCycle.habitacion_id == habitacion_id)
    if piso is not None:
        query = query.join(Habitacion, Habitacion.id == CleaningCycle.habitacion_id).filter(Habitacion.piso == piso)

    cycles = query.options(joinedload(CleaningCycle.checklist_items)).all()
    result = []
    for c in cycles:
        # Obtener el número de habitación
        habitacion = db.query(Habitacion).filter(Habitacion.id == c.habitacion_id).first()
        habitacion_numero = habitacion.numero if habitacion else None
        
        incidents_count = len(c.incidents)
        lost_count = len(c.lost_items)
        events_count = len(c.events)
        result.append(
            CleaningCycleList(
                id=c.id,
                habitacion_id=c.habitacion_id,
                habitacion_numero=habitacion_numero,
                reserva_id=c.reserva_id,
                estado=c.estado,
                responsable_inicio=c.responsable_inicio,
                responsable_fin=c.responsable_fin,
                fecha_inicio=c.fecha_inicio,
                fecha_fin=c.fecha_fin,
                observaciones_finales=c.observaciones_finales,
                minibar_snapshot=c.minibar_snapshot,
                created_at=c.created_at,
                updated_at=c.updated_at,
                checklist_items=c.checklist_items,
                incidents_count=incidents_count,
                lost_items_count=lost_count,
                events_count=events_count,
            )
        )
    return result


@router.get("/{cycle_id}", response_model=CleaningCycleDetail)
def obtener_cycle(cycle_id: int = Path(..., gt=0), db: Session = Depends(conexion.get_db)):
    return _get_cycle(db, cycle_id)


@router.patch("/{cycle_id}/start", response_model=CleaningCycleDetail)
def iniciar_cycle(cycle_id: int, payload: CleaningCycleStart = CleaningCycleStart(), db: Session = Depends(conexion.get_db)):
    cycle = _get_cycle(db, cycle_id)
    cycle.estado = "in_progress"
    cycle.fecha_inicio = datetime.utcnow()
    cycle.responsable_inicio = payload.responsable
    cycle.updated_at = datetime.utcnow()
    _append_event(db, cycle, "cycle_started", "Inicio de limpieza", None, payload.responsable)
    db.commit()
    return _get_cycle(db, cycle.id)


@router.patch("/{cycle_id}/pause", response_model=CleaningCycleDetail)
def pausar_cycle(cycle_id: int, payload: CleaningCyclePauseResume = CleaningCyclePauseResume(), db: Session = Depends(conexion.get_db)):
    cycle = _get_cycle(db, cycle_id)
    if cycle.estado != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se puede pausar un ciclo en progreso",
        )
    cycle.estado = "paused"
    cycle.updated_at = datetime.utcnow()
    _append_event(db, cycle, "pause", "Pausa", None, payload.responsable)
    db.commit()
    return _get_cycle(db, cycle.id)


@router.patch("/{cycle_id}/resume", response_model=CleaningCycleDetail)
def resume_cycle(cycle_id: int, payload: CleaningCyclePauseResume = CleaningCyclePauseResume(), db: Session = Depends(conexion.get_db)):
    cycle = _get_cycle(db, cycle_id)
    if cycle.estado != "paused":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se puede reanudar un ciclo en pausa",
        )
    cycle.estado = "in_progress"
    cycle.updated_at = datetime.utcnow()
    _append_event(db, cycle, "resume", "Reanudar", None, payload.responsable)
    db.commit()
    return _get_cycle(db, cycle.id)


@router.patch("/{cycle_id}/finish", response_model=CleaningCycleDetail)
def finalizar_cycle(cycle_id: int, payload: CleaningCycleFinish, db: Session = Depends(conexion.get_db)):
    cycle = _get_cycle(db, cycle_id)
    # Validar checklist completo
    pendientes = [i for i in cycle.checklist_items if not i.done]
    if pendientes and not payload.enviar_mantenimiento:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Checklist incompleto")

    cycle.estado = "maintenance" if payload.enviar_mantenimiento else "done"
    cycle.fecha_fin = datetime.utcnow()
    cycle.responsable_fin = payload.responsable
    cycle.observaciones_finales = payload.observaciones_finales
    cycle.updated_at = datetime.utcnow()
    _append_event(db, cycle, "cycle_finished", "Fin de limpieza", {"en_mantenimiento": payload.enviar_mantenimiento}, payload.responsable)
    db.commit()
    return _get_cycle(db, cycle.id)


@router.patch("/{cycle_id}/checklist/{task_id}", response_model=CleaningCycleDetail)
def marcar_checklist(
    cycle_id: int,
    task_id: int,
    payload: CleaningChecklistToggle,
    db: Session = Depends(conexion.get_db),
):
    cycle = _get_cycle(db, cycle_id)
    item = next((i for i in cycle.checklist_items if i.id == task_id), None)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist item no encontrado")
    item.done = payload.done
    item.observaciones = payload.observaciones
    cycle.updated_at = datetime.utcnow()
    _append_event(db, cycle, "checklist_item_done" if payload.done else "checklist_item_undo", item.nombre, None, None)
    db.commit()
    return _get_cycle(db, cycle.id)


@router.post("/{cycle_id}/events", response_model=CleaningCycleDetail)
def crear_evento(cycle_id: int, payload: CleaningEventCreate, db: Session = Depends(conexion.get_db)):
    cycle = _get_cycle(db, cycle_id)
    _append_event(db, cycle, payload.tipo_evento, payload.descripcion, payload.extra_json, payload.responsable)
    cycle.updated_at = datetime.utcnow()
    db.commit()
    return _get_cycle(db, cycle.id)


@router.post("/{cycle_id}/lost-items", response_model=CleaningCycleDetail)
def registrar_objeto_perdido(cycle_id: int, payload: CleaningLostItemCreate, db: Session = Depends(conexion.get_db)):
    cycle = _get_cycle(db, cycle_id)
    li = CleaningLostItem(
        cycle_id=cycle.id,
        descripcion=payload.descripcion,
        lugar=payload.lugar,
        entregado_a=payload.entregado_a,
        responsable=payload.responsable,
    )
    db.add(li)
    cycle.updated_at = datetime.utcnow()
    _append_event(db, cycle, "lost_item", payload.descripcion, None, payload.responsable)
    db.commit()
    return _get_cycle(db, cycle.id)


@router.post("/{cycle_id}/incidents", response_model=CleaningCycleDetail)
def registrar_incidencia(cycle_id: int, payload: CleaningIncidentCreate, db: Session = Depends(conexion.get_db)):
    cycle = _get_cycle(db, cycle_id)
    inc = CleaningIncident(
        cycle_id=cycle.id,
        tipo=payload.tipo,
        gravedad=payload.gravedad,
        descripcion=payload.descripcion,
        fotos_url=payload.fotos_url,
        responsable=payload.responsable,
    )
    db.add(inc)
    cycle.updated_at = datetime.utcnow()
    _append_event(db, cycle, "incident", payload.descripcion, {"tipo": payload.tipo, "gravedad": payload.gravedad}, payload.responsable)
    db.commit()
    return _get_cycle(db, cycle.id)
