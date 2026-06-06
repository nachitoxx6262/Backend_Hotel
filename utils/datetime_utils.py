"""
Utilidades de fecha/hora con compatibilidad Python 3.12+

datetime.utcnow() está deprecado desde Python 3.12.
Usar utcnow() de este módulo en su lugar.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """
    Retorna la fecha/hora UTC actual como datetime naive (sin tzinfo).
    Compatible con columnas TIMESTAMP WITHOUT TIME ZONE de PostgreSQL.

    Reemplaza datetime.utcnow() que está deprecado desde Python 3.12.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
