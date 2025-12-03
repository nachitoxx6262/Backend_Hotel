from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session, selectinload

from database import conexion
from models.reserva import Reserva, ReservaHabitacion, ReservaItem, HistorialReserva
from models.habitacion import Habitacion
from models.cliente import Cliente
from models.empresa import Empresa
from schemas.reservas import (
    ReservaCreate,
    ReservaRead,
    ReservaUpdate,
    HistorialReservaRead,
)
from utils.logging_utils import log_event


router = APIRouter(prefix="/reservas", tags=["Reservas"])
ACTIVE_RESERVATION_STATES = ("reservada", "ocupada")


def _buscar_reserva(db: Session, reserva_id: int, include_deleted: bool = False) -> Optional[Reserva]:
    query = (
        db.query(Reserva)
        .options(
            selectinload(Reserva.habitaciones),
            selectinload(Reserva.items),
            selectinload(Reserva.historial),
        )
        .filter(Reserva.id == reserva_id)
    )
    if not include_deleted:
        query = query.filter(Reserva.deleted.is_(False))
    return query.first()


def _obtener_habitaciones_validas(db: Session, habitaciones_ids: List[int]) -> List[Habitacion]:
    if not habitaciones_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Debe seleccionar al menos una habitacion")
    if len(habitaciones_ids) != len(set(habitaciones_ids)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Se detectaron habitaciones duplicadas en la solicitud")
    habitaciones = db.query(Habitacion).filter(Habitacion.id.in_(habitaciones_ids)).all()
    ids_encontrados = {habitacion.id for habitacion in habitaciones}
    faltantes = sorted(set(habitaciones_ids) - ids_encontrados)
    if faltantes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Habitaciones no encontradas: {faltantes}")
    for habitacion in habitaciones:
        if habitacion.mantenimiento:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"La habitacion {habitacion.id} se encuentra en mantenimiento",
            )
    return habitaciones


def _verificar_disponibilidad_habitaciones(
    db: Session,
    habitaciones_ids: List[int],
    checkin,
    checkout,
    reserva_id_excluir: Optional[int] = None,
) -> None:
    if checkout <= checkin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La fecha de checkout debe ser posterior al checkin")
    conflicto_query = (
        db.query(ReservaHabitacion)
        .join(Reserva)
        .filter(
            ReservaHabitacion.habitacion_id.in_(habitaciones_ids),
            Reserva.deleted.is_(False),
            Reserva.estado.in_(ACTIVE_RESERVATION_STATES),
            or_(
                and_(Reserva.fecha_checkin <= checkin, Reserva.fecha_checkout > checkin),
                and_(Reserva.fecha_checkin < checkout, Reserva.fecha_checkout >= checkout),
                and_(Reserva.fecha_checkin >= checkin, Reserva.fecha_checkout <= checkout),
            ),
        )
    )
    if reserva_id_excluir is not None:
        conflicto_query = conflicto_query.filter(Reserva.id != reserva_id_excluir)
    conflictos = conflicto_query.all()
    if conflictos:
        habitaciones_conflictivas = sorted({c.habitacion_id for c in conflictos})
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Las habitaciones {habitaciones_conflictivas} no estan disponibles para ese rango",
        )


def _validar_referencias(
    db: Session,
    cliente_id: Optional[int],
    empresa_id: Optional[int],
) -> None:
    cliente = None
    empresa = None
    if cliente_id is not None:
        cliente = (
            db.query(Cliente)
            .filter(Cliente.id == cliente_id, Cliente.deleted.is_(False))
            .first()
        )
        if not cliente:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
        if cliente.blacklist:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El cliente se encuentra en blacklist")
    if empresa_id is not None:
        empresa = (
            db.query(Empresa)
            .filter(Empresa.id == empresa_id, Empresa.deleted.is_(False))
            .first()
        )
        if not empresa:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada")
        if empresa.blacklist:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La empresa se encuentra en blacklist")
    if cliente and empresa and cliente.empresa_id and cliente.empresa_id != empresa_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El cliente pertenece a otra empresa")


def _registrar_historial(db: Session, reserva_id: int, estado: str, usuario: str) -> None:
    historial = HistorialReserva(
        reserva_id=reserva_id,
        estado=estado,
        usuario=usuario,
        fecha=datetime.utcnow(),
    )
    db.add(historial)


@router.get("", response_model=List[ReservaRead])
def listar_reservas(
    estado: Optional[str] = Query(None, min_length=1, max_length=20, strip_whitespace=True),
    cliente_id: Optional[int] = Query(None, gt=0),
    empresa_id: Optional[int] = Query(None, gt=0),
    desde: Optional[date] = Query(None),
    hasta: Optional[date] = Query(None),
    db: Session = Depends(conexion.get_db),
):
    if desde and hasta and hasta < desde:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El rango de fechas es invalido")
    query = (
        db.query(Reserva)
        .options(
            selectinload(Reserva.habitaciones),
            selectinload(Reserva.items),
            selectinload(Reserva.historial),
        )
        .filter(Reserva.deleted.is_(False))
    )
    if estado:
        query = query.filter(Reserva.estado == estado)
    if cliente_id:
        query = query.filter(Reserva.cliente_id == cliente_id)
    if empresa_id:
        query = query.filter(Reserva.empresa_id == empresa_id)
    if desde:
        query = query.filter(Reserva.fecha_checkin >= desde)
    if hasta:
        query = query.filter(Reserva.fecha_checkout <= hasta)
    reservas = query.all()
    log_event("reservas", "admin", "Listar reservas", f"total={len(reservas)}")
    return reservas


@router.get("/eliminadas", response_model=List[ReservaRead])
def listar_reservas_eliminadas(db: Session = Depends(conexion.get_db)):
    reservas = (
        db.query(Reserva)
        .options(
            selectinload(Reserva.habitaciones),
            selectinload(Reserva.items),
            selectinload(Reserva.historial),
        )
        .filter(Reserva.deleted.is_(True))
        .all()
    )
    log_event("reservas", "admin", "Listar reservas eliminadas", f"total={len(reservas)}")
    return reservas


@router.get("/{reserva_id}", response_model=ReservaRead)
def obtener_reserva(
    reserva_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    reserva = _buscar_reserva(db, reserva_id)
    if not reserva:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
    log_event("reservas", "admin", "Obtener reserva", f"id={reserva_id}")
    return reserva


@router.get("/{reserva_id}/historial", response_model=List[HistorialReservaRead])
def obtener_historial_reserva(
    reserva_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
    if not reserva:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
    historial = (
        db.query(HistorialReserva)
        .filter(HistorialReserva.reserva_id == reserva_id)
        .order_by(HistorialReserva.fecha.asc())
        .all()
    )
    log_event("reservas", "admin", "Obtener historial reserva", f"id={reserva_id} total={len(historial)}")
    return historial


@router.post("", response_model=ReservaRead, status_code=status.HTTP_201_CREATED)
def crear_reserva(reserva: ReservaCreate, db: Session = Depends(conexion.get_db)):
    _validar_referencias(db, reserva.cliente_id, reserva.empresa_id)
    habitaciones_ids = [h.habitacion_id for h in reserva.habitaciones]
    _obtener_habitaciones_validas(db, habitaciones_ids)
    _verificar_disponibilidad_habitaciones(
        db,
        habitaciones_ids,
        reserva.fecha_checkin,
        reserva.fecha_checkout,
    )
    dias = (reserva.fecha_checkout - reserva.fecha_checkin).days
    if dias <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La estadia debe tener al menos una noche")
    nueva = Reserva(
        cliente_id=reserva.cliente_id,
        empresa_id=reserva.empresa_id,
        fecha_checkin=reserva.fecha_checkin,
        fecha_checkout=reserva.fecha_checkout,
        estado=reserva.estado,
        notas=reserva.notas,
    )
    db.add(nueva)
    db.flush()
    total = Decimal("0")
    for habitacion_data in reserva.habitaciones:
        db.add(
            ReservaHabitacion(
                reserva_id=nueva.id,
                habitacion_id=habitacion_data.habitacion_id,
                precio_noche=habitacion_data.precio_noche,
            )
        )
        total += Decimal(habitacion_data.precio_noche) * dias
    for item_data in reserva.items:
        db.add(
            ReservaItem(
                reserva_id=nueva.id,
                producto_id=item_data.producto_id,
                descripcion=item_data.descripcion,
                cantidad=item_data.cantidad,
                monto_total=item_data.monto_total,
                tipo_item=item_data.tipo_item,
            )
        )
        total += Decimal(item_data.monto_total)
    if dias >= 7:
        total *= Decimal("0.9")
    nueva.total = total.quantize(Decimal("0.01"))
    _registrar_historial(db, nueva.id, nueva.estado, "admin")
    db.commit()
    db.refresh(nueva)
    log_event("reservas", "admin", "Crear reserva", f"id={nueva.id}")
    return nueva


@router.put("/{reserva_id}", response_model=ReservaRead)
def actualizar_reserva(
    cambios: ReservaUpdate,
    reserva_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    reserva_db = _buscar_reserva(db, reserva_id)
    if not reserva_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
    datos = cambios.dict(exclude_unset=True)
    if "fecha_checkin" in datos or "fecha_checkout" in datos:
        checkin = datos.get("fecha_checkin", reserva_db.fecha_checkin)
        checkout = datos.get("fecha_checkout", reserva_db.fecha_checkout)
        habitaciones_ids = [h.habitacion_id for h in reserva_db.habitaciones]
        _verificar_disponibilidad_habitaciones(db, habitaciones_ids, checkin, checkout, reserva_id_excluir=reserva_id)
        dias = (checkout - checkin).days
        if dias <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La estadia debe tener al menos una noche")
        total = Decimal("0")
        for habitacion in reserva_db.habitaciones:
            total += Decimal(habitacion.precio_noche) * dias
        for item in reserva_db.items:
            total += Decimal(item.monto_total)
        if dias >= 7:
            total *= Decimal("0.9")
        reserva_db.total = total.quantize(Decimal("0.01"))
        reserva_db.fecha_checkin = checkin
        reserva_db.fecha_checkout = checkout
        datos.pop("fecha_checkin", None)
        datos.pop("fecha_checkout", None)
    estado_anterior = reserva_db.estado
    if "estado" in datos and datos["estado"] != estado_anterior:
        reserva_db.estado = datos.pop("estado")
        _registrar_historial(db, reserva_db.id, reserva_db.estado, "admin")
    for campo, valor in datos.items():
        setattr(reserva_db, campo, valor)
    db.commit()
    db.refresh(reserva_db)
    log_event("reservas", "admin", "Actualizar reserva", f"id={reserva_id}")
    return reserva_db


@router.put("/{reserva_id}/estado", response_model=ReservaRead)
def actualizar_estado_reserva(
    reserva_id: int = Path(..., gt=0),
    nuevo_estado: str = Query(..., min_length=1, max_length=20, strip_whitespace=True),
    usuario: str = Query("admin", min_length=1, max_length=50, strip_whitespace=True),
    db: Session = Depends(conexion.get_db),
):
    reserva = _buscar_reserva(db, reserva_id)
    if not reserva:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
    if reserva.estado != nuevo_estado:
        reserva.estado = nuevo_estado
        _registrar_historial(db, reserva.id, nuevo_estado, usuario)
        db.commit()
        db.refresh(reserva)
        log_event("reservas", usuario, "Actualizar estado reserva", f"id={reserva_id} estado={nuevo_estado}")
    return reserva


@router.delete("/{reserva_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_reserva(
    reserva_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    reserva = _buscar_reserva(db, reserva_id)
    if not reserva:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
    reserva.deleted = True
    db.commit()
    log_event("reservas", "admin", "Baja logica reserva", f"id={reserva_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{reserva_id}/restaurar", response_model=ReservaRead)
def restaurar_reserva(
    reserva_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    reserva = _buscar_reserva(db, reserva_id, include_deleted=True)
    if not reserva or not reserva.deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
    reserva.deleted = False
    db.commit()
    db.refresh(reserva)
    log_event("reservas", "admin", "Restaurar reserva", f"id={reserva_id}")
    return reserva


@router.get("/resumen")
def resumen_reservas(db: Session = Depends(conexion.get_db)):
    resumen = (
        db.query(
            Reserva.estado,
            func.count(Reserva.id).label("cantidad"),
            func.coalesce(func.sum(Reserva.total), 0).label("total_facturado"),
        )
        .filter(Reserva.deleted.is_(False))
        .group_by(Reserva.estado)
        .all()
    )
    log_event("reservas", "admin", "Resumen reservas", f"total_estados={len(resumen)}")
    return [
        {
            "estado": registro.estado,
            "cantidad": registro.cantidad,
            "total_facturado": float(registro.total_facturado),
        }
        for registro in resumen
    ]

