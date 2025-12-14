"""
Services para operaciones de Check-in/Check-out
Contiene lógica de negocio para:
- Movimientos de habitación
- Extensión de estadía
- Procesamiento de pagos
- Check-out y cierre de reserva
- Reverso de operaciones (admin)
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple, List
from sqlalchemy.orm import Session
from sqlalchemy import and_

from models.reserva import Reserva
from models.habitacion import Habitacion
from models.reserva_eventos import (
    ReservaHuesped, ReservaEvento, ReservaPago, ReservaRoomMove,
    EstadoReserva, TipoEvento, MetodoPago
)
from utils.logging_utils import log_event


class RoomMoveService:
    """Servicio para gestionar movimientos de huéspedes entre habitaciones"""
    
    @staticmethod
    def validar_room_move(
        db: Session,
        reserva_id: int,
        habitacion_anterior_id: int,
        habitacion_nueva_id: int,
        huesped_id: int
    ) -> Tuple[bool, Optional[str]]:
        """
        Valida si un movimiento de habitación es permitido
        
        Returns:
            (es_valido, mensaje_error)
        """
        # Validar que reserva existe y está ocupada
        reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
        if not reserva:
            return False, f"Reserva {reserva_id} no encontrada"
        
        if reserva.estado_operacional != EstadoReserva.OCUPADA:
            return False, f"Reserva no está en estado OCUPADA (está: {reserva.estado_operacional})"
        
        # Validar que huesped existe en reserva
        huesped = db.query(ReservaHuesped).filter(
            and_(
                ReservaHuesped.reserva_id == reserva_id,
                ReservaHuesped.cliente_id == huesped_id
            )
        ).first()
        if not huesped:
            return False, f"Huésped {huesped_id} no está en reserva {reserva_id}"
        
        # Validar que habitaciones existen
        hab_anterior = db.query(Habitacion).filter(Habitacion.id == habitacion_anterior_id).first()
        hab_nueva = db.query(Habitacion).filter(Habitacion.id == habitacion_nueva_id).first()
        
        if not hab_anterior:
            return False, f"Habitación anterior {habitacion_anterior_id} no existe"
        if not hab_nueva:
            return False, f"Habitación nueva {habitacion_nueva_id} no existe"
        
        # Validar que nueva habitación no está ocupada
        huesped_en_nueva = db.query(ReservaHuesped).filter(
            ReservaHuesped.habitacion_id == habitacion_nueva_id
        ).first()
        if huesped_en_nueva:
            return False, f"Habitación {habitacion_nueva_id} ya está ocupada"
        
        return True, None
    
    @staticmethod
    def mover_huesped(
        db: Session,
        reserva_id: int,
        huesped_id: int,
        habitacion_anterior_id: int,
        habitacion_nueva_id: int,
        usuario: str,
        razon: str,
        notas: Optional[str] = None
    ) -> Tuple[bool, str, Optional[ReservaRoomMove]]:
        """
        Ejecuta el movimiento de huésped a nueva habitación
        
        Returns:
            (exitoso, mensaje, room_move_object)
        """
        try:
            # Validar
            es_valido, error = RoomMoveService.validar_room_move(
                db, reserva_id, habitacion_anterior_id, habitacion_nueva_id, huesped_id
            )
            if not es_valido:
                return False, error, None
            
            # Actualizar ReservaHuesped
            huesped = db.query(ReservaHuesped).filter(
                and_(
                    ReservaHuesped.reserva_id == reserva_id,
                    ReservaHuesped.cliente_id == huesped_id
                )
            ).first()
            huesped.habitacion_id = habitacion_nueva_id
            
            # Crear registro de room move
            room_move = ReservaRoomMove(
                reserva_id=reserva_id,
                habitacion_anterior_id=habitacion_anterior_id,
                habitacion_nueva_id=habitacion_nueva_id,
                razon=razon[:200],  # Limitar a 200 caracteres
                usuario=usuario,
                timestamp=datetime.utcnow()
            )
            db.add(room_move)
            db.flush()
            
            # Crear evento de auditoría
            evento = ReservaEvento(
                reserva_id=reserva_id,
                tipo_evento=TipoEvento.ROOM_MOVE,
                usuario=usuario,
                timestamp=datetime.utcnow(),
                payload={
                    "huesped_id": huesped_id,
                    "habitacion_anterior": habitacion_anterior_id,
                    "habitacion_nueva": habitacion_nueva_id,
                    "razon": razon,
                    "notas": notas
                },
                descripcion=f"Huésped {huesped_id} movido de hab {habitacion_anterior_id} a {habitacion_nueva_id}"
            )
            db.add(evento)
            db.commit()
            
            log_event("room_move", usuario, "Mover huésped", f"reserva_id={reserva_id}, huesped_id={huesped_id}")
            return True, "Huésped movido exitosamente", room_move
            
        except Exception as e:
            db.rollback()
            error_msg = f"Error moviendo huésped: {str(e)}"
            log_event("room_move", usuario, "Error", error_msg)
            return False, error_msg, None


class ExtendStayService:
    """Servicio para extender la estadía de una reserva"""
    
    @staticmethod
    def validar_extension(
        db: Session,
        reserva_id: int,
        fecha_checkout_nueva: datetime
    ) -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Valida si se puede extender la estadía
        
        Returns:
            (es_valido, mensaje_error, info_calculos)
        """
        reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
        if not reserva:
            return False, f"Reserva {reserva_id} no encontrada", None
        
        if reserva.estado_operacional != EstadoReserva.OCUPADA:
            return False, f"Reserva no está ocupada", None
        
        if fecha_checkout_nueva <= reserva.fecha_checkout:
            return False, "Nueva fecha debe ser posterior a fecha checkout actual", None
        
        # Calcular diferencia
        dias_adicionales = (fecha_checkout_nueva - reserva.fecha_checkout).days
        if dias_adicionales < 1:
            return False, "Debe extender mínimo 1 día", None
        
        # Calcular costo adicional (asumiendo tarifa_noche en Reserva o Habitacion)
        tarifa_noche = getattr(reserva, 'tarifa_noche', 0) or 0
        if tarifa_noche == 0:
            # Intenta obtener de habitación
            hab = db.query(Habitacion).filter(Habitacion.id == reserva.habitacion_id).first()
            if hab:
                tarifa_noche = getattr(hab, 'tarifa_noche', 100) or 100
            else:
                tarifa_noche = 100
        
        costo_adicional = dias_adicionales * tarifa_noche
        
        return True, None, {
            "dias_adicionales": dias_adicionales,
            "tarifa_noche": tarifa_noche,
            "costo_adicional": costo_adicional,
            "fecha_checkout_anterior": reserva.fecha_checkout,
            "fecha_checkout_nueva": fecha_checkout_nueva
        }
    
    @staticmethod
    def extender_estadia(
        db: Session,
        reserva_id: int,
        fecha_checkout_nueva: datetime,
        usuario: str,
        razon: str,
        notas: Optional[str] = None
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Ejecuta la extensión de estadía
        
        Returns:
            (exitoso, mensaje, resultado_dict)
        """
        try:
            es_valido, error, calculos = ExtendStayService.validar_extension(
                db, reserva_id, fecha_checkout_nueva
            )
            if not es_valido:
                return False, error, None
            
            reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
            
            # Guardar fecha anterior para auditoría
            fecha_anterior = reserva.fecha_checkout
            
            # Actualizar reserva
            reserva.fecha_checkout = fecha_checkout_nueva
            reserva.actualizado_por = usuario
            
            # Crear evento de auditoría
            evento = ReservaEvento(
                reserva_id=reserva_id,
                tipo_evento=TipoEvento.EXTEND_STAY,
                usuario=usuario,
                timestamp=datetime.utcnow(),
                payload={
                    "fecha_anterior": fecha_anterior.isoformat(),
                    "fecha_nueva": fecha_checkout_nueva.isoformat(),
                    "dias_adicionales": calculos["dias_adicionales"],
                    "costo_adicional": calculos["costo_adicional"],
                    "razon": razon,
                    "notas": notas
                },
                cambios_anteriores={
                    "fecha_checkout": fecha_anterior.isoformat()
                },
                descripcion=f"Estadía extendida por {calculos['dias_adicionales']} días"
            )
            db.add(evento)
            db.commit()
            
            log_event("extend_stay", usuario, "Extender estadía", f"reserva_id={reserva_id}, dias_adicionales={calculos['dias_adicionales']}")
            
            return True, "Estadía extendida exitosamente", {
                "reserva_id": reserva_id,
                "evento_id": evento.id,
                "fecha_checkout_nueva": fecha_checkout_nueva.isoformat(),
                "dias_adicionales": calculos["dias_adicionales"],
                "costo_adicional": calculos["costo_adicional"],
                "timestamp": evento.timestamp.isoformat()
            }
            
        except Exception as e:
            db.rollback()
            error_msg = f"Error extendiendo estadía: {str(e)}"
            log_event("extend_stay", usuario, "Error", error_msg)
            return False, error_msg, None


class PaymentService:
    """Servicio para gestionar pagos de reservas"""
    
    @staticmethod
    def registrar_pago(
        db: Session,
        reserva_id: int,
        monto: float,
        usuario: str,
        metodo: str,
        referencia: Optional[str] = None,
        notas: Optional[str] = None
    ) -> Tuple[bool, str, Optional[ReservaPago]]:
        """
        Registra un pago contra la reserva
        
        Returns:
            (exitoso, mensaje, pago_objeto)
        """
        try:
            # Validar reserva
            reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
            if not reserva:
                return False, f"Reserva {reserva_id} no encontrada", None
            
            if monto <= 0:
                return False, "Monto debe ser mayor a 0", None
            
            # Validar que no exceda saldo pendiente
            saldo_pendiente = reserva.saldo_pendiente or 0
            if monto > saldo_pendiente:
                return False, f"Monto excede saldo pendiente (${saldo_pendiente})", None
            
            # Crear registro de pago
            pago = ReservaPago(
                reserva_id=reserva_id,
                monto=monto,
                metodo=metodo,
                referencia=referencia,
                usuario=usuario,
                notas=notas,
                timestamp=datetime.utcnow(),
                es_reverso=False
            )
            db.add(pago)
            db.flush()
            
            # Actualizar saldo
            nuevo_monto_pagado = (reserva.monto_pagado or 0) + monto
            reserva.monto_pagado = nuevo_monto_pagado
            reserva.saldo_pendiente = (reserva.monto_total or 0) - nuevo_monto_pagado
            
            # Crear evento de auditoría
            evento = ReservaEvento(
                reserva_id=reserva_id,
                tipo_evento=TipoEvento.PAYMENT,
                usuario=usuario,
                timestamp=datetime.utcnow(),
                payload={
                    "monto": monto,
                    "metodo": metodo,
                    "referencia": referencia,
                    "saldo_anterior": saldo_pendiente,
                    "saldo_nuevo": reserva.saldo_pendiente,
                    "notas": notas
                },
                descripcion=f"Pago de ${monto} registrado via {metodo}"
            )
            db.add(evento)
            db.commit()
            
            log_event("payment", usuario, "Registrar pago", f"reserva_id={reserva_id}, monto=${monto}")
            return True, f"Pago de ${monto} registrado exitosamente", pago
            
        except Exception as e:
            db.rollback()
            error_msg = f"Error registrando pago: {str(e)}"
            log_event("payment", usuario, "Error", error_msg)
            return False, error_msg, None
    
    @staticmethod
    def revertir_pago(
        db: Session,
        pago_id: int,
        usuario: str,
        razon: str
    ) -> Tuple[bool, str]:
        """
        Revierte (deshace) un pago registrado
        
        Returns:
            (exitoso, mensaje)
        """
        try:
            pago = db.query(ReservaPago).filter(ReservaPago.id == pago_id).first()
            if not pago:
                return False, f"Pago {pago_id} no encontrado"
            
            if pago.es_reverso:
                return False, "Este pago ya fue revertido"
            
            reserva = pago.reserva
            
            # Crear reverso
            pago_reverso = ReservaPago(
                reserva_id=pago.reserva_id,
                monto=-pago.monto,
                metodo=pago.metodo,
                referencia=f"REVERSO de {pago_id}",
                usuario=usuario,
                notas=razon,
                timestamp=datetime.utcnow(),
                es_reverso=True
            )
            db.add(pago_reverso)
            pago.es_reverso = True
            
            # Recalcular saldo
            nuevo_monto_pagado = (reserva.monto_pagado or 0) - pago.monto
            reserva.monto_pagado = max(0, nuevo_monto_pagado)
            reserva.saldo_pendiente = (reserva.monto_total or 0) - reserva.monto_pagado
            
            # Evento de auditoría
            evento = ReservaEvento(
                reserva_id=pago.reserva_id,
                tipo_evento=TipoEvento.PAYMENT_REVERSAL,
                usuario=usuario,
                timestamp=datetime.utcnow(),
                payload={
                    "pago_id_reverso": pago_id,
                    "monto_revertido": pago.monto,
                    "razon": razon,
                    "nuevo_saldo": reserva.saldo_pendiente
                },
                descripcion=f"Pago ${pago.monto} revertido"
            )
            db.add(evento)
            db.commit()
            
            log_event("payment_reversal", usuario, "Revertir pago", f"pago_id={pago_id}, monto=${pago.monto}")
            return True, f"Pago ${pago.monto} revertido exitosamente"
            
        except Exception as e:
            db.rollback()
            error_msg = f"Error revirtiendo pago: {str(e)}"
            log_event("payment_reversal", usuario, "Error", error_msg)
            return False, error_msg


class CheckoutService:
    """Servicio para checkout y cierre de reservas"""
    
    @staticmethod
    def validar_checkout(
        db: Session,
        reserva_id: int
    ) -> Tuple[bool, Optional[str]]:
        """
        Valida si se puede hacer checkout
        
        Returns:
            (es_valido, mensaje_error)
        """
        reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
        if not reserva:
            return False, f"Reserva {reserva_id} no encontrada"
        
        if reserva.estado_operacional not in [EstadoReserva.OCUPADA, EstadoReserva.PENDIENTE_CHECKOUT]:
            return False, f"Reserva no está en estado checkout (está: {reserva.estado_operacional})"
        
        return True, None
    
    @staticmethod
    def realizar_checkout(
        db: Session,
        reserva_id: int,
        usuario: str,
        fecha_checkout_real: Optional[datetime] = None,
        pago_final: Optional[float] = None,
        metodo_pago_final: Optional[str] = None,
        estado_habitacion: Optional[str] = None,
        notas_limpieza: Optional[str] = None,
        daños_reportados: Optional[List[str]] = None,
        autorizar_deuda: bool = False
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Ejecuta el checkout de una reserva
        
        Returns:
            (exitoso, mensaje, resultado_dict)
        """
        try:
            # Validar
            es_valido, error = CheckoutService.validar_checkout(db, reserva_id)
            if not es_valido:
                return False, error, None
            
            reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
            
            # Registrar pago final si existe
            if pago_final and pago_final > 0:
                exitoso, msg, _ = PaymentService.registrar_pago(
                    db, reserva_id, pago_final, usuario, metodo_pago_final or "OTRO"
                )
                if not exitoso:
                    return False, f"Error con pago final: {msg}", None
            
            # Verificar deuda
            saldo_final = reserva.saldo_pendiente or 0
            if saldo_final > 0 and not autorizar_deuda:
                return False, f"Saldo pendiente ${saldo_final}. Use autorizar_deuda=True para permitir deuda", None
            
            # Actualizar reserva
            reserva.fecha_checkout_real = fecha_checkout_real or datetime.utcnow()
            reserva.estado_operacional = EstadoReserva.CERRADA
            reserva.estado_habitacion = estado_habitacion or "SUCIA"
            reserva.actualizado_por = usuario
            
            # Crear evento de auditoría
            evento = ReservaEvento(
                reserva_id=reserva_id,
                tipo_evento=TipoEvento.CHECKOUT,
                usuario=usuario,
                timestamp=datetime.utcnow(),
                payload={
                    "fecha_checkout_real": (fecha_checkout_real or datetime.utcnow()).isoformat(),
                    "pago_final": pago_final,
                    "metodo_pago_final": metodo_pago_final,
                    "estado_habitacion": estado_habitacion,
                    "notas_limpieza": notas_limpieza,
                    "daños_reportados": daños_reportados or [],
                    "saldo_final": saldo_final,
                    "deuda_autorizada": autorizar_deuda
                },
                descripcion="Checkout realizado"
            )
            db.add(evento)
            db.commit()
            
            log_event("checkout", usuario, "Cerrar reserva", f"reserva_id={reserva_id}")
            
            return True, "Checkout realizado exitosamente", {
                "reserva_id": reserva_id,
                "evento_id": evento.id,
                "fecha_checkout_real": reserva.fecha_checkout_real.isoformat(),
                "saldo_final": saldo_final,
                "deuda_autorizada": autorizar_deuda,
                "timestamp": evento.timestamp.isoformat()
            }
            
        except Exception as e:
            db.rollback()
            error_msg = f"Error en checkout: {str(e)}"
            log_event("checkout", usuario, "Error", error_msg)
            return False, error_msg, None


class AdminService:
    """Servicio para operaciones administrativas (reversiones, correcciones)"""
    
    @staticmethod
    def revertir_checkout(
        db: Session,
        reserva_id: int,
        usuario: str,
        razon: str
    ) -> Tuple[bool, str]:
        """
        Revierte un checkout (admin only)
        Permite reabrir una reserva cerrada para correcciones
        
        Returns:
            (exitoso, mensaje)
        """
        try:
            reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
            if not reserva:
                return False, f"Reserva {reserva_id} no encontrada"
            
            if reserva.estado_operacional != EstadoReserva.CERRADA:
                return False, f"Solo se puede revertir checkout de reservas cerradas"
            
            # Revertir a OCUPADA
            reserva.estado_operacional = EstadoReserva.OCUPADA
            reserva.actualizado_por = usuario
            
            # Crear evento
            evento = ReservaEvento(
                reserva_id=reserva_id,
                tipo_evento=TipoEvento.CORRECTION,
                usuario=usuario,
                timestamp=datetime.utcnow(),
                payload={
                    "accion": "REVERTIR_CHECKOUT",
                    "razon": razon
                },
                descripcion="Checkout revertido por administrador"
            )
            db.add(evento)
            db.commit()
            
            log_event("revert_checkout", usuario, "Reabrir reserva", f"reserva_id={reserva_id}")
            return True, "Checkout revertido. Reserva reabierta."
            
        except Exception as e:
            db.rollback()
            error_msg = f"Error revirtiendo checkout: {str(e)}"
            log_event("revert_checkout", usuario, "Error", error_msg)
            return False, error_msg
