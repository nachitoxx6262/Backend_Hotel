"""
Configuración de Stripe y Payment Gateway
"""
import os
from typing import Optional

# Stripe Configuration
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_dummy_key_for_development")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_dummy_key_for_development")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test_dummy_secret")

# Payment Configuration
PAYMENT_CURRENCY = "usd"
PAYMENT_SYSTEM_ENABLED = STRIPE_SECRET_KEY != "sk_test_dummy_key_for_development"

# Retry Configuration
MAX_PAYMENT_RETRIES = 3
RETRY_DELAY_SECONDS = 300  # 5 minutes

# Feature Flags
ENABLE_STRIPE_TESTING = os.getenv("ENABLE_STRIPE_TESTING", "false").lower() == "true"

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
