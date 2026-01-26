from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel, EmailStr

from database.conexion import get_db
from models.core import Cliente
from utils.dependencies import get_current_user

router = APIRouter(prefix="/clientes", tags=["Clientes"])

# --- Schemas ---
class ClienteBase(BaseModel):
    nombre: str
    apellido: str
    tipo_documento: str = "DNI"
    numero_documento: str
    email: Optional[str] = None
    telefono: Optional[str] = None
    nacionalidad: Optional[str] = None
    nota_interna: Optional[str] = None
    blacklist: bool = False
    motivo_blacklist: Optional[str] = None
    activo: bool = True

class ClienteCreate(ClienteBase):
    pass

class ClienteUpdate(BaseModel):
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    tipo_documento: Optional[str] = None
    numero_documento: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    nacionalidad: Optional[str] = None
    nota_interna: Optional[str] = None
    blacklist: Optional[bool] = None
    motivo_blacklist: Optional[str] = None
    activo: Optional[bool] = None

class ClienteRead(ClienteBase):
    id: int

    class Config:
        orm_mode = True

# --- Endpoints ---

@router.get("", response_model=List[ClienteRead])
def get_clientes(
    skip: int = 0,
    limit: int = 50,
    q: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Listar clientes con paginación y búsqueda opcional.
    """
    query = db.query(Cliente).filter(Cliente.activo == True)

    if q:
        search = f"%{q}%"
        query = query.filter(
            or_(
                Cliente.nombre.ilike(search),
                Cliente.apellido.ilike(search),
                Cliente.numero_documento.ilike(search),
                Cliente.email.ilike(search)
            )
        )

    clientes = query.order_by(Cliente.apellido, Cliente.nombre).offset(skip).limit(limit).all()
    return clientes

@router.get("/{cliente_id}", response_model=ClienteRead)
def get_cliente(cliente_id: int, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return cliente

@router.post("", response_model=ClienteRead, status_code=status.HTTP_201_CREATED)
def create_cliente(cliente: ClienteCreate, db: Session = Depends(get_db)):
    # Validar duplicados de documento
    existing = db.query(Cliente).filter(
        Cliente.tipo_documento == cliente.tipo_documento,
        Cliente.numero_documento == cliente.numero_documento
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Ya existe un cliente con ese documento")

    db_cliente = Cliente(**cliente.dict())
    db.add(db_cliente)
    db.commit()
    db.refresh(db_cliente)
    return db_cliente

@router.put("/{cliente_id}", response_model=ClienteRead)
def update_cliente(cliente_id: int, cliente_update: ClienteUpdate, db: Session = Depends(get_db)):
    db_cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not db_cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    update_data = cliente_update.dict(exclude_unset=True)
    
    # Si cambia documento, validar duplicado
    if "numero_documento" in update_data and update_data["numero_documento"] != db_cliente.numero_documento:
         existing = db.query(Cliente).filter(
            Cliente.numero_documento == update_data["numero_documento"],
            Cliente.tipo_documento == update_data.get("tipo_documento", db_cliente.tipo_documento),
            Cliente.id != cliente_id
        ).first()
         if existing:
            raise HTTPException(status_code=400, detail="Ya existe otro cliente con ese documento")

    for key, value in update_data.items():
        setattr(db_cliente, key, value)

    db.commit()
    db.refresh(db_cliente)
    return db_cliente

@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cliente(cliente_id: int, db: Session = Depends(get_db)):
    db_cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not db_cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    
    # Soft delete
    db_cliente.activo = False
    db.commit()
