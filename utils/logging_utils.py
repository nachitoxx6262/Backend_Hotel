"""
Logging estructurado para el backend.
- En producción: formato JSON (apto para Datadog, CloudWatch, Loki, etc.)
- En desarrollo: formato legible por humanos con colores
- Rotación automática de archivos de log
"""
import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


ENV = os.getenv("ENV", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = Path(os.getenv("LOG_FILE", "hotel_logs.txt"))

_LOGGER_NAME = "backend_hotel"


class _JSONFormatter(logging.Formatter):
    """Formateador JSON para producción."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Campos extra inyectados por log_event
        for field in ("area", "usuario", "accion", "detalle"):
            if hasattr(record, field):
                log_obj[field] = getattr(record, field)

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, ensure_ascii=False)


class _HumanFormatter(logging.Formatter):
    """Formateador legible para desarrollo."""

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        base = f"{color}{ts} | {record.levelname:<8}{self.RESET} | {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def _build_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger

    level = getattr(logging, LOG_LEVEL, logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    # Handler de consola (siempre activo)
    console = logging.StreamHandler()
    console.setFormatter(_HumanFormatter() if ENV != "production" else _JSONFormatter())
    console.setLevel(level)
    logger.addHandler(console)

    # Handler de archivo con rotación
    try:
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=5_000_000,   # 5 MB por archivo
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(_JSONFormatter())  # archivo siempre en JSON
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    except OSError as e:
        logger.warning(f"No se pudo crear el archivo de log '{LOG_FILE}': {e}")

    return logger


_logger = _build_logger()


# ─── API pública ──────────────────────────────────────────────────────────────

def log_event(
    area: str,
    usuario: str,
    accion: str,
    detalle: str = "",
    level: str = "INFO",
) -> None:
    """
    Registra un evento de negocio.

    Args:
        area: Módulo o sección (e.g. "auth", "billing", "caja")
        usuario: Username o identificador del actor
        accion: Descripción de la acción
        detalle: Información adicional (opcional)
        level: Nivel de log ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    message = f"[{area.upper()}] {usuario} | {accion}"
    if detalle:
        message += f" | {detalle}"

    extra = {"area": area, "usuario": usuario, "accion": accion, "detalle": detalle}
    _logger.log(log_level, message, extra=extra)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Retorna un logger hijo del logger principal.
    Útil para módulos que necesitan su propio namespace de log.
    """
    return logging.getLogger(f"{_LOGGER_NAME}.{name}" if name else _LOGGER_NAME)
