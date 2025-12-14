"""
Endpoints para Check-in y Gestión de Huéspedes
Implementa: POST /checkin, PUT/DELETE /huespedes, etc.
Con auditoría automática y validaciones inteligentes.
"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from database.conexion import get_db
from models.cliente import Cliente
from models.reserva import Reserva, EstadoReservaEnum
from models.reserva_eventos import (
    ReservaHuesped, ReservaEvento, ReservaPago, ReservaRoomMove,
    RolHuesped, TipoEvento, MetodoPago
)
from schemas.checkin_checkout import (
    CheckinRequest, CheckinResponse, CheckinHuespedRequest,
    HuespedResponse, UpdateHuespedRequest, DeleteHuespedRequest,
    DeleteHuespedResponse, DuplicadoAdvertencia, CapacidadAdvertencia,
    PagoRequest, PagoResponse, CheckoutRequest, CheckoutResponse,
    ResumenCheckout, EventosListResponse, EventoResponse
)
from utils.logging_utils import log_event


router = APIRouter(prefix="/reservas", tags=["Check-in/Check-out"])


# ========================================================================
# FUNCIONES AUXILIARES
# ========================================================================

def _normalizar_documento(doc: str) -> str:
    """Normalizar documento (remover espacios, caracteres especiales)"""
    return "".join(c for c in doc if c.isdigit())


def _buscar_duplicados_documento(
    db: Session, tipo_doc: str, numero_doc: str, reserva_id: int
) -> DuplicadoAdvertencia:
    """Detectar documentos duplicados en otras reservas activas"""
    numero_norm = _normalizar_documento(numero_doc)
    
    existentes = db.query(Reserva).join(Cliente).filter(
        Cliente.tipo_documento == tipo_doc,
        Cliente.numero_documento == numero_norm,
        Reserva.id != reserva_id,
        Reserva.estado_operacional.in_([EstadoReservaEnum.PENDIENTE_CHECKIN, EstadoReservaEnum.OCUPADA]),
        Reserva.deleted == False
    ).all()
    
    if existentes:
        return DuplicadoAdvertencia(
            duplicado=True,
            reservas_activas=[
                {
                    "id": r.id,
                    "cliente": r.cliente.nombre if r.cliente else "Desconocido",
                    "habitacion": r.habitaciones[0].numero if r.habitaciones else "N/A",
                    "estado": r.estado.value
                }
                for r in existentes
            ],
            mensaje=f"Cliente encontrado en {len(existentes)} reserva(s) activa(s)"
        )
    
    return DuplicadoAdvertencia(duplicado=False, mensaje="OK")


def _validar_capacidad(db: Session, habitacion_id: int, cantidad_personas: int) -> CapacidadAdvertencia:
    """Validar capacidad de habitación"""
    from models.habitacion import Habitacion
    
    hab = db.query(Habitacion).filter(Habitacion.id == habitacion_id).first()
    if not hab:
        raise HTTPException(400, "Habitación no encontrada")
    
    capacidad_max = hab.categoria.capacidad_personas or 1
    
    if cantidad_personas > capacidad_max:
        return CapacidadAdvertencia(
            supera_capacidad=True,
            capacidad_max=capacidad_max,
            personas_actuales=cantidad_personas,
            diferencia=cantidad_personas - capacidad_max
        )
    
    return CapacidadAdvertencia(
        supera_capacidad=False,
        capacidad_max=capacidad_max,
        personas_actuales=cantidad_personas,
        diferencia=0
    )


def _obtener_o_crear_cliente(
    db: Session, datos: CheckinHuespedRequest, usuario: str
) -> Cliente:
    """Obtener cliente existente o crear uno nuevo"""
    
    # Si cliente_id existe, buscar
    if datos.cliente_id:
        cliente = db.query(Cliente).filter(
            Cliente.id == datos.cliente_id,
            Cliente.deleted == False
        ).first()
        if cliente:
            return cliente
    
    # Buscar por documento
    numero_norm = _normalizar_documento(datos.documento)
    cliente = db.query(Cliente).filter(
        Cliente.tipo_documento == datos.tipo_documento,
        Cliente.numero_documento == numero_norm,
        Cliente.deleted == False
    ).first()
    
    if cliente:
        return cliente
    
    # Crear nuevo cliente
    cliente = Cliente(
        nombre=datos.nombre.strip(),
        apellido=datos.apellido.strip(),
        tipo_documento=datos.tipo_documento,
        numero_documento=numero_norm,
        email=datos.email,
        telefono=datos.telefono,
        nacionalidad=datos.nacionalidad,
        fecha_nacimiento=datos.fecha_nacimiento,
        genero=datos.genero,
        direccion=datos.direccion,
        actualizado_por=usuario,
        actualizado_en=datetime.utcnow()
    )
    db.add(cliente)
    db.flush()  # Para obtener el ID antes de commit
    
    return cliente


# ========================================================================
# ENDPOINT: POST /reservas/{id}/checkin
# ========================================================================

@router.post("/{id}/checkin", response_model=CheckinResponse, status_code=status.HTTP_201_CREATED)
def realizar_checkin(
    id: int = Path(..., gt=0),
    req: CheckinRequest = ...,
    db: Session = Depends(get_db)
):
    """
    Realizar check-in de una reserva.
    
    - Requiere: huésped principal con documento
    - Crea clientes faltantes
    - Registra evento CHECKIN en auditoría
    - Cambia estado a "ocupada"
    
    Validaciones (ADVERTENCIA, no bloquea):
    - Documento duplicado en otra reserva activa
    - Supera capacidad declarada
    """
    
    # Validar reserva existe
    reserva = db.query(Reserva).filter(Reserva.id == id).first()
    if not reserva:
        raise HTTPException(404, "Reserva no encontrada")
    
    if reserva.estado_operacional != EstadoReservaEnum.PENDIENTE_CHECKIN:
        raise HTTPException(
            409,
            f"Reserva no está en estado pendiente_checkin (actual: {reserva.estado_operacional.value})"
        )
    
    # Validar que hay huésped principal
    principal = next(
        (h for h in req.huespedes if h.rol == RolHuesped.PRINCIPAL),
        None
    )
    if not principal:
        raise HTTPException(400, "Debe haber al menos un huésped principal")
    
    if not principal.nombre.strip() or not principal.apellido.strip() or not principal.documento.strip():
        raise HTTPException(400, "Huésped principal requiere: nombre, apellido, documento")
    
    # Crear/obtener clientes
    huespedes_procesados = []
    for idx, huesped_req in enumerate(req.huespedes):
        cliente = _obtener_o_crear_cliente(db, huesped_req, req.usuario)
        
        # Detectar duplicados (advertencia, no bloquea)
        dup = _buscar_duplicados_documento(
            db, huesped_req.tipo_documento, huesped_req.documento, id
        )
        if dup.duplicado:
            log_event(
                "checkin",
                "recepcion",
                f"Documento duplicado detectado: {huesped_req.documento}",
                f"Reservas activas: {len(dup.reservas_activas)}"
            )
        
        # Crear relación reserva-huésped
        rh = ReservaHuesped(
            reserva_id=id,
            cliente_id=cliente.id,
            rol=huesped_req.rol,
            # Usar el ID de la Habitación real, no el ID de la relación ReservaHabitacion
            habitacion_id=(
                huesped_req.habitacion_id
                or (reserva.habitaciones[0].habitacion_id if reserva.habitaciones else None)
            ),
            orden_registro=idx,
            creado_por=req.usuario
        )
        db.add(rh)
        huespedes_procesados.append(rh)
    
    db.flush()  # Para obtener IDs
    
    # Validar capacidad (advertencia, no bloquea)
    if reserva.habitaciones:
        # Validar capacidad con el ID de Habitación correcto
        capacidad = _validar_capacidad(
            db,
            reserva.habitaciones[0].habitacion_id,
            len(huespedes_procesados)
        )
        if capacidad.supera_capacidad:
            log_event(
                "checkin",
                "recepcion",
                f"Supera capacidad: {capacidad.personas_actuales}/{capacidad.capacidad_max}",
                f"Reserva {id}"
            )
    
    # Actualizar estado de reserva
    reserva.estado_operacional = EstadoReservaEnum.OCUPADA
    reserva.estado = EstadoReservaEnum.OCUPADA.value
    reserva.fecha_checkin_real = req.fecha_checkin_real or datetime.utcnow()
    reserva.usuario_actual = req.usuario
    reserva.notas_internas = req.notas_internas
    reserva.actualizado_por = req.usuario
    reserva.actualizado_en = datetime.utcnow()
    
    # Crear evento de auditoría
    evento = ReservaEvento(
        reserva_id=id,
        tipo_evento=TipoEvento.CHECKIN,
        usuario=req.usuario,
        descripcion=f"Check-in realizado: {len(huespedes_procesados)} huéspedes",
        payload={
            "huespedes_count": len(huespedes_procesados),
            "fecha_checkin_real": reserva.fecha_checkin_real.isoformat(),
            "notas": req.notas_internas
        }
    )
    db.add(evento)
    
    db.commit()
    db.refresh(reserva)
    db.refresh(evento)
    
    log_event(
        "checkin",
        req.usuario,
        f"Check-in completado: Reserva {id}",
        f"Huéspedes: {len(huespedes_procesados)}"
    )
    
    return CheckinResponse(
        id=reserva.id,
        estado=reserva.estado,
        fecha_checkin_real=reserva.fecha_checkin_real,
        huespedes=[
            HuespedResponse(
                id=rh.id,
                cliente_id=rh.cliente_id,
                nombre=rh.cliente.nombre,
                apellido=rh.cliente.apellido,
                tipo_documento=rh.cliente.tipo_documento,
                documento=rh.cliente.numero_documento,
                rol=rh.rol,
                habitacion_id=rh.habitacion_id,
                fecha_agregado=rh.fecha_agregado,
                creado_por=rh.creado_por,
                telefono=rh.cliente.telefono,
                email=rh.cliente.email,
                nacionalidad=rh.cliente.nacionalidad,
                fecha_nacimiento=rh.cliente.fecha_nacimiento,
                genero=rh.cliente.genero,
                direccion=rh.cliente.direccion
            )
            for rh in huespedes_procesados
        ],
        evento_id=evento.id,
        timestamp=evento.timestamp
    )


# ========================================================================
# ENDPOINT: PUT /reservas/{id}/huespedes
# ========================================================================

@router.put("/{id}/huespedes", status_code=status.HTTP_200_OK)
def actualizar_lista_huespedes(
    id: int = Path(..., gt=0),
    usuario: str = Query(..., min_length=1),
    razon: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    req: List[CheckinHuespedRequest] = ...
):
    """
    Reemplazar lista COMPLETA de huéspedes en una reserva ocupada.
    
    Usar para:
    - Corregir datos después de check-in
    - Agregar/remover huéspedes
    - Cambiar roles
    
    Valida:
    - Reserva está ocupada
    - Al menos un huésped principal
    - Capacidad no excedida
    """
    
    reserva = db.query(Reserva).filter(Reserva.id == id).first()
    if not reserva:
        raise HTTPException(404, "Reserva no encontrada")
    
    if reserva.estado_operacional != EstadoReservaEnum.OCUPADA:
        raise HTTPException(409, f"Reserva no está ocupada (estado: {reserva.estado_operacional.value})")
    
    # Validar al menos un principal
    principales = [h for h in req if h.rol == RolHuesped.PRINCIPAL]
    if not principales:
        raise HTTPException(400, "Debe haber al menos un huésped principal")
    
    # Guardar estado anterior para auditoría
    huespedes_anteriores = [
        {"id": rh.id, "cliente_id": rh.cliente_id, "rol": rh.rol.value}
        for rh in reserva.huespedes
    ]
    
    # Eliminar huéspedes actuales
    db.query(ReservaHuesped).filter(ReservaHuesped.reserva_id == id).delete()
    
    # Crear nuevos
    for idx, huesped_req in enumerate(req):
        cliente = _obtener_o_crear_cliente(db, huesped_req, usuario)
        
        rh = ReservaHuesped(
            reserva_id=id,
            cliente_id=cliente.id,
            rol=huesped_req.rol,
            habitacion_id=huesped_req.habitacion_id or (reserva.habitaciones[0].id if reserva.habitaciones else None),
            orden_registro=idx,
            creado_por=usuario
        )
        db.add(rh)
    
    db.flush()
    
    # Crear evento
    evento = ReservaEvento(
        reserva_id=id,
        tipo_evento=TipoEvento.UPDATE_GUEST,
        usuario=usuario,
        descripcion=f"Lista de huéspedes actualizada: {len(huespedes_anteriores)} → {len(req)}",
        payload={
            "huespedes_nuevos": len(req),
            "razon": razon
        },
        cambios_anteriores={"huespedes_anteriores": huespedes_anteriores}
    )
    db.add(evento)
    
    reserva.actualizado_por = usuario
    reserva.actualizado_en = datetime.utcnow()
    
    db.commit()
    db.refresh(evento)
    
    log_event(
        "huespedes",
        usuario,
        f"Lista actualizada: Reserva {id}",
        f"{len(huespedes_anteriores)} → {len(req)} huéspedes"
    )
    
    return {
        "operacion_exitosa": True,
        "evento_id": evento.id,
        "timestamp": evento.timestamp
    }


# ========================================================================
# ENDPOINT: POST /reservas/{id}/huespedes
# ========================================================================

@router.post("/{id}/huespedes", status_code=status.HTTP_201_CREATED)
def agregar_huesped(
    id: int = Path(..., gt=0),
    usuario: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    req: CheckinHuespedRequest = ...
):
    """
    Agregar UN huésped a una reserva en curso.
    
    Usado durante estadía para:
    - Agregar persona olvidada
    - Incluir acompañante de último minuto
    """
    
    reserva = db.query(Reserva).filter(Reserva.id == id).first()
    if not reserva:
        raise HTTPException(404, "Reserva no encontrada")
    
    if reserva.estado_operacional != EstadoReservaEnum.OCUPADA:
        raise HTTPException(409, "Reserva no está ocupada")
    
    cliente = _obtener_o_crear_cliente(db, req, usuario)
    
    # Obtener siguiente número de orden
    max_orden = db.query(func.max(ReservaHuesped.orden_registro)).filter(
        ReservaHuesped.reserva_id == id
    ).scalar() or 0
    
    rh = ReservaHuesped(
        reserva_id=id,
        cliente_id=cliente.id,
        rol=req.rol,
        habitacion_id=req.habitacion_id or (reserva.habitaciones[0].id if reserva.habitaciones else None),
        orden_registro=max_orden + 1,
        creado_por=usuario
    )
    db.add(rh)
    db.flush()
    
    evento = ReservaEvento(
        reserva_id=id,
        tipo_evento=TipoEvento.ADD_GUEST,
        usuario=usuario,
        descripcion=f"Huésped agregado: {cliente.nombre} {cliente.apellido}",
        payload={
            "cliente_id": cliente.id,
            "nombre": cliente.nombre,
            "rol": req.rol.value
        }
    )
    db.add(evento)
    
    reserva.actualizado_por = usuario
    reserva.actualizado_en = datetime.utcnow()
    
    db.commit()
    db.refresh(rh)
    db.refresh(evento)
    
    return {
        "id": rh.id,
        "cliente_id": cliente.id,
        "nombre": cliente.nombre,
        "rol": rh.rol.value,
        "evento_id": evento.id
    }


# ========================================================================
# ENDPOINT: DELETE /reservas/{id}/huespedes/{huesped_id}
# ========================================================================

@router.delete("/{id}/huespedes/{huesped_id}")
def eliminar_huesped(
    id: int = Path(..., gt=0),
    huesped_id: int = Path(..., gt=0),
    usuario: str = Query(..., min_length=1),
    razon: str = Query(..., min_length=1),
    db: Session = Depends(get_db)
):
    """Eliminar UN huésped de la reserva"""
    
    reserva = db.query(Reserva).filter(Reserva.id == id).first()
    if not reserva:
        raise HTTPException(404, "Reserva no encontrada")
    
    rh = db.query(ReservaHuesped).filter(
        ReservaHuesped.id == huesped_id,
        ReservaHuesped.reserva_id == id
    ).first()
    
    if not rh:
        raise HTTPException(404, "Huésped no encontrado en esta reserva")
    
    # No permitir eliminar único principal
    principales = db.query(ReservaHuesped).filter(
        ReservaHuesped.reserva_id == id,
        ReservaHuesped.rol == RolHuesped.PRINCIPAL
    ).count()
    
    if rh.rol == RolHuesped.PRINCIPAL and principales == 1:
        raise HTTPException(400, "No se puede eliminar el único huésped principal")
    
    # Guardar datos para auditoría
    huesped_datos = {
        "id": rh.id,
        "nombre": rh.cliente.nombre if rh.cliente else "Desconocido",
        "rol": rh.rol.value
    }
    
    db.delete(rh)
    
    evento = ReservaEvento(
        reserva_id=id,
        tipo_evento=TipoEvento.DELETE_GUEST,
        usuario=usuario,
        descripcion=f"Huésped eliminado: {huesped_datos['nombre']}",
        payload={"razon": razon},
        cambios_anteriores={"huesped": huesped_datos}
    )
    db.add(evento)
    
    reserva.actualizado_por = usuario
    reserva.actualizado_en = datetime.utcnow()
    
    db.commit()
    db.refresh(evento)
    
    return DeleteHuespedResponse(
        eliminado=True,
        huesped_anterior=huesped_datos,
        evento_id=evento.id
    )


# ========================================================================
# ENDPOINT: GET /reservas/{id}/eventos
# ========================================================================

@router.get("/{id}/eventos", response_model=EventosListResponse)
def listar_eventos_reserva(
    id: int = Path(..., gt=0),
    limite: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Obtener timeline completo de eventos de una reserva"""
    
    reserva = db.query(Reserva).filter(Reserva.id == id).first()
    if not reserva:
        raise HTTPException(404, "Reserva no encontrada")
    
    total = db.query(ReservaEvento).filter(ReservaEvento.reserva_id == id).count()
    
    eventos_db = db.query(ReservaEvento).filter(
        ReservaEvento.reserva_id == id
    ).order_by(ReservaEvento.timestamp.desc()).offset(offset).limit(limite).all()
    
    return EventosListResponse(
        reserva_id=id,
        total_eventos=total,
        eventos=[
            EventoResponse(
                id=e.id,
                tipo=e.tipo_evento,
                usuario=e.usuario,
                timestamp=e.timestamp,
                descripcion=e.descripcion,
                payload=e.payload
            )
            for e in eventos_db
        ]
    )


# ========================================================================
# ENDPOINTS FASE 2: Operaciones avanzadas
# ========================================================================

@router.put(
    "/{id}/habitaciones",
    status_code=200,
    summary="Mover huésped a diferente habitación",
    description="Cambia un huésped de habitación con auditoría completa"
)
def mover_huesped_habitacion(
    id: int = Path(..., gt=0),
    huesped_id: int = Query(..., description="ID del huésped a mover"),
    habitacion_anterior_id: int = Query(..., description="Habitación actual"),
    habitacion_nueva_id: int = Query(..., description="Nueva habitación"),
    usuario: str = Query(..., min_length=1, description="Usuario realizando acción"),
    razon: str = Query(..., min_length=1, description="Razón del movimiento"),
    notas: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Mueve un huésped a diferente habitación
    - Valida que habitación nueva esté disponible
    - Crea evento de auditoría
    - Atomicidad garantizada
    """
    from services.checkin_checkout_service import RoomMoveService
    
    try:
        exitoso, mensaje, room_move = RoomMoveService.mover_huesped(
            db, id, huesped_id, habitacion_anterior_id, habitacion_nueva_id,
            usuario, razon, notas
        )
        
        if not exitoso:
            raise HTTPException(status_code=400, detail=mensaje)
        
        return {
            "operacion_exitosa": True,
            "reserva_id": id,
            "room_move_id": room_move.id,
            "habitacion_anterior": habitacion_anterior_id,
            "habitacion_nueva": habitacion_nueva_id,
            "timestamp": room_move.timestamp.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        log_event(f"ERROR en PUT /habitaciones: {str(e)}", "error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{id}/extender-estadia",
    status_code=200,
    summary="Extender fecha de checkout",
    description="Prolonga la estadía por días adicionales"
)
def extender_estadia(
    id: int = Path(..., gt=0),
    fecha_checkout_nueva: datetime = Query(..., description="Nueva fecha de checkout"),
    usuario: str = Query(..., min_length=1),
    razon: str = Query(..., min_length=1),
    notas: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Extiende la fecha de checkout de una reserva
    - Calcula automáticamente costo adicional
    - Registra cambios en auditoría
    - Requiere fecha posterior a fecha actual
    """
    from services.checkin_checkout_service import ExtendStayService
    
    try:
        exitoso, mensaje, resultado = ExtendStayService.extender_estadia(
            db, id, fecha_checkout_nueva, usuario, razon, notas
        )
        
        if not exitoso:
            raise HTTPException(status_code=400, detail=mensaje)
        
        return resultado
    except HTTPException:
        raise
    except Exception as e:
        log_event(f"ERROR en POST /extender-estadia: {str(e)}", "error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{id}/pagos",
    status_code=201,
    summary="Registrar pago contra reserva",
    description="Crea transacción de pago y actualiza saldo"
)
def registrar_pago(
    id: int = Path(..., gt=0),
    monto: float = Query(..., gt=0, description="Monto a pagar"),
    usuario: str = Query(..., min_length=1),
    metodo: str = Query(..., regex="^(EFECTIVO|TARJETA|TRANSFERENCIA|OTRO)$"),
    referencia: Optional[str] = Query(None, description="Referencia de pago (ej: ID transacción)"),
    notas: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Registra un pago contra la reserva
    - Valida que no exceda saldo pendiente
    - Actualiza automáticamente saldo_pendiente
    - Crea evento de auditoría PAYMENT
    """
    from services.checkin_checkout_service import PaymentService
    
    try:
        exitoso, mensaje, pago = PaymentService.registrar_pago(
            db, id, monto, usuario, metodo, referencia, notas
        )
        
        if not exitoso:
            raise HTTPException(status_code=400, detail=mensaje)
        
        # Obtener saldo actualizado
        reserva = db.query(Reserva).filter(Reserva.id == id).first()
        
        return {
            "operacion_exitosa": True,
            "pago_id": pago.id,
            "reserva_id": id,
            "monto_pagado": monto,
            "metodo": metodo,
            "saldo_anterior": (reserva.saldo_pendiente or 0) + monto,
            "saldo_nuevo": reserva.saldo_pendiente,
            "timestamp": pago.timestamp.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        log_event(f"ERROR en POST /pagos: {str(e)}", "error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{id}/checkout",
    status_code=200,
    summary="Realizar checkout (cierre de reserva)",
    description="Finaliza la reserva, valida saldo, cierra cuenta"
)
def realizar_checkout(
    id: int = Path(..., gt=0),
    usuario: str = Query(..., min_length=1),
    fecha_checkout_real: Optional[datetime] = Query(None),
    pago_final: Optional[float] = Query(None, ge=0),
    metodo_pago_final: Optional[str] = Query(None, regex="^(EFECTIVO|TARJETA|TRANSFERENCIA|OTRO)$"),
    estado_habitacion: Optional[str] = Query(None, regex="^(LIMPIA|REVISAR|EN_USO|SUCIA)$"),
    notas_limpieza: Optional[str] = Query(None),
    daños_reportados: Optional[List[str]] = Query(None),
    autorizar_deuda: bool = Query(False, description="Permitir cerrar con deuda pendiente"),
    db: Session = Depends(get_db)
):
    """
    Realiza el checkout de una reserva
    - Registra pago final si existe
    - Valida saldo o permite deuda autorizada
    - Marca reserva como CERRADA
    - Registra estado de limpieza
    """
    from services.checkin_checkout_service import CheckoutService
    
    try:
        exitoso, mensaje, resultado = CheckoutService.realizar_checkout(
            db, id, usuario, fecha_checkout_real, pago_final, metodo_pago_final,
            estado_habitacion, notas_limpieza, daños_reportados, autorizar_deuda
        )
        
        if not exitoso:
            raise HTTPException(status_code=400, detail=mensaje)
        
        return resultado
    except HTTPException:
        raise
    except Exception as e:
        log_event("checkout", usuario, "Error fatal", f"POST /checkout: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/{id}/revertir",
    status_code=200,
    summary="Revertir checkout (admin only)",
    description="Reabre una reserva cerrada para correcciones"
)
def revertir_checkout(
    id: int = Path(..., gt=0),
    usuario: str = Query(..., min_length=1, description="Admin user"),
    razon: str = Query(..., min_length=1, description="Razón de la reversión"),
    db: Session = Depends(get_db)
):
    """
    Revierte un checkout (admin only)
    - Reabre reserva cerrada
    - Cambia estado a OCUPADA
    - Crea evento de corrección
    """
    from services.checkin_checkout_service import AdminService
    
    try:
        exitoso, mensaje = AdminService.revertir_checkout(db, id, usuario, razon)
        
        if not exitoso:
            raise HTTPException(status_code=400, detail=mensaje)
        
        return {
            "operacion_exitosa": True,
            "reserva_id": id,
            "estado_nuevo": "OCUPADA",
            "mensaje": mensaje,
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        log_event(f"ERROR en PUT /revertir: {str(e)}", "error")
        raise HTTPException(status_code=500, detail=str(e))
