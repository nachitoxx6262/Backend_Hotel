"""
Empresas Endpoints
Gestión de empresas (clientes corporativos)
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel, Field, field_serializer, EmailStr

from database.conexion import get_db
from models.core import ClienteCorporativo, Reservation, Stay, StayCharge, Room, RoomType
from utils.dependencies import get_current_user

router = APIRouter(prefix="/empresas", tags=["Empresas"])

# --- Schemas ---

class EmpresaBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    cuit: str = Field(..., min_length=1, max_length=20)
    tipo_empresa: Optional[str] = None
    contacto_nombre: Optional[str] = None
    contacto_email: Optional[EmailStr] = None
    contacto_telefono: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    provincia: Optional[str] = None
    activo: bool = True


class EmpresaCreate(EmpresaBase):
    pass


class EmpresaUpdate(BaseModel):
    nombre: Optional[str] = None
    cuit: Optional[str] = None
    tipo_empresa: Optional[str] = None
    contacto_nombre: Optional[str] = None
    contacto_email: Optional[EmailStr] = None
    contacto_telefono: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    provincia: Optional[str] = None
    activo: Optional[bool] = None


class EmpresaRead(EmpresaBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

    @field_serializer('created_at')
    def serialize_created_at(self, value: datetime) -> str:
        """Convert datetime to ISO string"""
        return value.isoformat() if value else None


# --- Endpoints ---

@router.get("", response_model=List[EmpresaRead])
def list_empresas(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Listar empresas activas"""
    if not current_user or not current_user.empresa_usuario_id:
        raise HTTPException(status_code=401, detail="No autenticado o sin tenant asociado")
    
    tenant_id = current_user.empresa_usuario_id
    empresas = db.query(ClienteCorporativo).filter(
        ClienteCorporativo.empresa_usuario_id == tenant_id,
        ClienteCorporativo.activo == True
    ).order_by(ClienteCorporativo.nombre).all()  # noqa: E712
    return empresas


@router.get("/eliminadas", response_model=List[EmpresaRead])
def list_deleted_empresas(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Listar empresas eliminadas (inactivas)"""
    if not current_user or not current_user.empresa_usuario_id:
        raise HTTPException(status_code=401, detail="No autenticado o sin tenant asociado")
    
    tenant_id = current_user.empresa_usuario_id
    empresas = db.query(ClienteCorporativo).filter(
        ClienteCorporativo.empresa_usuario_id == tenant_id,
        ClienteCorporativo.activo == False
    ).all()  # noqa: E712
    return empresas


@router.post("", response_model=EmpresaRead, status_code=status.HTTP_201_CREATED)
def create_empresa(
    data: EmpresaCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Crear nueva empresa"""
    if not current_user or not current_user.empresa_usuario_id:
        raise HTTPException(status_code=401, detail="No autenticado o sin tenant asociado")
    
    tenant_id = current_user.empresa_usuario_id
    
    # Validar CUIT único dentro del tenant
    existing = db.query(ClienteCorporativo).filter(
        ClienteCorporativo.empresa_usuario_id == tenant_id,
        ClienteCorporativo.cuit == data.cuit
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ya existe una empresa con este CUIT")

    empresa = ClienteCorporativo(
        empresa_usuario_id=tenant_id,
        nombre=data.nombre.strip(),
        cuit=data.cuit.strip(),
        tipo_empresa=data.tipo_empresa,
        contacto_nombre=data.contacto_nombre,
        contacto_email=data.contacto_email,
        contacto_telefono=data.contacto_telefono,
        direccion=data.direccion,
        ciudad=data.ciudad,
        provincia=data.provincia,
        activo=data.activo,
    )

    db.add(empresa)
    db.commit()
    db.refresh(empresa)
    return empresa


@router.put("/{empresa_id}", response_model=EmpresaRead)
def update_empresa(
    empresa_id: int = Path(..., gt=0),
    data: EmpresaUpdate = ...,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Actualizar empresa"""
    if not current_user or not current_user.empresa_usuario_id:
        raise HTTPException(status_code=401, detail="No autenticado o sin tenant asociado")
    
    tenant_id = current_user.empresa_usuario_id
    
    empresa = db.query(ClienteCorporativo).filter(
        ClienteCorporativo.id == empresa_id,
        ClienteCorporativo.empresa_usuario_id == tenant_id
    ).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    # Validar CUIT único dentro del tenant (si cambió)
    if data.cuit and data.cuit != empresa.cuit:
        existing = db.query(ClienteCorporativo).filter(
            ClienteCorporativo.empresa_usuario_id == tenant_id,
            ClienteCorporativo.cuit == data.cuit
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Ya existe una empresa con este CUIT")

    # Actualizar solo campos no-None
    if data.nombre is not None:
        empresa.nombre = data.nombre.strip()
    if data.cuit is not None:
        empresa.cuit = data.cuit.strip()
    if data.tipo_empresa is not None:
        empresa.tipo_empresa = data.tipo_empresa
    if data.contacto_nombre is not None:
        empresa.contacto_nombre = data.contacto_nombre
    if data.contacto_email is not None:
        empresa.contacto_email = data.contacto_email
    if data.contacto_telefono is not None:
        empresa.contacto_telefono = data.contacto_telefono
    if data.direccion is not None:
        empresa.direccion = data.direccion
    if data.ciudad is not None:
        empresa.ciudad = data.ciudad
    if data.provincia is not None:
        empresa.provincia = data.provincia
    if data.activo is not None:
        empresa.activo = data.activo

    db.commit()
    db.refresh(empresa)
    return empresa


@router.delete("/{empresa_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_empresa(
    empresa_id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Eliminar (soft delete) empresa"""
    if not current_user or not current_user.empresa_usuario_id:
        raise HTTPException(status_code=401, detail="No autenticado o sin tenant asociado")
    
    tenant_id = current_user.empresa_usuario_id
    
    empresa = db.query(ClienteCorporativo).filter(
        ClienteCorporativo.id == empresa_id,
        ClienteCorporativo.empresa_usuario_id == tenant_id
    ).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    empresa.activo = False
    db.commit()


@router.put("/{empresa_id}/restaurar", response_model=EmpresaRead)
def restore_empresa(
    empresa_id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Restaurar empresa eliminada"""
    if not current_user or not current_user.empresa_usuario_id:
        raise HTTPException(status_code=401, detail="No autenticado o sin tenant asociado")
    
    tenant_id = current_user.empresa_usuario_id
    
    empresa = db.query(ClienteCorporativo).filter(
        ClienteCorporativo.id == empresa_id,
        ClienteCorporativo.empresa_usuario_id == tenant_id
    ).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    empresa.activo = True
    db.commit()
    db.refresh(empresa)
    return empresa


@router.get("/{empresa_id}", response_model=EmpresaRead)
def get_empresa(
    empresa_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Obtener empresa por ID"""
    if not current_user or not current_user.empresa_usuario_id:
        raise HTTPException(status_code=401, detail="No autenticado o sin tenant asociado")
    
    tenant_id = current_user.empresa_usuario_id
    
    empresa = db.query(ClienteCorporativo).filter(
        ClienteCorporativo.id == empresa_id,
        ClienteCorporativo.empresa_usuario_id == tenant_id
    ).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return empresa


# --- Schemas para Detalles ---

class CargoDetail(BaseModel):
    id: Optional[int] = None
    descripcion: str
    monto: float
    pagado: float = 0
    fecha: Optional[str] = None  # Fecha del cargo


class ReservacionDetail(BaseModel):
    id: int
    stay_id: Optional[int] = None  # ID de la estadía
    huesped_nombre: Optional[str]
    habitacion_numero: Optional[int]
    fecha_inicio: datetime
    fecha_fin: datetime
    estado: str
    monto: float


class EmpresaDetallesResponse(BaseModel):
    ocupacion: dict  # {"Standard": 2, "Suite": 1, ...}
    cargos: List[CargoDetail]
    reservaciones: List[ReservacionDetail]


# --- Endpoint de Detalles ---

@router.get("/{empresa_id}/detalles", response_model=EmpresaDetallesResponse)
def get_empresa_detalles(
    empresa_id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Obtener detalles de ocupación, cargos y reservaciones de una empresa"""
    
    if not current_user or not current_user.empresa_usuario_id:
        raise HTTPException(status_code=401, detail="No autenticado o sin tenant asociado")
    
    tenant_id = current_user.empresa_usuario_id
    
    # Verificar que la empresa existe y pertenece al tenant
    empresa = db.query(ClienteCorporativo).filter(
        ClienteCorporativo.id == empresa_id,
        ClienteCorporativo.empresa_usuario_id == tenant_id
    ).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    # Obtener ocupación por tipo de habitación
    # Contar habitaciones activas por tipo de empresa
    ocupacion = {}
    
    stays = db.query(Stay).filter(
        Stay.empresa_usuario_id == tenant_id,
        Stay.reservation.has(
            Reservation.empresa_id == empresa_id,
            Reservation.empresa_usuario_id == tenant_id
        ),
        Stay.estado.in_(["ocupada", "pendiente_checkout"])  # Estados donde está ocupada
    ).all()
    
    for stay in stays:
        for room_ocupancy in stay.occupancies:
            room = room_ocupancy.room
            room_type_name = room.tipo.nombre if room.tipo else "Desconocida"
            ocupacion[room_type_name] = ocupacion.get(room_type_name, 0) + 1

    # Obtener cargos pendientes
    cargos_list = []
    
    stays_con_cargos = db.query(Stay).filter(
        Stay.empresa_usuario_id == tenant_id,
        Stay.reservation.has(
            Reservation.empresa_id == empresa_id,
            Reservation.empresa_usuario_id == tenant_id
        ),
    ).all()
    
    for stay in stays_con_cargos:
        for charge in stay.charges:
            # Calcular monto pagado para este cargo
            total_pagado = sum(
                float(p.monto) for p in stay.payments 
                if not p.es_reverso
            )
            
            # Formatear fecha del cargo
            fecha_cargo = charge.created_at.strftime('%Y-%m-%d') if charge.created_at else None
            
            cargos_list.append(CargoDetail(
                id=charge.id,
                descripcion=charge.descripcion or f"{charge.tipo.upper()}",
                monto=float(charge.monto_total or 0),
                pagado=total_pagado,  # Simplificado: repartir entre todos los cargos
                fecha=fecha_cargo
            ))

    # Obtener reservaciones activas
    reservaciones_list = []
    
    reservas = db.query(Reservation).filter(
        Reservation.empresa_id == empresa_id,
        Reservation.empresa_usuario_id == tenant_id,
        Reservation.estado.in_(["confirmada", "ocupada", "draft"])
    ).all()
    
    for res in reservas:
        # Obtener huésped: priorizar titular de la reserva, luego primer huésped con cliente
        huesped_nombre = None
        if res.cliente:
            huesped_nombre = " ".join(filter(None, [res.cliente.nombre, res.cliente.apellido]))
        elif res.guests:
            for guest in res.guests:
                if guest.cliente:
                    huesped_nombre = " ".join(filter(None, [guest.cliente.nombre, guest.cliente.apellido]))
                    break
        
        # Obtener la primera habitación asignada
        habitacion_numero = None
        if res.rooms:
            first_room = res.rooms[0].room if res.rooms[0].room else None
            habitacion_numero = getattr(first_room, "numero", None)
        
        # Calcular monto sumando cargos de las stays vinculadas a la reserva
        monto_total = 0
        stay_id_principal = None
        stays_reserva = db.query(Stay).filter(
            Stay.reservation_id == res.id,
            Stay.empresa_usuario_id == tenant_id
        ).all()
        for stay in stays_reserva:
            if stay_id_principal is None:
                stay_id_principal = stay.id  # Usar la primera estadía encontrada
            monto_total += sum(float(c.monto_total or 0) for c in stay.charges)
        
        reservaciones_list.append(ReservacionDetail(
            id=res.id,
            stay_id=stay_id_principal,
            huesped_nombre=huesped_nombre or res.nombre_temporal,
            habitacion_numero=habitacion_numero,
            fecha_inicio=res.fecha_checkin,
            fecha_fin=res.fecha_checkout,
            estado=res.estado,
            monto=monto_total
        ))

    return EmpresaDetallesResponse(
        ocupacion=ocupacion,
        cargos=cargos_list,
        reservaciones=reservaciones_list
    )
