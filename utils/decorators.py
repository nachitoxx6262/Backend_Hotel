"""
Decorators para endpoints - Validaciones específicas de negocio
"""
from functools import wraps
from datetime import datetime
from typing import Callable

from fastapi import HTTPException, status, Depends
from sqlalchemy.orm import Session

from database import conexion
from models.usuario import Usuario
from models.core import EmpresaUsuario, Subscription
from utils.dependencies import get_current_user
from utils.tenant_middleware import is_trial_write_blocked


def require_trial_writable(func: Callable) -> Callable:
    """
    Decorator que bloquea operaciones de escritura (POST, PUT, DELETE)
    si el trial del usuario ha expirado.
    
    Retorna 402 Payment Required si el trial está bloqueado.
    
    Uso:
        @router.post("/clientes")
        @require_trial_writable
        def crear_cliente(data: ClienteCreate, ...):
            ...
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Obtener current_user y db de los kwargs
        current_user: Usuario = kwargs.get("current_user")
        db: Session = kwargs.get("db")
        
        if not current_user or not db:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error interno: usuario o BD no disponible"
            )
        
        # Super admin puede hacer lo que quiera
        if current_user.es_super_admin:
            return await func(*args, **kwargs) if hasattr(func, '__await__') else func(*args, **kwargs)
        
        # Si no está asignado a un tenant, es admin global
        if not current_user.empresa_usuario_id:
            return await func(*args, **kwargs) if hasattr(func, '__await__') else func(*args, **kwargs)
        
        # Verificar si el trial está bloqueado
        empresa = db.query(EmpresaUsuario).filter_by(
            id=current_user.empresa_usuario_id,
            deleted=False
        ).first()
        
        if not empresa:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Empresa no encontrada o fue eliminada"
            )
        
        # Obtener subscription
        subscription = db.query(Subscription).filter_by(
            empresa_usuario_id=empresa.id,
            deleted=False
        ).first()
        
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Suscripción no encontrada"
            )
        
        # Verificar si write está bloqueado por trial
        if is_trial_write_blocked(subscription):
            dias_restantes = 0
            if empresa.fecha_fin_demo:
                dias_restantes = max(0, (empresa.fecha_fin_demo - datetime.utcnow()).days)
            
            raise HTTPException(
                status_code=402,  # Payment Required
                detail={
                    "error": "trial_expired",
                    "message": "Tu período de prueba ha finalizado. Suscríbete a un plan para continuar.",
                    "trial_ended_at": empresa.fecha_fin_demo.isoformat() if empresa.fecha_fin_demo else None,
                    "call_to_action": "Elige un plan en /billing/planes",
                    "available_actions": ["GET (lectura)", "GET /billing/planes", "GET /billing/status"]
                }
            )
        
        # Trial aún activo o usuario tiene plan pagado - permitir
        return await func(*args, **kwargs) if hasattr(func, '__await__') else func(*args, **kwargs)
    
    return wrapper


def require_plan_feature(feature: str) -> Callable:
    """
    Decorator que valida que el plan actual incluya una feature específica.
    
    Features disponibles:
    - "facturacion": permite_facturacion
    - "reportes": permite_reportes
    - "soporte_email": soporte_email
    
    Uso:
        @router.post("/invoices")
        @require_plan_feature("facturacion")
        def crear_invoice(data: InvoiceCreate, ...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user: Usuario = kwargs.get("current_user")
            db: Session = kwargs.get("db")
            
            if not current_user or not db:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error interno"
                )
            
            # Super admin siempre tiene acceso
            if current_user.es_super_admin:
                return await func(*args, **kwargs) if hasattr(func, '__await__') else func(*args, **kwargs)
            
            # Obtener plan actual
            subscription = db.query(Subscription).filter_by(
                empresa_usuario_id=current_user.empresa_usuario_id,
                deleted=False
            ).first()
            
            if not subscription:
                raise HTTPException(
                    status_code=403,
                    detail="No hay suscripción activa"
                )
            
            plan = subscription.plan
            
            # Validar feature según tipo
            feature_allowed = False
            
            if feature == "facturacion":
                feature_allowed = plan.permite_facturacion
            elif feature == "reportes":
                feature_allowed = plan.permite_reportes
            elif feature == "soporte_email":
                feature_allowed = plan.soporte_email
            
            if not feature_allowed:
                raise HTTPException(
                    status_code=403,
                    detail=f"La feature '{feature}' no está disponible en tu plan '{plan.nombre}'. Actualiza tu plan para acceder.",
                    headers={"X-Feature-Locked": feature}
                )
            
            return await func(*args, **kwargs) if hasattr(func, '__await__') else func(*args, **kwargs)
        
        return wrapper
    
    return decorator


def validate_resource_limit(resource: str, limit_field: str) -> Callable:
    """
    Decorator que valida que no se haya excedido el límite de recursos del plan.
    
    Resources:
    - "habitaciones": limit_field = "limite_habitaciones"
    - "usuarios": limit_field = "limite_usuarios"
    
    Uso:
        @router.post("/habitaciones")
        @validate_resource_limit("habitaciones", "limite_habitaciones")
        def crear_habitacion(data: HabitacionCreate, ...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user: Usuario = kwargs.get("current_user")
            db: Session = kwargs.get("db")
            
            if not current_user or not db:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error interno"
                )
            
            # Super admin sin límites
            if current_user.es_super_admin:
                return await func(*args, **kwargs) if hasattr(func, '__await__') else func(*args, **kwargs)
            
            # Obtener subscription y plan
            subscription = db.query(Subscription).filter_by(
                empresa_usuario_id=current_user.empresa_usuario_id,
                deleted=False
            ).first()
            
            if not subscription:
                raise HTTPException(status_code=403, detail="No hay suscripción")
            
            plan = subscription.plan
            limit_value = getattr(plan, limit_field, -1)
            
            # -1 significa ilimitado
            if limit_value == -1:
                return await func(*args, **kwargs) if hasattr(func, '__await__') else func(*args, **kwargs)
            
            # Contar recursos actuales
            if resource == "habitaciones":
                from models.core import Room
                current_count = db.query(Room).filter_by(
                    empresa_usuario_id=current_user.empresa_usuario_id,
                    deleted=False
                ).count()
            
            elif resource == "usuarios":
                current_count = db.query(Usuario).filter_by(
                    empresa_usuario_id=current_user.empresa_usuario_id,
                    deleted=False,
                    activo=True
                ).count()
            
            else:
                return await func(*args, **kwargs) if hasattr(func, '__await__') else func(*args, **kwargs)
            
            # Verificar límite
            if current_count >= limit_value:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "resource_limit_exceeded",
                        "message": f"Límite de {resource} alcanzado ({current_count}/{limit_value})",
                        "resource": resource,
                        "current": current_count,
                        "limit": limit_value,
                        "call_to_action": f"Actualiza tu plan para agregar más {resource}",
                        "upgrade_url": "/billing/planes"
                    }
                )
            
            return await func(*args, **kwargs) if hasattr(func, '__await__') else func(*args, **kwargs)
        
        return wrapper
    
    return decorator
