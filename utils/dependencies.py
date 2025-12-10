"""
Dependencias de autenticación y autorización
"""
from typing import Optional, List
from datetime import datetime
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from database import conexion
from models.usuario import Usuario
from models.rol import UsuarioRol, RolPermiso, Permiso
from schemas.auth import TokenData
from utils.auth import decode_token, verify_token
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
    print("=== TOKEN DEL FRONT ===")
    print(token)
    print("=== PAYLOAD SIN VERIFICAR ===")
    print(decode_token(token))
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
    
    # Verificar si el usuario está bloqueado
    if user.bloqueado_hasta and user.bloqueado_hasta > datetime.utcnow():
        tiempo_restante = (user.bloqueado_hasta - datetime.utcnow()).seconds // 60
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Usuario bloqueado temporalmente. Intente en {tiempo_restante} minutos"
        )
    print("=== USUARIO AUTENTICADO ===")
    print(user.username)
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
