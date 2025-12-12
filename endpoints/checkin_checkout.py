"""
Endpoints para gestión de check-in y check-out
"""
from datetime import date, datetime, timedelta
import re
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field, condecimal, constr, PositiveInt
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import SQLAlchemyError

from database import conexion
from models.reserva import Reserva, HistorialReserva, ReservaItem
from models.reserva import Reserva, HistorialReserva, ReservaItem, ReservaHabitacion
from sqlalchemy.orm import Session, selectinload
from models.cliente import Cliente, ClienteVisita
from models.habitacion import Habitacion
from models.housekeeping import HousekeepingTarea, HousekeepingTareaTemplate
from schemas.reservas import ReservaRead
from utils.logging_utils import log_event
from schemas.cleaning_cycle import CleaningCycleCreate
from endpoints.cleaning_cycle import crear_cycle

router = APIRouter(prefix="/checkin-checkout", tags=["Check-In/Check-Out"])


class CheckInGuest(BaseModel):
    nombre: constr(strip_whitespace=True, min_length=2, max_length=120)
    apellido: Optional[constr(strip_whitespace=True, min_length=1, max_length=120)] = None
    documento: Optional[constr(strip_whitespace=True, max_length=50)] = None
    tipo_documento: Optional[constr(strip_whitespace=True, max_length=20)] = "DNI"
    email: Optional[constr(strip_whitespace=True, max_length=120)] = None
    telefono: Optional[constr(strip_whitespace=True, max_length=30)] = None
    habitacion_id: Optional[int] = None
    nacionalidad: Optional[constr(strip_whitespace=True, max_length=60)] = None
    fecha_nacimiento: Optional[date] = None
    genero: Optional[constr(strip_whitespace=True, max_length=10)] = None
    direccion: Optional[constr(strip_whitespace=True, max_length=200)] = None


class CheckInItem(BaseModel):
    descripcion: constr(strip_whitespace=True, min_length=2, max_length=200)
    cantidad: PositiveInt = 1
    monto_total: condecimal(max_digits=12, decimal_places=2)
    tipo_item: constr(strip_whitespace=True, min_length=3, max_length=20) = "desayuno"


class CheckInRequest(BaseModel):
    notas: Optional[str] = None
    usuario: str = "admin"
    huespedes: Optional[List[CheckInGuest]] = None
    items_consumo: Optional[List[CheckInItem]] = None


class CheckOutRequest(BaseModel):
    notas: Optional[str] = None
    usuario: str = "admin"
    pago_monto: Optional[condecimal(max_digits=12, decimal_places=2)] = None
    pago_metodo: Optional[constr(strip_whitespace=True, max_length=50)] = None
    descripcion_limpieza: Optional[constr(strip_whitespace=True, max_length=200)] = None
    noches_cobradas: Optional[PositiveInt] = None


# ===== HELPERS =====

def _crear_tareas_limpieza(db: Session, habitacion: Habitacion, reserva: Reserva) -> None:
    """
    Crea tareas de limpieza basadas en el template de la habitación.
    Si no hay template, crea una tarea genérica.
    """
    nombre_huesped = reserva.cliente.nombre if reserva.cliente else "Huésped"
    
    # Si la habitación tiene un template personalizado, usarlo
    if habitacion.template_tareas_id:
        template = db.query(HousekeepingTareaTemplate).filter(
            HousekeepingTareaTemplate.id == habitacion.template_tareas_id
        ).first()
        
        if template and template.tareas:
            # Crear una tarea padre que agrupe todas las subtareas
            tarea_padre = HousekeepingTarea(
                habitacion_id=habitacion.id,
                template_id=template.id,
                estado="pendiente",
                prioridad="media",
                es_padre=True,
                ultimo_huesped=nombre_huesped,
                notas=f"Limpieza post-huésped. Camas: {habitacion.tipo_camas}. Particularidades: {habitacion.particularidades}"
            )
            db.add(tarea_padre)
            db.flush()  # Para obtener el ID
            
            # Crear subtareas desde el template
            for idx, tarea_template in enumerate(template.tareas, 1):
                subtarea = HousekeepingTarea(
                    habitacion_id=habitacion.id,
                    template_id=template.id,
                    estado="pendiente",
                    prioridad="media",
                    tarea_padre_id=tarea_padre.id,
                    es_padre=False,
                    ultimo_huesped=nombre_huesped,
                    notas=tarea_template.get("descripcion", ""),
                    checklist_result={"orden": tarea_template.get("orden", idx)}
                )
                db.add(subtarea)
            return
    
    # Si no hay template, crear una tarea genérica
    tarea = HousekeepingTarea(
        habitacion_id=habitacion.id,
        estado="pendiente",
        prioridad="media",
        ultimo_huesped=nombre_huesped,
        notas=f"Limpieza estándar. Camas: {habitacion.tipo_camas}. Particularidades: {habitacion.particularidades}"
    )
    db.add(tarea)


def _normalize_doc(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\D+", "", value)


def _resolver_cliente_desde_checkin(db: Session, reserva: Reserva, huesped: CheckInGuest) -> Cliente:
    """Obtiene o crea un cliente a partir del huésped principal y lo vincula a la reserva."""
    numero_doc = _normalize_doc(huesped.documento)
    if not numero_doc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Se requiere el documento del huésped para registrar el check-in"
        )
    if not huesped.apellido:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Se requiere el apellido del huésped para registrar el check-in"
        )
    tipo_doc = (huesped.tipo_documento or "DNI").strip()

    cliente = db.query(Cliente).filter(
        Cliente.tipo_documento == tipo_doc,
        Cliente.numero_documento == numero_doc,
        Cliente.deleted.is_(False)
    ).first()

    if cliente:
        # Actualizar datos básicos si llegan y antes no estaban
        if huesped.nombre and huesped.nombre.strip() and cliente.nombre != huesped.nombre.strip():
            cliente.nombre = huesped.nombre.strip()
        if huesped.apellido and huesped.apellido.strip() and cliente.apellido != huesped.apellido.strip():
            cliente.apellido = huesped.apellido.strip()
        if huesped.email and huesped.email.strip():
            cliente.email = huesped.email.strip()
        if huesped.telefono and huesped.telefono.strip():
            cliente.telefono = huesped.telefono.strip()
        if huesped.nacionalidad and huesped.nacionalidad.strip():
            cliente.nacionalidad = huesped.nacionalidad.strip()
        if huesped.fecha_nacimiento:
            cliente.fecha_nacimiento = huesped.fecha_nacimiento
        if huesped.genero and huesped.genero.strip():
            cliente.genero = huesped.genero.strip()
        if huesped.direccion and huesped.direccion.strip():
            cliente.direccion = huesped.direccion.strip()
        cliente.actualizado_en = datetime.utcnow()
    else:
        cliente = Cliente(
            nombre=huesped.nombre.strip(),
            apellido=huesped.apellido.strip() if huesped.apellido else "",
            tipo_documento=tipo_doc,
            numero_documento=numero_doc,
            nacionalidad=huesped.nacionalidad.strip() if (huesped.nacionalidad and huesped.nacionalidad.strip()) else None,
            email=huesped.email.strip() if (huesped.email and huesped.email.strip()) else None,
            telefono=huesped.telefono.strip() if (huesped.telefono and huesped.telefono.strip()) else None,
            fecha_nacimiento=huesped.fecha_nacimiento,
            genero=huesped.genero.strip() if (huesped.genero and huesped.genero.strip()) else None,
            direccion=huesped.direccion.strip() if (huesped.direccion and huesped.direccion.strip()) else None,
            activo=True,
            deleted=False,
            blacklist=False,
        )
        db.add(cliente)
        db.flush()

    reserva.cliente_id = cliente.id
    return cliente


def _registrar_visita_cliente(db: Session, cliente: Cliente, reserva: Reserva) -> ClienteVisita:
    """Crea un registro de visita del cliente asociado a la reserva."""
    habitacion_id = None
    if reserva.habitaciones:
        habitacion_id = reserva.habitaciones[0].habitacion_id

    total_actual = Decimal(reserva.total) if reserva.total is not None else Decimal("0")
    visita = ClienteVisita(
        cliente_id=cliente.id,
        reserva_id=reserva.id,
        habitacion_id=habitacion_id,
        fecha_checkin=datetime.utcnow(),
        total_gastado=total_actual
    )
    db.add(visita)
    return visita




def _registrar_historial(db: Session, reserva_id: int, estado: str, usuario: str, estado_anterior: Optional[str] = None) -> None:
    """Registra un cambio de estado en el historial"""
    historial = HistorialReserva(
        reserva_id=reserva_id,
        estado_anterior=estado_anterior,
        estado_nuevo=estado,
        usuario=usuario,
        fecha=datetime.utcnow(),
    )
    db.add(historial)


@router.get("/pendientes-checkin", response_model=list[ReservaRead])
def listar_pendientes_checkin(
    fecha: Optional[date] = Query(None, description="Fecha para filtrar (default: hoy)"),
    db: Session = Depends(conexion.get_db)
):
    """
    Lista las reservas pendientes de check-in para una fecha específica
    """
    try:
        if not fecha:
            fecha = date.today()
        
        reservas = db.query(Reserva).options(
            selectinload(Reserva.habitaciones).selectinload(ReservaHabitacion.habitacion),
            selectinload(Reserva.items),
            selectinload(Reserva.historial)
        ).filter(
            Reserva.deleted.is_(False),
            Reserva.fecha_checkin == fecha,
            Reserva.estado == "reservada"
        ).all()
        
        log_event("checkin", "admin", "Listar pendientes de check-in", f"fecha={fecha} total={len(reservas)}")
        
        # Enriquecer con numero de habitacion si esta disponible
        for r in reservas:
            for hab in r.habitaciones or []:
                if hasattr(hab, "habitacion") and hab.habitacion:
                    hab.habitacion_numero = getattr(hab.habitacion, "numero", None)
        return reservas
        
    except SQLAlchemyError as e:
        log_event("checkin", "admin", "Error al listar pendientes check-in", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al consultar reservas pendientes de check-in"
        )


@router.get("/pendientes-checkout", response_model=list[ReservaRead])
def listar_pendientes_checkout(
    fecha: Optional[date] = Query(None, description="Fecha para filtrar (default: hoy)"),
    db: Session = Depends(conexion.get_db)
):
    """
    Lista las reservas pendientes de check-out para una fecha específica
    """
    try:
        if not fecha:
            fecha = date.today()
        
        reservas = db.query(Reserva).options(
            selectinload(Reserva.habitaciones).selectinload(ReservaHabitacion.habitacion),
            selectinload(Reserva.items),
            selectinload(Reserva.historial)
        ).filter(
            Reserva.deleted.is_(False),
            Reserva.fecha_checkout == fecha,
            Reserva.estado == "ocupada"
        ).all()
        
        log_event("checkout", "admin", "Listar pendientes de check-out", f"fecha={fecha} total={len(reservas)}")
        
        # Enriquecer con numero de habitacion si esta disponible
        for r in reservas:
            for hab in r.habitaciones or []:
                if hasattr(hab, "habitacion") and hab.habitacion:
                    hab.habitacion_numero = getattr(hab.habitacion, "numero", None)
        return reservas
        
    except SQLAlchemyError as e:
        log_event("checkout", "admin", "Error al listar pendientes check-out", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al consultar reservas pendientes de check-out"
        )


@router.post("/{reserva_id}/checkin", response_model=ReservaRead)
def realizar_checkin(
    reserva_id: int = Path(..., gt=0),
    datos: CheckInRequest = CheckInRequest(),
    db: Session = Depends(conexion.get_db)
):
    """
    Realiza el check-in de una reserva
    """
    try:
        # Obtener la reserva
        reserva = db.query(Reserva).options(
            selectinload(Reserva.habitaciones),
            selectinload(Reserva.items),
            selectinload(Reserva.historial)
        ).filter(
            Reserva.id == reserva_id,
            Reserva.deleted.is_(False)
        ).first()
        
        if not reserva:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reserva no encontrada"
            )
        
        # Validar que la reserva esté en estado "reservada"
        if reserva.estado != "reservada":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La reserva debe estar en estado 'reservada' (actual: {reserva.estado})"
            )
        
        # Validar que sea la fecha correcta
        hoy = date.today()
        if reserva.fecha_checkin > hoy:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El check-in solo puede realizarse a partir del {reserva.fecha_checkin}"
            )
        
        if not datos.huespedes or len(datos.huespedes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe registrar al menos un huésped con nombre, apellido y documento para el check-in"
            )

        # Vincular cliente principal a la reserva usando el primer huésped
        cliente_asociado = None
        if datos.huespedes and len(datos.huespedes) > 0:
            cliente_asociado = _resolver_cliente_desde_checkin(db, reserva, datos.huespedes[0])
        elif reserva.cliente_id:
            cliente_asociado = db.query(Cliente).filter(Cliente.id == reserva.cliente_id).first()

        estado_anterior = reserva.estado
        reserva.estado = "ocupada"
        
        # Agregar notas y huespedes si se proporcionaron
        notas_extra = []
        if datos.notas:
            notas_extra.append(datos.notas)
        if datos.huespedes:
            detalles_huespedes = [
                f"{h.nombre} ({h.documento or 's/DNI'})"
                + (f" hab:{h.habitacion_id}" if h.habitacion_id else "")
                for h in datos.huespedes
            ]
            notas_extra.append("Huéspedes: " + ", ".join(detalles_huespedes))
        if notas_extra:
            notas_texto = " | ".join(notas_extra)
            if reserva.notas:
                reserva.notas += f"\n[Check-in {hoy}]: {notas_texto}"
            else:
                reserva.notas = f"[Check-in {hoy}]: {notas_texto}"
        
        # Actualizar estado de habitaciones
        for reserva_habitacion in reserva.habitaciones:
            habitacion = db.query(Habitacion).filter(
                Habitacion.id == reserva_habitacion.habitacion_id
            ).first()
            if habitacion:
                habitacion.estado = "ocupada"

        # Agregar consumos (ej. desayunos) si vienen en el check-in
        total_incremento = Decimal("0")
        if datos.items_consumo:
            for item in datos.items_consumo:
                monto_total = Decimal(item.monto_total)
                cantidad = Decimal(item.cantidad)
                # Calcular monto unitario, asegurando que no sea cero si hay monto total
                if monto_total > 0 and cantidad > 0:
                    unitario = (monto_total / cantidad).quantize(Decimal("0.01"))
                else:
                    unitario = Decimal("0.00")
                
                db.add(
                    ReservaItem(
                        reserva_id=reserva.id,
                        producto_id=None,
                        descripcion=item.descripcion,
                        cantidad=item.cantidad,
                        monto_unitario=unitario,
                        monto_total=monto_total,
                        tipo_item=item.tipo_item,
                    )
                )
                total_incremento += monto_total
            reserva.total = (Decimal(reserva.total) + total_incremento).quantize(Decimal("0.01"))
        
        # Registrar en historial
        _registrar_historial(db, reserva.id, "ocupada", datos.usuario, estado_anterior=estado_anterior)

        # Registrar visita del cliente
        if cliente_asociado:
            _registrar_visita_cliente(db, cliente_asociado, reserva)
        
        db.commit()
        db.refresh(reserva)
        
        log_event(
            "checkin",
            datos.usuario,
            "Check-in realizado",
            f"reserva_id={reserva_id} huespedes={len(datos.huespedes or [])} items={len(datos.items_consumo or [])} incremento={str(total_incremento)}",
        )
        
        return reserva
        
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        log_event("checkin", "admin", "Error al realizar check-in", f"reserva_id={reserva_id} error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al realizar el check-in"
        )


@router.post("/{reserva_id}/checkout", response_model=ReservaRead)
def realizar_checkout(
    reserva_id: int = Path(..., gt=0),
    datos: CheckOutRequest = CheckOutRequest(),
    db: Session = Depends(conexion.get_db)
):
    """
    Realiza el check-out de una reserva
    """
    try:
        # Obtener la reserva
        reserva = db.query(Reserva).options(
            selectinload(Reserva.habitaciones),
            selectinload(Reserva.items),
            selectinload(Reserva.historial)
        ).filter(
            Reserva.id == reserva_id,
            Reserva.deleted.is_(False)
        ).first()
        
        if not reserva:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reserva no encontrada"
            )
        
        # Validar que la reserva esté en estado "ocupada"
        if reserva.estado != "ocupada":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La reserva debe estar en estado 'ocupada' (actual: {reserva.estado})"
            )
        
        estado_anterior = reserva.estado
        # Actualizar estado de la reserva
        reserva.estado = "finalizada"

        # Calcular noches facturadas (checkout anticipado)
        hoy = date.today()
        dias_desde_checkin = (min(hoy, reserva.fecha_checkout) - reserva.fecha_checkin).days
        if dias_desde_checkin <= 0:
            dias_desde_checkin = 1
        dias_facturados = int(datos.noches_cobradas) if datos.noches_cobradas else dias_desde_checkin
        if dias_facturados <= 0:
            dias_facturados = 1

        # Ajustar totales segun noches facturadas
        total = Decimal("0")
        nueva_fecha_checkout = reserva.fecha_checkin + timedelta(days=dias_facturados)
        reserva.fecha_checkout = nueva_fecha_checkout
        for hab in reserva.habitaciones:
            hab.cantidad_noches = dias_facturados
            hab.subtotal_habitacion = Decimal(hab.precio_noche) * dias_facturados
            total += hab.subtotal_habitacion
        for item in reserva.items:
            total += Decimal(item.monto_total)
        if dias_facturados >= 7:
            total *= Decimal("0.9")
        reserva.total = total.quantize(Decimal("0.01"))
        
        # Agregar notas si se proporcionaron
        notas_extra = []
        if datos.notas:
            notas_extra.append(datos.notas)
        if datos.pago_monto is not None:
            pago_det = f"Pago registrado: ${datos.pago_monto}"
            if datos.pago_metodo:
                pago_det += f" vía {datos.pago_metodo}"
            notas_extra.append(pago_det)
        if datos.descripcion_limpieza:
            notas_extra.append(f"Nota limpieza: {datos.descripcion_limpieza}")

        if notas_extra:
            texto_notas = " | ".join(notas_extra)
            if reserva.notas:
                reserva.notas += f"\n[Check-out {hoy}]: {texto_notas}"
            else:
                reserva.notas = f"[Check-out {hoy}]: {texto_notas}"
        
        # Actualizar estado de habitaciones
       # Actualizar estado de habitaciones y crear cleaning cycles nuevos
        for reserva_habitacion in reserva.habitaciones:
            habitacion = db.query(Habitacion).filter(
                Habitacion.id == reserva_habitacion.habitacion_id
            ).first()

            if habitacion and habitacion.estado != "mantenimiento":
                habitacion.estado = "limpieza"

                # Crear el nuevo ciclo de limpieza
                cycle_payload = CleaningCycleCreate(
                    habitacion_id=habitacion.id,
                    reserva_id=reserva.id,
                    responsable=datos.usuario
                )

                crear_cycle(payload=cycle_payload, db=db)
        
        # Actualizar visita del cliente (gasto y checkout)
        if reserva.cliente_id:
            visita = db.query(ClienteVisita).filter(ClienteVisita.reserva_id == reserva.id).order_by(ClienteVisita.id.desc()).first()
            total_final = Decimal(reserva.total) if reserva.total is not None else Decimal("0")
            if visita:
                visita.total_gastado = total_final
                visita.fecha_checkout = datetime.utcnow()
            else:
                cliente = db.query(Cliente).filter(Cliente.id == reserva.cliente_id, Cliente.deleted.is_(False)).first()
                habitacion_id = reserva.habitaciones[0].habitacion_id if reserva.habitaciones else None
                if cliente:
                    db.add(
                        ClienteVisita(
                            cliente_id=cliente.id,
                            reserva_id=reserva.id,
                            habitacion_id=habitacion_id,
                            fecha_checkin=datetime.utcnow(),
                            fecha_checkout=datetime.utcnow(),
                            total_gastado=total_final,
                        )
                    )

        # Registrar en historial
        _registrar_historial(db, reserva.id, "finalizada", datos.usuario, estado_anterior=estado_anterior)
        
        db.commit()
        db.refresh(reserva)
        
        log_event("checkout", datos.usuario, "Check-out realizado", f"reserva_id={reserva_id} pago={datos.pago_monto} metodo={datos.pago_metodo}")
        
        return reserva
        
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        log_event("checkout", "admin", "Error al realizar check-out", f"reserva_id={reserva_id} error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al realizar el check-out"
        )


@router.post("/{reserva_id}/checkin-express")
def checkin_express(
    reserva_id: int = Path(..., gt=0),
    usuario: str = Query("admin"),
    db: Session = Depends(conexion.get_db)
):
    """
    Realiza un check-in rápido sin datos adicionales
    """
    return realizar_checkin(
        reserva_id=reserva_id,
        datos=CheckInRequest(usuario=usuario),
        db=db
    )


@router.post("/{reserva_id}/checkout-express")
def checkout_express(
    reserva_id: int = Path(..., gt=0),
    usuario: str = Query("admin"),
    db: Session = Depends(conexion.get_db)
):
    """
    Realiza un check-out rápido sin datos adicionales
    """
    return realizar_checkout(
        reserva_id=reserva_id,
        datos=CheckOutRequest(usuario=usuario),
        db=db
    )


@router.get("/resumen")
def obtener_resumen_checkin_checkout(
    fecha: Optional[date] = Query(None, description="Fecha para el resumen (default: hoy)"),
    db: Session = Depends(conexion.get_db)
):
    """
    Obtiene un resumen de check-ins y check-outs del día
    """
    try:
        if not fecha:
            fecha = date.today()
        
        # Check-ins pendientes
        checkins_pendientes = db.query(Reserva).filter(
            Reserva.deleted.is_(False),
            Reserva.fecha_checkin == fecha,
            Reserva.estado == "reservada"
        ).count()
        
        # Check-ins completados
        checkins_completados = db.query(HistorialReserva).join(Reserva).filter(
            HistorialReserva.estado == "ocupada",
            func.date(HistorialReserva.fecha) == fecha,
            Reserva.fecha_checkin == fecha
        ).count()
        
        # Check-outs pendientes
        checkouts_pendientes = db.query(Reserva).filter(
            Reserva.deleted.is_(False),
            Reserva.fecha_checkout == fecha,
            Reserva.estado == "ocupada"
        ).count()
        
        # Check-outs completados
        checkouts_completados = db.query(HistorialReserva).join(Reserva).filter(
            HistorialReserva.estado == "finalizada",
            func.date(HistorialReserva.fecha) == fecha,
            Reserva.fecha_checkout == fecha
        ).count()
        
        log_event("checkin-checkout", "admin", "Resumen consultado", f"fecha={fecha}")
        
        return {
            "fecha": fecha,
            "checkin": {
                "pendientes": checkins_pendientes,
                "completados": checkins_completados,
                "total": checkins_pendientes + checkins_completados
            },
            "checkout": {
                "pendientes": checkouts_pendientes,
                "completados": checkouts_completados,
                "total": checkouts_pendientes + checkouts_completados
            }
        }
        
    except SQLAlchemyError as e:
        log_event("checkin-checkout", "admin", "Error al obtener resumen", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener resumen de check-in/check-out"
        )
