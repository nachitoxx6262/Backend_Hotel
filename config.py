"""
Configuración de Stripe y Payment Gateway
"""
import os
from typing import Optional

# Stripe Configuration
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_dummy_key_for_development")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_dummy_key_for_development")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test_dummy_secret")

# Stripe es OPCIONAL (el gateway principal es MercadoPago). Si en producción no hay
# clave real, el módulo Stripe queda deshabilitado (PAYMENT_SYSTEM_ENABLED=False) y
# se avisa — no se bloquea el arranque.
_IS_PROD = os.getenv("ENV", "development").lower() in ("production", "prod")
if _IS_PROD and STRIPE_SECRET_KEY == "sk_test_dummy_key_for_development":
    import logging
    logging.getLogger("uvicorn.error").warning(
        "STRIPE_SECRET_KEY no configurada en producción: módulo de pagos Stripe DESHABILITADO. "
        "Ignorá esto si usás MercadoPago."
    )

# Payment Configuration
PAYMENT_CURRENCY = "usd"
PAYMENT_SYSTEM_ENABLED = STRIPE_SECRET_KEY != "sk_test_dummy_key_for_development"

# Retry Configuration
MAX_PAYMENT_RETRIES = 3
RETRY_DELAY_SECONDS = 300  # 5 minutes

# Feature Flags
ENABLE_STRIPE_TESTING = os.getenv("ENABLE_STRIPE_TESTING", "false").lower() == "true"

# Housekeeping: token secreto para el cron de generación de tareas (endpoint interno).
# Si está vacío, el endpoint de cron responde 503 (deshabilitado).
HOUSEKEEPING_CRON_TOKEN = os.getenv("HOUSEKEEPING_CRON_TOKEN", "")

# Import stripe if available
try:
    import stripe
    if STRIPE_SECRET_KEY and STRIPE_SECRET_KEY != "sk_test_dummy_key_for_development":
        stripe.api_key = STRIPE_SECRET_KEY
        STRIPE_AVAILABLE = True
    else:
        STRIPE_AVAILABLE = False
except ImportError:
    stripe = None
    STRIPE_AVAILABLE = False

# Stripe Error Messages
STRIPE_ERRORS = {
    "card_declined": "Tarjeta rechazada. Por favor intenta con otra.",
    "expired_card": "Tarjeta expirada.",
    "incorrect_cvc": "CVC incorrecto.",
    "processing_error": "Error procesando pago. Intenta de nuevo.",
    "rate_limit": "Demasiados intentos. Por favor espera e intenta nuevamente.",
    "authentication_error": "Error de autenticación. Verifica tus credenciales.",
}

def get_stripe_client():
    """Retorna cliente de Stripe configurado"""
    if not STRIPE_AVAILABLE:
        return None
    return stripe

def is_stripe_configured() -> bool:
    """Verifica si Stripe está correctamente configurado"""
    return STRIPE_AVAILABLE and STRIPE_SECRET_KEY != "sk_test_dummy_key_for_development"
