from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from database import conexion
from models.empresa import Empresa
from models.reserva import Reserva
from schemas.empresas import EmpresaCreate, EmpresaUpdate, EmpresaRead

import os
import datetime

router = APIRouter()

# --- Logger
def log_accion(usuario, accion, detalle=""):
    print(f"EMPRESA [{datetime.datetime.now()}] Usuario: {usuario} | Acción: {accion} | Detalle: {detalle}")
    log_entry = f"EMPRESA [{datetime.datetime.now()}] Usuario: {usuario} | Acción: {accion} | Detalle: {detalle}\n"
    with open("hotel_logs.txt", "a", encoding="utf-8") as f:
        f.write(log_entry)
# ═════════════════════════════════════════════════════════════ #
#
# ║███████╗██╗     ██╗███╗   ███╗██╗███╗   ██╗ █████╗ ██████╗ ║ #
# ║██╔════╝██║     ██║████╗ ████║██║████╗  ██║██╔══██╗██╔══██╗║ #
# ║█████╗  ██║     ██║██╔████╔██║██║██╔██╗ ██║███████║██████╔╝║ #
# ║██╔══╝  ██║     ██║██║╚██╔╝██║██║██║╚██╗██║██╔══██║██╔══██╗║ #
# ║███████╗███████╗██║██║ ╚═╝ ██║██║██║ ╚████║██║  ██║██║  ██║║ #
# ║╚══════╝╚══════╝╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝║ #
#
#          ---  E N D P O I N T S   D E   ELIMINAR  ---         #
#
# ═════════════════════════════════════════════════════════════ #
# --- Listar empresas eliminadas ---
@router.get("/empresas/eliminadas", tags=["Eliminar empresas"], response_model=List[EmpresaRead])
def listar_empresas_eliminadas(db: Session = Depends(conexion.get_db)):
    log_accion("admin", "Listar empresas eliminadas")
    empresas = db.query(Empresa).filter(Empresa.deleted.is_(True)).all()
    return empresas

# --- Baja lógica ---
@router.delete("/empresas/{empresa_id}",tags=["Eliminar empresas"], status_code=204)
def eliminar_empresa(empresa_id: int, db: Session = Depends(conexion.get_db)):
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id, Empresa.deleted == False).first()
    if not empresa:
        log_accion("admin", "Intento eliminar empresa inexistente", f"id={empresa_id}")
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    reservas_activas = db.query(Reserva).filter(
        Reserva.empresa_id == empresa_id,
        Reserva.estado.in_(["reservada", "ocupada"])
    ).count()
    if reservas_activas > 0:
        log_accion("admin", "Intento eliminar empresa con reservas activas", f"id={empresa_id}")
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar una empresa con reservas activas."
        )
    empresa.deleted = True
    db.commit()
    log_accion("admin", "Baja lógica empresa", f"id={empresa_id}")
    return

# --- Restaurar empresa (baja lógica inversa) ---
@router.put("/empresas/{empresa_id}/restaurar",tags=["Eliminar empresas"], response_model=EmpresaRead)
def restaurar_empresa(empresa_id: int, db: Session = Depends(conexion.get_db)):
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id, Empresa.deleted == True).first()
    if not empresa:
        log_accion("admin", "Intento restaurar empresa inexistente/no eliminada", f"id={empresa_id}")
        raise HTTPException(status_code=404, detail="Empresa no encontrada o no está eliminada")
    empresa.deleted = False
    db.commit()
    db.refresh(empresa)
    log_accion("admin", "Restaurar empresa", f"id={empresa_id}")
    return empresa

# --- Eliminar físico (sólo superadmin) ---
@router.delete("/empresas/{empresa_id}/eliminar-definitivo",tags=["Eliminar empresas"], status_code=204)
def eliminar_fisico_empresa(empresa_id: int, db: Session = Depends(conexion.get_db), superadmin: bool = Query(False, description="¿Es superadmin?")):
    if not superadmin:
        log_accion("admin", "Intento eliminar físico sin permisos", f"id={empresa_id}")
        raise HTTPException(status_code=403, detail="Solo superadmin puede eliminar físicamente una empresa")
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if not empresa:
        log_accion("superadmin", "Intento eliminar físico empresa inexistente", f"id={empresa_id}")
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    db.delete(empresa)
    db.commit()
    log_accion("superadmin", "Eliminación física empresa", f"id={empresa_id}")
    return
# ══════════════════════════════════════════════════════════════════════ #
#
# ║██████╗ ██╗      █████╗  ██████╗██╗  ██╗██╗     ██╗███████╗████████╗║ #
# ║██╔══██╗██║     ██╔══██╗██╔════╝██║ ██╔╝██║     ██║██╔════╝╚══██╔══╝║ #
# ║██████╔╝██║     ███████║██║     █████╔╝ ██║     ██║███████╗   ██║   ║ #
# ║██╔══██╗██║     ██╔══██║██║     ██╔═██╗ ██║     ██║╚════██║   ██║   ║ #
# ║██████╔╝███████╗██║  ██║╚██████╗██║  ██╗███████╗██║███████║   ██║   ║ #
# ║╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝╚══════╝   ╚═╝   ║ #
#
#             ---  E N D P O I N T S   D E   BLACKLIST  ---              #
#
# ══════════════════════════════════════════════════════════════════════ #
# --- Listar empresas en blacklist ---
@router.get("/empresas/blacklist", tags=["Blacklist empresas"], response_model=List[EmpresaRead])
def listar_empresas_blacklist(db: Session = Depends(conexion.get_db)):
    log_accion("admin", "Listar empresas en blacklist")
    empresas = db.query(Empresa).filter(Empresa.blacklist.is_(True)).all()
    return empresas
# --- Agregar empresa a blacklist ---
@router.put("/empresas/{empresa_id}/blacklist", tags=["Blacklist empresas"], response_model=EmpresaRead)
def poner_empresa_blacklist(empresa_id: int, db: Session = Depends(conexion.get_db)):
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id, Empresa.deleted == False).first()
    if not empresa:
        log_accion("admin", "Intento poner en blacklist empresa inexistente", f"id={empresa_id}")
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    empresa.blacklist = True
    db.commit()
    db.refresh(empresa)
    log_accion("admin", "Poner empresa en blacklist", f"id={empresa_id}")
    return empresa
# --- Quitar empresa de blacklist ---
@router.put("/empresas/{empresa_id}/quitar-blacklist", tags=["Blacklist empresas"], response_model=EmpresaRead)
def quitar_empresa_blacklist(empresa_id: int, db: Session = Depends(conexion.get_db)):
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id, Empresa.deleted == False).first()
    if not empresa:
        log_accion("admin", "Intento quitar de blacklist empresa inexistente", f"id={empresa_id}")
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    empresa.blacklist = False
    db.commit()
    db.refresh(empresa)
    log_accion("admin", "Quitar empresa de blacklist", f"id={empresa_id}")
    return empresa
# ═════════════════════════════════════════════════════════════════════ #
#
# ║███████╗███╗   ███╗██████╗ ██████╗ ███████╗███████╗ █████╗ ███████╗║ #
# ║██╔════╝████╗ ████║██╔══██╗██╔══██╗██╔════╝██╔════╝██╔══██╗██╔════╝║ #
# ║█████╗  ██╔████╔██║██████╔╝██████╔╝█████╗  ███████╗███████║███████╗║ #
# ║██╔══╝  ██║╚██╔╝██║██╔═══╝ ██╔══██╗██╔══╝  ╚════██║██╔══██║╚════██║║ #
# ║███████╗██║ ╚═╝ ██║██║     ██║  ██║███████╗███████║██║  ██║███████║║ #
# ║╚══════╝╚═╝     ╚═╝╚═╝     ╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝╚══════╝║ #
#
#              ---  E N D P O I N T S   D E   EMPRESAS  ---             #
#
# ═════════════════════════════════════════════════════════════════════ #
# --- Resumen empresas ---
@router.get("/empresas/resumen", tags=["Empresas"])
def resumen_empresas(db: Session = Depends(conexion.get_db)):
    total = db.query(Empresa).count()
    activas = db.query(Empresa).filter(Empresa.deleted == False).count()
    eliminadas = db.query(Empresa).filter(Empresa.deleted == True).count()
    blacklist = db.query(Empresa).filter(Empresa.blacklist == True).count()
    log_accion("admin", "Resumen empresas")
    return {
        "total": total,
        "activas": activas,
        "eliminadas": eliminadas,
        "blacklist": blacklist
    }

# --- Verificar existencia empresa por CUIT ---
@router.get("/empresas/existe", tags=["Empresas"])
def verificar_empresa_por_cuit(cuit: str, db: Session = Depends(conexion.get_db)):
    existe = db.query(Empresa).filter(Empresa.cuit == cuit, Empresa.deleted == False).first()
    log_accion("admin", "Verificar existencia empresa por CUIT", f"CUIT={cuit}")
    return {"existe": existe is not None}

# --- Buscar empresa exacta por nombre o CUIT ---
@router.get("/empresas/buscar-exacta", tags=["Empresas"], response_model=Optional[EmpresaRead])
def buscar_empresa_exacta(nombre: Optional[str] = None, cuit: Optional[str] = None, db: Session = Depends(conexion.get_db)):
    query = db.query(Empresa).filter(Empresa.deleted == False)
    if nombre:
        query = query.filter(Empresa.nombre == nombre)
    if cuit:
        query = query.filter(Empresa.cuit == cuit)
    empresa = query.first()
    log_accion("admin", "Buscar empresa exacta", f"nombre={nombre} CUIT={cuit}")
    return empresa

# --- Listar empresas no eliminadas ---
@router.get("/empresas",tags=["Empresas"], response_model=List[EmpresaRead])
def listar_empresas(db: Session = Depends(conexion.get_db)):
    log_accion("admin", "Listar empresas")
    return db.query(Empresa).filter(Empresa.deleted == False).all()


# --- Crear empresa ---
@router.post("/empresas", response_model=EmpresaRead,tags=["Empresas"], status_code=201)
def crear_empresa(empresa: EmpresaCreate, db: Session = Depends(conexion.get_db)):
    existe = db.query(Empresa).filter(
        Empresa.cuit == empresa.cuit,
        Empresa.deleted == False
    ).first()
    if existe:
        log_accion("admin", "Intento crear empresa duplicada", f"CUIT={empresa.cuit}")
        raise HTTPException(
            status_code=409,
            detail="Ya existe una empresa con ese CUIT."
        )
    nueva_empresa = Empresa(**empresa.dict())
    db.add(nueva_empresa)
    db.commit()
    db.refresh(nueva_empresa)
    log_accion("admin", "Crear empresa", f"id={nueva_empresa.id}")
    return nueva_empresa

# --- Actualizar empresa ---
@router.put("/empresas/{empresa_id}",tags=["Empresas"], response_model=EmpresaRead)
def actualizar_empresa(empresa_id: int, empresa: EmpresaUpdate, db: Session = Depends(conexion.get_db)):
    empresa_db = db.query(Empresa).filter(Empresa.id == empresa_id, Empresa.deleted == False).first()
    if not empresa_db:
        log_accion("admin", "Intento actualizar empresa inexistente", f"id={empresa_id}")
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    if empresa.cuit != empresa_db.cuit:
        existe = db.query(Empresa).filter(
            Empresa.cuit == empresa.cuit,
            Empresa.id != empresa_id,
            Empresa.deleted == False
        ).first()
        if existe:
            log_accion("admin", "Intento duplicar CUIT en actualización", f"CUIT={empresa.cuit}")
            raise HTTPException(
                status_code=409,
                detail="Ya existe una empresa con ese CUIT."
            )
    for campo, valor in empresa.dict().items():
        setattr(empresa_db, campo, valor)
    db.commit()
    db.refresh(empresa_db)
    log_accion("admin", "Actualizar empresa", f"id={empresa_id}")
    return empresa_db

# --- Búsqueda avanzada de empresas ---
@router.get("/empresas/buscar", response_model=List[EmpresaRead])
def buscar_empresas(
    nombre: Optional[str] = None,
    cuit: Optional[str] = None,
    email: Optional[str] = None,
    db: Session = Depends(conexion.get_db)
):
    query = db.query(Empresa).filter(Empresa.deleted == False)
    if nombre:
        query = query.filter(Empresa.nombre.ilike(f"%{nombre}%"))
    if cuit:
        query = query.filter(Empresa.cuit.ilike(f"%{cuit}%"))
    if email:
        query = query.filter(Empresa.email.ilike(f"%{email}%"))
    resultados = query.all()
    log_accion("admin", "Buscar empresas", f"criterios={nombre} {cuit} {email}")
    return resultados
# --- Obtener empresa por ID ---
@router.get("/empresas/{empresa_id}",tags=["Empresas"], response_model=EmpresaRead)
def obtener_empresa(empresa_id: int, db: Session = Depends(conexion.get_db)):
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id, Empresa.deleted == False).first()
    log_accion("admin", "Obtener empresa", f"id={empresa_id}")
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return empresa
