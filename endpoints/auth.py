"""
Endpoints de autenticación y gestión de usuarios
"""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from database import conexion
from models.usuario import Usuario
from schemas.auth import (
    UsuarioCreate, UsuarioUpdate, UsuarioRead, UsuarioInDB,
    LoginRequest, Token, RefreshTokenRequest, ChangePasswordRequest
)
from utils.auth import (
    verify_password, get_password_hash,
    create_access_token, create_refresh_token, verify_token,
    ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS
)
from utils.dependencies import (
    get_current_user, require_admin, require_admin_or_manager,
    require_staff, usuario_puede_modificar, usuario_puede_eliminar
)
from utils.logging_utils import log_event


router = APIRouter(prefix="/auth", tags=["Autenticación"])


# ========== ENDPOINTS DE AUTENTICACIÓN ==========

@router.post("/register", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
def registrar_usuario(
    usuario_data: UsuarioCreate,
    db: Session = Depends(conexion.get_db),
    current_user: Usuario = Depends(require_admin)
):
    """
    Registra un nuevo usuario (solo admin)
    """
    try:
        # Verificar que el username no exista
        existe_username = db.query(Usuario).filter(
            Usuario.username == usuario_data.username,
            Usuario.deleted.is_(False)
        ).first()
        
        if existe_username:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El nombre de usuario ya está en uso"
            )
        
        # Verificar que el email no exista
        existe_email = db.query(Usuario).filter(
            Usuario.email == usuario_data.email,
            Usuario.deleted.is_(False)
        ).first()
        
        if existe_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El email ya está registrado"
            )
        
        # Crear usuario
        nuevo_usuario = Usuario(
            username=usuario_data.username,
            email=usuario_data.email,
            hashed_password=get_password_hash(usuario_data.password),
            nombre=usuario_data.nombre,
            apellido=usuario_data.apellido,
            rol=usuario_data.rol
        )
        
        db.add(nuevo_usuario)
        db.commit()
        db.refresh(nuevo_usuario)
        
        log_event("auth", current_user.username, "Usuario registrado", f"nuevo_usuario={nuevo_usuario.username}")
        
        return nuevo_usuario
        
    except HTTPException:
        raise
    except IntegrityError as e:
        db.rollback()
        log_event("auth", current_user.username, "Error de integridad al registrar", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Violación de restricción de integridad"
        )
    except SQLAlchemyError as e:
        db.rollback()
        log_event("auth", current_user.username, "Error al registrar usuario", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al registrar el usuario"
        )


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(conexion.get_db)
):
    """
    Inicia sesión y retorna tokens de acceso y refresco
    """
    try:
        # Buscar usuario
        usuario = db.query(Usuario).filter(
            Usuario.username == form_data.username,
            Usuario.deleted.is_(False)
        ).first()
        
        if not usuario:
            log_event("auth", form_data.username, "Intento de login con usuario inexistente", "")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales incorrectas",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verificar si está bloqueado
        if usuario.bloqueado_hasta and usuario.bloqueado_hasta > datetime.utcnow():
            tiempo_restante = (usuario.bloqueado_hasta - datetime.utcnow()).seconds // 60
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Usuario bloqueado temporalmente. Intente en {tiempo_restante} minutos"
            )
        
        # Verificar contraseña
        if not verify_password(form_data.password, usuario.hashed_password):
            # Incrementar intentos fallidos
            usuario.intentos_fallidos += 1
            
            # Bloquear después de 5 intentos fallidos
            if usuario.intentos_fallidos >= 5:
                usuario.bloqueado_hasta = datetime.utcnow() + timedelta(minutes=30)
                db.commit()
                log_event("auth", form_data.username, "Usuario bloqueado por intentos fallidos", "")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Usuario bloqueado por múltiples intentos fallidos. Intente en 30 minutos"
                )
            
            db.commit()
            log_event("auth", form_data.username, "Intento de login con password incorrecta", f"intentos={usuario.intentos_fallidos}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales incorrectas",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verificar si está activo
        if not usuario.activo:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario desactivado"
            )
        
        # Resetear intentos fallidos y actualizar último login
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        usuario.ultimo_login = datetime.utcnow()
        db.commit()
        
        # Crear tokens
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": usuario.username, "user_id": usuario.id, "rol": usuario.rol},
            expires_delta=access_token_expires
        )
        
        refresh_token = create_refresh_token(
            data={"sub": usuario.username, "user_id": usuario.id}
        )
        
        log_event("auth", usuario.username, "Login exitoso", f"rol={usuario.rol}")
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60  # en segundos
        }
        
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        log_event("auth", "system", "Error en login", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al procesar el login"
        )


@router.post("/refresh", response_model=Token)
def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: Session = Depends(conexion.get_db)
):
    """
    Renueva el token de acceso usando un refresh token válido
    """
    try:
        # Verificar refresh token
        payload = verify_token(refresh_data.refresh_token, token_type="refresh")
        username: str = payload.get("sub")
        user_id: int = payload.get("user_id")
        
        if username is None or user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de refresco inválido"
            )
        
        # Buscar usuario
        usuario = db.query(Usuario).filter(
            Usuario.id == user_id,
            Usuario.username == username,
            Usuario.deleted.is_(False),
            Usuario.activo.is_(True)
        ).first()
        
        if not usuario:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario no encontrado o inactivo"
            )
        
        # Crear nuevos tokens
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": usuario.username, "user_id": usuario.id, "rol": usuario.rol},
            expires_delta=access_token_expires
        )
        
        refresh_token = create_refresh_token(
            data={"sub": usuario.username, "user_id": usuario.id}
        )
        
        log_event("auth", usuario.username, "Token renovado", "")
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log_event("auth", "system", "Error al renovar token", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al renovar el token"
        )


@router.get("/me", response_model=UsuarioRead)
def obtener_perfil(current_user: Usuario = Depends(get_current_user)):
    """
    Obtiene el perfil del usuario actual
    """
    log_event("auth", current_user.username, "Consulta de perfil", "")
    return current_user


@router.put("/me", response_model=UsuarioRead)
def actualizar_perfil(
    datos: UsuarioUpdate,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    """
    Actualiza el perfil del usuario actual
    """
    try:
        datos_update = datos.dict(exclude_unset=True)
        
        # Los usuarios normales no pueden cambiar su propio rol
        if "rol" in datos_update and current_user.rol != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para cambiar su rol"
            )
        
        # Verificar email único si se está cambiando
        if "email" in datos_update and datos_update["email"] != current_user.email:
            existe_email = db.query(Usuario).filter(
                Usuario.email == datos_update["email"],
                Usuario.id != current_user.id,
                Usuario.deleted.is_(False)
            ).first()
            
            if existe_email:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El email ya está en uso"
                )
        
        # Actualizar campos
        for campo, valor in datos_update.items():
            setattr(current_user, campo, valor)
        
        current_user.fecha_ultima_modificacion = datetime.utcnow()
        db.commit()
        db.refresh(current_user)
        
        log_event("auth", current_user.username, "Perfil actualizado", "")
        
        return current_user
        
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        log_event("auth", current_user.username, "Error al actualizar perfil", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar el perfil"
        )


@router.post("/change-password")
def cambiar_password(
    datos: ChangePasswordRequest,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    """
    Cambia la contraseña del usuario actual
    """
    try:
        # Verificar contraseña actual
        if not verify_password(datos.current_password, current_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Contraseña actual incorrecta"
            )
        
        # Verificar que la nueva contraseña sea diferente
        if datos.current_password == datos.new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La nueva contraseña debe ser diferente a la actual"
            )
        
        # Actualizar contraseña
        current_user.hashed_password = get_password_hash(datos.new_password)
        current_user.fecha_ultima_modificacion = datetime.utcnow()
        db.commit()
        
        log_event("auth", current_user.username, "Contraseña cambiada", "")
        
        return {"message": "Contraseña actualizada exitosamente"}
        
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        log_event("auth", current_user.username, "Error al cambiar contraseña", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al cambiar la contraseña"
        )


# ========== GESTIÓN DE USUARIOS (ADMIN) ==========

@router.get("/usuarios", response_model=List[UsuarioRead])
def listar_usuarios(
    db: Session = Depends(conexion.get_db),
    current_user: Usuario = Depends(require_admin_or_manager)
):
    """
    Lista todos los usuarios activos (admin/gerente)
    """
    usuarios = db.query(Usuario).filter(Usuario.deleted.is_(False)).all()
    log_event("auth", current_user.username, "Listar usuarios", f"total={len(usuarios)}")
    return usuarios


@router.get("/usuarios/{usuario_id}", response_model=UsuarioRead)
def obtener_usuario(
    usuario_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
    current_user: Usuario = Depends(require_admin_or_manager)
):
    """
    Obtiene un usuario por ID (admin/gerente)
    """
    usuario = db.query(Usuario).filter(
        Usuario.id == usuario_id,
        Usuario.deleted.is_(False)
    ).first()
    
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    log_event("auth", current_user.username, "Consultar usuario", f"usuario_id={usuario_id}")
    return usuario


@router.put("/usuarios/{usuario_id}", response_model=UsuarioRead)
def actualizar_usuario(
    usuario_id: int = Path(..., gt=0),
    datos: UsuarioUpdate = ...,
    db: Session = Depends(conexion.get_db),
    current_user: Usuario = Depends(require_admin_or_manager)
):
    """
    Actualiza un usuario (admin/gerente con restricciones)
    """
    try:
        usuario = db.query(Usuario).filter(
            Usuario.id == usuario_id,
            Usuario.deleted.is_(False)
        ).first()
        
        if not usuario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )
        
        # Verificar permisos
        if not usuario_puede_modificar(current_user, usuario):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para modificar este usuario"
            )
        
        datos_update = datos.dict(exclude_unset=True)
        
        # Verificar email único si se está cambiando
        if "email" in datos_update and datos_update["email"] != usuario.email:
            existe_email = db.query(Usuario).filter(
                Usuario.email == datos_update["email"],
                Usuario.id != usuario_id,
                Usuario.deleted.is_(False)
            ).first()
            
            if existe_email:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El email ya está en uso"
                )
        
        # Actualizar campos
        for campo, valor in datos_update.items():
            setattr(usuario, campo, valor)
        
        usuario.fecha_ultima_modificacion = datetime.utcnow()
        db.commit()
        db.refresh(usuario)
        
        log_event("auth", current_user.username, "Usuario actualizado", f"usuario_id={usuario_id}")
        
        return usuario
        
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        log_event("auth", current_user.username, "Error al actualizar usuario", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar el usuario"
        )


@router.delete("/usuarios/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_usuario(
    usuario_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
    current_user: Usuario = Depends(require_admin)
):
    """
    Elimina (soft delete) un usuario (solo admin)
    """
    try:
        usuario = db.query(Usuario).filter(
            Usuario.id == usuario_id,
            Usuario.deleted.is_(False)
        ).first()
        
        if not usuario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )
        
        # Verificar permisos
        if not usuario_puede_eliminar(current_user, usuario):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para eliminar este usuario"
            )
        
        usuario.deleted = True
        usuario.activo = False
        db.commit()
        
        log_event("auth", current_user.username, "Usuario eliminado", f"usuario_id={usuario_id}")
        
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        log_event("auth", current_user.username, "Error al eliminar usuario", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar el usuario"
        )
