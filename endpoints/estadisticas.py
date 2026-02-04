"""
Estadísticas y Dashboard
Datos para dashboards administrativos
"""
from datetime import datetime, timedelta, date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from decimal import Decimal

from database.conexion import get_db
from models.core import (
    Reservation, Stay, Room, RoomType, Cliente, StayCharge,
    StayPayment, AuditEvent, ClienteCorporativo, StayRoomOccupancy
)
from models.usuario import Usuario
from utils.dependencies import get_current_user

router = APIRouter(prefix="/estadisticas", tags=["Estadísticas"])


# --- Schemas ---

class PagoDeudorRequest(BaseModel):
    """Solicitud para registrar pago de deudor"""
    deudor_id: int
    deudor_tipo: str  # "Cliente" o "Empresa"
    monto: float
    metodo: str = "efectivo"
    referencia: str = ""
    notas: str = ""


class OcupacionDia(dict):
    """Ocupación para un día específico"""
    fecha: date
    ocupadas: int
    total: int
    porcentaje: float


class EstadisticasHoy(dict):
    """Estadísticas del día actual"""
    pass


class IngresosPorDia(dict):
    """Ingresos diarios"""
    fecha: date
    monto: float
    pagos: float
    saldo_pendiente: float


class TasaOcupacionPeriodo(dict):
    """Tasa de ocupación por período"""
    periodo: str
    ocupacion_promedio: float
    dias_datos: int


# --- Endpoints ---

@router.get("/hoy")
def get_estadisticas_hoy(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Estadísticas del día actual"""
    hoy = datetime.now().date()
    tenant_id = current_user.empresa_usuario_id

    # Total habitaciones
    total_rooms = db.query(func.count(Room.id)).filter(
        Room.empresa_usuario_id == tenant_id
    ).scalar() or 0

    # Habitaciones ocupadas hoy
    ocupadas = db.query(func.count(Room.id.distinct())).join(
        StayRoomOccupancy, StayRoomOccupancy.room_id == Room.id, isouter=True
    ).join(
        Stay, Stay.id == StayRoomOccupancy.stay_id, isouter=True
    ).filter(
        Room.empresa_usuario_id == tenant_id,
        Stay.estado.in_(["activa", "llegada"]),
        func.date(Stay.checkin_real) <= hoy,
        (Stay.checkout_real.is_(None) | (func.date(Stay.checkout_real) >= hoy))
    ).scalar() or 0

    # Check-ins hoy
    checkins_hoy = db.query(func.count(Stay.id)).filter(
        Stay.empresa_usuario_id == tenant_id,
        func.date(Stay.checkin_real) == hoy
    ).scalar() or 0

    # Check-outs hoy
    checkouts_hoy = db.query(func.count(Stay.id)).filter(
        Stay.empresa_usuario_id == tenant_id,
        func.date(Stay.checkout_real) == hoy
    ).scalar() or 0

    # Ingresos hoy
    ingresos_hoy = db.query(
        func.coalesce(func.sum(StayCharge.monto_total), 0)
    ).join(Stay).filter(
        Stay.empresa_usuario_id == tenant_id,
        func.date(StayCharge.created_at) == hoy
    ).scalar() or 0

    # Pagos hoy
    pagos_hoy = db.query(
        func.coalesce(func.sum(StayPayment.monto), 0)
    ).join(Stay).filter(
        Stay.empresa_usuario_id == tenant_id,
        func.date(StayPayment.timestamp) == hoy,
        StayPayment.es_reverso == False
    ).scalar() or 0

    # Nuevos clientes
    nuevos_clientes = db.query(func.count(Cliente.id)).filter(
        Cliente.empresa_usuario_id == tenant_id,
        func.date(Cliente.created_at) == hoy
    ).scalar() or 0

    porcentaje_ocupacion = round((ocupadas / total_rooms * 100) if total_rooms > 0 else 0, 2)

    return {
        "fecha": hoy.isoformat(),
        "total_habitaciones": total_rooms,
        "habitaciones_ocupadas": ocupadas,
        "porcentaje_ocupacion": porcentaje_ocupacion,
        "checkins_hoy": checkins_hoy,
        "checkouts_hoy": checkouts_hoy,
        "ingresos_hoy": float(ingresos_hoy),
        "pagos_hoy": float(pagos_hoy),
        "nuevos_clientes": nuevos_clientes,
    }


@router.get("/ocupacion/ultimos-dias")
def get_ocupacion_ultimos_dias(
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Ocupación por día para los últimos N días"""
    tenant_id = current_user.empresa_usuario_id
    total_rooms = db.query(func.count(Room.id)).filter(
        Room.empresa_usuario_id == tenant_id
    ).scalar() or 1

    datos = []
    for i in range(dias, 0, -1):
        fecha_check = (datetime.now() - timedelta(days=i)).date()

        ocupadas = db.query(func.count(Room.id.distinct())).join(
            StayRoomOccupancy, StayRoomOccupancy.room_id == Room.id, isouter=True
        ).join(
            Stay, Stay.id == StayRoomOccupancy.stay_id, isouter=True
        ).filter(
            Room.empresa_usuario_id == tenant_id,
            Stay.estado.in_(["activa", "llegada", "cerrada"]),
            func.date(Stay.checkin_real) <= fecha_check,
            (Stay.checkout_real.is_(None) | (func.date(Stay.checkout_real) >= fecha_check))
        ).scalar() or 0

        porcentaje = round((ocupadas / total_rooms * 100) if total_rooms > 0 else 0, 2)

        datos.append({
            "fecha": fecha_check.isoformat(),
            "ocupadas": ocupadas,
            "total": total_rooms,
            "porcentaje": porcentaje,
        })

    return {"datos": datos}


@router.get("/ingresos/ultimos-dias")
def get_ingresos_ultimos_dias(
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Ingresos diarios para los últimos N días"""
    tenant_id = current_user.empresa_usuario_id
    datos = []
    for i in range(dias, 0, -1):
        fecha_check = (datetime.now() - timedelta(days=i)).date()

        ingresos = db.query(
            func.coalesce(func.sum(StayCharge.monto_total), 0)
        ).join(Stay).filter(
            Stay.empresa_usuario_id == tenant_id,
            func.date(StayCharge.created_at) == fecha_check
        ).scalar() or 0

        pagos = db.query(
            func.coalesce(func.sum(StayPayment.monto), 0)
        ).join(Stay).filter(
            Stay.empresa_usuario_id == tenant_id,
            func.date(StayPayment.timestamp) == fecha_check,
            StayPayment.es_reverso == False
        ).scalar() or 0

        saldo_pendiente = float(ingresos) - float(pagos)

        datos.append({
            "fecha": fecha_check.isoformat(),
            "ingresos": float(ingresos),
            "pagos": float(pagos),
            "saldo_pendiente": saldo_pendiente,
        })

    return {"datos": datos}


@router.get("/resumen-mes-actual")
def get_resumen_mes_actual(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Resumen completo del mes actual"""
    tenant_id = current_user.empresa_usuario_id
    hoy = datetime.now()
    primer_dia_mes = hoy.replace(day=1).date()
    ultimo_dia_mes = (hoy.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    # Total ingresos mes
    total_ingresos_mes = db.query(
        func.coalesce(func.sum(StayCharge.monto_total), 0)
    ).join(Stay).filter(
        Stay.empresa_usuario_id == tenant_id,
        func.date(StayCharge.created_at) >= primer_dia_mes,
        func.date(StayCharge.created_at) <= ultimo_dia_mes
    ).scalar() or 0

    # Total pagado mes
    total_pagado_mes = db.query(
        func.coalesce(func.sum(StayPayment.monto), 0)
    ).join(Stay).filter(
        Stay.empresa_usuario_id == tenant_id,
        func.date(StayPayment.timestamp) >= primer_dia_mes,
        func.date(StayPayment.timestamp) <= ultimo_dia_mes,
        StayPayment.es_reverso == False
    ).scalar() or 0

    # Reservaciones mes
    reservaciones_mes = db.query(func.count(Reservation.id)).filter(
        Reservation.empresa_usuario_id == tenant_id,
        func.date(Reservation.created_at) >= primer_dia_mes,
        func.date(Reservation.created_at) <= ultimo_dia_mes
    ).scalar() or 0

    # Check-ins mes
    checkins_mes = db.query(func.count(Stay.id)).filter(
        Stay.empresa_usuario_id == tenant_id,
        func.date(Stay.checkin_real) >= primer_dia_mes,
        func.date(Stay.checkin_real) <= ultimo_dia_mes
    ).scalar() or 0

    # ADR (Average Daily Rate)
    noches_ocupadas = db.query(
        func.coalesce(func.sum(StayCharge.cantidad), 0)
    ).join(Stay).filter(
        Stay.empresa_usuario_id == tenant_id,
        StayCharge.tipo == "room_revenue",
        func.date(StayCharge.created_at) >= primer_dia_mes,
        func.date(StayCharge.created_at) <= ultimo_dia_mes
    ).scalar() or 1

    adr = float(total_ingresos_mes) / float(noches_ocupadas) if noches_ocupadas > 0 else 0

    # Ocupación promedio mes
    total_rooms = db.query(func.count(Room.id)).filter(
        Room.empresa_usuario_id == tenant_id
    ).scalar() or 1
    dias_mes = (ultimo_dia_mes.date() - primer_dia_mes).days + 1
    capacidad_mes = total_rooms * dias_mes
    
    total_noches_ocupadas = db.query(
        func.coalesce(func.sum(StayCharge.cantidad), 0)
    ).join(Stay).filter(
        Stay.empresa_usuario_id == tenant_id,
        StayCharge.tipo == "room_revenue",
        func.date(StayCharge.created_at) >= primer_dia_mes,
        func.date(StayCharge.created_at) <= ultimo_dia_mes
    ).scalar() or 0

    ocupacion_promedio = round((float(total_noches_ocupadas) / capacidad_mes * 100) if capacidad_mes > 0 else 0, 2)

    saldo_pendiente_mes = float(total_ingresos_mes) - float(total_pagado_mes)

    return {
        "periodo": f"{hoy.year}-{hoy.month:02d}",
        "total_ingresos": float(total_ingresos_mes),
        "total_pagado": float(total_pagado_mes),
        "saldo_pendiente": saldo_pendiente_mes,
        "reservaciones": reservaciones_mes,
        "checkins": checkins_mes,
        "adr": round(adr, 2),
        "ocupacion_promedio": ocupacion_promedio,
    }


@router.get("/top-empresas")
def get_top_empresas(
    limite: int = 5,
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Top empresas por ingresos en los últimos N días"""
    tenant_id = current_user.empresa_usuario_id
    fecha_desde = (datetime.now() - timedelta(days=dias)).date()

    empresas = db.query(
        ClienteCorporativo.id,
        ClienteCorporativo.nombre,
        func.coalesce(func.sum(StayCharge.monto_total), 0).label("total_ingresos"),
        func.coalesce(func.sum(StayPayment.monto), 0).label("total_pagado"),
    ).filter(
        ClienteCorporativo.empresa_usuario_id == tenant_id
    ).outerjoin(
        Reservation, Reservation.empresa_id == ClienteCorporativo.id
    ).outerjoin(
        Stay, Stay.reservation_id == Reservation.id
    ).outerjoin(
        StayCharge, StayCharge.stay_id == Stay.id
    ).outerjoin(
        StayPayment, (StayPayment.stay_id == Stay.id) & (StayPayment.es_reverso == False)
    ).filter(
        func.date(StayCharge.created_at) >= fecha_desde
    ).group_by(
        ClienteCorporativo.id, ClienteCorporativo.nombre
    ).order_by(
        func.sum(StayCharge.monto_total).desc()
    ).limit(limite).all()

    return {
        "empresas": [
            {
                "id": emp.id,
                "nombre": emp.nombre,
                "ingresos": float(emp.total_ingresos) if emp.total_ingresos else 0,
                "pagado": float(emp.total_pagado) if emp.total_pagado else 0,
                "saldo_pendiente": float(emp.total_ingresos or 0) - float(emp.total_pagado or 0),
            }
            for emp in empresas
        ]
    }


@router.get("/actividad-reciente")
def get_actividad_reciente(
    limite: int = 10,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Actividad reciente del sistema"""
    tenant_id = current_user.empresa_usuario_id
    
    # Obtener usuarios de la misma empresa para filtrar eventos
    usuarios_empresa = db.query(Usuario.username).filter(
        Usuario.empresa_usuario_id == tenant_id
    ).all()
    usernames = [u.username for u in usuarios_empresa]
    
    eventos = db.query(AuditEvent).filter(
        AuditEvent.usuario.in_(usernames)
    ).order_by(
        AuditEvent.timestamp.desc()
    ).limit(limite).all()

    return {
        "eventos": [
            {
                "timestamp": evt.timestamp.isoformat(),
                "usuario": evt.usuario,
                "accion": evt.action,
                "entidad": evt.entity_type,
                "descripcion": evt.descripcion,
            }
            for evt in eventos
        ]
    }


@router.get("/prediccion-ocupacion")
def get_prediccion_ocupacion(
    dias_futuros: int = 14,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Predicción de ocupación para los próximos N días basada en reservaciones"""
    tenant_id = current_user.empresa_usuario_id
    total_rooms = db.query(func.count(Room.id)).filter(
        Room.empresa_usuario_id == tenant_id
    ).scalar() or 1

    predicciones = []
    for i in range(1, dias_futuros + 1):
        fecha_check = (datetime.now() + timedelta(days=i)).date()

        # Contar reservaciones confirmadas para esa fecha
        reservaciones = db.query(func.count(Reservation.id)).filter(
            Reservation.empresa_usuario_id == tenant_id,
            Reservation.fecha_checkin <= fecha_check,
            Reservation.fecha_checkout > fecha_check,
            Reservation.estado.in_(["confirmada", "ocupada"])
        ).scalar() or 0

        porcentaje = round((reservaciones / total_rooms * 100) if total_rooms > 0 else 0, 2)

        predicciones.append({
            "fecha": fecha_check.isoformat(),
            "reservaciones_esperadas": reservaciones,
            "porcentaje_ocupacion_esperado": porcentaje,
        })

    return {"predicciones": predicciones}


@router.get("/tipos-habitacion-performance")
def get_tipos_habitacion_performance(
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Performance por tipo de habitación"""
    tenant_id = current_user.empresa_usuario_id
    fecha_desde = (datetime.now() - timedelta(days=dias)).date()

    tipos = db.query(
        RoomType.id,
        RoomType.nombre,
        func.count(Room.id).label("cantidad_habitaciones"),
        func.coalesce(func.sum(StayCharge.cantidad), 0).label("noches_ocupadas"),
        func.coalesce(func.sum(StayCharge.monto_total), 0).label("ingresos"),
    ).filter(
        RoomType.empresa_usuario_id == tenant_id
    ).outerjoin(
        Room, Room.room_type_id == RoomType.id
    ).outerjoin(
        StayRoomOccupancy, StayRoomOccupancy.room_id == Room.id
    ).outerjoin(
        Stay, Stay.id == StayRoomOccupancy.stay_id
    ).outerjoin(
        StayCharge, (StayCharge.stay_id == Stay.id) & (StayCharge.tipo == "room_revenue")
    ).filter(
        func.date(StayCharge.created_at) >= fecha_desde
    ).group_by(
        RoomType.id, RoomType.nombre
    ).all()

    return {
        "tipos": [
            {
                "tipo_id": t.id,
                "nombre": t.nombre,
                "cantidad": t.cantidad_habitaciones or 0,
                "noches_ocupadas": float(t.noches_ocupadas) if t.noches_ocupadas else 0,
                "ingresos": float(t.ingresos) if t.ingresos else 0,
            }
            for t in tipos
        ]
    }


@router.get("/deudores")
def get_deudores(
    dias: int = None,  # Si es None, todos los deudores históricos
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Obtener lista de clientes/empresas con saldo pendiente"""
    tenant_id = current_user.empresa_usuario_id
    
    deudores = []
    
    # Deudores Personas (Clientes)
    clientes_deudores = db.query(
        Cliente.id,
        func.concat(Cliente.nombre, ' ', Cliente.apellido).label("nombre"),
        func.coalesce(func.sum(StayCharge.monto_total), 0).label("total_cargos"),
        func.coalesce(func.sum(StayPayment.monto), 0).label("total_pagado"),
    ).filter(
        Cliente.empresa_usuario_id == tenant_id
    ).outerjoin(
        Reservation, Reservation.cliente_id == Cliente.id
    ).outerjoin(
        Stay, Stay.reservation_id == Reservation.id
    ).outerjoin(
        StayCharge, StayCharge.stay_id == Stay.id
    ).outerjoin(
        StayPayment, (StayPayment.stay_id == Stay.id) & (StayPayment.es_reverso == False)
    )
    
    if dias:
        fecha_desde = (datetime.now() - timedelta(days=dias)).date()
        clientes_deudores = clientes_deudores.filter(
            func.date(StayCharge.created_at) >= fecha_desde
        )
    
    clientes_deudores = clientes_deudores.group_by(
        Cliente.id, Cliente.nombre, Cliente.apellido
    ).having(
        func.coalesce(func.sum(StayCharge.monto_total), 0) > 
        func.coalesce(func.sum(StayPayment.monto), 0)
    ).order_by(
        (func.coalesce(func.sum(StayCharge.monto_total), 0) - 
         func.coalesce(func.sum(StayPayment.monto), 0)).desc()
    ).all()
    
    for cliente in clientes_deudores:
        saldo = float(cliente.total_cargos or 0) - float(cliente.total_pagado or 0)
        if saldo > 0:
            deudores.append({
                "id": cliente.id,
                "nombre": cliente.nombre,
                "tipo": "Cliente",
                "total_cargos": float(cliente.total_cargos or 0),
                "total_pagado": float(cliente.total_pagado or 0),
                "saldo_pendiente": saldo,
            })
    
    # Deudores Empresas
    empresas_deudores = db.query(
        ClienteCorporativo.id,
        ClienteCorporativo.nombre,
        func.coalesce(func.sum(StayCharge.monto_total), 0).label("total_cargos"),
        func.coalesce(func.sum(StayPayment.monto), 0).label("total_pagado"),
    ).filter(
        ClienteCorporativo.empresa_usuario_id == tenant_id
    ).outerjoin(
        Reservation, Reservation.empresa_id == ClienteCorporativo.id
    ).outerjoin(
        Stay, Stay.reservation_id == Reservation.id
    ).outerjoin(
        StayCharge, StayCharge.stay_id == Stay.id
    ).outerjoin(
        StayPayment, (StayPayment.stay_id == Stay.id) & (StayPayment.es_reverso == False)
    )
    
    if dias:
        fecha_desde = (datetime.now() - timedelta(days=dias)).date()
        empresas_deudores = empresas_deudores.filter(
            func.date(StayCharge.created_at) >= fecha_desde
        )
    
    empresas_deudores = empresas_deudores.group_by(
        ClienteCorporativo.id, ClienteCorporativo.nombre
    ).having(
        func.coalesce(func.sum(StayCharge.monto_total), 0) > 
        func.coalesce(func.sum(StayPayment.monto), 0)
    ).order_by(
        (func.coalesce(func.sum(StayCharge.monto_total), 0) - 
         func.coalesce(func.sum(StayPayment.monto), 0)).desc()
    ).all()
    
    for empresa in empresas_deudores:
        saldo = float(empresa.total_cargos or 0) - float(empresa.total_pagado or 0)
        if saldo > 0:
            deudores.append({
                "id": empresa.id,
                "nombre": empresa.nombre,
                "tipo": "Empresa",
                "total_cargos": float(empresa.total_cargos or 0),
                "total_pagado": float(empresa.total_pagado or 0),
                "saldo_pendiente": saldo,
            })
    
    # Ordenar todos por saldo pendiente descendente
    deudores.sort(key=lambda x: x['saldo_pendiente'], reverse=True)
    
    total_deuda = sum(d['saldo_pendiente'] for d in deudores)
    total_cargos = sum(d['total_cargos'] for d in deudores)
    total_pagado = sum(d['total_pagado'] for d in deudores)
    
    return {
        "deudores": deudores,
        "resumen": {
            "cantidad_deudores": len(deudores),
            "total_cargos": total_cargos,
            "total_pagado": total_pagado,
            "total_deuda": total_deuda,
        }
    }

@router.post("/deudores/registrar-pago")
def registrar_pago_deudor(
    data: PagoDeudorRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Registrar pago para un cliente o empresa deudor"""
    
    # Buscar la estadía más reciente sin cerrar del deudor
    if data.deudor_tipo == "Cliente":
        stay = db.query(Stay).join(
            Reservation, Reservation.id == Stay.reservation_id
        ).filter(
            Reservation.cliente_id == data.deudor_id,
            Stay.estado.in_(["activa", "llegada"])
        ).order_by(Stay.id.desc()).first()
    else:  # Empresa
        stay = db.query(Stay).join(
            Reservation, Reservation.id == Stay.reservation_id
        ).filter(
            Reservation.empresa_id == data.deudor_id,
            Stay.estado.in_(["activa", "llegada"])
        ).order_by(Stay.id.desc()).first()
    
    if not stay:
        # Si no hay estadía activa, buscar la última cerrada
        if data.deudor_tipo == "Cliente":
            stay = db.query(Stay).join(
                Reservation, Reservation.id == Stay.reservation_id
            ).filter(
                Reservation.cliente_id == data.deudor_id
            ).order_by(Stay.id.desc()).first()
        else:  # Empresa
            stay = db.query(Stay).join(
                Reservation, Reservation.id == Stay.reservation_id
            ).filter(
                Reservation.empresa_id == data.deudor_id
            ).order_by(Stay.id.desc()).first()
    
    if not stay:
        raise HTTPException(404, f"No se encontraron estadías para este {data.deudor_tipo}")
    
    # Registrar el pago
    payment = StayPayment(
        stay_id=stay.id,
        monto=Decimal(str(data.monto)),
        metodo=data.metodo,
        referencia=data.referencia,
        usuario=current_user.get("username", "sistema") if isinstance(current_user, dict) else "sistema",
        es_reverso=False
    )
    db.add(payment)
    
    # Auditoría
    audit = AuditEvent(
        entity_type="stay",
        entity_id=stay.id,
        action="PAYMENT_FROM_DEUDORES",
        usuario=current_user.get("username", "sistema") if isinstance(current_user, dict) else "sistema",
        descripcion=f"Pago {data.metodo} ${data.monto} - {data.deudor_tipo}:{data.deudor_id}",
        payload={
            "ref": data.referencia,
            "notas": data.notas,
            "deudor_tipo": data.deudor_tipo,
            "deudor_id": data.deudor_id
        }
    )
    db.add(audit)
    
    db.commit()
    
    return {
        "id": payment.id,
        "stay_id": stay.id,
        "monto": float(payment.monto),
        "metodo": payment.metodo,
        "referencia": payment.referencia,
        "timestamp": payment.timestamp.isoformat()
    }