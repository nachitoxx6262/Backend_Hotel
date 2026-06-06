"""
Email Service — Envío de emails transaccionales usando SMTP.
Usa Jinja2 para plantillas HTML y fastapi-mail para el transporte.
Falla silenciosamente: nunca hace rollback de operaciones de negocio.
"""
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger("email_service")

TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "email"

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _render(template_name: str, **ctx) -> str:
    ctx.setdefault("year", datetime.now().year)
    tpl = _jinja_env.get_template(template_name)
    return tpl.render(**ctx)


def _get_smtp_config(settings=None) -> dict:
    """
    Obtiene la configuración SMTP: primero desde HotelSettings del tenant,
    luego desde variables de entorno globales.
    """
    host = (getattr(settings, "smtp_host", None) or os.getenv("SMTP_HOST", ""))
    port = int(getattr(settings, "smtp_port", None) or os.getenv("SMTP_PORT", "587"))
    user = (getattr(settings, "smtp_user", None) or os.getenv("SMTP_USER", ""))
    from_email = (getattr(settings, "smtp_from_email", None) or os.getenv("SMTP_FROM", user))

    # Descifrar contraseña si está cifrada en DB
    raw_pass = getattr(settings, "smtp_password_encrypted", None)
    if raw_pass:
        try:
            from cryptography.fernet import Fernet
            fernet_key = os.getenv("FERNET_KEY", "")
            if fernet_key:
                f = Fernet(fernet_key.encode())
                password = f.decrypt(raw_pass.encode()).decode()
            else:
                password = raw_pass  # fallback: stored plaintext
        except Exception:
            password = raw_pass
    else:
        password = os.getenv("SMTP_PASSWORD", "")

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "from_email": from_email,
    }


async def _send_email(
    to: str,
    subject: str,
    html_body: str,
    attachments: Optional[list] = None,
    settings=None,
) -> bool:
    """
    Envía un email. Retorna True si tuvo éxito, False si falló.
    NUNCA lanza excepciones hacia el caller.
    """
    cfg = _get_smtp_config(settings)
    if not cfg["host"] or not cfg["user"]:
        logger.warning("SMTP no configurado — email no enviado a %s", to)
        return False

    try:
        from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType

        conf = ConnectionConfig(
            MAIL_USERNAME=cfg["user"],
            MAIL_PASSWORD=cfg["password"],
            MAIL_FROM=cfg["from_email"],
            MAIL_PORT=cfg["port"],
            MAIL_SERVER=cfg["host"],
            MAIL_STARTTLS=cfg["port"] in (587, 25),
            MAIL_SSL_TLS=cfg["port"] == 465,
            USE_CREDENTIALS=bool(cfg["user"]),
            VALIDATE_CERTS=True,
        )

        message = MessageSchema(
            subject=subject,
            recipients=[to],
            body=html_body,
            subtype=MessageType.html,
            attachments=attachments or [],
        )

        fm = FastMail(conf)
        await fm.send_message(message)
        logger.info("Email enviado a %s: %s", to, subject)
        return True

    except Exception as exc:
        logger.error("Error enviando email a %s: %s", to, str(exc))
        return False


# ─────────────────────────────────────────────────────────────
# Métodos de negocio
# ─────────────────────────────────────────────────────────────

async def send_password_reset(
    to: str,
    username: str,
    reset_url: str,
    hotel_nombre: str = "Hotel",
    settings=None,
) -> bool:
    html = _render(
        "password_reset.html",
        username=username,
        reset_url=reset_url,
        hotel_nombre=hotel_nombre,
    )
    return await _send_email(
        to=to,
        subject=f"[{hotel_nombre}] Restablecer contraseña",
        html_body=html,
        settings=settings,
    )


async def send_reservation_confirmation(
    to: str,
    huesped_nombre: str,
    reservation_id: int,
    fecha_checkin: str,
    fecha_checkout: str,
    tipo_habitacion: str,
    hotel_nombre: str = "Hotel",
    settings=None,
) -> bool:
    html = _render(
        "reservation_confirmation.html",
        huesped_nombre=huesped_nombre,
        reservation_id=reservation_id,
        fecha_checkin=fecha_checkin,
        fecha_checkout=fecha_checkout,
        tipo_habitacion=tipo_habitacion,
        hotel_nombre=hotel_nombre,
    )
    return await _send_email(
        to=to,
        subject=f"[{hotel_nombre}] Confirmación de reserva #{reservation_id}",
        html_body=html,
        settings=settings,
    )


async def send_checkout_invoice(
    to: str,
    huesped_nombre: str,
    invoice_number: str,
    total: str,
    saldo: str,
    saldo_ok: bool,
    pdf_bytes: bytes,
    hotel_nombre: str = "Hotel",
    settings=None,
) -> bool:
    html = _render(
        "checkout_invoice.html",
        huesped_nombre=huesped_nombre,
        invoice_number=invoice_number,
        total=total,
        saldo=saldo,
        saldo_ok=saldo_ok,
        hotel_nombre=hotel_nombre,
    )
    attachments = [
        {
            "file": pdf_bytes,
            "filename": f"factura-{invoice_number}.pdf",
            "mime_type": "application",
            "mime_subtype": "pdf",
        }
    ]
    return await _send_email(
        to=to,
        subject=f"[{hotel_nombre}] Factura {invoice_number}",
        html_body=html,
        attachments=attachments,
        settings=settings,
    )
