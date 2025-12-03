import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGGER_NAME = "backend_hotel"
_LOG_FILE = Path("hotel_logs.txt")


def _configure_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        handler = RotatingFileHandler(_LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


_logger = _configure_logger()


def log_event(area: str, usuario: str, accion: str, detalle: str = "") -> None:
    area_label = area.upper()
    message = f"{area_label} | Usuario: {usuario} | Accion: {accion}"
    if detalle:
        message += f" | Detalle: {detalle}"
    _logger.info(message)
