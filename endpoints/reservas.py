from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from decimal import Decimal
from datetime import date
from pydantic import BaseModel

from database import conexion
from models.reserva import Reserva, ReservaItem, ReservaHabitacion
from models.cliente import Cliente
from models.empresa import Empresa
from models.habitacion import Habitacion
from schemas.reservas import (
    ReservaCreate,
    ReservaRead,
    ReservaUpdate
)

router = APIRouter()

# ----------- GET LISTA RESERVAS -----------
@router.get("/reservas", response_model=List[ReservaRead])
def listar_reservas(db: Session = Depends(conexion.get_db)):
    return db.query(Reserva).all()

# ----------- GET RESERVA DETALLE -----------
@router.get("/reservas/{reserva_id}", response_model=ReservaRead)
def obtener_reserva(reserva_id: int, db: Session = Depends(conexion.get_db)):
    reserva = db.query(Reserva).options(
        joinedload(Reserva.habitaciones),
        joinedload(Reserva.items)
    ).filter(Reserva.id == reserva_id).first()

    if not reserva:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")

    return reserva

# ----------- PUT RESERVA (ACTUALIZAR) -----------
@router.put("/reservas/{reserva_id}", response_model=ReservaRead)
def actualizar_reserva(reserva_id: int, data: ReservaUpdate, db: Session = Depends(conexion.get_db)):
    reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
    if not reserva:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")

    # Validar coherencia de fechas si se actualizan
    if data.fecha_checkin and data.fecha_checkout:
        if data.fecha_checkin >= data.fecha_checkout:
            raise HTTPException(status_code=400, detail="Las fechas no son válidas")

    for campo, valor in data.dict(exclude_unset=True).items():
        setattr(reserva, campo, valor)

    db.commit()
    db.refresh(reserva)
    return reserva

# ----------- POST RESERVA (CREAR) -----------
@router.post("/reservas", response_model=ReservaRead, status_code=201)
def crear_reserva(reserva_data: ReservaCreate, db: Session = Depends(conexion.get_db)):
    # Validación de fechas
    if reserva_data.fecha_checkin >= reserva_data.fecha_checkout:
        raise HTTPException(status_code=400, detail="Las fechas no son válidas")

    # Debe tener cliente o empresa
    if not reserva_data.cliente_id and not reserva_data.empresa_id:
        raise HTTPException(status_code=400, detail="Debe indicar un cliente o una empresa")

    # Verificar existencia de cliente
    if reserva_data.cliente_id:
        if not db.query(Cliente).filter(Cliente.id == reserva_data.cliente_id).first():
            raise HTTPException(status_code=400, detail="Cliente no encontrado")

    # Verificar existencia de empresa
    if reserva_data.empresa_id:
        if not db.query(Empresa).filter(Empresa.id == reserva_data.empresa_id).first():
            raise HTTPException(status_code=400, detail="Empresa no encontrada")

    total = Decimal("0.00")
    nueva_reserva = Reserva(
        cliente_id=reserva_data.cliente_id,
        empresa_id=reserva_data.empresa_id,
        fecha_checkin=reserva_data.fecha_checkin,
        fecha_checkout=reserva_data.fecha_checkout,
        estado=reserva_data.estado,
        total=0
    )
    db.add(nueva_reserva)
    db.flush()  # Obtener el id de la reserva

    # ---- Agregar habitaciones ----
    for hab in reserva_data.habitaciones:
        habitacion_db = db.query(Habitacion).filter(Habitacion.id == hab.habitacion_id).first()
        if not habitacion_db:
            raise HTTPException(status_code=400, detail=f"Habitación {hab.habitacion_id} no encontrada")

        dias = (reserva_data.fecha_checkout - reserva_data.fecha_checkin).days
        subtotal = hab.precio_noche * dias
        total += subtotal

        db.add(ReservaHabitacion(
            reserva_id=nueva_reserva.id,
            habitacion_id=hab.habitacion_id,
            precio_noche=hab.precio_noche
        ))

    # ---- Agregar ítems ----
    for item in reserva_data.items:
        if item.tipo_item not in ["producto", "servicio", "descuento"]:
            raise HTTPException(status_code=400, detail="Tipo de ítem inválido")

        monto = item.monto_total if item.tipo_item != "descuento" else -item.monto_total
        total += monto

        db.add(ReservaItem(
            reserva_id=nueva_reserva.id,
            producto_id=item.producto_id,
            descripcion=item.descripcion,
            cantidad=item.cantidad,
            monto_total=item.monto_total,
            tipo_item=item.tipo_item
        ))

    nueva_reserva.total = total

    try:
        db.commit()
        # Refrescar para cargar habitaciones e ítems
        reserva_completa = db.query(Reserva).options(
            joinedload(Reserva.habitaciones),
            joinedload(Reserva.items)
        ).get(nueva_reserva.id)
        return reserva_completa
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Error al guardar la reserva")

# ----------- DELETE RESERVA -----------
@router.delete("/reservas/{reserva_id}", status_code=204)
def eliminar_reserva(reserva_id: int, db: Session = Depends(conexion.get_db)):
    reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
    if not reserva:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    db.delete(reserva)
    db.commit()
    return
