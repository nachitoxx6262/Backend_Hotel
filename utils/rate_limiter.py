"""
Rate Limiting Middleware
Protección contra ataques de fuerza bruta y abuso de API
"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
import os

# Configurar limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[os.getenv("RATE_LIMIT_DEFAULT", "100/minute")],
    storage_uri=os.getenv("REDIS_URL", "memory://"),  # Usar Redis en producción
    strategy="fixed-window"
)

def setup_rate_limiting(app):
    """Configurar rate limiting en la aplicación FastAPI"""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
    return limiter
