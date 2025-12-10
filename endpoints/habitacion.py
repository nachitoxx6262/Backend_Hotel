from typing import List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import joinedload

from database import conexion
from models.habitacion import Habitacion, CategoriaHabitacion, MantenimientoHabitacion
from models.reserva import ReservaHabitacion, Reserva
from schemas.habitacion import HabitacionCreate, HabitacionUpdate, HabitacionRead
from schemas.habitacion import HistorialHabitacionResponse, OcupacionHabitacion, EventoHistorialHabitacion
from utils.logging_utils import log_event


router = APIRouter()
ACTIVE_RESERVATION_STATES = ("reservada", "ocupada", "confirmada", "activa")


def _nombre_reserva(reserva: Reserva) -> str:
    if reserva.cliente:
        nombre = f"{reserva.cliente.nombre} {reserva.cliente.apellido}".strip()
        return nombre or "Sin asignar"
    if reserva.empresa:
        return reserva.empresa.nombre or "Empresa sin nombre"
    return reserva.nombre_temporal or "Sin asignar"


def _habitacion_con_reserva_activa(db: Session, habitacion_id: int) -> bool:
    return (
        db.query(ReservaHabitacion)
        .join(Reserva)
        .filter(
            ReservaHabitacion.habitacion_id == habitacion_id,
            Reserva.deleted.is_(False),
            Reserva.estado.in_(ACTIVE_RESERVATION_STATES),
        )
        .count()
        > 0
    )


@router.get("/habitaciones", response_model=List[HabitacionRead])
def listar_habitaciones(db: Session = Depends(conexion.get_db)):
    habitaciones = db.query(Habitacion).options(joinedload(Habitacion.categoria)).all()
    
    # Enriquecer con datos de categoría
    for habitacion in habitaciones:
        if habitacion.categoria:
            habitacion.categoria_nombre = habitacion.categoria.nombre
            habitacion.precio_noche = float(habitacion.categoria.precio_base_noche)
        habitacion.descripcion = habitacion.observaciones
    
    log_event("habitaciones", "admin", "Listar habitaciones", f"total={len(habitaciones)}")
    return habitaciones


@router.get("/habitaciones/{habitacion_id}", response_model=HabitacionRead)
def obtener_habitacion(
    habitacion_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    habitacion = db.query(Habitacion).filter(Habitacion.id == habitacion_id).first()
    if not habitacion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Habitacion no encontrada")
    log_event("habitaciones", "admin", "Obtener habitacion", f"id={habitacion_id}")
    return habitacion


@router.post("/habitaciones", response_model=HabitacionRead, status_code=status.HTTP_201_CREATED)
def crear_habitacion(habitacion_data: HabitacionCreate, db: Session = Depends(conexion.get_db)):
    try:
        # Validaciones de datos
        if habitacion_data.numero <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El número de habitación debe ser mayor a 0"
            )
        
        if not habitacion_data.estado or not habitacion_data.estado.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El estado de la habitación es requerido"
            )
        
        # Validar categoría existe
        if habitacion_data.categoria_id:
            categoria = db.query(CategoriaHabitacion).filter(
                CategoriaHabitacion.id == habitacion_data.categoria_id,
                CategoriaHabitacion.activo.is_(True)
            ).first()
            if not categoria:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="La categoría de habitación especificada no existe o está inactiva"
                )
        
        # Verificar número duplicado
        existe = db.query(Habitacion).filter(Habitacion.numero == habitacion_data.numero).first()
        if existe:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe una habitación con ese número"
            )
        
        habitacion = Habitacion(**habitacion_data.model_dump(exclude_unset=True))
        db.add(habitacion)
        db.commit()
        db.refresh(habitacion)
        log_event("habitaciones", "admin", "Crear habitación", f"id={habitacion.id} numero={habitacion_data.numero}")
        return habitacion
        
    except HTTPException:
        raise
    except IntegrityError as e:
        db.rollback()
        log_event("habitaciones", "admin", "Error de integridad al crear habitación", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Error de integridad (número de habitación duplicado)"
        )
    except SQLAlchemyError as e:
        db.rollback()
        log_event("habitaciones", "admin", "Error de BD al crear habitación", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear la habitación en la base de datos"
        )


@router.put("/habitaciones/{habitacion_id}", response_model=HabitacionRead)
def actualizar_habitacion(
    habitacion_data: HabitacionUpdate,
    habitacion_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    try:
        habitacion = db.query(Habitacion).filter(Habitacion.id == habitacion_id).first()
        if not habitacion:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Habitación no encontrada"
            )
        
        datos = habitacion_data.model_dump(exclude_unset=True)
        
        # Validar número único si se cambía
        if "numero" in datos and datos["numero"] != habitacion.numero:
            existe = db.query(Habitacion).filter(
                Habitacion.numero == datos["numero"],
                Habitacion.id != habitacion_id
            ).first()
            if existe:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Ya existe otra habitación con ese número"
                )
        
        # Validar categoría si se proporciona
        if "categoria_id" in datos and datos["categoria_id"]:
            categoria = db.query(CategoriaHabitacion).filter(
                CategoriaHabitacion.id == datos["categoria_id"],
                CategoriaHabitacion.activo.is_(True)
            ).first()
            if not categoria:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="La categoría especificada no existe o está inactiva"
                )
        
        # Actualizar solo campos proporcionados
        for campo, valor in datos.items():
            if valor is not None:
                setattr(habitacion, campo, valor)
        
        # Actualizar marca de tiempo
        habitacion.actualizado_en = datetime.utcnow()
        
        db.commit()
        db.refresh(habitacion)
        log_event("habitaciones", "admin", "Actualizar habitación", f"id={habitacion_id} campos={len(datos)}")
        return habitacion
        
    except HTTPException:
        raise
    except IntegrityError as e:
        db.rollback()
        log_event("habitaciones", "admin", "Error de integridad al actualizar", f"id={habitacion_id} error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Error de integridad (número duplicado)"
        )
    except SQLAlchemyError as e:
        db.rollback()
        log_event("habitaciones", "admin", "Error de BD al actualizar", f"id={habitacion_id} error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar la habitación"
        )


@router.get("/habitaciones/{habitacion_id}/historial", response_model=HistorialHabitacionResponse)
def historial_habitacion(
    habitacion_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    habitacion = db.query(Habitacion).filter(Habitacion.id == habitacion_id).first()
    if not habitacion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Habitación no encontrada")

    reservas_hab = (
        db.query(ReservaHabitacion)
        .join(Reserva)
        .options(
            selectinload(ReservaHabitacion.reserva).selectinload(Reserva.cliente),
            selectinload(ReservaHabitacion.reserva).selectinload(Reserva.empresa),
            selectinload(ReservaHabitacion.reserva).selectinload(Reserva.historial),
        )
        .filter(
            ReservaHabitacion.habitacion_id == habitacion_id,
            Reserva.deleted.is_(False),
        )
        .order_by(Reserva.fecha_checkin.desc())
        .all()
    )

    ocupaciones: List[OcupacionHabitacion] = []
    historial: List[EventoHistorialHabitacion] = []

    for res_hab in reservas_hab:
        reserva = res_hab.reserva
        if not reserva:
            continue
        ocupaciones.append(
            OcupacionHabitacion(
                reserva_id=reserva.id,
                huesped=_nombre_reserva(reserva),
                fecha_checkin=reserva.fecha_checkin,
                fecha_checkout=reserva.fecha_checkout,
                estado=reserva.estado,
                empresa=reserva.empresa.nombre if reserva.empresa else None,
            )
        )

        for h in reserva.historial or []:
            historial.append(
                EventoHistorialHabitacion(
                    fecha=h.fecha,
                    estado_anterior=h.estado_anterior,
                    estado_nuevo=h.estado_nuevo,
                    usuario=h.usuario,
                    motivo=h.motivo,
                    reserva_id=reserva.id,
                )
            )

    historial.sort(key=lambda x: x.fecha, reverse=True)

    mantenimientos = (
        db.query(MantenimientoHabitacion)
        .filter(MantenimientoHabitacion.habitacion_id == habitacion_id)
        .order_by(MantenimientoHabitacion.fecha_programada.desc())
        .all()
    )

    log_event("habitaciones", "admin", "Historial habitacion", f"id={habitacion_id}")

    return HistorialHabitacionResponse(
        habitacion_id=habitacion.id,
        numero=habitacion.numero,
        ocupaciones=ocupaciones,
        historial_estados=historial,
        mantenimientos=mantenimientos,
    )


@router.delete("/habitaciones/{habitacion_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_habitacion(
    habitacion_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    try:
        habitacion = db.query(Habitacion).filter(Habitacion.id == habitacion_id).first()
        if not habitacion:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Habitacion no encontrada")
        if _habitacion_con_reserva_activa(db, habitacion_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No se puede eliminar una habitacion con reservas activas",
            )
        db.delete(habitacion)
        db.commit()
        log_event("habitaciones", "admin", "Eliminar habitacion", f"id={habitacion_id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        log_event("habitaciones", "admin", "Error al eliminar habitacion", f"id={habitacion_id} error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar la habitación de la base de datos"
        )
