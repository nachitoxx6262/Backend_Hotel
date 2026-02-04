"""
Dependencias de autenticación y autorización
"""
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import conexion
from models.usuario import Usuario
from models.rol import UsuarioRol, RolPermiso, Permiso
from models.core import EmpresaUsuario
from schemas.auth import TokenData
from utils.auth import verify_token, TokenPayload
from utils.logging_utils import log_event


# Esquema OAuth2 para obtener el token del header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ========== DEPENDENCIAS DE AUTENTICACIÓN ==========

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(conexion.get_db)
) -> Usuario:
    """
    Obtiene el usuario actual desde el token JWT
    
    Raises:
        HTTPException: Si el token es inválido o el usuario no existe
    """
    # Debug logging of tokens removed to avoid leaking sensitive data
    payload = verify_token(token, token_type="access")
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Verificar y decodificar token
        payload = verify_token(token, token_type="access")
        username: str = payload.get("sub")
        user_id: int = payload.get("user_id")
        
        if username is None or user_id is None:
            raise credentials_exception
        
        token_data = TokenData(username=username, user_id=user_id, rol=payload.get("rol"))
        
    except HTTPException:
        raise
    except Exception:
        raise credentials_exception
    
    # Buscar usuario en la base de datos
    user = db.query(Usuario).filter(
        Usuario.id == token_data.user_id,
        Usuario.username == token_data.username,
        Usuario.deleted.is_(False)
    ).first()
    
    if user is None:
        raise credentials_exception
    
    # Verificar que el usuario esté activo
    if not user.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario desactivado"
        )

    # Verificar tenant activo/no eliminado (excepto super admin)
    if not user.es_super_admin and user.empresa_usuario_id:
        tenant = db.query(EmpresaUsuario).filter(
            EmpresaUsuario.id == user.empresa_usuario_id,
            EmpresaUsuario.deleted.is_(False)
        ).first()
        if not tenant or not tenant.activa:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant inactivo o eliminado"
            )
    
    # Verificar si el usuario está bloqueado
    if user.bloqueado_hasta and user.bloqueado_hasta > datetime.utcnow():
        tiempo_restante = (user.bloqueado_hasta - datetime.utcnow()).seconds // 60
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Usuario bloqueado temporalmente. Intente en {tiempo_restante} minutos"
        )
    # Debug logging removed to avoid leaking user data
    return user


async def get_current_active_user(
    current_user: Usuario = Depends(get_current_user)
) -> Usuario:
    """
    Verifica que el usuario actual esté activo
    """
    if not current_user.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo"
        )
    return current_user


# ========== DEPENDENCIAS DE AUTORIZACIÓN ==========

def require_roles(roles_permitidos: List[str]):
    """
    Decorator/dependency para requerir roles específicos
    
    Args:
        roles_permitidos: Lista de roles que tienen acceso (ej: ["admin", "gerente"])
    
    Returns:
        Función de dependencia que verifica el rol del usuario
    """
    async def check_role(current_user: Usuario = Depends(get_current_active_user)) -> Usuario:
        if current_user.rol not in roles_permitidos:
            log_event(
                "auth",
                current_user.username,
                "Intento de acceso no autorizado",
                f"rol={current_user.rol} roles_requeridos={roles_permitidos}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Roles permitidos: {', '.join(roles_permitidos)}"
            )
        return current_user
    
    return check_role


# ========== DEPENDENCIAS POR ROL ==========

# Solo administradores
async def require_admin(current_user: Usuario = Depends(get_current_active_user)) -> Usuario:
    """Requiere rol de administrador"""
    if current_user.rol != "admin":
        log_event("auth", current_user.username, "Intento de acceso admin sin permisos", f"rol={current_user.rol}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren privilegios de administrador"
        )
    return current_user


# Administradores o gerentes
async def require_admin_or_manager(current_user: Usuario = Depends(get_current_active_user)) -> Usuario:
    """Requiere rol de administrador o gerente"""
    if current_user.rol not in ["admin", "gerente"]:
        log_event(
            "auth",
            current_user.username,
            "Intento de acceso admin/gerente sin permisos",
            f"rol={current_user.rol}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren privilegios de administrador o gerente"
        )
    return current_user


# Staff del hotel (admin, gerente, recepcionista)
async def require_staff(current_user: Usuario = Depends(get_current_active_user)) -> Usuario:
    """Requiere rol de staff (admin, gerente o recepcionista)"""
    if current_user.rol not in ["admin", "gerente", "recepcionista"]:
        log_event("auth", current_user.username, "Intento de acceso staff sin permisos", f"rol={current_user.rol}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren privilegios de staff del hotel"
        )
    return current_user


# Usuario autenticado (cualquier rol)
async def require_authenticated(current_user: Usuario = Depends(get_current_active_user)) -> Usuario:
    """Solo requiere que el usuario esté autenticado"""
    return current_user


# ========== UTILIDADES DE PERMISOS ==========

def usuario_puede_modificar(usuario_actual: Usuario, usuario_objetivo: Usuario) -> bool:
    """
    Verifica si un usuario puede modificar a otro usuario
    
    Reglas:
    - Admin puede modificar a cualquiera
    - Gerente puede modificar a recepcionistas y readonly
    - Recepcionista solo puede modificar su propio perfil
    - Readonly solo puede modificar su propio perfil
    """
    if usuario_actual.id == usuario_objetivo.id:
        return True  # Siempre puede modificarse a sí mismo
    
    if usuario_actual.rol == "admin":
        return True  # Admin puede modificar a cualquiera
    
    if usuario_actual.rol == "gerente":
        return usuario_objetivo.rol in ["recepcionista", "readonly"]
    
    return False


def usuario_puede_eliminar(usuario_actual: Usuario, usuario_objetivo: Usuario) -> bool:
    """
    Verifica si un usuario puede eliminar a otro usuario
    
    Reglas:
    - Admin puede eliminar a cualquiera excepto a sí mismo
    - Gerente puede eliminar a recepcionistas y readonly
    - Otros no pueden eliminar
    """
    if usuario_actual.id == usuario_objetivo.id:
        return False  # No puede eliminarse a sí mismo
    
    if usuario_actual.rol == "admin":
        return True
    
    if usuario_actual.rol == "gerente":
        return usuario_objetivo.rol in ["recepcionista", "readonly"]
    
    return False


# ========== DEPENDENCIA OPCIONAL ==========

async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(conexion.get_db)
) -> Optional[Usuario]:
    """
    Obtiene el usuario actual si hay token, sino retorna None
    Útil para endpoints que funcionan con o sin autenticación
    """
    if not token:
        return None
    
    try:
        return await get_current_user(token, db)
    except HTTPException:
        return None


# ========== PERMISOS DINÁMICOS (RBAC) ==========

def _user_permissions(db: Session, user_id: int):
    perms = (
        db.query(Permiso.codigo)
        .join(RolPermiso, Permiso.id == RolPermiso.permiso_id)
        .join(UsuarioRol, UsuarioRol.rol_id == RolPermiso.rol_id)
        .filter(UsuarioRol.usuario_id == user_id, Permiso.activo == True)
        .distinct()
        .all()
    )
    return {p.codigo for p in perms}


def require_permission(codigo_permiso: str):
    def dependency(current_user: Usuario = Depends(get_current_active_user), db: Session = Depends(conexion.get_db)):
        # Admin siempre permitido
        if current_user.rol == "admin":
            return current_user
        user_perms = _user_permissions(db, current_user.id)
        if codigo_permiso not in user_perms:
            log_event("auth", current_user.username, "Acceso denegado por permiso", f"permiso={codigo_permiso}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")
        return current_user
    return dependency


def require_any_permission(codigos: List[str]):
    def dependency(current_user: Usuario = Depends(get_current_active_user), db: Session = Depends(conexion.get_db)):
        if current_user.rol == "admin":
            return current_user
        user_perms = _user_permissions(db, current_user.id)
        if not any(c in user_perms for c in codigos):
            log_event("auth", current_user.username, "Acceso denegado por permisos", f"permisos={codigos}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permisos insuficientes")
        return current_user
    return dependency


# ========== MULTI-TENANT DEPENDENCIES ==========

async def get_current_tenant(
    current_user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(conexion.get_db)
) -> EmpresaUsuario:
    """
    Obtiene el tenant actual del usuario.
    
    Raises:
        HTTPException: Si el usuario no está asignado a un tenant y no es super_admin
    """
    # Si es super_admin, no tiene tenant específico
    if current_user.es_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin debe especificar un tenant"
        )
    
    # Usuario regular debe tener empresa_usuario_id
    if not current_user.empresa_usuario_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no asignado a ningún hotel"
        )
    
    # Verificar que el tenant existe y está activo
    tenant = db.query(EmpresaUsuario).filter(
        EmpresaUsuario.id == current_user.empresa_usuario_id,
        EmpresaUsuario.activa == True
    ).first()
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hotel no disponible o inactivo"
        )
    
    return tenant


async def get_tenant_from_token(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(conexion.get_db)
) -> TokenPayload:
    """
    Obtiene el payload del token con información multi-tenant
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = verify_token(token, token_type="access")
        token_payload = TokenPayload(payload)
        
        if not token_payload.is_valid():
            raise credentials_exception
        
        return token_payload
    except HTTPException:
        raise
    except Exception:
        raise credentials_exception


async def require_super_admin(
    current_user: Usuario = Depends(get_current_active_user)
) -> Usuario:
    """
    Requiere que el usuario sea super_admin del SaaS
    """
    if not current_user.es_super_admin:
        log_event(
            "auth",
            current_user.username,
            "Acceso denegado - se requiere super_admin",
            f"es_super_admin={current_user.es_super_admin}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren privilegios de super administrador"
        )
    return current_user


async def validate_trial_status(
    current_user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(conexion.get_db)
) -> bool:
    """
    Valida si el trial del usuario está activo
    
    Returns:
        True si el trial está activo, False si ha expirado
    
    Raises:
        HTTPException si el usuario no tiene trial o no está asociado a un tenant
    """
    if current_user.es_super_admin:
        return True  # Super admin no tiene restricción de trial
    
    if not current_user.empresa_usuario_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no asignado a ningún hotel"
        )
    
    # Obtener el empresa_usuario
    tenant = db.query(EmpresaUsuario).filter(
        EmpresaUsuario.id == current_user.empresa_usuario_id
    ).first()
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hotel no encontrado"
        )
    
    # Verificar si está en trial (plan DEMO)
    from models.core import PlanType
    
    if tenant.plan_tipo != PlanType.DEMO:
        return True  # No es trial, es suscripción pagada
    
    # Verificar si el trial ha expirado
    if tenant.fecha_fin_demo and datetime.utcnow() > tenant.fecha_fin_demo:
        return False
    
    return True


async def require_active_trial(
    is_trial_active: bool = Depends(validate_trial_status)
) -> None:
    """
    Requiere que el trial esté activo para operaciones de escritura
    """
    if not is_trial_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Trial expirado. Por favor, upgrade a un plan de pago"
        )


async def set_tenant_context(
    request: Request,
    current_user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(conexion.get_db)
) -> int:
    """
    Middleware: Configura el contexto del tenant para PostgreSQL RLS
    
    Esto setea app.current_tenant_id en la sesión de PostgreSQL
    para que las políticas RLS sepan cuál es el tenant actual
    """
    tenant_id = current_user.empresa_usuario_id
    
    # Si es super_admin, permitir acceso a todo (null tenant_id)
    if current_user.es_super_admin:
        tenant_id = None
    
    if tenant_id:
        try:
            # Setear app.current_tenant_id en PostgreSQL para RLS
            db.execute(text(f"SET app.current_tenant_id = {tenant_id}"))
            db.commit()
        except Exception as e:
            log_event(
                "error",
                current_user.username,
                "Error setting tenant context",
                str(e)
            )
    
    # Guardar en request state para usar en handlers
    request.state.tenant_id = tenant_id
    request.state.current_user = current_user
    
    return tenant_id


async def get_request_tenant_id(request: Request) -> Optional[int]:
    """
    Obtiene el tenant_id desde el request state (set por middleware)
    """
    return getattr(request.state, "tenant_id", None)
