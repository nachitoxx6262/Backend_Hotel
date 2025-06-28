from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from database import conexion
from models.cliente import Cliente
from models.empresa import Empresa
from models.reserva import Reserva
from schemas.clientes import ClienteCreate, ClienteUpdate, ClienteRead
import datetime

router = APIRouter()

def log_accion(usuario, accion, detalle=""):
    # Reemplaza por un logger real si querés logs en archivo/base
    print(f"CLIENTE [{datetime.datetime.now()}] Usuario: {usuario} | Acción: {accion} | Detalle: {detalle}")

    log_entry = f"CLIENTE [{datetime.datetime.now()}] Usuario: {usuario} | Acción: {accion} | Detalle: {detalle}\n"
    with open("hotel_logs.txt", "a", encoding="utf-8") as f:
        f.write(log_entry)


# --- Listar clientes no eliminados ---
@router.get("/clientes", response_model=List[ClienteRead])
def listar_clientes(db: Session = Depends(conexion.get_db)):
    log_accion("admin", "Listar clientes")
    return db.query(Cliente).filter(Cliente.deleted == False).all()

# --- Obtener cliente por ID ---
@router.get("/clientes/{cliente_id}", response_model=ClienteRead)
def obtener_cliente(cliente_id: int, db: Session = Depends(conexion.get_db)):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id, Cliente.deleted == False).first()
    log_accion("admin", "Obtener cliente", f"id={cliente_id}")
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return cliente

# --- Crear cliente ---
@router.post("/clientes", response_model=ClienteRead, status_code=201)
def crear_cliente(cliente: ClienteCreate, db: Session = Depends(conexion.get_db)):
    existe = db.query(Cliente).filter(
        Cliente.tipo_documento == cliente.tipo_documento,
        Cliente.numero_documento == cliente.numero_documento,
        Cliente.deleted == False
    ).first()
    if existe:
        log_accion("admin", "Intento crear cliente duplicado", f"doc={cliente.tipo_documento}-{cliente.numero_documento}")
        raise HTTPException(
            status_code=409,
            detail="Ya existe un cliente con ese tipo y número de documento."
        )

    if cliente.empresa_id is not None:
        empresa = db.query(Empresa).filter(Empresa.id == cliente.empresa_id).first()
        if not empresa:
            log_accion("admin", "Intento crear cliente con empresa inexistente", f"empresa_id={cliente.empresa_id}")
            raise HTTPException(
                status_code=400,
                detail=f"No existe ninguna empresa con id={cliente.empresa_id}"
            )

    nuevo_cliente = Cliente(**cliente.dict())
    db.add(nuevo_cliente)
    db.commit()
    db.refresh(nuevo_cliente)
    log_accion("admin", "Crear cliente", f"id={nuevo_cliente.id}")
    return nuevo_cliente

# --- Actualizar cliente ---
@router.put("/clientes/{cliente_id}", response_model=ClienteRead)
def actualizar_cliente(cliente_id: int, cliente: ClienteUpdate, db: Session = Depends(conexion.get_db)):
    cliente_db = db.query(Cliente).filter(Cliente.id == cliente_id, Cliente.deleted == False).first()
    if not cliente_db:
        log_accion("admin", "Intento actualizar cliente inexistente", f"id={cliente_id}")
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if (cliente.tipo_documento != cliente_db.tipo_documento or cliente.numero_documento != cliente_db.numero_documento):
        existe = db.query(Cliente).filter(
            Cliente.tipo_documento == cliente.tipo_documento,
            Cliente.numero_documento == cliente.numero_documento,
            Cliente.id != cliente_id,
            Cliente.deleted == False
        ).first()
        if existe:
            log_accion("admin", "Intento duplicar documento en actualización", f"id={cliente_id}")
            raise HTTPException(
                status_code=409,
                detail="Ya existe un cliente con ese tipo y número de documento."
            )
    if cliente.empresa_id is not None:
        empresa = db.query(Empresa).filter(Empresa.id == cliente.empresa_id).first()
        if not empresa:
            log_accion("admin", "Intento actualizar cliente con empresa inexistente", f"empresa_id={cliente.empresa_id}")
            raise HTTPException(
                status_code=400,
                detail=f"No existe ninguna empresa con id={cliente.empresa_id}"
            )
    for campo, valor in cliente.dict().items():
        setattr(cliente_db, campo, valor)
    db.commit()
    db.refresh(cliente_db)
    log_accion("admin", "Actualizar cliente", f"id={cliente_id}")
    return cliente_db

# --- Baja lógica ---
@router.delete("/clientes/{cliente_id}", status_code=204)
def eliminar_cliente(cliente_id: int, db: Session = Depends(conexion.get_db)):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id, Cliente.deleted == False).first()
    if not cliente:
        log_accion("admin", "Intento eliminar cliente inexistente", f"id={cliente_id}")
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    reservas_activas = db.query(Reserva).filter(
        Reserva.cliente_id == cliente_id,
        Reserva.estado.in_(["reservada", "ocupada"])
    ).count()
    if reservas_activas > 0:
        log_accion("admin", "Intento eliminar cliente con reservas activas", f"id={cliente_id}")
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar un cliente con reservas activas."
        )
    cliente.deleted = True
    db.commit()
    log_accion("admin", "Baja lógica cliente", f"id={cliente_id}")
    return

# --- Restaurar cliente (baja lógica inversa) ---
@router.put("/clientes/{cliente_id}/restaurar", response_model=ClienteRead)
def restaurar_cliente(cliente_id: int, db: Session = Depends(conexion.get_db)):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id, Cliente.deleted == True).first()
    if not cliente:
        log_accion("admin", "Intento restaurar cliente inexistente/no eliminado", f"id={cliente_id}")
        raise HTTPException(status_code=404, detail="Cliente no encontrado o no está eliminado")
    cliente.deleted = False
    db.commit()
    db.refresh(cliente)
    log_accion("admin", "Restaurar cliente", f"id={cliente_id}")
    return cliente

# --- Eliminar físico (sólo superadmin) ---
@router.delete("/clientes/{cliente_id}/eliminar-definitivo", status_code=204)
def eliminar_fisico_cliente(cliente_id: int, db: Session = Depends(conexion.get_db), superadmin: bool = Query(False, description="¿Es superadmin?")):
    if not superadmin:
        log_accion("admin", "Intento eliminar físico sin permisos", f"id={cliente_id}")
        raise HTTPException(status_code=403, detail="Solo superadmin puede eliminar físicamente un cliente")
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        log_accion("superadmin", "Intento eliminar físico cliente inexistente", f"id={cliente_id}")
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    db.delete(cliente)
    db.commit()
    log_accion("superadmin", "Eliminación física cliente", f"id={cliente_id}")
    return

# --- Búsqueda avanzada de clientes ---
@router.get("/clientes/buscar", response_model=List[ClienteRead])
def buscar_clientes(
    nombre: Optional[str] = None,
    apellido: Optional[str] = None,
    tipo_documento: Optional[str] = None,
    numero_documento: Optional[str] = None,
    empresa_id: Optional[int] = None,
    db: Session = Depends(conexion.get_db)
):
    query = db.query(Cliente).filter(Cliente.deleted == False)
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
    log_accion("admin", "Buscar clientes", f"criterios={nombre} {apellido} {tipo_documento} {numero_documento} {empresa_id}")
    return resultados
