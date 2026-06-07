"""
Servicio central de suscripciones (Fase A — Subscription como única fuente de verdad).

Toda decisión de "qué plan tiene y si puede escribir un tenant" pasa por
`resolve_access()`, y todo cambio de plan pasa por `apply_plan_change()`.
Esto elimina la desincronización histórica entre `EmpresaUsuario.plan_tipo`/
`fecha_fin_demo` (que ahora son sólo un ESPEJO) y `Subscription` (la verdad).

Reglas:
- La autoridad del estado vive en `Subscription` (plan_id, estado, fecha_proxima_renovacion).
- `EmpresaUsuario.plan_tipo` / `fecha_inicio_demo` / `fecha_fin_demo` se escriben SIEMPRE
  desde `apply_plan_change` para mantener compatibilidad con admin/RLS, pero NADIE decide
  acceso leyéndolos directamente: se usa `resolve_access`.
- El vencimiento (VENCIDO) se DERIVA en vivo de `fecha_proxima_renovacion` vs ahora; no
  depende de un cron (un cron sólo lo persiste/notifica más adelante, Fase B/C).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from utils.datetime_utils import utcnow
from models.core import (
    EmpresaUsuario,
    Plan,
    Subscription,
    PlanType,
    SubscriptionStatus,
    PaymentAttempt,
    PaymentStatus,
    PaymentProvider,
)

# Período por defecto de un ciclo pago (mensual).
DEFAULT_BILLING_DAYS = 30
# Duración del trial al registrarse / volver a demo.
TRIAL_DAYS = 10


def _as_naive_utc(dt):
    """Normaliza un datetime a naive-UTC para comparar contra `utcnow()` (naive)."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@dataclass
class AccessState:
    """Estado efectivo de acceso de un tenant, derivado de su Subscription."""
    plan: Optional[Plan]
    estado: str            # 'trial' | 'activo' | 'vencido' | 'cancelado' | 'bloqueado'
    is_trial: bool
    writable: bool         # False => sólo lectura (writes deben responder 402)
    expired: bool          # el período venció por fecha
    periodo_fin: Optional[object]   # datetime original (aware) para mostrar
    days_remaining: Optional[int]   # días hasta periodo_fin (None si no aplica)
    message: str

    # ---- helpers de presentación / compat con el frontend ----
    @property
    def frontend_status(self) -> str:
        """Mapea a los strings que ya entiende el frontend / TrialInfo."""
        if self.estado == "trial":
            return "expired" if self.expired else "active"
        if self.estado in ("vencido",):
            return "expired"
        if self.estado in ("cancelado", "bloqueado"):
            return self.estado
        return "not_trial"  # plan pago vigente


def resolve_access(empresa: EmpresaUsuario, subscription: Optional[Subscription]) -> AccessState:
    """
    Calcula el estado efectivo de acceso de un tenant.

    Es la ÚNICA función que decide writable / vencimiento. La usan /billing/status,
    el enforcement (Fase B) y todo lo que necesite saber el estado real.
    """
    now = utcnow()  # naive UTC

    if subscription is None:
        return AccessState(
            plan=None, estado="bloqueado", is_trial=False, writable=False,
            expired=False, periodo_fin=None, days_remaining=0,
            message="Sin suscripción asociada",
        )

    plan = subscription.plan
    is_trial = bool(plan and plan.nombre == PlanType.DEMO)

    # Fin del período vigente: la verdad es la suscripción; caemos a fecha_fin_demo
    # (espejo) sólo si la suscripción aún no lo tiene seteado (datos legados).
    periodo_fin = subscription.fecha_proxima_renovacion
    if periodo_fin is None and is_trial:
        periodo_fin = empresa.fecha_fin_demo
    periodo_fin_naive = _as_naive_utc(periodo_fin)

    raw_estado = subscription.estado
    raw_value = raw_estado.value if hasattr(raw_estado, "value") else str(raw_estado)

    # Estados "duros": no dependen de la fecha.
    if raw_value in (SubscriptionStatus.CANCELADO.value, SubscriptionStatus.BLOQUEADO.value):
        return AccessState(
            plan=plan, estado=raw_value, is_trial=is_trial, writable=False,
            expired=False, periodo_fin=periodo_fin, days_remaining=0,
            message="Suscripción cancelada" if raw_value == "cancelado" else "Suscripción bloqueada",
        )

    # ¿Venció por fecha?
    expired = periodo_fin_naive is not None and now > periodo_fin_naive
    if expired:
        return AccessState(
            plan=plan, estado=("trial" if is_trial else SubscriptionStatus.VENCIDO.value),
            is_trial=is_trial, writable=False, expired=True,
            periodo_fin=periodo_fin, days_remaining=0,
            message="Período de prueba finalizado" if is_trial else "Suscripción vencida",
        )

    # Vigente.
    days_remaining = (periodo_fin_naive - now).days if periodo_fin_naive else None
    estado = "trial" if is_trial else SubscriptionStatus.ACTIVO.value
    if is_trial:
        msg = f"Prueba activa — {days_remaining} días restantes" if days_remaining else "La prueba expira hoy"
    else:
        msg = f"Suscripción activa ({plan.nombre.value if plan else '—'})"
    return AccessState(
        plan=plan, estado=estado, is_trial=is_trial, writable=True,
        expired=False, periodo_fin=periodo_fin, days_remaining=days_remaining,
        message=msg,
    )


def apply_plan_change(
    db: Session,
    empresa: EmpresaUsuario,
    subscription: Subscription,
    nuevo_plan: Plan,
    *,
    proveedor: Optional[PaymentProvider] = None,
    periodo_dias: Optional[int] = None,
    periodo_fin=None,
    registrar_pago: bool = False,
    monto: Optional[Decimal] = None,
    external_id: Optional[str] = None,
) -> Optional[PaymentAttempt]:
    """
    ÚNICO punto de cambio de plan. Actualiza Subscription y sincroniza el espejo en
    EmpresaUsuario en una sola operación, para que nunca queden desincronizados.

    No hace commit: el caller controla la transacción.

    Args:
        nuevo_plan: plan destino (incluye demo para downgrade a trial).
        proveedor: proveedor de pago (para el PaymentAttempt si registrar_pago).
        periodo_dias: duración del nuevo período. Default: TRIAL_DAYS si demo, si no DEFAULT_BILLING_DAYS.
        periodo_fin: fecha de fin explícita (override de periodo_dias). Útil cuando un admin
            fija manualmente "pagado hasta" (pagos offline / convert).
        registrar_pago: si True, crea un PaymentAttempt EXITOSO por `monto`.
        monto: monto del pago (default: precio del plan).
        external_id: id externo del pago (Stripe/MP/comprobante).

    Returns:
        El PaymentAttempt creado (si registrar_pago), o None.
    """
    now = utcnow()
    es_demo = nuevo_plan.nombre == PlanType.DEMO

    if periodo_fin is not None:
        nuevo_fin = periodo_fin
    else:
        if periodo_dias is None:
            periodo_dias = TRIAL_DAYS if es_demo else DEFAULT_BILLING_DAYS
        nuevo_fin = now + timedelta(days=periodo_dias)

    # --- Subscription (la verdad) ---
    subscription.plan_id = nuevo_plan.id
    subscription.estado = SubscriptionStatus.ACTIVO
    subscription.fecha_proxima_renovacion = nuevo_fin

    # --- Espejo en EmpresaUsuario (compat admin/RLS; nadie decide acceso leyendo esto) ---
    empresa.plan_tipo = nuevo_plan.nombre
    if es_demo:
        empresa.fecha_inicio_demo = now
        empresa.fecha_fin_demo = nuevo_fin
    else:
        empresa.fecha_fin_demo = None

    pago = None
    if registrar_pago:
        pago = PaymentAttempt(
            subscription_id=subscription.id,
            monto=Decimal(str(monto)) if monto is not None else Decimal(str(nuevo_plan.precio_mensual or 0)),
            estado=PaymentStatus.EXITOSO,
            proveedor=proveedor or PaymentProvider.DUMMY,
            external_id=external_id,
        )
        db.add(pago)

    return pago


def check_resource_limit(db: Session, empresa_usuario_id: int, subscription: Optional[Subscription], resource: str) -> None:
    """
    Verifica que crear un recurso no supere el límite del plan actual. Lanza HTTPException
    403 (resource_limit_exceeded) si el tenant ya alcanzó el tope.

    resource: "habitaciones" | "usuarios". Un límite <= 0 (o None) se interpreta como ilimitado.
    """
    from fastapi import HTTPException
    from models.core import Room
    from models.usuario import Usuario

    plan = subscription.plan if subscription else None
    if plan is None:
        return  # sin plan no podemos validar; el enforcement de acceso ya cubre lo crítico

    if resource == "habitaciones":
        limite = plan.max_habitaciones
        actual = db.query(Room).filter_by(empresa_usuario_id=empresa_usuario_id, activo=True).count()
    elif resource == "usuarios":
        limite = plan.max_usuarios
        actual = db.query(Usuario).filter_by(
            empresa_usuario_id=empresa_usuario_id, deleted=False, activo=True
        ).count()
    else:
        return

    if not limite or limite <= 0:
        return  # ilimitado

    if actual >= limite:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "resource_limit_exceeded",
                "resource": resource,
                "current": actual,
                "limit": limite,
                "message": f"Alcanzaste el límite de {resource} de tu plan ({actual}/{limite}).",
                "call_to_action": f"Actualizá tu plan para agregar más {resource}.",
                "upgrade_url": "/app/billing",
            },
        )


def start_trial(empresa: EmpresaUsuario, subscription: Subscription, plan_demo: Plan) -> None:
    """
    Inicializa (o reinicia) un trial demo. Usado en el registro y en downgrade_to_demo.
    No hace commit.
    """
    now = utcnow()
    fin = now + timedelta(days=TRIAL_DAYS)
    subscription.plan_id = plan_demo.id
    subscription.estado = SubscriptionStatus.ACTIVO
    subscription.fecha_proxima_renovacion = fin
    empresa.plan_tipo = PlanType.DEMO
    empresa.fecha_inicio_demo = now
    empresa.fecha_fin_demo = fin
