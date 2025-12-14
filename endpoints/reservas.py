from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

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
    ReservaMove,
)
from utils.logging_utils import log_event


from models.reserva import EstadoReservaEnum

router = APIRouter(prefix="/reservas", tags=["Reservas"])
# Estados activos: reservas pendientes, en proceso, o en checkout
ACTIVE_RESERVATION_STATES = (
    EstadoReservaEnum.PENDIENTE_CHECKIN,
    EstadoReservaEnum.OCUPADA,
    EstadoReservaEnum.PENDIENTE_CHECKOUT
)


def _recalcular_totales(reserva: Reserva, dias: int) -> None:
    total = Decimal("0")
    for habitacion in reserva.habitaciones:
        habitacion.cantidad_noches = dias
        habitacion.subtotal_habitacion = Decimal(habitacion.precio_noche) * dias
        total += habitacion.subtotal_habitacion
    for item in reserva.items:
        total += Decimal(item.monto_total)
    if dias >= 7:
        total *= Decimal("0.9")
    reserva.total = total.quantize(Decimal("0.01"))


def _enriquecer_reserva(db: Session, reserva: Reserva) -> None:
    """Agrega alias y datos derivados usados por el frontend."""
    reserva.fecha_entrada = reserva.fecha_checkin
    reserva.fecha_salida = reserva.fecha_checkout
    try:
        reserva.numero_noches = (reserva.fecha_checkout - reserva.fecha_checkin).days
    except Exception:
        reserva.numero_noches = None

    if reserva.cliente_id:
        cliente = db.query(Cliente).filter(Cliente.id == reserva.cliente_id).first()
        if cliente:
            reserva.cliente_nombre = f"{cliente.nombre} {cliente.apellido}"
    elif reserva.empresa_id:
        empresa = db.query(Empresa).filter(Empresa.id == reserva.empresa_id).first()
        if empresa:
            reserva.empresa_nombre = empresa.nombre
    else:
        reserva.cliente_nombre = reserva.nombre_temporal or "Sin asignar"

    if reserva.habitaciones:
        # Asignar numero de la primera habitación como alias de reserva
        primera = reserva.habitaciones[0]
        habitacion = db.query(Habitacion).filter(Habitacion.id == primera.habitacion_id).first()
        if habitacion:
            reserva.habitacion_numero = str(habitacion.numero)

        # Enriquecer cada relación ReservaHabitacion con el número
        for rh in reserva.habitaciones:
            try:
                hab = db.query(Habitacion).filter(Habitacion.id == rh.habitacion_id).first()
                if hab:
                    # Atributo dinámico para serialización en schema
                    rh.habitacion_numero = str(hab.numero)
            except Exception:
                # Evitar que un fallo puntual rompa la respuesta completa
                pass


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
        if habitacion.estado == "mantenimiento":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"La habitacion {habitacion.numero} se encuentra en mantenimiento",
            )
        if not habitacion.activo or habitacion.deleted:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"La habitacion {habitacion.numero} no está disponible",
            )
    return habitaciones


def _verificar_disponibilidad_habitaciones(db, habitacion_ids, start_date, end_date, reserva_id_excluir=None):
    # Buscamos cualquier reserva que se superponga en fechas para las habitaciones solicitadas
    # Checkout es 10:00 AM, así que permite: reserva_A (05-10) + reserva_B (10-12) mismo día
    # Overlap solo si: existente.fecha_checkin < nueva.fecha_checkout AND existente.fecha_checkout > nueva.fecha_checkin
    # Usamos < y > para permitir checkin == checkout (turnover)
    query = (
        db.query(Reserva)
        .join(ReservaHabitacion)
        .filter(
            ReservaHabitacion.habitacion_id.in_(habitacion_ids),
            Reserva.deleted.is_(False),
            Reserva.estado_operacional.in_(ACTIVE_RESERVATION_STATES),  # Solo verificar reservas activas
            # NO hay conflicto si: existente.checkin >= nueva.checkout O existente.checkout <= nueva.checkin
            # HAY conflicto si: existente.checkin < nueva.checkout AND existente.checkout > nueva.checkin
            Reserva.fecha_checkin < end_date,
            Reserva.fecha_checkout > start_date,
        )
    )

    if reserva_id_excluir:
        query = query.filter(Reserva.id != reserva_id_excluir)

    conflicto = query.first()

    if conflicto:
        print(
            f"CONFLICTO DETECTADO CON RESERVA ID: {conflicto.id} "
            f"({conflicto.fecha_checkin} - {conflicto.fecha_checkout})"
        )

        raise HTTPException(
            status_code=409,
            detail=f"La habitación no está disponible. Choca con reserva #{conflicto.id}"
        )

def _validar_referencias(
    db: Session,
    cliente_id: Optional[int],
    empresa_id: Optional[int],
) -> None:
    # Permitir reservas sin asignar (ambos None)
    # Solo validar si se proporcionan
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


def _registrar_historial(db: Session, reserva_id: int, estado_nuevo, usuario: str, estado_anterior=None, motivo: Optional[str] = None) -> None:
    # Convertir enum a string si es necesario
    estado_nuevo_str = estado_nuevo.value if hasattr(estado_nuevo, 'value') else str(estado_nuevo)
    estado_anterior_str = estado_anterior.value if hasattr(estado_anterior, 'value') else (str(estado_anterior) if estado_anterior else None)
    
    historial = HistorialReserva(
        reserva_id=reserva_id,
        estado_anterior=estado_anterior_str,
        estado_nuevo=estado_nuevo_str,
        usuario=usuario,
        fecha=datetime.utcnow(),
        motivo=motivo,
    )
    db.add(historial)

@router.get("/disponibilidad")
def verificar_disponibilidad(
    habitacion_id: int = Query(..., gt=0),
    fecha_checkin: str = Query(..., description="ISO date: YYYY-MM-DD"),
    fecha_checkout: str = Query(..., description="ISO date: YYYY-MM-DD"),
    reserva_id_excluir: Optional[int] = Query(None, gt=0),
    db: Session = Depends(conexion.get_db),
):
    try:
        from dateutil import parser
        checkin = parser.isoparse(fecha_checkin).date() if isinstance(fecha_checkin, str) else fecha_checkin
        checkout = parser.isoparse(fecha_checkout).date() if isinstance(fecha_checkout, str) else fecha_checkout
        
        _obtener_habitaciones_validas(db, [habitacion_id])
        _verificar_disponibilidad_habitaciones(
            db,
            [habitacion_id],
            checkin,
            checkout,
            reserva_id_excluir=reserva_id_excluir,
        )
        return {"disponible": True, "mensaje": "La habitación está disponible en el rango solicitado"}

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al verificar disponibilidad: {str(e)}"
        )

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
        query = query.filter(Reserva.estado_operacional == estado)
    if cliente_id:
        query = query.filter(Reserva.cliente_id == cliente_id)
    if empresa_id:
        query = query.filter(Reserva.empresa_id == empresa_id)
    if desde:
        query = query.filter(Reserva.fecha_checkin >= desde)
    if hasta:
        query = query.filter(Reserva.fecha_checkout <= hasta)
    reservas = query.all()
    
    # Enriquecer con datos de cliente, empresa, habitación y alias de fechas para el frontend
    for reserva in reservas:
        _enriquecer_reserva(db, reserva)
    
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
    for reserva in reservas:
        _enriquecer_reserva(db, reserva)
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
    _enriquecer_reserva(db, reserva)
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
    try:
        print(f"[DEBUG CREATE] Creando reserva: checkin={reserva.fecha_checkin}, checkout={reserva.fecha_checkout}, habitaciones={[h.habitacion_id for h in reserva.habitaciones]}")
        
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
        
        # Permitir reservas sin cliente_id para walk-ins (se registra en check-in)
        # Solo validar referencias si est\u00e1n presentes
        if reserva.cliente_id or reserva.empresa_id:
            _validar_referencias(db, reserva.cliente_id, reserva.empresa_id)
        
        nueva = Reserva(
            cliente_id=reserva.cliente_id,
            empresa_id=reserva.empresa_id,
            nombre_temporal=reserva.nombre_temporal,
            fecha_checkin=reserva.fecha_checkin,
            fecha_checkout=reserva.fecha_checkout,
            estado=EstadoReservaEnum.PENDIENTE_CHECKIN.value,  # Compatibilidad backwards
            estado_operacional=EstadoReservaEnum.PENDIENTE_CHECKIN,
            notas=reserva.notas,
        )
        db.add(nueva)
        db.flush()
        total = Decimal("0")
        for habitacion_data in reserva.habitaciones:
            if habitacion_data.precio_noche <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El precio por noche debe ser mayor a 0"
                )
            subtotal_hab = Decimal(habitacion_data.precio_noche) * dias
            db.add(
                ReservaHabitacion(
                    reserva_id=nueva.id,
                    habitacion_id=habitacion_data.habitacion_id,
                    precio_noche=habitacion_data.precio_noche,
                    cantidad_noches=dias,
                    subtotal_habitacion=subtotal_hab,
                )
            )
            # Actualizar estado de la habitación a "reservado"
            habitacion = db.query(Habitacion).filter(
                Habitacion.id == habitacion_data.habitacion_id
            ).first()
            if habitacion and habitacion.estado == "disponible":
                habitacion.estado = "reservado"
            total += subtotal_hab
        for item_data in reserva.items:
            if item_data.cantidad <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La cantidad de items debe ser mayor a 0"
                )
            if item_data.monto_total < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El monto total no puede ser negativo"
                )
            
            # Calcular monto_unitario
            monto_total = Decimal(item_data.monto_total)
            cantidad = Decimal(item_data.cantidad)
            if monto_total > 0 and cantidad > 0:
                monto_unitario = (monto_total / cantidad).quantize(Decimal("0.01"))
            else:
                monto_unitario = Decimal("0.00")
            
            db.add(
                ReservaItem(
                    reserva_id=nueva.id,
                    producto_id=item_data.producto_id,
                    descripcion=item_data.descripcion,
                    cantidad=item_data.cantidad,
                    monto_unitario=monto_unitario,
                    monto_total=monto_total,
                    tipo_item=item_data.tipo_item,
                )
            )
            total += monto_total
        if dias >= 7:
            total *= Decimal("0.9")
        nueva.total = total.quantize(Decimal("0.01"))
        _registrar_historial(db, nueva.id, nueva.estado_operacional, "admin", estado_anterior=None)
        db.commit()
        db.refresh(nueva)
        _enriquecer_reserva(db, nueva)
        log_event("reservas", "admin", "Crear reserva", f"id={nueva.id}")
        return nueva
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as e:
        db.rollback()
        log_event("reservas", "admin", "Error de integridad al crear reserva", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Violación de restricción de integridad en la base de datos"
        )
    except SQLAlchemyError as e:
        db.rollback()
        log_event("reservas", "admin", "Error al crear reserva", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear la reserva en la base de datos"
        )
    except Exception as e:
        db.rollback()
        # Imprimir el error completo en consola para debugging
        import traceback
        print(f"ERROR COMPLETO AL CREAR RESERVA:")
        print(traceback.format_exc())
        log_event("reservas", "admin", "Error inesperado al crear reserva", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error inesperado al procesar la reserva: {str(e)}"
        )


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
        _recalcular_totales(reserva_db, dias)
        reserva_db.fecha_checkin = checkin
        reserva_db.fecha_checkout = checkout
        datos.pop("fecha_checkin", None)
        datos.pop("fecha_checkout", None)
    estado_anterior = reserva_db.estado_operacional
    if "estado" in datos:
        try:
            nuevo_estado_enum = EstadoReservaEnum[datos.pop("estado").upper()]
            if reserva_db.estado_operacional != nuevo_estado_enum:
                reserva_db.estado_operacional = nuevo_estado_enum
                reserva_db.estado = nuevo_estado_enum.value
                reserva_db.actualizado_por = "admin"
                reserva_db.actualizado_en = datetime.utcnow()
                _registrar_historial(db, reserva_db.id, nuevo_estado_enum, "admin", estado_anterior=estado_anterior)
        except KeyError:
            pass  # Ignorar estado inválido
    for campo, valor in datos.items():
        setattr(reserva_db, campo, valor)
    db.commit()
    db.refresh(reserva_db)
    _enriquecer_reserva(db, reserva_db)
    log_event("reservas", "admin", "Actualizar reserva", f"id={reserva_id}")
    return reserva_db


@router.put("/{reserva_id}/estado", response_model=ReservaRead)
def actualizar_estado_reserva(
    reserva_id: int = Path(..., gt=0),
    nuevo_estado: str = Query(..., min_length=1, max_length=50, strip_whitespace=True),
    usuario: str = Query("admin", min_length=1, max_length=50, strip_whitespace=True),
    db: Session = Depends(conexion.get_db),
):
    reserva = _buscar_reserva(db, reserva_id)
    if not reserva:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
    
    try:
        nuevo_estado_enum = EstadoReservaEnum[nuevo_estado.upper()]
    except KeyError:
        valores_validos = ", ".join([e.name for e in EstadoReservaEnum])
        raise HTTPException(status_code=400, detail=f"Estado inválido. Usa: {valores_validos}")
    
    if reserva.estado_operacional != nuevo_estado_enum:
        estado_anterior = reserva.estado_operacional
        reserva.estado_operacional = nuevo_estado_enum
        reserva.estado = nuevo_estado_enum.value
        reserva.actualizado_por = usuario
        reserva.actualizado_en = datetime.utcnow()
        _registrar_historial(db, reserva.id, nuevo_estado_enum, usuario, estado_anterior=estado_anterior)
        db.commit()
        db.refresh(reserva)
        _enriquecer_reserva(db, reserva)
        log_event("reservas", usuario, "Actualizar estado reserva", f"id={reserva_id} estado={nuevo_estado}")
    return reserva


@router.patch("/{reserva_id}/mover", response_model=ReservaRead)
def mover_reserva(
    cambios: ReservaMove,
    reserva_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    reserva = _buscar_reserva(db, reserva_id)
    if not reserva:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")

    relacion = next((h for h in reserva.habitaciones if h.id == cambios.reserva_habitacion_id), None)
    if not relacion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Habitación no asociada a la reserva")

    nueva_habitacion_id = cambios.nueva_habitacion_id or relacion.habitacion_id
    habitaciones_ids = [h.habitacion_id if h.id != relacion.id else nueva_habitacion_id for h in reserva.habitaciones]

    _obtener_habitaciones_validas(db, habitaciones_ids)
    _verificar_disponibilidad_habitaciones(
        db,
        habitaciones_ids,
        cambios.fecha_checkin,
        cambios.fecha_checkout,
        reserva_id_excluir=reserva_id,
    )

    # Aplicar cambios
    relacion.habitacion_id = nueva_habitacion_id
    dias = (cambios.fecha_checkout - cambios.fecha_checkin).days
    if dias <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La estadia debe tener al menos una noche")

    reserva.fecha_checkin = cambios.fecha_checkin
    reserva.fecha_checkout = cambios.fecha_checkout
    _recalcular_totales(reserva, dias)

    _registrar_historial(
        db,
        reserva.id,
        reserva.estado_operacional,
        cambios.usuario,
        estado_anterior=reserva.estado_operacional,
        motivo=cambios.motivo or "Reprogramación drag and drop",
    )

    db.commit()
    db.refresh(reserva)
    _enriquecer_reserva(db, reserva)
    log_event(
        "reservas",
        cambios.usuario,
        "Mover reserva",
        f"id={reserva_id} hab_rel_id={relacion.id} nueva_hab={nueva_habitacion_id}",
    )
    return reserva


@router.delete("/{reserva_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_reserva(
    reserva_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    reserva = _buscar_reserva(db, reserva_id)
    if not reserva:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
    
    # Restaurar habitaciones a disponible si la reserva no está cerrada
    if reserva.estado_operacional != EstadoReservaEnum.CERRADA:
        for reserva_habitacion in reserva.habitaciones:
            habitacion = db.query(Habitacion).filter(
                Habitacion.id == reserva_habitacion.habitacion_id
            ).first()
            if habitacion and habitacion.estado in ["ocupada", "reservado"]:
                habitacion.estado = "disponible"
    
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
    _enriquecer_reserva(db, reserva)
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

