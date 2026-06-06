"""
Mercado Pago Integration — Procesamiento de pagos para el mercado argentino.

Solo se activa si MERCADO_PAGO_ACCESS_TOKEN está configurado en el entorno.
Sigue la misma estructura que billing.py (Stripe) para consistencia.

Flujo:
1. Frontend llama POST /mercadopago/create-preference con el monto
2. Backend crea preferencia en MP y devuelve init_point (URL de pago)
3. Usuario paga en la plataforma de MP
4. MP llama al webhook (POST /mercadopago/webhook)
5. Backend actualiza el PaymentAttempt y la suscripción
"""
import os
import hmac
import hashlib
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import conexion
from models.usuario import Usuario
from models.core import Subscription, PaymentAttempt, PaymentStatus, PaymentProvider, EmpresaUsuario
from utils.dependencies import get_current_user
from utils.logging_utils import log_event
from utils.datetime_utils import utcnow

logger = logging.getLogger("mercadopago")

router = APIRouter(prefix="/mercadopago", tags=["Mercado Pago"])

MP_ACCESS_TOKEN = os.getenv("MERCADO_PAGO_ACCESS_TOKEN", "")
MP_WEBHOOK_SECRET = os.getenv("MERCADO_PAGO_WEBHOOK_SECRET", "")


def _is_configured() -> bool:
    return bool(MP_ACCESS_TOKEN)


def _get_mp_sdk():
    """Retorna el SDK de Mercado Pago inicializado."""
    try:
        import mercadopago
        sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
        return sdk
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="SDK de Mercado Pago no instalado. Correr: pip install mercadopago"
        )


# ─────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────

class CreatePreferenceRequest(BaseModel):
    monto: float = Field(..., gt=0, description="Monto a cobrar en ARS")
    descripcion: str = Field(default="Suscripción Hotel PMS", max_length=255)
    external_reference: Optional[str] = Field(None, description="Referencia interna (ej. subscription_id)")


class PreferenceResponse(BaseModel):
    preference_id: str
    init_point: str        # URL de pago en producción
    sandbox_init_point: str  # URL de pago en sandbox
    payment_attempt_id: int


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@router.get("/status")
def mercadopago_status():
    """Indica si Mercado Pago está configurado en este entorno."""
    return {
        "configured": _is_configured(),
        "message": "Mercado Pago activo" if _is_configured() else "MERCADO_PAGO_ACCESS_TOKEN no configurado",
    }


@router.post("/create-preference", response_model=PreferenceResponse)
def create_preference(
    data: CreatePreferenceRequest,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db),
):
    """
    Crea una preferencia de pago en Mercado Pago.
    Retorna la URL de pago (init_point) para redirigir al usuario.
    """
    if not _is_configured():
        raise HTTPException(
            status_code=503,
            detail="Mercado Pago no está configurado. Agregar MERCADO_PAGO_ACCESS_TOKEN en .env"
        )

    if current_user.es_super_admin or not current_user.empresa_usuario_id:
        raise HTTPException(status_code=403, detail="No disponible para super admin")

    subscription = db.query(Subscription).filter_by(
        empresa_usuario_id=current_user.empresa_usuario_id
    ).first()
    if not subscription:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")

    empresa = db.query(EmpresaUsuario).filter_by(id=current_user.empresa_usuario_id).first()
    hotel_nombre = empresa.nombre_hotel if empresa else "Hotel PMS"

    # Crear intento de pago en la DB antes de llamar a MP
    attempt = PaymentAttempt(
        subscription_id=subscription.id,
        monto=Decimal(str(data.monto)),
        estado=PaymentStatus.PENDIENTE,
        proveedor=PaymentProvider.MERCADO_PAGO,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    sdk = _get_mp_sdk()

    # URL base del backend para notificaciones
    base_url = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")

    preference_data = {
        "items": [
            {
                "title": f"{hotel_nombre} — {data.descripcion}",
                "quantity": 1,
                "unit_price": float(data.monto),
                "currency_id": "ARS",
            }
        ],
        "external_reference": data.external_reference or str(attempt.id),
        "notification_url": f"{base_url}/mercadopago/webhook",
        "back_urls": {
            "success": f"{os.getenv('FRONTEND_URL', 'http://localhost:5173')}/app/billing?mp_status=success",
            "failure": f"{os.getenv('FRONTEND_URL', 'http://localhost:5173')}/app/billing?mp_status=failure",
            "pending": f"{os.getenv('FRONTEND_URL', 'http://localhost:5173')}/app/billing?mp_status=pending",
        },
        "auto_return": "approved",
        "metadata": {
            "payment_attempt_id": attempt.id,
            "subscription_id": subscription.id,
            "empresa_usuario_id": current_user.empresa_usuario_id,
        },
    }

    try:
        result = sdk.preference().create(preference_data)
        response = result.get("response", {})

        if result.get("status") not in (200, 201):
            raise ValueError(f"MP error: {result}")

        preference_id = response.get("id", "")
        init_point = response.get("init_point", "")
        sandbox_init_point = response.get("sandbox_init_point", "")

        # Guardar external_id en el intento de pago
        attempt.external_id = preference_id
        attempt.response_json = {"preference_id": preference_id, "status": "preference_created"}
        db.commit()

        log_event("mercadopago", current_user.username, "Preferencia creada",
                  f"preference_id={preference_id} monto={data.monto} attempt_id={attempt.id}")

        return PreferenceResponse(
            preference_id=preference_id,
            init_point=init_point,
            sandbox_init_point=sandbox_init_point,
            payment_attempt_id=attempt.id,
        )

    except Exception as exc:
        attempt.estado = PaymentStatus.FALLIDO
        attempt.response_json = {"error": str(exc)}
        db.commit()
        log_event("mercadopago", current_user.username, "Error al crear preferencia", str(exc))
        raise HTTPException(status_code=500, detail=f"Error al crear preferencia: {str(exc)}")


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def mercadopago_webhook(
    request: Request,
    db: Session = Depends(conexion.get_db),
):
    """
    Webhook de Mercado Pago — recibe notificaciones de pago.

    MP envía notificaciones de tipo 'payment' con el payment_id.
    Verificamos el estado y actualizamos el PaymentAttempt.
    """
    if not _is_configured():
        return {"status": "mp_not_configured"}

    try:
        body = await request.body()
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Payload inválido")

    # Verificar firma si hay secret configurado
    if MP_WEBHOOK_SECRET:
        signature = request.headers.get("x-signature", "")
        expected = hmac.new(
            MP_WEBHOOK_SECRET.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            log_event("mercadopago", "webhook", "Firma inválida", f"signature={signature[:20]}")
            raise HTTPException(status_code=401, detail="Firma inválida")

    topic = payload.get("type") or payload.get("topic", "")
    log_event("mercadopago", "webhook", f"Notificación recibida tipo={topic}", str(payload)[:200])

    if topic != "payment":
        return {"status": "ignored", "type": topic}

    # Obtener el payment_id y consultar a MP
    data_obj = payload.get("data", {})
    payment_id = str(data_obj.get("id", ""))
    if not payment_id:
        return {"status": "no_payment_id"}

    try:
        sdk = _get_mp_sdk()
        payment_info = sdk.payment().get(payment_id)
        payment_data = payment_info.get("response", {})

        mp_status = payment_data.get("status", "")
        external_reference = payment_data.get("external_reference", "")
        transaction_amount = payment_data.get("transaction_amount", 0)

        # Buscar el PaymentAttempt por external_id (preference_id) o external_reference
        attempt = (
            db.query(PaymentAttempt)
            .filter(
                (PaymentAttempt.external_id == payment_data.get("preference_id")) |
                (PaymentAttempt.id == int(external_reference) if external_reference.isdigit() else False)
            )
            .first()
        )

        if not attempt:
            # Crear nuevo intento si no existe (pago directo sin preferencia previa)
            log_event("mercadopago", "webhook", "PaymentAttempt no encontrado", f"payment_id={payment_id}")
            return {"status": "attempt_not_found"}

        # Mapear estado de MP a nuestro enum
        estado_map = {
            "approved": PaymentStatus.EXITOSO,
            "authorized": PaymentStatus.EXITOSO,
            "in_process": PaymentStatus.PENDIENTE,
            "pending": PaymentStatus.PENDIENTE,
            "rejected": PaymentStatus.FALLIDO,
            "cancelled": PaymentStatus.FALLIDO,
            "refunded": PaymentStatus.FALLIDO,
            "charged_back": PaymentStatus.FALLIDO,
        }
        nuevo_estado = estado_map.get(mp_status, PaymentStatus.PENDIENTE)

        attempt.estado = nuevo_estado
        attempt.external_id = payment_id
        attempt.response_json = {
            "mp_status": mp_status,
            "mp_payment_id": payment_id,
            "transaction_amount": transaction_amount,
        }

        # Si el pago fue exitoso, registrar en la suscripción
        if nuevo_estado == PaymentStatus.EXITOSO:
            from datetime import timedelta
            subscription = db.query(Subscription).filter_by(
                id=attempt.subscription_id
            ).first()
            if subscription:
                subscription.estado = "activo"
                if subscription.fecha_proxima_renovacion:
                    subscription.fecha_proxima_renovacion += timedelta(days=30)
                else:
                    subscription.fecha_proxima_renovacion = utcnow() + timedelta(days=30)

            log_event("mercadopago", "webhook", "Pago aprobado",
                      f"payment_id={payment_id} monto={transaction_amount}")

        db.commit()
        return {"status": "processed", "mp_status": mp_status, "estado": nuevo_estado.value}

    except Exception as exc:
        log_event("mercadopago", "webhook", "Error procesando webhook", str(exc))
        # Retornar 200 para que MP no reintente
        return {"status": "error", "detail": str(exc)}
