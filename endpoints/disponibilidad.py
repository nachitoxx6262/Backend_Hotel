"""
Endpoints para consulta de disponibilidad de habitaciones
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from database import conexion
from models.habitacion import Habitacion
from models.reserva import Reserva, ReservaHabitacion
from schemas.habitacion import HabitacionRead
from utils.logging_utils import log_event


router = APIRouter(prefix="/disponibilidad", tags=["Disponibilidad"])

ACTIVE_RESERVATION_STATES = ("reservada", "ocupada")


@router.get("/habitaciones", response_model=List[HabitacionRead])
def consultar_disponibilidad(
    fecha_checkin: date = Query(..., description="Fecha de entrada"),
    fecha_checkout: date = Query(..., description="Fecha de salida"),
    tipo: Optional[str] = Query(None, description="Tipo de habitación (simple, doble, suite, etc.)"),
    db: Session = Depends(conexion.get_db)
):
    """
    Consulta habitaciones disponibles para un rango de fechas específico
    """
    try:
        # Validaciones
        if fecha_checkout <= fecha_checkin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La fecha de checkout debe ser posterior al checkin"
            )
        
        hoy = date.today()
        if fecha_checkin < hoy:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La fecha de check-in no puede ser en el pasado"
            )
        
        # Obtener habitaciones que NO están en mantenimiento
        query = db.query(Habitacion).filter(
            Habitacion.mantenimiento.is_(False)
        )
        
        # Filtrar por tipo si se especifica
        if tipo:
            query = query.filter(Habitacion.tipo == tipo)
        
        habitaciones_base = query.all()
        
        # Encontrar habitaciones ocupadas en el rango
        habitaciones_ocupadas_ids = db.query(ReservaHabitacion.habitacion_id).join(Reserva).filter(
            Reserva.deleted.is_(False),
            Reserva.estado.in_(ACTIVE_RESERVATION_STATES),
            or_(
                and_(Reserva.fecha_checkin <= fecha_checkin, Reserva.fecha_checkout > fecha_checkin),
                and_(Reserva.fecha_checkin < fecha_checkout, Reserva.fecha_checkout >= fecha_checkout),
                and_(Reserva.fecha_checkin >= fecha_checkin, Reserva.fecha_checkout <= fecha_checkout),
            )
        ).distinct().subquery()
        
        # Filtrar habitaciones disponibles
        habitaciones_disponibles = [
            habitacion for habitacion in habitaciones_base
            if habitacion.id not in [row[0] for row in db.query(habitaciones_ocupadas_ids).all()]
        ]
        
        log_event(
            "disponibilidad",
            "admin",
            "Consulta de disponibilidad",
            f"checkin={fecha_checkin} checkout={fecha_checkout} tipo={tipo} disponibles={len(habitaciones_disponibles)}"
        )
        
        return habitaciones_disponibles
        
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        log_event("disponibilidad", "admin", "Error al consultar disponibilidad", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al consultar disponibilidad de habitaciones"
        )


@router.get("/calendario")
def obtener_calendario_disponibilidad(
    habitacion_id: int = Query(..., gt=0, description="ID de la habitación"),
    fecha_inicio: date = Query(..., description="Fecha de inicio del calendario"),
    dias: int = Query(30, ge=1, le=365, description="Cantidad de días a consultar"),
    db: Session = Depends(conexion.get_db)
):
    """
    Obtiene un calendario de disponibilidad para una habitación específica
    """
    try:
        # Verificar que la habitación existe
        habitacion = db.query(Habitacion).filter(Habitacion.id == habitacion_id).first()
        if not habitacion:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Habitación no encontrada"
            )
        
        fecha_fin = fecha_inicio + timedelta(days=dias - 1)
        
        # Obtener todas las reservas de la habitación en el rango
        reservas = db.query(Reserva).join(ReservaHabitacion).filter(
            ReservaHabitacion.habitacion_id == habitacion_id,
            Reserva.deleted.is_(False),
            Reserva.estado.in_(ACTIVE_RESERVATION_STATES),
            Reserva.fecha_checkin <= fecha_fin,
            Reserva.fecha_checkout >= fecha_inicio
        ).all()
        
        # Construir calendario
        calendario = []
        fecha_actual = fecha_inicio
        
        while fecha_actual <= fecha_fin:
            # Verificar si hay alguna reserva activa para este día
            reserva_activa = None
            for reserva in reservas:
                if reserva.fecha_checkin <= fecha_actual < reserva.fecha_checkout:
                    reserva_activa = reserva
                    break
            
            estado = "disponible"
            if habitacion.estado == "mantenimiento":
                estado = "mantenimiento"
            elif reserva_activa:
                estado = "ocupado" if reserva_activa.estado == "ocupada" else "reservado"
            
            calendario.append({
                "fecha": fecha_actual.isoformat(),
                "estado": estado,
                "reserva_id": reserva_activa.id if reserva_activa else None
            })
            
            fecha_actual += timedelta(days=1)
        
        log_event(
            "disponibilidad",
            "admin",
            "Calendario de disponibilidad",
            f"habitacion_id={habitacion_id} desde={fecha_inicio} dias={dias}"
        )
        
        return {
            "habitacion": {
                "id": habitacion.id,
                "numero": habitacion.numero,
                "tipo": habitacion.tipo
            },
            "periodo": {
                "inicio": fecha_inicio,
                "fin": fecha_fin,
                "dias": dias
            },
            "calendario": calendario
        }
        
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        log_event("disponibilidad", "admin", "Error al obtener calendario", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener calendario de disponibilidad"
        )


@router.get("/resumen")
def obtener_resumen_disponibilidad(
    fecha: date = Query(None, description="Fecha a consultar (default: hoy)"),
    db: Session = Depends(conexion.get_db)
):
    """
    Obtiene un resumen de disponibilidad para una fecha específica
    """
    try:
        if not fecha:
            fecha = date.today()
        
        # Total de habitaciones
        total_habitaciones = db.query(Habitacion).count()
        
        # Habitaciones en mantenimiento
        en_mantenimiento = db.query(Habitacion).filter(
            Habitacion.estado == "mantenimiento"
        ).count()
        
        # Habitaciones ocupadas/reservadas
        habitaciones_ocupadas = db.query(ReservaHabitacion.habitacion_id).join(Reserva).filter(
            Reserva.deleted.is_(False),
            Reserva.fecha_checkin <= fecha,
            Reserva.fecha_checkout > fecha,
            Reserva.estado.in_(ACTIVE_RESERVATION_STATES)
        ).distinct().count()
        
        # Calcular disponibles
        disponibles = total_habitaciones - habitaciones_ocupadas - en_mantenimiento
        
        # Tasa de ocupación
        tasa_ocupacion = (habitaciones_ocupadas / total_habitaciones * 100) if total_habitaciones > 0 else 0
        
        # Resumen por tipo de habitación
        tipos = db.query(Habitacion.tipo, func.count(Habitacion.id)).group_by(Habitacion.tipo).all()
        
        resumen_por_tipo = []
        for tipo, cantidad_tipo in tipos:
            ocupadas_tipo = db.query(ReservaHabitacion.habitacion_id).join(Reserva).join(
                Habitacion, ReservaHabitacion.habitacion_id == Habitacion.id
            ).filter(
                Habitacion.tipo == tipo,
                Reserva.deleted.is_(False),
                Reserva.fecha_checkin <= fecha,
                Reserva.fecha_checkout > fecha,
                Reserva.estado.in_(ACTIVE_RESERVATION_STATES)
            ).distinct().count()
            
            mantenimiento_tipo = db.query(Habitacion).filter(
                Habitacion.tipo == tipo,
                Habitacion.estado == "mantenimiento"
            ).count()
            
            disponibles_tipo = cantidad_tipo - ocupadas_tipo - mantenimiento_tipo
            
            resumen_por_tipo.append({
                "tipo": tipo,
                "total": cantidad_tipo,
                "ocupadas": ocupadas_tipo,
                "disponibles": disponibles_tipo,
                "mantenimiento": mantenimiento_tipo
            })
        
        log_event("disponibilidad", "admin", "Resumen de disponibilidad", f"fecha={fecha}")
        
        return {
            "fecha": fecha,
            "resumen_general": {
                "total_habitaciones": total_habitaciones,
                "ocupadas": habitaciones_ocupadas,
                "disponibles": disponibles,
                "en_mantenimiento": en_mantenimiento,
                "tasa_ocupacion": round(tasa_ocupacion, 2)
            },
            "por_tipo": resumen_por_tipo
        }
        
    except SQLAlchemyError as e:
        log_event("disponibilidad", "admin", "Error al obtener resumen", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener resumen de disponibilidad"
        )
