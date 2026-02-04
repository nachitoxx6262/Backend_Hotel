"""
Schemas para endpoints de Billing y Suscripciones
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class PlanType(str, Enum):
    """Tipos de planes disponibles"""
    DEMO = "demo"
    BASICO = "basico"
    PREMIUM = "premium"


class PlanResponse(BaseModel):
    """Información pública de un plan"""
    id: int
    nombre: str
    tipo: PlanType
    precio_mensual: float = Field(..., ge=0)
    limite_habitaciones: int = Field(..., description="-1 para ilimitado")
    limite_usuarios: int = Field(..., description="-1 para ilimitado")
    permite_facturacion: bool
    permite_reportes: bool
    soporte_email: bool
    descripcion: Optional[str] = None
    features: List[str] = []

    class Config:
        from_attributes = True


class SubscriptionInfo(BaseModel):
    """Información actual de suscripción"""
    id: int
    plan: PlanResponse
    estado: str  # ACTIVE, PAUSED, CANCELLED
    fecha_inicio: datetime
    fecha_proximo_pago: datetime
    

class UsageInfo(BaseModel):
    """Uso actual de recursos por plan"""
    habitaciones_usadas: int
    habitaciones_limite: int
    habitaciones_porcentaje: float = Field(..., ge=0, le=100)
    
    usuarios_usados: int
    usuarios_limite: int
    usuarios_porcentaje: float = Field(..., ge=0, le=100)


class TrialInfo(BaseModel):
    """Información de período de prueba"""
    is_active: bool
    days_remaining: int
    expires_at: Optional[datetime] = None
    status: str  # 'active' | 'expired' | 'not_trial'


class BillingStatusResponse(BaseModel):
    """Respuesta de GET /billing/status"""
    current_plan: SubscriptionInfo
    trial_info: TrialInfo
    usage: UsageInfo
    payment_method_configured: bool
    next_billing_date: Optional[datetime] = None
    total_spent: float = Field(default=0, ge=0)
    
    class Config:
        from_attributes = True


class UpgradePlanRequest(BaseModel):
    """Request para POST /billing/upgrade"""
    new_plan_type: PlanType = Field(..., description="basico o premium")


class UpgradeResponse(BaseModel):
    """Response de POST /billing/upgrade"""
    status: str  # 'pending_payment', 'upgraded', 'downgraded'
    old_plan: PlanResponse
    new_plan: PlanResponse
    effective_date: datetime
    message: str
    next_billing_date: Optional[datetime] = None
    payment_url: Optional[str] = None  # Para Stripe si es upgrade con pago


class CancelSubscriptionRequest(BaseModel):
    """Request para POST /billing/cancel"""
    action: str = Field(..., description="'downgrade_to_demo' o 'delete'")
    reason: Optional[str] = None
    feedback: Optional[str] = None


class CancelSubscriptionResponse(BaseModel):
    """Response de POST /billing/cancel"""
    status: str  # 'cancelled', 'downgraded_to_trial'
    message: str
    data_retention_until: Optional[datetime] = None
    retention_offer: Optional[str] = None


class PaymentIntentRequest(BaseModel):
    """Request para crear intent de pago (Stripe)"""
    plan_type: PlanType


class PaymentIntentResponse(BaseModel):
    """Response con info para Stripe"""
    client_secret: str
    publishable_key: str
    amount: float
    currency: str = "usd"
    plan: PlanResponse
    billing_period_days: int = 30


class PaymentWebhookData(BaseModel):
    """Data del webhook de Stripe"""
    type: str  # payment_intent.succeeded, etc
    payment_intent_id: str
    amount: int  # en centavos
    status: str
    metadata: Dict[str, Any]


class BillingHistoryItem(BaseModel):
    """Item del historial de billing"""
    id: int
    fecha: datetime
    tipo: str  # 'trial_start', 'upgrade', 'payment_success', 'payment_failed', 'downgrade'
    plan: Optional[str] = None
    monto: Optional[float] = None
    descripcion: str


class FeatureUnavailableError(BaseModel):
    """Error cuando feature no está en plan"""
    error: str = "feature_unavailable"
    message: str
    feature: str
    current_plan: str
    required_plan: str
    upgrade_url: str = "/billing/planes"


class ResourceLimitExceededError(BaseModel):
    """Error cuando se alcanza límite de recursos"""
    error: str = "resource_limit_exceeded"
    message: str
    resource: str
    current: int
    limit: int
    call_to_action: str
    upgrade_url: str = "/billing/planes"


class TrialExpiredError(BaseModel):
    """Error cuando trial expiró"""
    error: str = "trial_expired"
    message: str
    trial_ended_at: datetime
    call_to_action: str = "Elige un plan en /billing/planes"
    available_actions: List[str] = ["GET (lectura)", "GET /billing/planes"]
    upgrade_url: str = "/billing/planes"
