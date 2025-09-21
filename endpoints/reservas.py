from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal
from database import conexion
from models.reserva import Reserva, ReservaHabitacion, ReservaItem, HistorialReserva
from models.habitacion import Habitacion
from models.cliente import Cliente
from schemas.reservas import ReservaCreate, ReservaRead, ReservaUpdate
from sqlalchemy import and_, or_, func

router = APIRouter(tags=["Reservas"])

# ═══════════════════════════════════════════════════════════════ #
# UTILIDADES INTERNAS                                             #
# ═══════════════════════════════════════════════════════════════ #

def verificar_disponibilidad_habitaciones(db: Session, habitaciones: List[int], checkin: date, checkout: date):
    conflictos = db.query(ReservaHabitacion).join(Reserva).filter(
        ReservaHabitacion.habitacion_id.in_(habitaciones),
        Reserva.estado.in_(["reservada", "ocupada"]),
        or_(
            and_(Reserva.fecha_checkin <= checkin, Reserva.fecha_checkout > checkin),
            and_(Reserva.fecha_checkin < checkout, Reserva.fecha_checkout >= checkout),
            and_(Reserva.fecha_checkin >= checkin, Reserva.fecha_checkout <= checkout)
        )
    ).all()

    if conflictos:
        habitaciones_conflictivas = list({c.habitacion_id for c in conflictos})
        raise HTTPException(
            status_code=409,
            detail=f"Las siguientes habitaciones no están disponibles: {habitaciones_conflictivas}"
        )

def log_accion(usuario, accion, detalle=""):
    print(f"RESERVAS | {usuario} | {accion} | {detalle}")
    with open("hotel_logs.txt", "a", encoding="utf-8") as f:
        f.write(f"RESERVAS | {usuario} | {accion} | {detalle}\n")

def registrar_historial(db: Session, reserva_id: int, estado: str, usuario: str):
    historial = HistorialReserva(
        reserva_id=reserva_id,
        estado=estado,
        usuario=usuario,
        fecha=datetime.now()
    )
    db.add(historial)

# ═══════════════════════════════════════════════════════════════ #
# 1. VISUALIZACIÓN GENERAL                                        #
# ═══════════════════════════════════════════════════════════════ #

@router.get("/reservas", response_model=List[ReservaRead])
def listar_reservas(
    estado: Optional[str] = None,
    cliente_id: Optional[int] = None,
    empresa_id: Optional[int] = None,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    db: Session = Depends(conexion.get_db)
):
    query = db.query(Reserva).filter(Reserva.deleted == False)
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
    log_accion("admin", "Listar reservas", f"filtros: estado={estado}")
    return reservas

@router.get("/reservas/eliminadas", response_model=List[ReservaRead])
def listar_reservas_eliminadas(db: Session = Depends(conexion.get_db)):
    log_accion("admin", "Listar reservas eliminadas")
    return db.query(Reserva).filter(Reserva.deleted == True).all()

# ═══════════════════════════════════════════════════════════════ #
# 2. CREAR UNA NUEVA RESERVA                                      #
# ═══════════════════════════════════════════════════════════════ #

@router.post("/reservas", response_model=ReservaRead, status_code=201)
def crear_reserva(reserva: ReservaCreate, db: Session = Depends(conexion.get_db)):
    # Validación cruzada
    if reserva.cliente_id and reserva.empresa_id:
        cliente = db.query(Cliente).filter(Cliente.id == reserva.cliente_id).first()
        if cliente and cliente.empresa_id and cliente.empresa_id != reserva.empresa_id:
            raise HTTPException(status_code=400, detail="El cliente pertenece a otra empresa.")

    # Disponibilidad
    ids_hab = [h.habitacion_id for h in reserva.habitaciones]
    verificar_disponibilidad_habitaciones(db, ids_hab, reserva.fecha_checkin, reserva.fecha_checkout)

    # Crear reserva
    nueva = Reserva(
        cliente_id=reserva.cliente_id,
        empresa_id=reserva.empresa_id,
        fecha_checkin=reserva.fecha_checkin,
        fecha_checkout=reserva.fecha_checkout,
        estado=reserva.estado,
        notas=reserva.notas
    )
    db.add(nueva)
    db.flush()

    total = Decimal("0.00")
    dias = (reserva.fecha_checkout - reserva.fecha_checkin).days

    for h in reserva.habitaciones:
        db.add(ReservaHabitacion(reserva_id=nueva.id, habitacion_id=h.habitacion_id, precio_noche=h.precio_noche))
        total += h.precio_noche * dias

    for i in reserva.items:
        db.add(ReservaItem(reserva_id=nueva.id, producto_id=i.producto_id, descripcion=i.descripcion,
                           cantidad=i.cantidad, monto_total=i.monto_total, tipo_item=i.tipo_item))
        total += i.monto_total

    if dias >= 7:
        total *= Decimal("0.9")  # descuento 10%

    nueva.total = total
    registrar_historial(db, nueva.id, nueva.estado, "admin")
    db.commit()
    db.refresh(nueva)
    log_accion("admin", "Crear reserva", f"id={nueva.id}")
    return nueva

# ═══════════════════════════════════════════════════════════════ #
# 3. ACTUALIZAR ESTADO / RESERVA COMPLETA                         #
# ═══════════════════════════════════════════════════════════════ #

@router.put("/reservas/{reserva_id}", response_model=ReservaRead)
def actualizar_reserva(reserva_id: int, cambios: ReservaUpdate, db: Session = Depends(conexion.get_db)):
    reserva = db.query(Reserva).filter(Reserva.id == reserva_id, Reserva.deleted == False).first()
    if not reserva:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")

    estado_anterior = reserva.estado
    datos = cambios.dict(exclude_unset=True)

    if "fecha_checkin" in datos or "fecha_checkout" in datos:
        checkin = datos.get("fecha_checkin", reserva.fecha_checkin)
        checkout = datos.get("fecha_checkout", reserva.fecha_checkout)
        ids_hab = [h.habitacion_id for h in reserva.habitaciones]
        verificar_disponibilidad_habitaciones(db, ids_hab, checkin, checkout)

        dias = (checkout - checkin).days
        total = sum(h.precio_noche * dias for h in reserva.habitaciones)
        total += sum(i.monto_total for i in reserva.items)
        if dias >= 7:
            total *= Decimal("0.9")
        reserva.total = total

    for campo, valor in datos.items():
        setattr(reserva, campo, valor)

    if "estado" in datos and datos["estado"] != estado_anterior:
        registrar_historial(db, reserva.id, datos["estado"], "admin")

    db.commit()
    db.refresh(reserva)
    log_accion("admin", "Actualizar reserva", f"id={reserva_id}")
    return reserva

# ═══════════════════════════════════════════════════════════════ #
# 4. ELIMINAR / RESTAURAR                                         #
# ═══════════════════════════════════════════════════════════════ #

@router.delete("/reservas/{reserva_id}", status_code=204)
def eliminar_reserva(reserva_id: int, db: Session = Depends(conexion.get_db)):
    reserva = db.query(Reserva).filter(Reserva.id == reserva_id, Reserva.deleted == False).first()
    if not reserva:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    reserva.deleted = True
    db.commit()
    log_accion("admin", "Baja lógica", f"id={reserva_id}")
    return

@router.put("/reservas/{reserva_id}/restaurar", response_model=ReservaRead)
def restaurar_reserva(reserva_id: int, db: Session = Depends(conexion.get_db)):
    reserva = db.query(Reserva).filter(Reserva.id == reserva_id, Reserva.deleted == True).first()
    if not reserva:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    reserva.deleted = False
    db.commit()
    db.refresh(reserva)
    log_accion("admin", "Restaurar reserva", f"id={reserva_id}")
    return reserva

# ═══════════════════════════════════════════════════════════════ #
# 5. RESUMEN                                                      #
# ═══════════════════════════════════════════════════════════════ #

@router.get("/reservas/resumen")
def resumen_reservas(db: Session = Depends(conexion.get_db)):
    resumen = db.query(
        Reserva.estado,
        func.count(Reserva.id).label("cantidad"),
        func.coalesce(func.sum(Reserva.total), 0).label("total_facturado")
    ).filter(Reserva.deleted == False).group_by(Reserva.estado).all()

    return [{"estado": r.estado, "cantidad": r.cantidad, "total_facturado": float(r.total_facturado)} for r in resumen]
