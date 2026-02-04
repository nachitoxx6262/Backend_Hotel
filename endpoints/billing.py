"""
Endpoints de Billing - Gestión de suscripciones y planes
"""
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import json
import hmac
import hashlib

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import conexion
from models.usuario import Usuario
from models.core import EmpresaUsuario, Plan, Subscription, PlanType, SubscriptionStatus, PaymentAttempt, PaymentStatus, PaymentProvider
from schemas.billing import (
    PlanResponse, BillingStatusResponse, SubscriptionInfo, UsageInfo, TrialInfo,
    UpgradePlanRequest, UpgradeResponse, CancelSubscriptionRequest, CancelSubscriptionResponse,
    PaymentIntentRequest, PaymentIntentResponse, PlanType as SchemaPlanType
)
from utils.dependencies import get_current_user, require_admin_or_manager
from utils.tenant_middleware import check_trial_expiration, is_trial_write_blocked
from utils.logging_utils import log_event
from config import STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET, get_stripe_client, is_stripe_configured


router = APIRouter(prefix="/billing", tags=["Billing"])


# ========== GET ENDPOINTS ==========

@router.get("/planes", response_model=List[PlanResponse])
async def get_available_planes(
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    """
    Retorna lista de planes disponibles para upgrade.
    Accesible para todos los usuarios (lectura pública).
    """
    try:
        planes = db.query(Plan).filter(
            Plan.activo == True
        ).order_by(Plan.precio_mensual).all()
        
        if not planes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No hay planes disponibles"
            )
        
        return [_map_plan_to_response(plan) for plan in planes]
        
    except HTTPException:
        raise
    except Exception as e:
        log_event("billing", current_user.username, "Error al listar planes", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener planes"
        )


@router.get("/status", response_model=BillingStatusResponse)
async def get_subscription_status(
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    """
    Retorna información completa de la suscripción actual del tenant.
    Incluye: plan, uso de recursos, estado del trial, próximo pago.
    """
    try:
        # Super admin no tiene suscripción
        if current_user.es_super_admin or not current_user.empresa_usuario_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Super admin no tiene suscripción"
            )
        
        # Obtener empresa y suscripción
        empresa = db.query(EmpresaUsuario).filter_by(
            id=current_user.empresa_usuario_id,
            deleted=False
        ).first()
        
        if not empresa:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Empresa no encontrada"
            )
        
        subscription = db.query(Subscription).filter_by(
            empresa_usuario_id=empresa.id
        ).first()
        
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Suscripción no encontrada"
            )
        
        plan = subscription.plan
        
        # Obtener información de uso
        from models.core import Room
        habitaciones_count = db.query(Room).filter_by(
            empresa_usuario_id=empresa.id,
            activo=True
        ).count()
        
        usuarios_count = db.query(Usuario).filter_by(
            empresa_usuario_id=empresa.id,
            deleted=False,
            activo=True
        ).count()
        
        # Calcular porcentajes
        hab_limite = plan.max_habitaciones if plan.max_habitaciones and plan.max_habitaciones > 0 else 999
        usr_limite = plan.max_usuarios if plan.max_usuarios and plan.max_usuarios > 0 else 999
        
        hab_porcentaje = (habitaciones_count / hab_limite * 100) if hab_limite > 0 else 0
        usr_porcentaje = (usuarios_count / usr_limite * 100) if usr_limite > 0 else 0
        
        # Trial info
        trial_info_dict = check_trial_expiration(subscription)
        trial_info = TrialInfo(
            is_active=trial_info_dict["is_active"],
            days_remaining=trial_info_dict["days_remaining"],
            expires_at=trial_info_dict.get("expires_at"),
            status=trial_info_dict["status"]
        )
        
        return BillingStatusResponse(
            current_plan=SubscriptionInfo(
                id=subscription.id,
                plan=_map_plan_to_response(plan),
                estado=subscription.estado,
                fecha_inicio=subscription.created_at,
                fecha_proximo_pago=subscription.fecha_proxima_renovacion
            ),
            trial_info=trial_info,
            usage=UsageInfo(
                habitaciones_usadas=habitaciones_count,
                habitaciones_limite=plan.max_habitaciones,
                habitaciones_porcentaje=hab_porcentaje,
                usuarios_usados=usuarios_count,
                usuarios_limite=plan.max_usuarios,
                usuarios_porcentaje=usr_porcentaje
            ),
            payment_method_configured=False,  # TODO: Cuando integre Stripe
            next_billing_date=subscription.fecha_proxima_renovacion
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_event("billing", current_user.username, "Error al obtener status", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener información de suscripción"
        )


# ========== POST ENDPOINTS ==========

@router.post("/upgrade", response_model=UpgradeResponse)
async def upgrade_plan(
    upgrade_data: UpgradePlanRequest,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    """
    Cambia a un nuevo plan (upgrade o downgrade).
    
    Por ahora (sin Stripe integrado): cambio inmediato sin pago.
    Con Stripe (Phase 3B): crea PaymentIntent y cobra diferencia prorrateada.
    """
    try:
        if current_user.es_super_admin or not current_user.empresa_usuario_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Super admin no puede cambiar plan"
            )
        
        # Obtener plan nuevo
        target_plan_type = PlanType[upgrade_data.new_plan_type.name]
        nuevo_plan = db.query(Plan).filter_by(
            nombre=target_plan_type,
            activo=True
        ).first()
        
        if not nuevo_plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan {upgrade_data.new_plan_type} no existe"
            )
        
        # Obtener subscription actual
        subscription = db.query(Subscription).filter_by(
            empresa_usuario_id=current_user.empresa_usuario_id
        ).first()
        
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Suscripción no encontrada"
            )
        
        plan_actual = subscription.plan
        
        if plan_actual.id == nuevo_plan.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ya tienes el plan {nuevo_plan.nombre}"
            )
        
        # Actualizar subscription
        subscription.plan_id = nuevo_plan.id
        subscription.estado = SubscriptionStatus.ACTIVE
        subscription.fecha_proxima_renovacion = datetime.utcnow() + timedelta(days=30)
        
        db.commit()
        
        # Log evento
        log_event(
            "billing",
            current_user.username,
            "Plan actualizado",
            f"de {plan_actual.nombre} a {nuevo_plan.nombre}"
        )
        
        return UpgradeResponse(
            status="upgraded",
            old_plan=_map_plan_to_response(plan_actual),
            new_plan=_map_plan_to_response(nuevo_plan),
            effective_date=datetime.utcnow(),
            message=f"¡Bienvenido a {nuevo_plan.nombre}!",
            next_billing_date=subscription.fecha_proxima_renovacion
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_event("billing", current_user.username, "Error al actualizar plan", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al cambiar de plan"
        )


@router.post("/cancel", response_model=CancelSubscriptionResponse)
async def cancel_subscription(
    cancel_data: CancelSubscriptionRequest,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    """
    Cancela o downgrade de suscripción.
    
    Acciones:
    - 'downgrade_to_demo': Vuelve a trial (Plan DEMO)
    - 'delete': Marca empresa como deletada (soft delete)
    """
    try:
        if current_user.es_super_admin or not current_user.empresa_usuario_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Super admin no puede cancelar"
            )
        
        empresa = db.query(EmpresaUsuario).filter_by(
            id=current_user.empresa_usuario_id,
            deleted=False
        ).first()
        
        if not empresa:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Empresa no encontrada"
            )
        
        subscription = db.query(Subscription).filter_by(
            empresa_usuario_id=empresa.id
        ).first()
        
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Suscripción no encontrada"
            )
        
        if cancel_data.action == "downgrade_to_demo":
            # Volver a plan DEMO (trial)
            plan_demo = db.query(Plan).filter_by(
                nombre=PlanType.DEMO
            ).first()
            
            if plan_demo:
                ahora = datetime.utcnow()
                empresa.plan_tipo = PlanType.DEMO
                empresa.fecha_inicio_demo = ahora
                empresa.fecha_fin_demo = ahora + timedelta(days=10)
                
                subscription.plan_id = plan_demo.id
                subscription.estado = SubscriptionStatus.ACTIVE
                subscription.fecha_proxima_renovacion = ahora + timedelta(days=10)
            
            db.commit()
            
            log_event(
                "billing",
                current_user.username,
                "Downgraded a DEMO",
                f"razón={cancel_data.reason}"
            )
            
            return CancelSubscriptionResponse(
                status="downgraded_to_trial",
                message="Te hemos downgradeado a Plan Demostración (10 días)",
                data_retention_until=None,
                retention_offer="Si cambias de idea, puedes upgradear en cualquier momento"
            )
        
        elif cancel_data.action == "delete":
            # Soft delete de empresa
            empresa.activa = False
            empresa.deleted = True
            subscription.estado = SubscriptionStatus.CANCELADO
            subscription.fecha_proxima_renovacion = None
            db.commit()
            
            log_event(
                "billing",
                current_user.username,
                "Empresa eliminada",
                f"razón={cancel_data.reason}, feedback={cancel_data.feedback}"
            )
            
            retention_date = datetime.utcnow() + timedelta(days=30)
            
            return CancelSubscriptionResponse(
                status="cancelled",
                message="Tu empresa ha sido eliminada. Los datos se retienen por 30 días.",
                data_retention_until=retention_date,
                retention_offer="Si cambias de idea, contacta a soporte dentro de 30 días"
            )
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Acción no válida: {cancel_data.action}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_event("billing", current_user.username, "Error al cancelar", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al procesar cancelación"
        )


# ========== HELPER FUNCTIONS ==========

def _map_plan_to_response(plan: Plan) -> PlanResponse:
    """Adapta el modelo Plan a PlanResponse usando los campos reales de la base."""
    feature_flags = plan.caracteristicas or {}
    permite_facturacion = bool(feature_flags.get("invoicing"))
    permite_reportes = bool(feature_flags.get("reports") or feature_flags.get("custom_reports"))
    soporte_valor = feature_flags.get("support")
    soporte_email = soporte_valor in {"email", "phone_email"}

    return PlanResponse(
        id=plan.id,
        nombre=plan.nombre.name if hasattr(plan.nombre, "name") else str(plan.nombre),
        tipo=SchemaPlanType[plan.nombre.name] if hasattr(plan.nombre, "name") else SchemaPlanType(plan.nombre),
        precio_mensual=float(plan.precio_mensual or 0),
        limite_habitaciones=plan.max_habitaciones,
        limite_usuarios=plan.max_usuarios,
        permite_facturacion=permite_facturacion,
        permite_reportes=permite_reportes,
        soporte_email=soporte_email,
        descripcion=plan.descripcion,
        features=_get_plan_features(plan, permite_facturacion, permite_reportes, soporte_valor)
    )


def _get_plan_features(plan: Plan, permite_facturacion: bool, permite_reportes: bool, soporte_valor: Optional[str]) -> List[str]:
    """Retorna lista de features del plan"""
    features = []

    if plan.max_habitaciones and plan.max_habitaciones > 0:
        features.append(f"{plan.max_habitaciones} habitaciones")
    else:
        features.append("Habitaciones ilimitadas")

    if plan.max_usuarios and plan.max_usuarios > 0:
        features.append(f"{plan.max_usuarios} usuarios")
    else:
        features.append("Usuarios ilimitados")

    if permite_facturacion:
        features.append("Facturación incluida")

    if permite_reportes:
        features.append("Reportes avanzados")

    if soporte_valor:
        features.append("Soporte prioritario" if soporte_valor == "phone_email" else "Soporte por email")

    if plan.nombre == PlanType.DEMO:
        features.append("10 días gratis")

    return features


# ========== STRIPE PAYMENT ENDPOINTS ==========

@router.post("/payment-intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    request_data: PaymentIntentRequest,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    """
    Crea un PaymentIntent en Stripe para cobrar la suscripción.
    
    El frontend debe:
    1. Obtener client_secret de esta respuesta
    2. Usar Stripe Elements para capturar el pago
    3. Confirmar el pago con confirmCardPayment(client_secret)
    
    El webhook (/billing/webhook/stripe) procesará automáticamente
    cuando el pago sea exitoso.
    """
    try:
        if current_user.es_super_admin or not current_user.empresa_usuario_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Super admin no puede crear payment intent"
            )
        
        # Obtener plan
        target_plan_type = PlanType[request_data.plan_type.name]
        nuevo_plan = db.query(Plan).filter_by(
            nombre=target_plan_type,
            activo=True
        ).first()
        
        if not nuevo_plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plan no encontrado"
            )
        
        # Obtener empresa y subscription
        empresa = db.query(EmpresaUsuario).filter_by(
            id=current_user.empresa_usuario_id,
            activa=True,
            deleted=False
        ).first()
        
        subscription = db.query(Subscription).filter_by(
            empresa_usuario_id=empresa.id
        ).first()
        
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Suscripción no encontrada"
            )
        
        # Calcular monto a cobrar (en centavos)
        amount_cents = int(nuevo_plan.precio_mensual * 100)
        
        # Si no hay Stripe configurado, retornar intent demo
        if not is_stripe_configured():
            log_event(
                "billing",
                current_user.username,
                "Payment intent (demo mode - sin Stripe)",
                f"plan={nuevo_plan.nombre}, amount=${nuevo_plan.precio_mensual}"
            )
            
            return PaymentIntentResponse(
                client_secret="pi_test_secret_demo_12345",
                publishable_key=STRIPE_PUBLISHABLE_KEY,
                amount=nuevo_plan.precio_mensual,
                currency="usd",
                plan=_map_plan_to_response(nuevo_plan),
                billing_period_days=30
            )
        
        # Con Stripe configurado
        stripe = get_stripe_client()
        
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="usd",
            metadata={
                "empresa_usuario_id": empresa.id,
                "plan_type": nuevo_plan.nombre.value,
                "user_id": current_user.id,
                "usuario_email": current_user.email
            },
            receipt_email=current_user.email
        )
        
        log_event(
            "billing",
            current_user.username,
            "Payment intent created (Stripe)",
            f"intent_id={intent.id}, plan={nuevo_plan.nombre}, amount=${nuevo_plan.precio_mensual}"
        )
        
        return PaymentIntentResponse(
            client_secret=intent.client_secret,
            publishable_key=STRIPE_PUBLISHABLE_KEY,
            amount=nuevo_plan.precio_mensual,
            currency="usd",
            plan=_map_plan_to_response(nuevo_plan),
            billing_period_days=30
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_event(
            "billing",
            current_user.username if current_user else "unknown",
            "Error creating payment intent",
            f"error={str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear payment intent"
        )


@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(conexion.get_db)
):
    """
    Webhook que Stripe llama cuando ocurren eventos de pago.
    
    Eventos procesados:
    - payment_intent.succeeded: Pago exitoso → Upgrade subscription
    - payment_intent.payment_failed: Pago falló → Registrar intento fallido
    - charge.refunded: Reembolso procesado
    
    Verifica firma de Stripe para seguridad.
    """
    try:
        # Obtener payload y firma
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature")
        
        # Verificar firma si Stripe está configurado
        if is_stripe_configured():
            stripe = get_stripe_client()
            try:
                event = stripe.Webhook.construct_event(
                    payload,
                    sig_header,
                    STRIPE_WEBHOOK_SECRET
                )
            except ValueError:
                log_event("billing", "webhook", "Invalid payload", "ValueError")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid payload"
                )
            except stripe.error.SignatureVerificationError:
                log_event("billing", "webhook", "Invalid signature", "SignatureVerificationError")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid signature"
                )
        else:
            # En modo demo, parse manual
            event = json.loads(payload)
        
        # ========== PROCESAR EVENTOS ==========
        
        if event["type"] == "payment_intent.succeeded":
            intent = event["data"]["object"]
            await _handle_payment_succeeded(intent, db)
        
        elif event["type"] == "payment_intent.payment_failed":
            intent = event["data"]["object"]
            await _handle_payment_failed(intent, db)
        
        elif event["type"] == "charge.refunded":
            charge = event["data"]["object"]
            await _handle_refund(charge, db)
        
        else:
            log_event(
                "billing",
                "webhook",
                f"Unhandled event type: {event['type']}",
                ""
            )
        
        return {"status": "received", "event_type": event.get("type")}
        
    except HTTPException:
        raise
    except Exception as e:
        log_event("billing", "webhook", "Webhook error", f"error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook processing error"
        )


# ========== WEBHOOK HELPER FUNCTIONS ==========

async def _handle_payment_succeeded(intent: Dict[str, Any], db: Session):
    """
    Procesa pago exitoso.
    Actualiza subscription y crea PaymentAttempt record.
    """
    try:
        metadata = intent.get("metadata", {})
        empresa_usuario_id = int(metadata.get("empresa_usuario_id", 0))
        plan_type = metadata.get("plan_type")
        user_id = int(metadata.get("user_id", 0))
        
        if not empresa_usuario_id or not plan_type:
            log_event(
                "billing",
                "webhook",
                "Missing metadata in payment_intent",
                f"intent_id={intent['id']}"
            )
            return
        
        # Obtener plan y subscription
        plan = db.query(Plan).filter_by(
            nombre=PlanType(plan_type)
        ).first()
        
        subscription = db.query(Subscription).filter_by(
            empresa_usuario_id=empresa_usuario_id
        ).first()
        
        if not subscription or not plan:
            log_event(
                "billing",
                "webhook",
                "Subscription or plan not found",
                f"empresa_id={empresa_usuario_id}, plan_type={plan_type}"
            )
            return
        
        # Actualizar subscription
        subscription.plan_id = plan.id
        subscription.estado = SubscriptionStatus.ACTIVO
        subscription.fecha_proxima_renovacion = datetime.utcnow() + timedelta(days=30)
        
        # Crear PaymentAttempt record
        payment = PaymentAttempt(
            subscription_id=subscription.id,
            monto=intent["amount"] / 100,
            estado=PaymentStatus.EXITOSO,
            proveedor=PaymentProvider.STRIPE,
            external_id=intent["id"],
            response_json=json.dumps({
                "charge_id": intent.get("charges", {}).get("data", [{}])[0].get("id"),
                "receipt_url": intent.get("charges", {}).get("data", [{}])[0].get("receipt_url")
            })
        )
        
        db.add(payment)
        db.commit()
        
        # CREAR TRANSACCIÓN AUTOMÁTICA EN CAJA (Ingreso por suscripción)
        from models.core import TransactionCategory, Transaction, TransactionType, PaymentMethod
        
        categoria_suscripcion = db.query(TransactionCategory).filter(
            TransactionCategory.empresa_usuario_id == empresa_usuario_id,
            TransactionCategory.nombre == "Suscripción SaaS",
            TransactionCategory.tipo == "ingreso"  # Usar string directo
        ).first()
        
        if not categoria_suscripcion:
            # Crear categoría del sistema si no existe
            categoria_suscripcion = TransactionCategory(
                empresa_usuario_id=empresa_usuario_id,
                nombre="Suscripción SaaS",
                tipo="ingreso",  # Usar string directo
                descripcion="Pagos de suscripción al sistema",
                activo=True,
                es_sistema=True
            )
            db.add(categoria_suscripcion)
            db.flush()
        
        # Crear transacción automática
        ingreso_transaction = Transaction(
            empresa_usuario_id=empresa_usuario_id,
            tipo="ingreso",  # Usar string directo
            category_id=categoria_suscripcion.id,
            monto=Decimal(str(intent["amount"] / 100)),
            metodo_pago="tarjeta",  # Stripe siempre es tarjeta - usar string directo
            referencia=f"Stripe Payment Intent: {intent['id']}",
            fecha=datetime.utcnow(),
            usuario_id=user_id if user_id > 0 else None,
            subscription_id=subscription.id,
            notas=f"Pago automático vía Stripe - Plan {plan_type}",
            es_automatica=True
        )
        db.add(ingreso_transaction)
        db.commit()
        
        # Log
        empresa = db.query(EmpresaUsuario).filter_by(id=empresa_usuario_id, deleted=False).first()
        log_event(
            "billing",
            empresa.nombre if empresa else f"empresa_{empresa_usuario_id}",
            "Payment succeeded - Subscription upgraded",
            f"plan={plan_type}, amount=${intent['amount']/100}, intent_id={intent['id']}"
        )
        
    except Exception as e:
        db.rollback()
        log_event(
            "billing",
            "webhook",
            "Error handling payment_succeeded",
            f"error={str(e)}, intent_id={intent.get('id')}"
        )


async def _handle_payment_failed(intent: Dict[str, Any], db: Session):
    """
    Procesa pago fallido.
    Crea PaymentAttempt record con estado FAILED.
    """
    try:
        metadata = intent.get("metadata", {})
        empresa_usuario_id = int(metadata.get("empresa_usuario_id", 0))
        plan_type = metadata.get("plan_type")
        
        if not empresa_usuario_id:
            return
        
        # Obtener subscription
        subscription = db.query(Subscription).filter_by(
            empresa_usuario_id=empresa_usuario_id
        ).first()
        
        if not subscription:
            log_event(
                "billing",
                "webhook",
                "Subscription not found for payment_failed",
                f"empresa_id={empresa_usuario_id}"
            )
            return
        
        # Crear PaymentAttempt record (fallido)
        payment = PaymentAttempt(
            subscription_id=subscription.id,
            monto=intent["amount"] / 100,
            estado=PaymentStatus.FALLIDO,
            proveedor=PaymentProvider.STRIPE,
            external_id=intent["id"],
            response_json=json.dumps({
                "error_message": intent.get("last_payment_error", {}).get("message"),
                "error_code": intent.get("last_payment_error", {}).get("code")
            })
        )
        
        db.add(payment)
        db.commit()
        
        empresa = db.query(EmpresaUsuario).filter_by(id=empresa_usuario_id, deleted=False).first()
        log_event(
            "billing",
            empresa.nombre if empresa else f"empresa_{empresa_usuario_id}",
            "Payment failed",
            f"plan={plan_type}, amount=${intent['amount']/100}, error={intent.get('last_payment_error', {}).get('message')}"
        )
        
    except Exception as e:
        db.rollback()
        log_event(
            "billing",
            "webhook",
            "Error handling payment_failed",
            f"error={str(e)}"
        )


async def _handle_refund(charge: Dict[str, Any], db: Session):
    """
    Procesa reembolso.
    Crea PaymentAttempt record con estado REFUNDED.
    """
    try:
        # La metadata está en el payment_intent asociado
        intent_id = charge.get("payment_intent")
        refund_amount = charge.get("refunded", 0)
        
        if not intent_id:
            return
        
        log_event(
            "billing",
            "webhook",
            "Refund processed",
            f"intent_id={intent_id}, amount=${refund_amount/100}"
        )
        
    except Exception as e:
        log_event(
            "billing",
            "webhook",
            "Error handling refund",
            f"error={str(e)}"
        )
