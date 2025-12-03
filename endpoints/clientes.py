from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from database import conexion
from models.cliente import Cliente
from models.empresa import Empresa
from models.reserva import Reserva
from schemas.clientes import ClienteCreate, ClienteUpdate, ClienteRead
from utils.logging_utils import log_event


router = APIRouter()
ACTIVE_RESERVATION_STATES = ("reservada", "ocupada")


def _buscar_cliente(db: Session, cliente_id: int, include_deleted: bool = False) -> Optional[Cliente]:
    query = db.query(Cliente).filter(Cliente.id == cliente_id)
    if not include_deleted:
        query = query.filter(Cliente.deleted.is_(False))
    return query.first()


def _validar_empresa_existente(db: Session, empresa_id: Optional[int]) -> None:
    if empresa_id is None:
        return
    empresa = (
        db.query(Empresa)
        .filter(Empresa.id == empresa_id, Empresa.deleted.is_(False))
        .first()
    )
    if not empresa:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No existe una empresa activa con id={empresa_id}",
        )
    if empresa.blacklist:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La empresa {empresa_id} se encuentra en blacklist",
        )


def _tiene_reservas_activas(db: Session, cliente_id: int) -> bool:
    return (
        db.query(Reserva)
        .filter(
            Reserva.cliente_id == cliente_id,
            Reserva.deleted.is_(False),
            Reserva.estado.in_(ACTIVE_RESERVATION_STATES),
        )
        .count()
        > 0
    )


@router.get(
    "/clientes/eliminados",
    tags=["Eliminar clientes"],
    response_model=List[ClienteRead],
)
def listar_clientes_eliminados(db: Session = Depends(conexion.get_db)):
    clientes = db.query(Cliente).filter(Cliente.deleted.is_(True)).all()
    log_event("clientes", "admin", "Listar clientes eliminados", f"total={len(clientes)}")
    return clientes


@router.delete(
    "/clientes/{cliente_id}",
    tags=["Eliminar clientes"],
    status_code=status.HTTP_204_NO_CONTENT,
)
def eliminar_cliente_logico(
    cliente_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    cliente = _buscar_cliente(db, cliente_id)
    if not cliente:
        log_event("clientes", "admin", "Intento eliminar cliente inexistente", f"id={cliente_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
    if _tiene_reservas_activas(db, cliente_id):
        log_event("clientes", "admin", "Intento eliminar cliente con reservas activas", f"id={cliente_id}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar un cliente con reservas activas",
        )
    cliente.deleted = True
    db.commit()
    log_event("clientes", "admin", "Baja logica cliente", f"id={cliente_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/clientes/{cliente_id}/restaurar",
    tags=["Eliminar clientes"],
    response_model=ClienteRead,
)
def restaurar_cliente(
    cliente_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    cliente = (
        db.query(Cliente)
        .filter(Cliente.id == cliente_id, Cliente.deleted.is_(True))
        .first()
    )
    if not cliente:
        log_event(
            "clientes",
            "admin",
            "Intento restaurar cliente inexistente o activo",
            f"id={cliente_id}",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado o no eliminado",
        )
    cliente.deleted = False
    db.commit()
    db.refresh(cliente)
    log_event("clientes", "admin", "Restaurar cliente", f"id={cliente_id}")
    return cliente


@router.delete(
    "/clientes/{cliente_id}/eliminar-definitivo",
    tags=["Eliminar clientes"],
    status_code=status.HTTP_204_NO_CONTENT,
)
def eliminar_fisico_cliente(
    cliente_id: int = Path(..., gt=0),
    superadmin: bool = Query(False, description="Debe ser True para eliminar definitivamente"),
    db: Session = Depends(conexion.get_db),
):
    if not superadmin:
        log_event("clientes", "admin", "Intento eliminar fisico sin permiso", f"id={cliente_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo superadmin puede eliminar fisicamente un cliente",
        )
    cliente = _buscar_cliente(db, cliente_id, include_deleted=True)
    if not cliente:
        log_event("clientes", "superadmin", "Intento eliminar cliente inexistente", f"id={cliente_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
    if db.query(Reserva).filter(Reserva.cliente_id == cliente_id).count() > 0:
        log_event(
            "clientes",
            "superadmin",
            "Intento eliminar cliente con reservas registradas",
            f"id={cliente_id}",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar el cliente porque existen reservas asociadas",
        )
    db.delete(cliente)
    db.commit()
    log_event("clientes", "superadmin", "Eliminacion fisica cliente", f"id={cliente_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/clientes/blacklist",
    tags=["Blacklist clientes"],
    response_model=List[ClienteRead],
)
def listar_clientes_blacklist(db: Session = Depends(conexion.get_db)):
    clientes = (
        db.query(Cliente)
        .filter(Cliente.blacklist.is_(True), Cliente.deleted.is_(False))
        .all()
    )
    log_event("clientes", "admin", "Listar clientes en blacklist", f"total={len(clientes)}")
    return clientes


@router.put(
    "/clientes/{cliente_id}/blacklist",
    tags=["Blacklist clientes"],
    response_model=ClienteRead,
)
def poner_cliente_blacklist(
    cliente_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    cliente = _buscar_cliente(db, cliente_id)
    if not cliente:
        log_event("clientes", "admin", "Intento poner en blacklist cliente inexistente", f"id={cliente_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
    if cliente.blacklist:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El cliente ya esta en blacklist")
    cliente.blacklist = True
    db.commit()
    db.refresh(cliente)
    log_event("clientes", "admin", "Poner cliente en blacklist", f"id={cliente_id}")
    return cliente


@router.put(
    "/clientes/{cliente_id}/quitar-blacklist",
    tags=["Blacklist clientes"],
    response_model=ClienteRead,
)
def quitar_cliente_blacklist(
    cliente_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    cliente = _buscar_cliente(db, cliente_id)
    if not cliente:
        log_event("clientes", "admin", "Intento quitar de blacklist cliente inexistente", f"id={cliente_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
    if not cliente.blacklist:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El cliente no esta en blacklist")
    cliente.blacklist = False
    db.commit()
    db.refresh(cliente)
    log_event("clientes", "admin", "Quitar cliente de blacklist", f"id={cliente_id}")
    return cliente


@router.get("/clientes/resumen", tags=["Clientes"])
def resumen_clientes(db: Session = Depends(conexion.get_db)):
    total = db.query(Cliente).count()
    activos = db.query(Cliente).filter(Cliente.deleted.is_(False)).count()
    eliminados = db.query(Cliente).filter(Cliente.deleted.is_(True)).count()
    blacklist = db.query(Cliente).filter(Cliente.blacklist.is_(True)).count()
    log_event(
        "clientes",
        "admin",
        "Resumen clientes",
        f"total={total} activos={activos} eliminados={eliminados} blacklist={blacklist}",
    )
    return {
        "total": total,
        "activos": activos,
        "eliminados": eliminados,
        "blacklist": blacklist,
    }


@router.get("/clientes/existe", tags=["Clientes"])
def verificar_existencia_cliente(
    tipo_documento: str = Query(..., min_length=2, max_length=20, strip_whitespace=True),
    numero_documento: str = Query(..., min_length=2, max_length=40, strip_whitespace=True),
    db: Session = Depends(conexion.get_db),
):
    existe = (
        db.query(Cliente)
        .filter(
            Cliente.tipo_documento == tipo_documento,
            Cliente.numero_documento == numero_documento,
            Cliente.deleted.is_(False),
        )
        .first()
        is not None
    )
    log_event(
        "clientes",
        "admin",
        "Verificar existencia cliente",
        f"tipo={tipo_documento} numero={numero_documento} existe={existe}",
    )
    return {"existe": existe}


@router.get(
    "/clientes/sin-empresa",
    tags=["Clientes"],
    response_model=List[ClienteRead],
)
def listar_clientes_sin_empresa(db: Session = Depends(conexion.get_db)):
    clientes = (
        db.query(Cliente)
        .filter(Cliente.empresa_id.is_(None), Cliente.deleted.is_(False))
        .all()
    )
    log_event("clientes", "admin", "Listar clientes sin empresa", f"total={len(clientes)}")
    return clientes


@router.get("/clientes", tags=["Clientes"], response_model=List[ClienteRead])
def listar_clientes(db: Session = Depends(conexion.get_db)):
    clientes = db.query(Cliente).filter(Cliente.deleted.is_(False)).all()
    log_event("clientes", "admin", "Listar clientes", f"total={len(clientes)}")
    return clientes


@router.get("/clientes/buscar", tags=["Clientes"], response_model=List[ClienteRead])
def buscar_clientes(
    nombre: Optional[str] = Query(None, min_length=1, max_length=60, strip_whitespace=True),
    apellido: Optional[str] = Query(None, min_length=1, max_length=60, strip_whitespace=True),
    tipo_documento: Optional[str] = Query(None, min_length=2, max_length=20, strip_whitespace=True),
    numero_documento: Optional[str] = Query(None, min_length=2, max_length=40, strip_whitespace=True),
    empresa_id: Optional[int] = Query(None, gt=0),
    db: Session = Depends(conexion.get_db),
):
    query = db.query(Cliente).filter(Cliente.deleted.is_(False))
    if nombre:
        query = query.filter(Cliente.nombre.ilike(f"%{nombre}%"))
    if apellido:
        query = query.filter(Cliente.apellido.ilike(f"%{apellido}%"))
    if tipo_documento:
        query = query.filter(Cliente.tipo_documento.ilike(f"%{tipo_documento}%"))
    if numero_documento:
        query = query.filter(Cliente.numero_documento.ilike(f"%{numero_documento}%"))
    if empresa_id:
        query = query.filter(Cliente.empresa_id == empresa_id)
    resultados = query.all()
    log_event(
        "clientes",
        "admin",
        "Buscar clientes",
        f"nombre={nombre} apellido={apellido} tipo={tipo_documento} numero={numero_documento} empresa={empresa_id} total={len(resultados)}",
    )
    return resultados


@router.get(
    "/clientes/{cliente_id}",
    tags=["Clientes"],
    response_model=ClienteRead,
)
def obtener_cliente(
    cliente_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    cliente = _buscar_cliente(db, cliente_id)
    if not cliente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
    log_event("clientes", "admin", "Obtener cliente", f"id={cliente_id}")
    return cliente


@router.post(
    "/clientes",
    tags=["Clientes"],
    response_model=ClienteRead,
    status_code=status.HTTP_201_CREATED,
)
def crear_cliente(cliente: ClienteCreate, db: Session = Depends(conexion.get_db)):
    existe = (
        db.query(Cliente)
        .filter(
            Cliente.tipo_documento == cliente.tipo_documento,
            Cliente.numero_documento == cliente.numero_documento,
            Cliente.deleted.is_(False),
        )
        .first()
    )
    if existe:
        log_event(
            "clientes",
            "admin",
            "Intento crear cliente duplicado",
            f"doc={cliente.tipo_documento}-{cliente.numero_documento}",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un cliente con ese tipo y numero de documento",
        )
    _validar_empresa_existente(db, cliente.empresa_id)
    nuevo_cliente = Cliente(**cliente.dict())
    db.add(nuevo_cliente)
    db.commit()
    db.refresh(nuevo_cliente)
    log_event("clientes", "admin", "Crear cliente", f"id={nuevo_cliente.id}")
    return nuevo_cliente


@router.put(
    "/clientes/{cliente_id}",
    tags=["Clientes"],
    response_model=ClienteRead,
)
def actualizar_cliente(
    cliente: ClienteUpdate,
    cliente_id: int = Path(..., gt=0),
    db: Session = Depends(conexion.get_db),
):
    cliente_db = _buscar_cliente(db, cliente_id)
    if not cliente_db:
        log_event("clientes", "admin", "Intento actualizar cliente inexistente", f"id={cliente_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
    datos = cliente.dict(exclude_unset=True)
    nuevo_tipo = datos.get("tipo_documento", cliente_db.tipo_documento)
    nuevo_numero = datos.get("numero_documento", cliente_db.numero_documento)
    if (nuevo_tipo, nuevo_numero) != (cliente_db.tipo_documento, cliente_db.numero_documento):
        existe = (
            db.query(Cliente)
            .filter(
                Cliente.tipo_documento == nuevo_tipo,
                Cliente.numero_documento == nuevo_numero,
                Cliente.id != cliente_id,
                Cliente.deleted.is_(False),
            )
            .first()
        )
        if existe:
            log_event("clientes", "admin", "Intento duplicar documento en actualizacion", f"id={cliente_id}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe un cliente con ese tipo y numero de documento",
            )
    if "empresa_id" in datos:
        _validar_empresa_existente(db, datos["empresa_id"])
    for campo, valor in datos.items():
        setattr(cliente_db, campo, valor)
    db.commit()
    db.refresh(cliente_db)
    log_event("clientes", "admin", "Actualizar cliente", f"id={cliente_id}")
    return cliente_db

