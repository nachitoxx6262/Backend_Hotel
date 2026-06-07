"""
Admin SaaS endpoints (super admin only)
"""
from datetime import datetime, timedelta
from utils.datetime_utils import utcnow
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from database.conexion import get_db
from models.core import (
    EmpresaUsuario, Subscription, Plan, PlanType, SubscriptionStatus,
    PaymentAttempt, PaymentStatus, PaymentProvider,
)
from decimal import Decimal
from models.usuario import Usuario
from models.rol import Rol, Permiso
from utils.dependencies import require_super_admin
from utils.logging_utils import log_event
from utils.subscription_service import apply_plan_change

router = APIRouter(prefix="/admin", tags=["Admin SaaS"])


def _plan_type_value(value: Optional[str]) -> Optional[str]:
    return value.value if hasattr(value, "value") else value


def _build_tenant_summary(db: Session, tenant: "EmpresaUsuario") -> "TenantSummary":
    """Arma el TenantSummary de un tenant (uso compartido por varios endpoints)."""
    usuarios_count = db.query(func.count(Usuario.id)).filter(
        Usuario.empresa_usuario_id == tenant.id,
        Usuario.deleted.is_(False)
    ).scalar() or 0

    dias_restantes_demo = None
    if _plan_type_value(tenant.plan_tipo) == PlanType.DEMO.value and tenant.fecha_fin_demo:
        dias_restantes_demo = (tenant.fecha_fin_demo.date() - utcnow().date()).days

    subscription = None
    if tenant.subscription:
        plan = tenant.subscription.plan
        plan_summary = None
        if plan:
            plan_summary = PlanSummary(
                id=plan.id,
                nombre=_plan_type_value(plan.nombre),
                precio_mensual=float(plan.precio_mensual),
                max_habitaciones=plan.max_habitaciones,
                max_usuarios=plan.max_usuarios,
                activo=plan.activo
            )
        subscription = SubscriptionSummary(
            id=tenant.subscription.id,
            estado=tenant.subscription.estado,
            fecha_proxima_renovacion=tenant.subscription.fecha_proxima_renovacion,
            plan=plan_summary
        )

    return TenantSummary(
        id=tenant.id,
        nombre_hotel=tenant.nombre_hotel,
        cuit=tenant.cuit,
        contacto_nombre=tenant.contacto_nombre,
        contacto_email=tenant.contacto_email,
        contacto_telefono=tenant.contacto_telefono,
        direccion=tenant.direccion,
        ciudad=tenant.ciudad,
        provincia=tenant.provincia,
        plan_tipo=_plan_type_value(tenant.plan_tipo),
        fecha_inicio_demo=tenant.fecha_inicio_demo,
        fecha_fin_demo=tenant.fecha_fin_demo,
        activa=tenant.activa,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
        subscription=subscription,
        usuarios_count=usuarios_count,
        dias_restantes_demo=dias_restantes_demo
    )


class PlanSummary(BaseModel):
    id: int
    nombre: str
    precio_mensual: float
    max_habitaciones: int
    max_usuarios: int
    activo: bool

    class Config:
        from_attributes = True


class SubscriptionSummary(BaseModel):
    id: int
    estado: str
    fecha_proxima_renovacion: Optional[datetime] = None
    plan: Optional[PlanSummary] = None

    class Config:
        from_attributes = True


class TenantSummary(BaseModel):
    id: int
    nombre_hotel: str
    cuit: str
    contacto_nombre: Optional[str] = None
    contacto_email: Optional[str] = None
    contacto_telefono: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    provincia: Optional[str] = None
    plan_tipo: str
    fecha_inicio_demo: Optional[datetime] = None
    fecha_fin_demo: Optional[datetime] = None
    activa: bool
    created_at: datetime
    updated_at: datetime
    subscription: Optional[SubscriptionSummary] = None
    usuarios_count: int = 0
    dias_restantes_demo: Optional[int] = None

    class Config:
        from_attributes = True


class TenantUpdate(BaseModel):
    activa: Optional[bool] = None
    plan_tipo: Optional[str] = None
    fecha_fin_demo: Optional[datetime] = None


class ConvertDemoRequest(BaseModel):
    plan_tipo: str = Field(..., description="basico | premium")
    fecha_proxima_renovacion: Optional[datetime] = None


class UserSummary(BaseModel):
    id: int
    username: str
    email: str
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    rol: str
    activo: bool
    empresa_usuario_id: Optional[int] = None
    es_super_admin: bool
    fecha_creacion: datetime

    class Config:
        from_attributes = True


class DemoSummary(BaseModel):
    id: int
    nombre_hotel: str
    cuit: str
    contacto_email: Optional[str] = None
    fecha_inicio_demo: Optional[datetime] = None
    fecha_fin_demo: Optional[datetime] = None
    dias_restantes_demo: Optional[int] = None
    activa: bool

    class Config:
        from_attributes = True


class RoleSummary(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str] = None
    activo: bool
    empresa_usuario_id: Optional[int] = None
    permisos: List[str] = Field(default_factory=list)


class PermissionSummary(BaseModel):
    id: int
    codigo: str
    nombre: str
    descripcion: Optional[str] = None
    activo: bool

    class Config:
        from_attributes = True


@router.get("/tenants", response_model=List[TenantSummary])
def list_tenants(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_super_admin)
):
    tenants = (
        db.query(EmpresaUsuario)
        .options(joinedload(EmpresaUsuario.subscription).joinedload(Subscription.plan))
        .filter(EmpresaUsuario.deleted.is_(False))
        .order_by(EmpresaUsuario.created_at.desc())
        .all()
    )

    results: List[TenantSummary] = []
    for tenant in tenants:
        usuarios_count = db.query(func.count(Usuario.id)).filter(
            Usuario.empresa_usuario_id == tenant.id,
            Usuario.deleted.is_(False)
        ).scalar() or 0

        dias_restantes_demo = None
        if _plan_type_value(tenant.plan_tipo) == PlanType.DEMO.value and tenant.fecha_fin_demo:
            dias_restantes_demo = (tenant.fecha_fin_demo.date() - utcnow().date()).days

        subscription = None
        if tenant.subscription:
            plan = tenant.subscription.plan
            plan_summary = None
            if plan:
                plan_summary = PlanSummary(
                    id=plan.id,
                    nombre=_plan_type_value(plan.nombre),
                    precio_mensual=float(plan.precio_mensual),
                    max_habitaciones=plan.max_habitaciones,
                    max_usuarios=plan.max_usuarios,
                    activo=plan.activo
                )
            subscription = SubscriptionSummary(
                id=tenant.subscription.id,
                estado=tenant.subscription.estado,
                fecha_proxima_renovacion=tenant.subscription.fecha_proxima_renovacion,
                plan=plan_summary
            )

        results.append(TenantSummary(
            id=tenant.id,
            nombre_hotel=tenant.nombre_hotel,
            cuit=tenant.cuit,
            contacto_nombre=tenant.contacto_nombre,
            contacto_email=tenant.contacto_email,
            contacto_telefono=tenant.contacto_telefono,
            direccion=tenant.direccion,
            ciudad=tenant.ciudad,
            provincia=tenant.provincia,
            plan_tipo=_plan_type_value(tenant.plan_tipo),
            fecha_inicio_demo=tenant.fecha_inicio_demo,
            fecha_fin_demo=tenant.fecha_fin_demo,
            activa=tenant.activa,
            created_at=tenant.created_at,
            updated_at=tenant.updated_at,
            subscription=subscription,
            usuarios_count=usuarios_count,
            dias_restantes_demo=dias_restantes_demo
        ))

    log_event("admin", current_user.username, "Listar tenants", f"total={len(results)}")
    return results


@router.patch("/tenants/{tenant_id}", response_model=TenantSummary)
def update_tenant(
    tenant_id: int,
    payload: TenantUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_super_admin)
):
    tenant = db.query(EmpresaUsuario).filter(
        EmpresaUsuario.id == tenant_id,
        EmpresaUsuario.deleted.is_(False)
    ).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    if payload.activa is not None:
        tenant.activa = payload.activa
    if payload.plan_tipo is not None:
        tenant.plan_tipo = payload.plan_tipo
    if payload.fecha_fin_demo is not None:
        tenant.fecha_fin_demo = payload.fecha_fin_demo

    db.commit()
    db.refresh(tenant)

    usuarios_count = db.query(func.count(Usuario.id)).filter(
        Usuario.empresa_usuario_id == tenant.id,
        Usuario.deleted.is_(False)
    ).scalar() or 0

    dias_restantes_demo = None
    if _plan_type_value(tenant.plan_tipo) == PlanType.DEMO.value and tenant.fecha_fin_demo:
        dias_restantes_demo = (tenant.fecha_fin_demo.date() - utcnow().date()).days

    subscription = None
    if tenant.subscription:
        plan = tenant.subscription.plan
        plan_summary = None
        if plan:
            plan_summary = PlanSummary(
                id=plan.id,
                    nombre=_plan_type_value(plan.nombre),
                precio_mensual=float(plan.precio_mensual),
                max_habitaciones=plan.max_habitaciones,
                max_usuarios=plan.max_usuarios,
                activo=plan.activo
            )
        subscription = SubscriptionSummary(
            id=tenant.subscription.id,
            estado=tenant.subscription.estado,
            fecha_proxima_renovacion=tenant.subscription.fecha_proxima_renovacion,
            plan=plan_summary
        )

    log_event("admin", current_user.username, "Actualizar tenant", f"tenant_id={tenant_id}")

    return TenantSummary(
        id=tenant.id,
        nombre_hotel=tenant.nombre_hotel,
        cuit=tenant.cuit,
        contacto_nombre=tenant.contacto_nombre,
        contacto_email=tenant.contacto_email,
        contacto_telefono=tenant.contacto_telefono,
        direccion=tenant.direccion,
        ciudad=tenant.ciudad,
        provincia=tenant.provincia,
        plan_tipo=_plan_type_value(tenant.plan_tipo),
        fecha_inicio_demo=tenant.fecha_inicio_demo,
        fecha_fin_demo=tenant.fecha_fin_demo,
        activa=tenant.activa,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
        subscription=subscription,
        usuarios_count=usuarios_count,
        dias_restantes_demo=dias_restantes_demo
    )


@router.post("/tenants/{tenant_id}/convert", response_model=TenantSummary)
def convert_demo_to_subscription(
    tenant_id: int,
    payload: ConvertDemoRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_super_admin)
):
    plan_tipo = payload.plan_tipo.lower().strip()
    if plan_tipo not in [PlanType.BASICO.value, PlanType.PREMIUM.value]:
        raise HTTPException(status_code=400, detail="plan_tipo inválido. Use basico o premium")

    tenant = db.query(EmpresaUsuario).filter(
        EmpresaUsuario.id == tenant_id,
        EmpresaUsuario.deleted.is_(False)
    ).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    plan = db.query(Plan).filter(Plan.nombre == plan_tipo).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")

    next_renewal = payload.fecha_proxima_renovacion or (utcnow() + timedelta(days=30))

    subscription = db.query(Subscription).filter(Subscription.empresa_usuario_id == tenant.id).first()
    if not subscription:
        # Crear suscripción mínima si el tenant no tenía (datos legados).
        subscription = Subscription(empresa_usuario_id=tenant.id, plan_id=plan.id)
        db.add(subscription)
        db.flush()

    # Cambio de plan vía servicio central: subscription + espejo en empresa atómico.
    apply_plan_change(
        db, tenant, subscription, plan,
        periodo_fin=next_renewal,
    )
    tenant.activa = True

    db.commit()
    db.refresh(tenant)

    usuarios_count = db.query(func.count(Usuario.id)).filter(
        Usuario.empresa_usuario_id == tenant.id,
        Usuario.deleted.is_(False)
    ).scalar() or 0

    plan_summary = PlanSummary(
        id=plan.id,
        nombre=_plan_type_value(plan.nombre),
        precio_mensual=float(plan.precio_mensual),
        max_habitaciones=plan.max_habitaciones,
        max_usuarios=plan.max_usuarios,
        activo=plan.activo
    )
    subscription_summary = SubscriptionSummary(
        id=subscription.id,
        estado=subscription.estado,
        fecha_proxima_renovacion=subscription.fecha_proxima_renovacion,
        plan=plan_summary
    )

    log_event("admin", current_user.username, "Convertir demo", f"tenant_id={tenant_id} plan={plan_tipo}")

    return TenantSummary(
        id=tenant.id,
        nombre_hotel=tenant.nombre_hotel,
        cuit=tenant.cuit,
        contacto_nombre=tenant.contacto_nombre,
        contacto_email=tenant.contacto_email,
        contacto_telefono=tenant.contacto_telefono,
        direccion=tenant.direccion,
        ciudad=tenant.ciudad,
        provincia=tenant.provincia,
        plan_tipo=_plan_type_value(tenant.plan_tipo),
        fecha_inicio_demo=tenant.fecha_inicio_demo,
        fecha_fin_demo=tenant.fecha_fin_demo,
        activa=tenant.activa,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
        subscription=subscription_summary,
        usuarios_count=usuarios_count,
        dias_restantes_demo=None
    )


@router.delete("/tenants/{tenant_id}")
def delete_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_super_admin)
):
    """Elimina un tenant (empresa/demo) de forma lógica (soft delete)"""
    tenant = db.query(EmpresaUsuario).filter(
        EmpresaUsuario.id == tenant_id,
        EmpresaUsuario.deleted.is_(False)
    ).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    # Soft delete: marcar como eliminado
    tenant.deleted = True
    tenant.updated_at = utcnow()
    
    db.commit()
    
    log_event("admin", current_user.username, "Eliminar tenant", f"tenant_id={tenant_id} nombre={tenant.nombre_hotel}")
    
    return {"message": "Tenant eliminado correctamente", "tenant_id": tenant_id}


@router.get("/tenants/{tenant_id}/usuarios", response_model=List[UserSummary])
def list_tenant_users(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_super_admin)
):
    users = db.query(Usuario).filter(
        Usuario.empresa_usuario_id == tenant_id,
        Usuario.deleted.is_(False)
    ).order_by(Usuario.id.desc()).all()

    return [UserSummary.model_validate(u) for u in users]


@router.get("/subscriptions", response_model=List[SubscriptionSummary])
def list_subscriptions(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_super_admin)
):
    subs = db.query(Subscription).options(joinedload(Subscription.plan)).order_by(Subscription.id.desc()).all()
    results: List[SubscriptionSummary] = []
    for sub in subs:
        plan = sub.plan
        plan_summary = None
        if plan:
            plan_summary = PlanSummary(
                id=plan.id,
                nombre=_plan_type_value(plan.nombre),
                precio_mensual=float(plan.precio_mensual),
                max_habitaciones=plan.max_habitaciones,
                max_usuarios=plan.max_usuarios,
                activo=plan.activo
            )
        results.append(SubscriptionSummary(
            id=sub.id,
            estado=sub.estado,
            fecha_proxima_renovacion=sub.fecha_proxima_renovacion,
            plan=plan_summary
        ))

    return results


@router.get("/demos", response_model=List[DemoSummary])
def list_demos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_super_admin)
):
    demos = db.query(EmpresaUsuario).filter(
    EmpresaUsuario.plan_tipo == PlanType.DEMO.value,
        EmpresaUsuario.deleted.is_(False)
    ).order_by(EmpresaUsuario.fecha_fin_demo.desc()).all()
    results: List[DemoSummary] = []
    for tenant in demos:
        dias_restantes_demo = None
        if tenant.fecha_fin_demo:
            dias_restantes_demo = (tenant.fecha_fin_demo.date() - utcnow().date()).days
        results.append(DemoSummary(
            id=tenant.id,
            nombre_hotel=tenant.nombre_hotel,
            cuit=tenant.cuit,
            contacto_email=tenant.contacto_email,
            fecha_inicio_demo=tenant.fecha_inicio_demo,
            fecha_fin_demo=tenant.fecha_fin_demo,
            dias_restantes_demo=dias_restantes_demo,
            activa=tenant.activa
        ))
    return results


@router.get("/roles", response_model=List[RoleSummary])
def list_roles(
    tenant_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_super_admin)
):
    query = db.query(Rol)
    if tenant_id is not None:
        query = query.filter(Rol.empresa_usuario_id == tenant_id)
    roles = query.order_by(Rol.id.desc()).all()

    results: List[RoleSummary] = []
    for role in roles:
        permisos = [rp.permiso.codigo for rp in role.permisos]
        results.append(RoleSummary(
            id=role.id,
            nombre=role.nombre,
            descripcion=role.descripcion,
            activo=role.activo,
            empresa_usuario_id=role.empresa_usuario_id,
            permisos=permisos
        ))

    return results


@router.get("/permisos", response_model=List[PermissionSummary])
def list_permissions(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_super_admin)
):
    permisos = db.query(Permiso).order_by(Permiso.codigo.asc()).all()
    return [PermissionSummary.model_validate(p) for p in permisos]


# ============================================================
# PAGOS (confirmación de offline + carga directa del dueño)
# ============================================================

class PendingPaymentItem(BaseModel):
    id: int
    tenant_id: int
    tenant_nombre: str
    monto: float
    proveedor: str
    plan_destino: Optional[str] = None
    nota: Optional[str] = None
    reported_by: Optional[str] = None
    created_at: Optional[datetime] = None


class RegisterOfflinePaymentRequest(BaseModel):
    plan_tipo: str = Field(..., description="basico | premium")
    metodo: str = Field(..., description="transferencia | efectivo")
    monto: Optional[float] = Field(None, ge=0)
    periodo_dias: int = Field(30, ge=1, le=3650)
    nota: Optional[str] = None


def _provider_value(p) -> str:
    return p.value if hasattr(p, "value") else str(p)


@router.get("/pending-payments", response_model=List[PendingPaymentItem])
def list_pending_payments(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_super_admin)
):
    """Avisos de pago offline (transferencia/efectivo) pendientes de confirmación."""
    attempts = (
        db.query(PaymentAttempt)
        .filter(
            PaymentAttempt.estado == PaymentStatus.PENDIENTE,
            PaymentAttempt.proveedor.in_([PaymentProvider.TRANSFERENCIA, PaymentProvider.EFECTIVO]),
        )
        .order_by(PaymentAttempt.created_at.asc())
        .all()
    )
    items: List[PendingPaymentItem] = []
    for a in attempts:
        sub = a.subscription
        empresa = sub.empresa_usuario if sub else None
        meta = a.response_json if isinstance(a.response_json, dict) else {}
        items.append(PendingPaymentItem(
            id=a.id,
            tenant_id=empresa.id if empresa else 0,
            tenant_nombre=empresa.nombre_hotel if empresa else "—",
            monto=float(a.monto),
            proveedor=_provider_value(a.proveedor),
            plan_destino=meta.get("target_plan_type"),
            nota=meta.get("nota"),
            reported_by=meta.get("reported_by"),
            created_at=a.created_at,
        ))
    return items


@router.post("/payments/{attempt_id}/confirm", response_model=TenantSummary)
def confirm_offline_payment(
    attempt_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_super_admin)
):
    """Confirma un pago offline pendiente: activa el plan destino y marca el intento EXITOSO."""
    attempt = db.query(PaymentAttempt).filter(PaymentAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Intento de pago no encontrado")
    if attempt.estado != PaymentStatus.PENDIENTE:
        raise HTTPException(status_code=409, detail="El intento ya fue procesado")

    subscription = attempt.subscription
    if not subscription:
        raise HTTPException(status_code=404, detail="Suscripción del intento no encontrada")
    tenant = subscription.empresa_usuario or db.query(EmpresaUsuario).filter_by(
        id=subscription.empresa_usuario_id
    ).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    meta = attempt.response_json if isinstance(attempt.response_json, dict) else {}
    plan_destino = meta.get("target_plan_type")
    if not plan_destino:
        raise HTTPException(status_code=400, detail="El intento no tiene plan destino registrado")

    plan = db.query(Plan).filter(Plan.nombre == plan_destino).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan destino no encontrado")

    apply_plan_change(db, tenant, subscription, plan, proveedor=attempt.proveedor, periodo_dias=30)
    attempt.estado = PaymentStatus.EXITOSO
    tenant.activa = True
    db.commit()
    db.refresh(tenant)

    log_event("admin", current_user.username, "Pago offline confirmado",
              f"attempt_id={attempt_id} tenant_id={tenant.id} plan={plan_destino}")

    return _build_tenant_summary(db, tenant)


@router.post("/payments/{attempt_id}/reject")
def reject_offline_payment(
    attempt_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_super_admin)
):
    """Rechaza un aviso de pago offline pendiente (lo marca FALLIDO)."""
    attempt = db.query(PaymentAttempt).filter(PaymentAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Intento de pago no encontrado")
    if attempt.estado != PaymentStatus.PENDIENTE:
        raise HTTPException(status_code=409, detail="El intento ya fue procesado")
    attempt.estado = PaymentStatus.FALLIDO
    db.commit()
    log_event("admin", current_user.username, "Pago offline rechazado", f"attempt_id={attempt_id}")
    return {"status": "rejected", "attempt_id": attempt_id}


@router.post("/tenants/{tenant_id}/register-offline-payment", response_model=TenantSummary)
def register_offline_payment(
    tenant_id: int,
    payload: RegisterOfflinePaymentRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_super_admin)
):
    """Carga directa de un pago offline por el dueño: activa el plan y registra el pago EXITOSO."""
    plan_tipo = payload.plan_tipo.lower().strip()
    if plan_tipo not in (PlanType.BASICO.value, PlanType.PREMIUM.value):
        raise HTTPException(status_code=400, detail="plan_tipo inválido. Use basico o premium")
    metodo = (payload.metodo or "").lower().strip()
    if metodo not in ("transferencia", "efectivo"):
        raise HTTPException(status_code=400, detail="metodo debe ser 'transferencia' o 'efectivo'")

    tenant = db.query(EmpresaUsuario).filter(
        EmpresaUsuario.id == tenant_id, EmpresaUsuario.deleted.is_(False)
    ).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    plan = db.query(Plan).filter(Plan.nombre == plan_tipo).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")

    subscription = db.query(Subscription).filter(Subscription.empresa_usuario_id == tenant.id).first()
    if not subscription:
        subscription = Subscription(empresa_usuario_id=tenant.id, plan_id=plan.id)
        db.add(subscription)
        db.flush()

    proveedor = PaymentProvider.TRANSFERENCIA if metodo == "transferencia" else PaymentProvider.EFECTIVO
    monto = Decimal(str(payload.monto)) if payload.monto is not None else None
    apply_plan_change(
        db, tenant, subscription, plan,
        proveedor=proveedor, periodo_dias=payload.periodo_dias,
        registrar_pago=True, monto=monto,
    )
    tenant.activa = True
    db.commit()
    db.refresh(tenant)

    log_event("admin", current_user.username, "Pago offline cargado (directo)",
              f"tenant_id={tenant.id} plan={plan_tipo} metodo={metodo}")

    return _build_tenant_summary(db, tenant)
