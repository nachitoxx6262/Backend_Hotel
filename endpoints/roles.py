from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from typing import List

from database.conexion import get_db
from models.rol import Rol, Permiso, RolPermiso, UsuarioRol
from models.usuario import Usuario
from schemas.rbac import (
    RolCreate, RolRead, RolUpdate,
    PermisoCreate, PermisoRead, PermisoUpdate,
    AsignarPermisosRequest, AsignarRolesRequest,
)
from utils.dependencies import require_admin_or_manager
from utils.logging_utils import log_event

router = APIRouter(prefix="/roles", tags=["Roles & Permisos"])


@router.post("/roles", response_model=RolRead, dependencies=[Depends(require_admin_or_manager)])
def crear_rol(payload: RolCreate, db: Session = Depends(get_db)):
    try:
        rol = Rol(nombre=payload.nombre, descripcion=payload.descripcion, activo=payload.activo)
        db.add(rol)
        db.flush()

        if payload.permisos_codigos:
            perms = db.query(Permiso).filter(Permiso.codigo.in_(payload.permisos_codigos)).all()
            for p in perms:
                db.add(RolPermiso(rol_id=rol.id, permiso_id=p.id))
        db.commit()
        db.refresh(rol)
        log_event("roles", f"Rol creado: {rol.nombre}")
        # Build response with permisos
        permisos = [PermisoRead.model_validate(p.permiso) for p in rol.permisos]
        return RolRead(id=rol.id, nombre=rol.nombre, descripcion=rol.descripcion, activo=rol.activo, permisos=permisos)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="El rol ya existe")
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear rol: {str(e)}")


@router.get("/roles", response_model=List[RolRead], dependencies=[Depends(require_admin_or_manager)])
def listar_roles(db: Session = Depends(get_db)):
    roles = db.query(Rol).all()
    result = []
    for r in roles:
        permisos = [PermisoRead.model_validate(rp.permiso) for rp in r.permisos]
        result.append(RolRead(id=r.id, nombre=r.nombre, descripcion=r.descripcion, activo=r.activo, permisos=permisos))
    return result


@router.patch("/roles/{rol_id}", response_model=RolRead, dependencies=[Depends(require_admin_or_manager)])
def actualizar_rol(rol_id: int, payload: RolUpdate, db: Session = Depends(get_db)):
    rol = db.query(Rol).filter(Rol.id == rol_id).first()
    if not rol:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    try:
        if payload.nombre is not None:
            rol.nombre = payload.nombre
        if payload.descripcion is not None:
            rol.descripcion = payload.descripcion
        if payload.activo is not None:
            rol.activo = payload.activo
        db.flush()

        if payload.permisos_codigos is not None:
            # Replace permissions set
            db.query(RolPermiso).filter(RolPermiso.rol_id == rol.id).delete()
            if payload.permisos_codigos:
                perms = db.query(Permiso).filter(Permiso.codigo.in_(payload.permisos_codigos)).all()
                for p in perms:
                    db.add(RolPermiso(rol_id=rol.id, permiso_id=p.id))
        db.commit()
        db.refresh(rol)
        log_event("roles", f"Rol actualizado: {rol.nombre}")
        permisos = [PermisoRead.model_validate(rp.permiso) for rp in rol.permisos]
        return RolRead(id=rol.id, nombre=rol.nombre, descripcion=rol.descripcion, activo=rol.activo, permisos=permisos)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Nombre de rol duplicado")
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al actualizar rol: {str(e)}")


@router.delete("/roles/{rol_id}", status_code=204, dependencies=[Depends(require_admin_or_manager)])
def eliminar_rol(rol_id: int, db: Session = Depends(get_db)):
    rol = db.query(Rol).filter(Rol.id == rol_id).first()
    if not rol:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    try:
        db.delete(rol)
        db.commit()
        log_event("roles", f"Rol eliminado: {rol.nombre}")
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al eliminar rol: {str(e)}")


# Permisos
@router.post("/permisos", response_model=PermisoRead, dependencies=[Depends(require_admin_or_manager)])
def crear_permiso(payload: PermisoCreate, db: Session = Depends(get_db)):
    try:
        p = Permiso(codigo=payload.codigo, nombre=payload.nombre, descripcion=payload.descripcion, activo=payload.activo)
        db.add(p)
        db.commit()
        db.refresh(p)
        log_event("roles", f"Permiso creado: {p.codigo}")
        return p
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Código de permiso ya existe")
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear permiso: {str(e)}")


@router.get("/permisos", response_model=List[PermisoRead], dependencies=[Depends(require_admin_or_manager)])
def listar_permisos(db: Session = Depends(get_db)):
    return db.query(Permiso).all()


@router.patch("/permisos/{permiso_id}", response_model=PermisoRead, dependencies=[Depends(require_admin_or_manager)])
def actualizar_permiso(permiso_id: int, payload: PermisoUpdate, db: Session = Depends(get_db)):
    p = db.query(Permiso).filter(Permiso.id == permiso_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Permiso no encontrado")
    try:
        if payload.nombre is not None:
            p.nombre = payload.nombre
        if payload.descripcion is not None:
            p.descripcion = payload.descripcion
        if payload.activo is not None:
            p.activo = payload.activo
        db.commit()
        db.refresh(p)
        log_event("roles", f"Permiso actualizado: {p.codigo}")
        return p
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Datos inválidos")
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al actualizar permiso: {str(e)}")


@router.delete("/permisos/{permiso_id}", status_code=204, dependencies=[Depends(require_admin_or_manager)])
def eliminar_permiso(permiso_id: int, db: Session = Depends(get_db)):
    p = db.query(Permiso).filter(Permiso.id == permiso_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Permiso no encontrado")
    try:
        db.delete(p)
        db.commit()
        log_event("roles", f"Permiso eliminado: {p.codigo}")
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al eliminar permiso: {str(e)}")


# Asignaciones
@router.post("/roles/{rol_id}/permisos", response_model=RolRead, dependencies=[Depends(require_admin_or_manager)])
def asignar_permisos_a_rol(rol_id: int, payload: AsignarPermisosRequest, db: Session = Depends(get_db)):
    rol = db.query(Rol).filter(Rol.id == rol_id).first()
    if not rol:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    try:
        perms = db.query(Permiso).filter(Permiso.codigo.in_(payload.permisos_codigos)).all()
        existing = {(rp.permiso_id) for rp in rol.permisos}
        for p in perms:
            if p.id not in existing:
                db.add(RolPermiso(rol_id=rol.id, permiso_id=p.id))
        db.commit()
        db.refresh(rol)
        permisos = [PermisoRead.model_validate(rp.permiso) for rp in rol.permisos]
        return RolRead(id=rol.id, nombre=rol.nombre, descripcion=rol.descripcion, activo=rol.activo, permisos=permisos)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al asignar permisos: {str(e)}")


@router.delete("/roles/{rol_id}/permisos", response_model=RolRead, dependencies=[Depends(require_admin_or_manager)])
def quitar_permisos_de_rol(rol_id: int, payload: AsignarPermisosRequest, db: Session = Depends(get_db)):
    rol = db.query(Rol).filter(Rol.id == rol_id).first()
    if not rol:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    try:
        perms = db.query(Permiso).filter(Permiso.codigo.in_(payload.permisos_codigos)).all()
        perm_ids = [p.id for p in perms]
        db.query(RolPermiso).filter(RolPermiso.rol_id == rol.id, RolPermiso.permiso_id.in_(perm_ids)).delete(synchronize_session=False)
        db.commit()
        db.refresh(rol)
        permisos = [PermisoRead.model_validate(rp.permiso) for rp in rol.permisos]
        return RolRead(id=rol.id, nombre=rol.nombre, descripcion=rol.descripcion, activo=rol.activo, permisos=permisos)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al quitar permisos: {str(e)}")


@router.post("/usuarios/{usuario_id}/roles", dependencies=[Depends(require_admin_or_manager)])
def asignar_roles_a_usuario(usuario_id: int, payload: AsignarRolesRequest, db: Session = Depends(get_db)):
    user = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    try:
        roles = db.query(Rol).filter(Rol.nombre.in_(payload.roles_nombres)).all()
        existing = {(ur.rol_id) for ur in user.roles}
        for r in roles:
            if r.id not in existing:
                db.add(UsuarioRol(usuario_id=user.id, rol_id=r.id))
        db.commit()
        log_event("roles", f"Roles asignados a usuario {user.username}")
        return {"message": "Roles asignados"}
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al asignar roles: {str(e)}")


@router.delete("/usuarios/{usuario_id}/roles", dependencies=[Depends(require_admin_or_manager)])
def quitar_roles_de_usuario(usuario_id: int, payload: AsignarRolesRequest, db: Session = Depends(get_db)):
    user = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    try:
        roles = db.query(Rol).filter(Rol.nombre.in_(payload.roles_nombres)).all()
        role_ids = [r.id for r in roles]
        db.query(UsuarioRol).filter(UsuarioRol.usuario_id == user.id, UsuarioRol.rol_id.in_(role_ids)).delete(synchronize_session=False)
        db.commit()
        log_event("roles", f"Roles quitados de usuario {user.username}")
        return {"message": "Roles removidos"}
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al remover roles: {str(e)}")
