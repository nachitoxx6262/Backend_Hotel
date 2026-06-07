"""
Configuración de housekeeping (Fase 3): plantillas/checklists y reglas de limpieza recurrente.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database import conexion
from models.core import HKTemplate, HKRecurringRule, RoomType
from models.usuario import Usuario
from utils.dependencies import get_current_user, require_admin_or_manager
from utils.logging_utils import log_event

router = APIRouter(prefix="/pms/hk", tags=["Housekeeping Config"])


def _tenant(u: Usuario) -> int:
    if not u.empresa_usuario_id:
        raise HTTPException(status_code=403, detail="Usuario sin tenant asociado")
    return u.empresa_usuario_id


# ============================ Plantillas ============================
class TemplateIn(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    tipo: str = Field("eventual", pattern="^(checkout|stayover|eventual)$")
    checklist: List[str] = Field(default_factory=list)
    activo: bool = True


def _tpl_dict(t: HKTemplate) -> dict:
    items = t.checklist or []
    # normalizar a lista de strings para el front
    norm = [(i.get("nombre") if isinstance(i, dict) else str(i)) for i in items]
    return {"id": t.id, "nombre": t.nombre, "tipo": t.tipo, "checklist": norm, "activo": t.activo}


@router.get("/templates")
def list_templates(current_user: Usuario = Depends(get_current_user), db: Session = Depends(conexion.get_db)):
    tid = _tenant(current_user)
    rows = db.query(HKTemplate).filter(HKTemplate.empresa_usuario_id == tid).order_by(HKTemplate.nombre).all()
    return [_tpl_dict(t) for t in rows]


@router.post("/templates", status_code=status.HTTP_201_CREATED)
def create_template(data: TemplateIn, current_user: Usuario = Depends(require_admin_or_manager), db: Session = Depends(conexion.get_db)):
    tid = _tenant(current_user)
    tpl = HKTemplate(
        empresa_usuario_id=tid, nombre=data.nombre.strip(), tipo=data.tipo, activo=data.activo,
        checklist=[{"nombre": s.strip(), "orden": i} for i, s in enumerate(data.checklist) if s.strip()],
    )
    db.add(tpl)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Ya existe una plantilla '{data.nombre}'")
    db.refresh(tpl)
    log_event("housekeeping", current_user.username, "Plantilla creada", f"id={tpl.id}")
    return _tpl_dict(tpl)


@router.patch("/templates/{tpl_id}")
def update_template(tpl_id: int, data: TemplateIn, current_user: Usuario = Depends(require_admin_or_manager), db: Session = Depends(conexion.get_db)):
    tid = _tenant(current_user)
    tpl = db.query(HKTemplate).filter(HKTemplate.id == tpl_id, HKTemplate.empresa_usuario_id == tid).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    tpl.nombre = data.nombre.strip()
    tpl.tipo = data.tipo
    tpl.activo = data.activo
    tpl.checklist = [{"nombre": s.strip(), "orden": i} for i, s in enumerate(data.checklist) if s.strip()]
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe una plantilla con ese nombre")
    db.refresh(tpl)
    return _tpl_dict(tpl)


@router.delete("/templates/{tpl_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(tpl_id: int, current_user: Usuario = Depends(require_admin_or_manager), db: Session = Depends(conexion.get_db)):
    tid = _tenant(current_user)
    tpl = db.query(HKTemplate).filter(HKTemplate.id == tpl_id, HKTemplate.empresa_usuario_id == tid).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    db.delete(tpl)
    db.commit()


# ============================ Reglas recurrentes ============================
class RuleIn(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=120)
    cada_n_dias: int = Field(15, ge=1, le=365)
    scope: str = Field("todas", pattern="^(todas|tipo)$")
    room_type_id: Optional[int] = None
    template_id: Optional[int] = None
    prioridad: str = Field("media", pattern="^(baja|media|alta|urgente)$")
    activo: bool = True


def _rule_dict(r: HKRecurringRule) -> dict:
    return {
        "id": r.id, "nombre": r.nombre, "cada_n_dias": r.cada_n_dias, "scope": r.scope,
        "room_type_id": r.room_type_id, "template_id": r.template_id, "prioridad": r.prioridad,
        "activo": r.activo,
        "ultima_generacion": r.ultima_generacion.isoformat() if r.ultima_generacion else None,
    }


@router.get("/recurring-rules")
def list_rules(current_user: Usuario = Depends(get_current_user), db: Session = Depends(conexion.get_db)):
    tid = _tenant(current_user)
    rows = db.query(HKRecurringRule).filter(HKRecurringRule.empresa_usuario_id == tid).order_by(HKRecurringRule.nombre).all()
    return [_rule_dict(r) for r in rows]


def _validate_rule_refs(data: RuleIn, tid: int, db: Session):
    if data.scope == "tipo" and not data.room_type_id:
        raise HTTPException(status_code=400, detail="Indicá el tipo de habitación para alcance 'tipo'")
    if data.room_type_id:
        rt = db.query(RoomType).filter(RoomType.id == data.room_type_id, RoomType.empresa_usuario_id == tid).first()
        if not rt:
            raise HTTPException(status_code=404, detail="Tipo de habitación no encontrado")
    if data.template_id:
        tpl = db.query(HKTemplate).filter(HKTemplate.id == data.template_id, HKTemplate.empresa_usuario_id == tid).first()
        if not tpl:
            raise HTTPException(status_code=404, detail="Plantilla no encontrada")


@router.post("/recurring-rules", status_code=status.HTTP_201_CREATED)
def create_rule(data: RuleIn, current_user: Usuario = Depends(require_admin_or_manager), db: Session = Depends(conexion.get_db)):
    tid = _tenant(current_user)
    _validate_rule_refs(data, tid, db)
    rule = HKRecurringRule(
        empresa_usuario_id=tid, nombre=data.nombre.strip(), cada_n_dias=data.cada_n_dias,
        scope=data.scope, room_type_id=data.room_type_id if data.scope == "tipo" else None,
        template_id=data.template_id, prioridad=data.prioridad, activo=data.activo,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    log_event("housekeeping", current_user.username, "Regla recurrente creada", f"id={rule.id}, cada={rule.cada_n_dias}d")
    return _rule_dict(rule)


@router.patch("/recurring-rules/{rule_id}")
def update_rule(rule_id: int, data: RuleIn, current_user: Usuario = Depends(require_admin_or_manager), db: Session = Depends(conexion.get_db)):
    tid = _tenant(current_user)
    rule = db.query(HKRecurringRule).filter(HKRecurringRule.id == rule_id, HKRecurringRule.empresa_usuario_id == tid).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Regla no encontrada")
    _validate_rule_refs(data, tid, db)
    rule.nombre = data.nombre.strip()
    rule.cada_n_dias = data.cada_n_dias
    rule.scope = data.scope
    rule.room_type_id = data.room_type_id if data.scope == "tipo" else None
    rule.template_id = data.template_id
    rule.prioridad = data.prioridad
    rule.activo = data.activo
    db.commit()
    db.refresh(rule)
    return _rule_dict(rule)


@router.delete("/recurring-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, current_user: Usuario = Depends(require_admin_or_manager), db: Session = Depends(conexion.get_db)):
    tid = _tenant(current_user)
    rule = db.query(HKRecurringRule).filter(HKRecurringRule.id == rule_id, HKRecurringRule.empresa_usuario_id == tid).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Regla no encontrada")
    db.delete(rule)
    db.commit()
