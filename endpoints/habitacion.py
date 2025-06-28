from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import conexion
from models.habitacion import Habitacion
from schemas.habitacion import (
    HabitacionCreate,
    HabitacionUpdate,
    HabitacionRead
)

router = APIRouter()

# ----------- GET lista de habitaciones -----------
@router.get("/habitaciones", response_model=List[HabitacionRead])
def listar_habitaciones(db: Session = Depends(conexion.get_db)):
    return db.query(Habitacion).all()

# ----------- GET una habitación -----------
@router.get("/habitaciones/{habitacion_id}", response_model=HabitacionRead)
def obtener_habitacion(habitacion_id: int, db: Session = Depends(conexion.get_db)):
    habitacion = db.query(Habitacion).filter(Habitacion.id == habitacion_id).first()
    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")
    return habitacion

# ----------- POST crear habitación -----------
@router.post("/habitaciones", response_model=HabitacionRead, status_code=201)
def crear_habitacion(habitacion_data: HabitacionCreate, db: Session = Depends(conexion.get_db)):
    # Validación: que no exista otra con ese número
    existe = db.query(Habitacion).filter(Habitacion.numero == habitacion_data.numero).first()
    if existe:
        raise HTTPException(status_code=409, detail="Ya existe una habitación con ese número")
    habitacion = Habitacion(**habitacion_data.dict())
    db.add(habitacion)
    db.commit()
    db.refresh(habitacion)
    return habitacion

# ----------- PUT actualizar habitación -----------
@router.put("/habitaciones/{habitacion_id}", response_model=HabitacionRead)
def actualizar_habitacion(habitacion_id: int, habitacion_data: HabitacionUpdate, db: Session = Depends(conexion.get_db)):
    habitacion = db.query(Habitacion).filter(Habitacion.id == habitacion_id).first()
    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")
    for campo, valor in habitacion_data.dict(exclude_unset=True).items():
        setattr(habitacion, campo, valor)
    db.commit()
    db.refresh(habitacion)
    return habitacion

# ----------- DELETE eliminar habitación -----------
@router.delete("/habitaciones/{habitacion_id}", status_code=204)
def eliminar_habitacion(habitacion_id: int, db: Session = Depends(conexion.get_db)):
    habitacion = db.query(Habitacion).filter(Habitacion.id == habitacion_id).first()
    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")
    db.delete(habitacion)
    db.commit()
    return
