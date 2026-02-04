"""
Middleware para multi-tenant: Configura el contexto del tenant en cada request
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from datetime import datetime
import logging
from typing import Optional

from utils.auth import verify_token, TokenPayload
from utils.logging_utils import log_event

logger = logging.getLogger(__name__)


class TenantContextMiddleware:
    """
    Middleware que extrae el tenant_id del JWT y lo configura en PostgreSQL para RLS
    """
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        """
        Procesa cada request y configura el contexto del tenant
        """
        from starlette.requests import Request
        
        # Solo procesar requests HTTP
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Rutas públicas que no requieren tenant
        public_routes = [
            "/docs",
            "/openapi.json",
            "/health",
            "/auth/login",
            "/auth/register",
            "/auth/refresh",
            "/",
        ]
        
        request = Request(scope, receive, send)
        
        # Si es ruta pública, pasar al siguiente
        if any(request.url.path.startswith(route) for route in public_routes):
            await self.app(scope, receive, send)
            return
        
        # Inicializar state
        request.state.tenant_id = None
        request.state.current_user_id = None
        request.state.is_super_admin = False
        
        # Obtener token del header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            # Sin token, dejar pasar (será validado por Depends en el endpoint)
            await self.app(scope, receive, send)
            return
        
        token = auth_header[7:]  # Remover "Bearer "
        
        try:
            # Decodificar token
            payload = verify_token(token, token_type="access")
            token_payload = TokenPayload(payload)
            
            # Guardar en request state
            request.state.current_user_id = token_payload.user_id
            request.state.is_super_admin = token_payload.is_super_admin()
            request.state.tenant_id = token_payload.get_tenant_id()
            
            # Log
            log_event(
                "auth",
                f"user_{token_payload.user_id}",
                "Token validated",
                f"tenant_id={request.state.tenant_id}, es_super_admin={token_payload.es_super_admin}"
            )
            
        except Exception as e:
            # Token inválido, dejar pasar (será rechazado por Depends)
            logger.debug(f"Token validation failed: {str(e)}")
            pass
        
        # Continuar con la request
        await self.app(scope, receive, send)


class PostgreSQLRLSMiddleware:
    """
    Middleware que configura PostgreSQL RLS (Row Level Security) por request
    
    Nota: Esto debe ejecutarse DESPUÉS de que la request sea procesada por FastAPI
    porque necesita acceso a la DB session específica
    """
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        """
        Ejecuta después de que se resuelven las dependencias con la DB session
        """
        from starlette.requests import Request
        
        # Solo procesar requests HTTP
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        request = Request(scope, receive, send)
        
        async def send_wrapper(message):
            # Agregar tenant_id a los response headers (útil para debugging)
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                
                if hasattr(request.state, "tenant_id") and request.state.tenant_id:
                    headers.append((b"x-tenant-id", str(request.state.tenant_id).encode()))
                
                if hasattr(request.state, "is_super_admin") and request.state.is_super_admin:
                    headers.append((b"x-super-admin", b"true"))
                
                message["headers"] = headers
            
            await send(message)
        
        await self.app(scope, receive, send_wrapper)


def set_rls_context(db_session, tenant_id: Optional[int], user_id: int, is_super_admin: bool):
    """
    Función auxiliar para configurar RLS context en una sesión de PostgreSQL
    
    Args:
        db_session: SQLAlchemy session
        tenant_id: ID del tenant (None para super_admin)
        user_id: ID del usuario
        is_super_admin: Boolean indicando si es super admin
    """
    try:
        # Setear app.current_tenant_id para RLS
        if tenant_id:
            db_session.execute(text(f"SET app.current_tenant_id = {tenant_id}"))
        else:
            # Super admin: setear a null (las políticas RLS lo detectan)
            db_session.execute(text("SET app.current_tenant_id = NULL"))
        
        # Setear app.current_user_id para auditoría (opcional)
        db_session.execute(text(f"SET app.current_user_id = {user_id}"))
        db_session.execute(text(f"SET app.is_super_admin = {str(is_super_admin).lower()}"))
        
        db_session.commit()
        
        logger.debug(f"RLS context set: tenant_id={tenant_id}, user_id={user_id}, is_super_admin={is_super_admin}")
        
    except Exception as e:
        logger.error(f"Error setting RLS context: {str(e)}")
        raise


# ========== TRIAL STATUS HELPERS ==========

def check_trial_expiration(empresa_usuario) -> dict:
    """
    Verifica el estado del trial de una empresa usuario
    
    Returns:
        dict con información del trial: {
            "is_active": bool,
            "days_remaining": int or None,
            "expires_at": str or None,
            "status": "active" | "expired" | "not_trial",
            "message": str
        }
    """
    from models.core import PlanType
    
    # Si no es plan DEMO, no es trial
    if empresa_usuario.plan_tipo != PlanType.DEMO:
        return {
            "is_active": True,
            "days_remaining": None,
            "expires_at": None,
            "status": "not_trial",
            "message": f"Suscripción activa: {empresa_usuario.plan_tipo.value}"
        }
    
    # Es DEMO, verificar fechas
    if not empresa_usuario.fecha_fin_demo:
        return {
            "is_active": False,
            "days_remaining": 0,
            "expires_at": None,
            "status": "expired",
            "message": "Trial expirado sin fecha de expiración registrada"
        }
    
    now = datetime.utcnow()
    
    if now > empresa_usuario.fecha_fin_demo:
        # Trial expirado
        return {
            "is_active": False,
            "days_remaining": 0,
            "expires_at": empresa_usuario.fecha_fin_demo.isoformat(),
            "status": "expired",
            "message": "Trial expirado"
        }
    
    # Trial activo
    remaining_days = (empresa_usuario.fecha_fin_demo - now).days
    
    return {
        "is_active": True,
        "days_remaining": remaining_days,
        "expires_at": empresa_usuario.fecha_fin_demo.isoformat(),
        "status": "active",
        "message": f"Trial activo - Expira en {remaining_days} días" if remaining_days > 0 else "Trial expira hoy"
    }


def is_trial_write_blocked(empresa_usuario) -> bool:
    """
    Verifica si el trial está en período de bloqueo de escrituras (día 10+)
    
    El bloqueo de escrituras comienza después de que el trial expira
    Los usuarios pueden seguir LEYENDO pero no pueden hacer cambios
    """
    from models.core import PlanType
    
    if empresa_usuario.plan_tipo != PlanType.DEMO:
        return False  # Suscripciones pagadas no tienen bloqueo
    
    trial_info = check_trial_expiration(empresa_usuario)
    
    # Bloquear si el trial ha expirado
    return trial_info["status"] == "expired"
