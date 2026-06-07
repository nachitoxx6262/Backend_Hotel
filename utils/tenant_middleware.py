"""
Middleware para multi-tenant: Configura el contexto del tenant en cada request
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from datetime import datetime, timezone
from utils.datetime_utils import utcnow
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
        # Usamos SET LOCAL con cast explícito para evitar inyección SQL
        if tenant_id is not None:
            db_session.execute(
                text("SELECT set_config('app.current_tenant_id', :val, false)"),
                {"val": str(int(tenant_id))}
            )
        else:
            # Super admin: setear a vacío (las políticas RLS lo detectan)
            db_session.execute(
                text("SELECT set_config('app.current_tenant_id', '', false)")
            )

        # Setear app.current_user_id para auditoría
        db_session.execute(
            text("SELECT set_config('app.current_user_id', :val, false)"),
            {"val": str(int(user_id))}
        )
        db_session.execute(
            text("SELECT set_config('app.is_super_admin', :val, false)"),
            {"val": "true" if is_super_admin else "false"}
        )
        
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
    
    now = utcnow()

    # utcnow() es naive (UTC); fecha_fin_demo puede venir aware (timestamptz).
    # Normalizar a naive-UTC para comparar/restar sin TypeError.
    fin_demo = empresa_usuario.fecha_fin_demo
    if fin_demo.tzinfo is not None:
        fin_demo = fin_demo.astimezone(timezone.utc).replace(tzinfo=None)

    if now > fin_demo:
        # Trial expirado
        return {
            "is_active": False,
            "days_remaining": 0,
            "expires_at": empresa_usuario.fecha_fin_demo.isoformat(),
            "status": "expired",
            "message": "Trial expirado"
        }

    # Trial activo
    remaining_days = (fin_demo - now).days
    
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


# ========== ENFORCEMENT DE SUSCRIPCIÓN (Fase B) ==========

from starlette.middleware.base import BaseHTTPMiddleware

# Métodos que modifican estado y por lo tanto se bloquean si la suscripción no es writable.
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Prefijos exentos del bloqueo:
# - /auth: login/registro/refresh.
# - /billing y /mercadopago: un tenant VENCIDO DEBE poder ver planes y PAGAR para reactivarse.
# - infra/docs.
# (Las rutas de super-admin /admin no se listan: el super-admin se exime por rol.)
_ENFORCE_EXEMPT_PREFIXES = (
    "/auth",
    "/billing",
    "/mercadopago",
    "/health",
    "/docs",
    "/redoc",
    "/openapi",
)


def _enforce_is_exempt(path: str) -> bool:
    if path == "/":
        return True
    return any(path.startswith(p) for p in _ENFORCE_EXEMPT_PREFIXES)


class SubscriptionEnforcementMiddleware(BaseHTTPMiddleware):
    """
    Bloquea operaciones de escritura cuando la suscripción del tenant no permite escribir
    (trial vencido, suscripción vencida/cancelada/bloqueada) devolviendo 402 Payment Required.

    La verdad del estado la calcula `subscription_service.resolve_access` (Subscription como
    única fuente). El bloqueo es SOLO para escrituras: las lecturas (GET) siempre pasan.

    Es autocontenido (decodifica el JWT y abre su propia sesión) para no depender del orden
    de los otros middlewares ni de Depends.
    """

    async def dispatch(self, request, call_next):
        # Solo escrituras.
        if request.method not in _WRITE_METHODS:
            return await call_next(request)

        # Rutas exentas (auth, pagos, billing, infra).
        if _enforce_is_exempt(request.url.path):
            return await call_next(request)

        # Sin token válido -> dejar pasar; el endpoint responderá 401 por su cuenta.
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return await call_next(request)

        try:
            payload = verify_token(auth_header[7:], token_type="access")
            token_payload = TokenPayload(payload)
        except Exception:
            return await call_next(request)

        # Super-admin y usuarios sin tenant (admin global) no tienen suscripción que aplicar.
        if token_payload.is_super_admin() or not token_payload.empresa_usuario_id:
            return await call_next(request)

        from database.conexion import SessionLocal
        from models.core import EmpresaUsuario, Subscription
        from utils.subscription_service import resolve_access

        db = SessionLocal()
        try:
            empresa = db.query(EmpresaUsuario).filter_by(
                id=token_payload.empresa_usuario_id, deleted=False
            ).first()
            if not empresa:
                # Empresa inexistente/eliminada: que lo maneje el endpoint.
                return await call_next(request)

            subscription = db.query(Subscription).filter_by(
                empresa_usuario_id=empresa.id
            ).first()

            access = resolve_access(empresa, subscription)
            if not access.writable:
                expires_at = None
                if access.periodo_fin is not None:
                    try:
                        expires_at = access.periodo_fin.isoformat()
                    except Exception:
                        expires_at = None
                return JSONResponse(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    content={
                        "detail": {
                            "error": "subscription_blocked",
                            "estado": access.estado,
                            "is_trial": access.is_trial,
                            "message": (
                                "Tu período de prueba finalizó. Suscribite a un plan para seguir trabajando."
                                if access.is_trial
                                else "Tu suscripción no está activa. Regularizá el pago para seguir trabajando."
                            ),
                            "expires_at": expires_at,
                            "call_to_action": "Elegí un plan y pagá para reactivar tu cuenta.",
                            "upgrade_url": "/app/billing",
                            "read_only": True,
                        }
                    },
                )
        finally:
            db.close()

        return await call_next(request)
