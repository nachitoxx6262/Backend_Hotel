from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from database import conexion
from models.empresa import Empresa
from models.reserva import Reserva
from models.cliente import Cliente
from schemas.empresas import EmpresaCreate, EmpresaUpdate, EmpresaRead
from utils.logging_utils import log_event


router = APIRouter()
ACTIVE_RESERVATION_STATES = ("reservada", "ocupada")


def _buscar_empresa(db: Session, empresa_id: int, include_deleted: bool = False) -> Optional[Empresa]:
    query = db.query(Empresa).filter(Empresa.id == empresa_id)
    if not include_deleted:
        query = query.filter(Empresa.deleted.is_(False))
    return query.first()


def _tiene_reservas_activas(db: Session, empresa_id: int) -> bool:
    return (
        db.query(Reserva)
        .filter(
            Reserva.empresa_id == empresa_id,
            Reserva.deleted.is_(False),
            Reserva.estado.in_(ACTIVE_RESERVATION_STATES),
        )
        .count()
        > 0
    )


def _tiene_clientes_asociados(db: Session, empresa_id: int) -> bool:
    return db.query(Cliente).filter(Cliente.empresa_id == empresa_id).count() > 0


@router.get(
    "/empresas/eliminadas",
    tags=["Eliminar empresas"],
    response_model=List[EmpresaRead],
)
def listar_empresas_eliminadas(db: Session = Depends(conexion.get_db)):
    empresas = db.query(Empresa).filter(Empresa.deleted.is_(True)).all()
    log_event("empresas", "admin", "Listar empresas eliminadas", f"total={len(empresas)}")
    return empresas


@router.delete(
    "/empresas/{empresa_id}",
    tags=["Eliminar empresas"],
    status_code=status.HTTP_204_NO_CONTENT,
)
def eliminar_empresa(
    empresa_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    try:
        empresa = _buscar_empresa(db, empresa_id)
        if not empresa:
            log_event("empresas", "admin", "Intento eliminar empresa inexistente", f"id={empresa_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada")
        if _tiene_reservas_activas(db, empresa_id):
            log_event("empresas", "admin", "Intento eliminar empresa con reservas activas", f"id={empresa_id}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No se puede eliminar una empresa con reservas activas",
            )
        empresa.deleted = True
        db.commit()
        log_event("empresas", "admin", "Baja logica empresa", f"id={empresa_id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        log_event("empresas", "admin", "Error al eliminar empresa", f"id={empresa_id} error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al procesar la eliminación de la empresa"
        )


@router.put(
    "/empresas/{empresa_id}/restaurar",
    tags=["Eliminar empresas"],
    response_model=EmpresaRead,
)
def restaurar_empresa(
    empresa_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    empresa = (
        db.query(Empresa)
        .filter(Empresa.id == empresa_id, Empresa.deleted.is_(True))
        .first()
    )
    if not empresa:
        log_event(
            "empresas",
            "admin",
            "Intento restaurar empresa inexistente o activa",
            f"id={empresa_id}",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa no encontrada o no eliminada",
        )
    empresa.deleted = False
    db.commit()
    db.refresh(empresa)
    log_event("empresas", "admin", "Restaurar empresa", f"id={empresa_id}")
    return empresa


@router.delete(
    "/empresas/{empresa_id}/eliminar-definitivo",
    tags=["Eliminar empresas"],
    status_code=status.HTTP_204_NO_CONTENT,
)
def eliminar_fisico_empresa(
    empresa_id: int = Path(..., gt=0),
    superadmin: bool = Query(False, description="Debe ser True para eliminar definitivamente"),
    db: Session = Depends(conexion.get_db),
):
    if not superadmin:
        log_event("empresas", "admin", "Intento eliminar fisico sin permiso", f"id={empresa_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo superadmin puede eliminar fisicamente una empresa",
        )
    empresa = _buscar_empresa(db, empresa_id, include_deleted=True)
    if not empresa:
        log_event("empresas", "superadmin", "Intento eliminar empresa inexistente", f"id={empresa_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada")
    if db.query(Reserva).filter(Reserva.empresa_id == empresa_id).count() > 0:
        log_event(
            "empresas",
            "superadmin",
            "Intento eliminar empresa con reservas registradas",
            f"id={empresa_id}",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar la empresa porque existen reservas asociadas",
        )
    if _tiene_clientes_asociados(db, empresa_id):
        log_event(
            "empresas",
            "superadmin",
            "Intento eliminar empresa con clientes asociados",
            f"id={empresa_id}",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar la empresa porque existen clientes asociados",
        )
    db.delete(empresa)
    db.commit()
    log_event("empresas", "superadmin", "Eliminacion fisica empresa", f"id={empresa_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/empresas/blacklist",
    tags=["Blacklist empresas"],
    response_model=List[EmpresaRead],
)
def listar_empresas_blacklist(db: Session = Depends(conexion.get_db)):
    empresas = (
        db.query(Empresa)
        .filter(Empresa.blacklist.is_(True), Empresa.deleted.is_(False))
        .all()
    )
    log_event("empresas", "admin", "Listar empresas en blacklist", f"total={len(empresas)}")
    return empresas


@router.put(
    "/empresas/{empresa_id}/blacklist",
    tags=["Blacklist empresas"],
    response_model=EmpresaRead,
)
def poner_empresa_blacklist(
    empresa_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    empresa = _buscar_empresa(db, empresa_id)
    if not empresa:
        log_event("empresas", "admin", "Intento poner en blacklist empresa inexistente", f"id={empresa_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada")
    if empresa.blacklist:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La empresa ya esta en blacklist")
    empresa.blacklist = True
    db.commit()
    db.refresh(empresa)
    log_event("empresas", "admin", "Poner empresa en blacklist", f"id={empresa_id}")
    return empresa


@router.put(
    "/empresas/{empresa_id}/quitar-blacklist",
    tags=["Blacklist empresas"],
    response_model=EmpresaRead,
)
def quitar_empresa_blacklist(
    empresa_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    empresa = _buscar_empresa(db, empresa_id)
    if not empresa:
        log_event("empresas", "admin", "Intento quitar de blacklist empresa inexistente", f"id={empresa_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada")
    if not empresa.blacklist:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La empresa no esta en blacklist")
    empresa.blacklist = False
    db.commit()
    db.refresh(empresa)
    log_event("empresas", "admin", "Quitar empresa de blacklist", f"id={empresa_id}")
    return empresa


@router.get("/empresas/resumen", tags=["Empresas"])
def resumen_empresas(db: Session = Depends(conexion.get_db)):
    total = db.query(Empresa).count()
    activas = db.query(Empresa).filter(Empresa.deleted.is_(False)).count()
    eliminadas = db.query(Empresa).filter(Empresa.deleted.is_(True)).count()
    blacklist = db.query(Empresa).filter(Empresa.blacklist.is_(True)).count()
    log_event(
        "empresas",
        "admin",
        "Resumen empresas",
        f"total={total} activas={activas} eliminadas={eliminadas} blacklist={blacklist}",
    )
    return {
        "total": total,
        "activas": activas,
        "eliminadas": eliminadas,
        "blacklist": blacklist,
    }


@router.get("/empresas/existe", tags=["Empresas"])
def verificar_empresa_por_cuit(
    cuit: str = Query(..., min_length=6, max_length=20, strip_whitespace=True),
    db: Session = Depends(conexion.get_db),
):
    existe = (
        db.query(Empresa)
        .filter(Empresa.cuit == cuit, Empresa.deleted.is_(False))
        .first()
        is not None
    )
    log_event("empresas", "admin", "Verificar existencia empresa por CUIT", f"cuit={cuit} existe={existe}")
    return {"existe": existe}


@router.get(
    "/empresas/buscar-exacta",
    tags=["Empresas"],
    response_model=Optional[EmpresaRead],
)
def buscar_empresa_exacta(
    nombre: Optional[str] = Query(None, min_length=1, max_length=100, strip_whitespace=True),
    cuit: Optional[str] = Query(None, min_length=6, max_length=20, strip_whitespace=True),
    db: Session = Depends(conexion.get_db),
):
    query = db.query(Empresa).filter(Empresa.deleted.is_(False))
    if nombre:
        query = query.filter(Empresa.nombre == nombre)
    if cuit:
        query = query.filter(Empresa.cuit == cuit)
    empresa = query.first()
    log_event("empresas", "admin", "Buscar empresa exacta", f"nombre={nombre} cuit={cuit} encontrada={empresa is not None}")
    return empresa


@router.get("/empresas", tags=["Empresas"], response_model=List[EmpresaRead])
def listar_empresas(db: Session = Depends(conexion.get_db)):
    empresas = db.query(Empresa).filter(Empresa.deleted.is_(False)).all()
    log_event("empresas", "admin", "Listar empresas", f"total={len(empresas)}")
    return empresas


@router.post(
    "/empresas",
    tags=["Empresas"],
    response_model=EmpresaRead,
    status_code=status.HTTP_201_CREATED,
)
def crear_empresa(empresa: EmpresaCreate, db: Session = Depends(conexion.get_db)):
    try:
        # Validaciones de integridad
        if not empresa.nombre.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El nombre de la empresa no puede estar vacío"
            )
        if not empresa.cuit.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El CUIT de la empresa no puede estar vacío"
            )
        if not empresa.contacto_principal_nombre.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El nombre del contacto principal es requerido"
            )
        if not empresa.direccion.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La dirección de la empresa es requerida"
            )
        if not empresa.ciudad.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La ciudad de la empresa es requerida"
            )
        
        # Verificar CUIT duplicado
        existe = (
            db.query(Empresa)
            .filter(Empresa.cuit == empresa.cuit, Empresa.deleted.is_(False))
            .first()
        )
        if existe:
            log_event("empresas", "admin", "Intento crear empresa duplicada", f"cuit={empresa.cuit}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe una empresa activa con ese CUIT"
            )
        
        # Crear empresa
        nueva_empresa = Empresa(
            **empresa.dict(exclude_unset=True),
            activo=True,
            deleted=False,
            blacklist=False
        )
        
        db.add(nueva_empresa)
        db.commit()
        db.refresh(nueva_empresa)
        log_event("empresas", "admin", "Crear empresa", f"id={nueva_empresa.id} cuit={empresa.cuit}")
        return nueva_empresa
        
    except HTTPException:
        raise
    except IntegrityError as e:
        db.rollback()
        log_event("empresas", "admin", "Error de integridad al crear empresa", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Violación de restricción de integridad (CUIT o email duplicado)"
        )
    except SQLAlchemyError as e:
        db.rollback()
        log_event("empresas", "admin", "Error de BD al crear empresa", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear la empresa en la base de datos"
        )


@router.put(
    "/empresas/{empresa_id}",
    tags=["Empresas"],
    response_model=EmpresaRead,
)
def actualizar_empresa(
    empresa: EmpresaUpdate,
    empresa_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    try:
        empresa_db = _buscar_empresa(db, empresa_id)
        if not empresa_db:
            log_event("empresas", "admin", "Intento actualizar empresa inexistente", f"id={empresa_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Empresa no encontrada"
            )
        
        datos = empresa.dict(exclude_unset=True)
        
        # Validar cambio de CUIT si se proporciona
        if "cuit" in datos:
            nuevo_cuit = datos["cuit"]
            if nuevo_cuit != empresa_db.cuit:
                existe = (
                    db.query(Empresa)
                    .filter(
                        Empresa.cuit == nuevo_cuit,
                        Empresa.id != empresa_id,
                        Empresa.deleted.is_(False),
                    )
                    .first()
                )
                if existe:
                    log_event("empresas", "admin", "Intento duplicar CUIT en actualización", f"cuit={nuevo_cuit}")
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Ya existe otra empresa con ese CUIT"
                    )
        
        # No permitir actualizar deleted y blacklist directamente
        datos.pop("deleted", None)
        datos.pop("blacklist", None)
        
        # Actualizar solo los campos proporcionados
        for campo, valor in datos.items():
            if valor is not None:
                setattr(empresa_db, campo, valor)
        
        # Actualizar marca de tiempo
        empresa_db.actualizado_en = datetime.utcnow()
        
        db.commit()
        db.refresh(empresa_db)
        log_event("empresas", "admin", "Actualizar empresa", f"id={empresa_id} campos={len(datos)}")
        return empresa_db
        
    except HTTPException:
        raise
    except IntegrityError as e:
        db.rollback()
        log_event("empresas", "admin", "Error de integridad al actualizar empresa", f"id={empresa_id} error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Error de integridad (CUIT o email duplicado)"
        )
    except SQLAlchemyError as e:
        db.rollback()
        log_event("empresas", "admin", "Error de BD al actualizar empresa", f"id={empresa_id} error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar la empresa en la base de datos"
        )
    db.commit()
    db.refresh(empresa_db)
    log_event("empresas", "admin", "Actualizar empresa", f"id={empresa_id}")
    return empresa_db


@router.get("/empresas/buscar", tags=["Empresas"], response_model=List[EmpresaRead])
def buscar_empresas(
    nombre: Optional[str] = Query(None, min_length=1, max_length=100, strip_whitespace=True),
    cuit: Optional[str] = Query(None, min_length=6, max_length=20, strip_whitespace=True),
    email: Optional[str] = Query(None, min_length=3, max_length=100, strip_whitespace=True),
    db: Session = Depends(conexion.get_db),
):
    query = db.query(Empresa).filter(Empresa.deleted.is_(False))
    if nombre:
        query = query.filter(Empresa.nombre.ilike(f"%{nombre}%"))
    if cuit:
        query = query.filter(Empresa.cuit.ilike(f"%{cuit}%"))
    if email:
        query = query.filter(Empresa.email.ilike(f"%{email}%"))
    resultados = query.all()
    log_event(
        "empresas",
        "admin",
        "Buscar empresas",
        f"nombre={nombre} cuit={cuit} email={email} total={len(resultados)}",
    )
    return resultados


@router.get(
    "/empresas/{empresa_id}",
    tags=["Empresas"],
    response_model=EmpresaRead,
)
def obtener_empresa(
    empresa_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    empresa = _buscar_empresa(db, empresa_id)
    if not empresa:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada")
    log_event("empresas", "admin", "Obtener empresa", f"id={empresa_id}")
    return empresa

