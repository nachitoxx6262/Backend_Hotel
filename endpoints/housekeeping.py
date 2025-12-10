from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy.orm import Session, joinedload

from database import conexion
from models.habitacion import Habitacion
from models.housekeeping import HousekeepingTarea, HousekeepingIncidencia, HousekeepingObjetoPerdido, HousekeepingTareaTemplate
from schemas.housekeeping import (
    HousekeepingTareaBase,
    HousekeepingTareaDetalle,
    HousekeepingObservacion,
    HousekeepingIniciar,
    HousekeepingFinalizar,
    HousekeepingIncidenciaCreate,
    HousekeepingObjetoPerdidoCreate,
    HousekeepingTareaTemplateRead,
    HousekeepingTareaTemplateCreate,
    HousekeepingTareaTemplateUpdate,
)
from utils.logging_utils import log_event

router = APIRouter(prefix="/housekeeping", tags=["Housekeeping"])


# ===== HELPERS =====

def _get_tarea(db: Session, tarea_id: int) -> HousekeepingTarea:
    tarea = (
        db.query(HousekeepingTarea)
        .options(
            joinedload(HousekeepingTarea.incidencias),
            joinedload(HousekeepingTarea.objetos_perdidos),
        )
        .filter(HousekeepingTarea.id == tarea_id)
        .first()
    )
    if not tarea:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarea no encontrada")
    return tarea


def _append_notas(tarea: HousekeepingTarea, texto: str):
    if tarea.notas:
        tarea.notas += f"\n{texto}"
    else:
        tarea.notas = texto


def _get_template(db: Session, template_id: int) -> HousekeepingTareaTemplate:
    template = db.query(HousekeepingTareaTemplate).filter(HousekeepingTareaTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template no encontrado")
    return template


# ===== TEMPLATES =====

@router.get("/templates", response_model=list[HousekeepingTareaTemplateRead])
def listar_templates(
    activos_solo: bool = Query(True),
    db: Session = Depends(conexion.get_db),
):
    """Lista todos los templates de tareas de limpieza"""
    query = db.query(HousekeepingTareaTemplate)
    if activos_solo:
        query = query.filter(HousekeepingTareaTemplate.activo == True)
    templates = query.all()
    return templates


@router.get("/templates/{template_id}", response_model=HousekeepingTareaTemplateRead)
def obtener_template(
    template_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    """Obtiene un template específico"""
    return _get_template(db, template_id)


@router.post("/templates", response_model=HousekeepingTareaTemplateRead, status_code=status.HTTP_201_CREATED)
def crear_template(
    payload: HousekeepingTareaTemplateCreate,
    db: Session = Depends(conexion.get_db),
):
    """Crea un nuevo template de tareas"""
    existe = db.query(HousekeepingTareaTemplate).filter(HousekeepingTareaTemplate.nombre == payload.nombre).first()
    if existe:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe un template con ese nombre")
    
    template = HousekeepingTareaTemplate(**payload.dict())
    db.add(template)
    db.commit()
    db.refresh(template)
    log_event("housekeeping", "admin", "Crear template", f"nombre={template.nombre}")
    return template


@router.put("/templates/{template_id}", response_model=HousekeepingTareaTemplateRead)
def actualizar_template(
    template_id: int = Path(..., gt=0),
    payload: HousekeepingTareaTemplateUpdate = None,
    db: Session = Depends(conexion.get_db),
):
    """Actualiza un template existente"""
    template = _get_template(db, template_id)
    
    if payload.nombre and payload.nombre != template.nombre:
        existe = db.query(HousekeepingTareaTemplate).filter(HousekeepingTareaTemplate.nombre == payload.nombre).first()
        if existe:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe un template con ese nombre")
    
    datos = payload.dict(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(template, campo, valor)
    
    db.commit()
    db.refresh(template)
    log_event("housekeeping", "admin", "Actualizar template", f"template_id={template_id}")
    return template


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_template(
    template_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    """Elimina un template (lo desactiva)"""
    template = _get_template(db, template_id)
    
    # Verificar que no haya habitaciones asociadas
    habitaciones_asociadas = db.query(Habitacion).filter(Habitacion.template_tareas_id == template_id).count()
    if habitaciones_asociadas > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se puede eliminar: hay {habitaciones_asociadas} habitación(es) usando este template"
        )
    
    template.activo = False
    db.commit()
    log_event("housekeeping", "admin", "Eliminar template", f"template_id={template_id}")
    return


# ===== TAREAS =====

@router.get("/tareas", response_model=list[HousekeepingTareaBase])
def listar_tareas(
    estado: Optional[str] = Query(None),
    piso: Optional[int] = Query(None),
    asignado_a: Optional[str] = Query(None),
    habitacion_id: Optional[int] = Query(None),
    solo_padre: Optional[bool] = Query(False),
    db: Session = Depends(conexion.get_db),
):
    """Lista tareas con filtros opcionales"""
    query = db.query(HousekeepingTarea)
    
    if estado:
        query = query.filter(HousekeepingTarea.estado == estado)
    if asignado_a:
        query = query.filter(HousekeepingTarea.asignado_a == asignado_a)
    if habitacion_id:
        query = query.filter(HousekeepingTarea.habitacion_id == habitacion_id)
    if piso is not None:
        query = query.join(Habitacion, Habitacion.id == HousekeepingTarea.habitacion_id).filter(Habitacion.piso == piso)
    if solo_padre:
        query = query.filter((HousekeepingTarea.es_padre == True) | (HousekeepingTarea.tarea_padre_id.is_(None)))
    
    tareas = query.options(
        joinedload(HousekeepingTarea.incidencias),
        joinedload(HousekeepingTarea.objetos_perdidos),
    ).all()
    return tareas


@router.get("/tareas/{tarea_id}", response_model=HousekeepingTareaDetalle)
def obtener_tarea(
    tarea_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    """Obtiene una tarea específica"""
    return _get_tarea(db, tarea_id)


@router.post("/tareas/{tarea_id}/iniciar", response_model=HousekeepingTareaDetalle)
def iniciar_tarea(
    tarea_id: int = Path(..., gt=0),
    payload: HousekeepingIniciar = HousekeepingIniciar(),
    db: Session = Depends(conexion.get_db),
):
    """Inicia una tarea (cambiar estado a en_curso)"""
    tarea = _get_tarea(db, tarea_id)
    tarea.estado = "en_curso"
    tarea.cleaning_started_at = datetime.utcnow()
    if payload.asignado_a:
        tarea.asignado_a = payload.asignado_a
    db.commit()
    db.refresh(tarea)
    log_event("housekeeping", payload.asignado_a or "system", "Iniciar limpieza", f"tarea={tarea_id}")
    return tarea


@router.post("/tareas/{tarea_id}/pausar", response_model=HousekeepingTareaDetalle)
def pausar_tarea(
    tarea_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    """Pausa una tarea (cambiar estado a pausada)"""
    tarea = _get_tarea(db, tarea_id)
    tarea.estado = "pausada"
    db.commit()
    db.refresh(tarea)
    log_event("housekeeping", "system", "Pausar limpieza", f"tarea={tarea_id}")
    return tarea


@router.post("/tareas/{tarea_id}/finalizar", response_model=HousekeepingTareaDetalle)
def finalizar_tarea(
    tarea_id: int = Path(..., gt=0),
    payload: HousekeepingFinalizar = HousekeepingFinalizar(resultado="ok"),
    db: Session = Depends(conexion.get_db),
):
    """Finaliza una tarea (cambiar estado a finalizada)"""
    tarea = _get_tarea(db, tarea_id)
    tarea.estado = "finalizada"
    tarea.cleaning_finished_at = datetime.utcnow()
    tarea.checklist_result = payload.checklist_result
    tarea.minibar = payload.minibar
    if payload.notas:
        _append_notas(tarea, payload.notas)

    habitacion = db.query(Habitacion).filter(Habitacion.id == tarea.habitacion_id).first()
    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")

    if payload.resultado == "ok":
        habitacion.estado = "disponible"
    else:
        habitacion.estado = "mantenimiento"
        if payload.incidencia_tipo and payload.incidencia_descripcion:
            incidencia = HousekeepingIncidencia(
                tarea_id=tarea.id,
                habitacion_id=tarea.habitacion_id,
                tipo=payload.incidencia_tipo,
                gravedad=payload.incidencia_gravedad or "media",
                descripcion=payload.incidencia_descripcion,
                created_by="housekeeping",
            )
            db.add(incidencia)

    db.commit()
    db.refresh(tarea)
    log_event("housekeeping", payload.resultado, "Finalizar limpieza", f"tarea={tarea_id} resultado={payload.resultado}")
    return tarea


@router.post("/tareas/{tarea_id}/observacion", response_model=HousekeepingTareaDetalle)
def agregar_observacion(
    payload: HousekeepingObservacion,
    tarea_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    """Agrega una observación a una tarea"""
    tarea = _get_tarea(db, tarea_id)
    _append_notas(tarea, payload.notas)
    db.commit()
    db.refresh(tarea)
    log_event("housekeeping", "system", "Observacion", f"tarea={tarea_id}")
    return tarea


@router.post("/tareas/{tarea_id}/incidencia", response_model=HousekeepingTareaDetalle)
def reportar_incidencia(
    tarea_id: int = Path(..., gt=0),
    payload: HousekeepingIncidenciaCreate = HousekeepingIncidenciaCreate(tipo="general", gravedad="media", descripcion=""),
    db: Session = Depends(conexion.get_db),
):
    """Reporta una incidencia durante la limpieza"""
    tarea = _get_tarea(db, tarea_id)
    incidencia = HousekeepingIncidencia(
        tarea_id=tarea.id,
        habitacion_id=tarea.habitacion_id,
        tipo=payload.tipo,
        gravedad=payload.gravedad,
        descripcion=payload.descripcion,
        fotos_url=payload.fotos_url,
        created_by="housekeeping",
    )
    db.add(incidencia)
    habitacion = db.query(Habitacion).filter(Habitacion.id == tarea.habitacion_id).first()
    if habitacion:
        habitacion.estado = "mantenimiento"
    db.commit()
    db.refresh(tarea)
    log_event("housekeeping", "system", "Incidencia", f"tarea={tarea_id}")
    return tarea


@router.post("/tareas/{tarea_id}/lost-found", response_model=HousekeepingTareaDetalle)
def registrar_objeto_perdido(
    tarea_id: int = Path(..., gt=0),
    payload: HousekeepingObjetoPerdidoCreate = HousekeepingObjetoPerdidoCreate(descripcion=""),
    db: Session = Depends(conexion.get_db),
):
    """Registra un objeto perdido encontrado durante la limpieza"""
    tarea = _get_tarea(db, tarea_id)
    obj = HousekeepingObjetoPerdido(
        tarea_id=tarea.id,
        habitacion_id=tarea.habitacion_id,
        descripcion=payload.descripcion,
        lugar=payload.lugar,
        entregado_a=payload.entregado_a,
        created_by="housekeeping",
    )
    db.add(obj)
    db.commit()
    db.refresh(tarea)
    log_event("housekeeping", "system", "Lost&Found", f"tarea={tarea_id}")
    return tarea
