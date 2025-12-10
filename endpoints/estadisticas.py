"""
Endpoints de estadísticas y reportes del hotel
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, extract
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from database import conexion
from models.reserva import Reserva, ReservaHabitacion
from models.habitacion import Habitacion
from models.cliente import Cliente
from models.empresa import Empresa
from utils.logging_utils import log_event


router = APIRouter(prefix="/estadisticas", tags=["Estadísticas"])


@router.get("/dashboard")
def obtener_dashboard(db: Session = Depends(conexion.get_db)):
    """
    Obtiene un resumen general del estado del hotel para el dashboard
    """
    try:
        hoy = date.today()
        
        # Habitaciones
        total_habitaciones = db.query(Habitacion).count()
        habitaciones_mantenimiento = db.query(Habitacion).filter(
            Habitacion.estado == "mantenimiento"
        ).count()
        
        # Reservas activas hoy
        reservas_hoy = db.query(Reserva).filter(
            Reserva.deleted.is_(False),
            Reserva.fecha_checkin <= hoy,
            Reserva.fecha_checkout > hoy,
            Reserva.estado.in_(["reservada", "ocupada"])
        ).count()
        
        # Check-ins de hoy
        checkins_hoy = db.query(Reserva).filter(
            Reserva.deleted.is_(False),
            Reserva.fecha_checkin == hoy
        ).count()
        
        # Check-outs de hoy
        checkouts_hoy = db.query(Reserva).filter(
            Reserva.deleted.is_(False),
            Reserva.fecha_checkout == hoy
        ).count()
        
        # Ingresos del mes
        primer_dia_mes = hoy.replace(day=1)
        ingresos_mes = db.query(
            func.coalesce(func.sum(Reserva.total), 0)
        ).filter(
            Reserva.deleted.is_(False),
            Reserva.fecha_checkin >= primer_dia_mes,
            Reserva.estado != "cancelada"
        ).scalar()
        
        # Ocupación actual
        habitaciones_ocupadas = db.query(ReservaHabitacion).join(Reserva).filter(
            Reserva.deleted.is_(False),
            Reserva.fecha_checkin <= hoy,
            Reserva.fecha_checkout > hoy,
            Reserva.estado == "ocupada"
        ).count()
        
        tasa_ocupacion = (habitaciones_ocupadas / total_habitaciones * 100) if total_habitaciones > 0 else 0
        
        log_event("estadisticas", "admin", "Dashboard consultado", "")
        
        return {
            "fecha": hoy,
            "habitaciones": {
                "total": total_habitaciones,
                "ocupadas": habitaciones_ocupadas,
                "disponibles": total_habitaciones - habitaciones_ocupadas - habitaciones_mantenimiento,
                "mantenimiento": habitaciones_mantenimiento,
                "tasa_ocupacion": round(tasa_ocupacion, 2)
            },
            "hoy": {
                "reservas_activas": reservas_hoy,
                "checkins": checkins_hoy,
                "checkouts": checkouts_hoy
            },
            "mes_actual": {
                "ingresos": float(ingresos_mes),
                "moneda": "ARS"
            }
        }
    except SQLAlchemyError as e:
        log_event("estadisticas", "admin", "Error al obtener dashboard", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener estadísticas del dashboard"
        )


@router.get("/ocupacion")
def obtener_estadisticas_ocupacion(
    fecha_inicio: Optional[date] = Query(None),
    fecha_fin: Optional[date] = Query(None),
    db: Session = Depends(conexion.get_db)
):
    """
    Obtiene estadísticas de ocupación por período
    """
    try:
        if not fecha_inicio:
            fecha_inicio = date.today() - timedelta(days=30)
        if not fecha_fin:
            fecha_fin = date.today()
            
        if fecha_fin < fecha_inicio:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La fecha de fin debe ser posterior a la fecha de inicio"
            )
        
        total_habitaciones = db.query(Habitacion).count()
        
        # Calcular ocupación diaria
        ocupacion_diaria = []
        fecha_actual = fecha_inicio
        
        while fecha_actual <= fecha_fin:
            habitaciones_ocupadas = db.query(ReservaHabitacion).join(Reserva).filter(
                Reserva.deleted.is_(False),
                Reserva.fecha_checkin <= fecha_actual,
                Reserva.fecha_checkout > fecha_actual,
                Reserva.estado == "ocupada"
            ).count()
            
            tasa = (habitaciones_ocupadas / total_habitaciones * 100) if total_habitaciones > 0 else 0
            
            ocupacion_diaria.append({
                "fecha": fecha_actual.isoformat(),
                "habitaciones_ocupadas": habitaciones_ocupadas,
                "tasa_ocupacion": round(tasa, 2)
            })
            
            fecha_actual += timedelta(days=1)
        
        # Promedio del período
        promedio_ocupacion = sum(d["tasa_ocupacion"] for d in ocupacion_diaria) / len(ocupacion_diaria) if ocupacion_diaria else 0
        
        log_event("estadisticas", "admin", "Estadísticas de ocupación", f"desde={fecha_inicio} hasta={fecha_fin}")
        
        return {
            "periodo": {
                "inicio": fecha_inicio,
                "fin": fecha_fin
            },
            "promedio_ocupacion": round(promedio_ocupacion, 2),
            "total_habitaciones": total_habitaciones,
            "ocupacion_diaria": ocupacion_diaria
        }
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        log_event("estadisticas", "admin", "Error al obtener ocupación", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener estadísticas de ocupación"
        )


@router.get("/ingresos")
def obtener_estadisticas_ingresos(
    fecha_inicio: Optional[date] = Query(None),
    fecha_fin: Optional[date] = Query(None),
    agrupar_por: str = Query("mes", regex="^(dia|mes|año)$"),
    db: Session = Depends(conexion.get_db)
):
    """
    Obtiene estadísticas de ingresos agrupadas por período
    """
    try:
        if not fecha_inicio:
            fecha_inicio = date.today().replace(day=1, month=1)
        if not fecha_fin:
            fecha_fin = date.today()
            
        if fecha_fin < fecha_inicio:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La fecha de fin debe ser posterior a la fecha de inicio"
            )
        
        query = db.query(
            func.sum(Reserva.total).label("total_ingresos"),
            func.count(Reserva.id).label("cantidad_reservas")
        ).filter(
            Reserva.deleted.is_(False),
            Reserva.fecha_checkin >= fecha_inicio,
            Reserva.fecha_checkin <= fecha_fin,
            Reserva.estado != "cancelada"
        )
        
        if agrupar_por == "dia":
            query = query.add_columns(Reserva.fecha_checkin.label("fecha"))
            query = query.group_by(Reserva.fecha_checkin)
        elif agrupar_por == "mes":
            query = query.add_columns(
                extract('year', Reserva.fecha_checkin).label("año"),
                extract('month', Reserva.fecha_checkin).label("mes")
            )
            query = query.group_by(
                extract('year', Reserva.fecha_checkin),
                extract('month', Reserva.fecha_checkin)
            )
        else:  # año
            query = query.add_columns(extract('year', Reserva.fecha_checkin).label("año"))
            query = query.group_by(extract('year', Reserva.fecha_checkin))
        
        resultados = query.all()
        
        ingresos_agrupados = []
        total_general = Decimal("0")
        
        for resultado in resultados:
            total = Decimal(resultado.total_ingresos or 0)
            total_general += total
            
            item = {
                "ingresos": float(total),
                "cantidad_reservas": resultado.cantidad_reservas
            }
            
            if agrupar_por == "dia":
                item["fecha"] = resultado.fecha.isoformat()
            elif agrupar_por == "mes":
                item["año"] = int(resultado.año)
                item["mes"] = int(resultado.mes)
            else:
                item["año"] = int(resultado.año)
            
            ingresos_agrupados.append(item)
        
        log_event("estadisticas", "admin", "Estadísticas de ingresos", f"desde={fecha_inicio} hasta={fecha_fin}")
        
        return {
            "periodo": {
                "inicio": fecha_inicio,
                "fin": fecha_fin
            },
            "agrupacion": agrupar_por,
            "total_general": float(total_general),
            "ingresos": ingresos_agrupados
        }
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        log_event("estadisticas", "admin", "Error al obtener ingresos", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener estadísticas de ingresos"
        )


@router.get("/top-clientes")
def obtener_top_clientes(
    limite: int = Query(10, ge=1, le=100),
    fecha_inicio: Optional[date] = Query(None),
    fecha_fin: Optional[date] = Query(None),
    db: Session = Depends(conexion.get_db)
):
    """
    Obtiene los clientes con más reservas o mayor gasto
    """
    try:
        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La fecha de fin debe ser posterior a la fecha de inicio"
            )
        
        query = db.query(
            Cliente.id,
            Cliente.nombre,
            Cliente.apellido,
            func.count(Reserva.id).label("cantidad_reservas"),
            func.coalesce(func.sum(Reserva.total), 0).label("total_gastado")
        ).join(Reserva).filter(
            Reserva.deleted.is_(False),
            Cliente.deleted.is_(False),
            Reserva.estado != "cancelada"
        )
        
        if fecha_inicio:
            query = query.filter(Reserva.fecha_checkin >= fecha_inicio)
        if fecha_fin:
            query = query.filter(Reserva.fecha_checkin <= fecha_fin)
        
        query = query.group_by(Cliente.id, Cliente.nombre, Cliente.apellido)
        query = query.order_by(func.sum(Reserva.total).desc())
        query = query.limit(limite)
        
        resultados = query.all()
        
        top_clientes = [
            {
                "cliente_id": r.id,
                "nombre": r.nombre,
                "apellido": r.apellido,
                "cantidad_reservas": r.cantidad_reservas,
                "total_gastado": float(r.total_gastado)
            }
            for r in resultados
        ]
        
        log_event("estadisticas", "admin", "Top clientes consultado", f"limite={limite}")
        
        return {
            "top_clientes": top_clientes,
            "limite": limite,
            "periodo": {
                "inicio": fecha_inicio,
                "fin": fecha_fin
            }
        }
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        log_event("estadisticas", "admin", "Error al obtener top clientes", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener estadísticas de clientes"
        )


@router.get("/habitaciones-populares")
def obtener_habitaciones_populares(
    limite: int = Query(10, ge=1, le=100),
    fecha_inicio: Optional[date] = Query(None),
    fecha_fin: Optional[date] = Query(None),
    db: Session = Depends(conexion.get_db)
):
    """
    Obtiene las habitaciones más reservadas
    """
    try:
        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La fecha de fin debe ser posterior a la fecha de inicio"
            )
        
        query = db.query(
            Habitacion.id,
            Habitacion.numero,
            Habitacion.tipo,
            func.count(ReservaHabitacion.id).label("cantidad_reservas"),
            func.coalesce(func.sum(ReservaHabitacion.precio_noche), 0).label("total_ingresos")
        ).join(ReservaHabitacion).join(Reserva).filter(
            Reserva.deleted.is_(False),
            Reserva.estado != "cancelada"
        )
        
        if fecha_inicio:
            query = query.filter(Reserva.fecha_checkin >= fecha_inicio)
        if fecha_fin:
            query = query.filter(Reserva.fecha_checkin <= fecha_fin)
        
        query = query.group_by(Habitacion.id, Habitacion.numero, Habitacion.tipo)
        query = query.order_by(func.count(ReservaHabitacion.id).desc())
        query = query.limit(limite)
        
        resultados = query.all()
        
        habitaciones_populares = [
            {
                "habitacion_id": r.id,
                "numero": r.numero,
                "tipo": r.tipo,
                "cantidad_reservas": r.cantidad_reservas,
                "total_ingresos": float(r.total_ingresos)
            }
            for r in resultados
        ]
        
        log_event("estadisticas", "admin", "Habitaciones populares consultado", f"limite={limite}")
        
        return {
            "habitaciones_populares": habitaciones_populares,
            "limite": limite,
            "periodo": {
                "inicio": fecha_inicio,
                "fin": fecha_fin
            }
        }
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        log_event("estadisticas", "admin", "Error al obtener habitaciones populares", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener estadísticas de habitaciones"
        )
