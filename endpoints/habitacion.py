from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.orm import Session

from database import conexion
from models.habitacion import Habitacion
from models.reserva import ReservaHabitacion, Reserva
from schemas.habitacion import HabitacionCreate, HabitacionUpdate, HabitacionRead
from utils.logging_utils import log_event


router = APIRouter()
ACTIVE_RESERVATION_STATES = ("reservada", "ocupada")


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
    habitaciones = db.query(Habitacion).all()
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
    existe = db.query(Habitacion).filter(Habitacion.numero == habitacion_data.numero).first()
    if existe:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe una habitacion con ese numero")
    habitacion = Habitacion(**habitacion_data.dict())
    db.add(habitacion)
    db.commit()
    db.refresh(habitacion)
    log_event("habitaciones", "admin", "Crear habitacion", f"id={habitacion.id}")
    return habitacion


@router.put("/habitaciones/{habitacion_id}", response_model=HabitacionRead)
def actualizar_habitacion(
    habitacion_data: HabitacionUpdate,
    habitacion_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    habitacion = db.query(Habitacion).filter(Habitacion.id == habitacion_id).first()
    if not habitacion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Habitacion no encontrada")
    datos = habitacion_data.dict(exclude_unset=True)
    if "numero" in datos and datos["numero"] != habitacion.numero:
        existe = db.query(Habitacion).filter(Habitacion.numero == datos["numero"]).first()
        if existe:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe una habitacion con ese numero")
    for campo, valor in datos.items():
        setattr(habitacion, campo, valor)
    db.commit()
    db.refresh(habitacion)
    log_event("habitaciones", "admin", "Actualizar habitacion", f"id={habitacion_id}")
    return habitacion


@router.delete("/habitaciones/{habitacion_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_habitacion(
    habitacion_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
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
