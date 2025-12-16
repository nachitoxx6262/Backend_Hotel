"""
Invoice Engine - Motor de cálculo financiero para estadías
SINGLE SOURCE OF TRUTH para cálculos de checkout e invoice-preview
"""

from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session

from models.core import Stay, Reservation, Room, RoomType, StayCharge, StayPayment
from utils.logging_utils import log_event


# Constantes
IVA_RATE_DEFAULT = 0.21  # 21%


def _safe_float(value, fallback: float = 0.0) -> float:
    """Convierte a float de forma segura"""
    if value is None:
        return fallback
    try:
        if isinstance(value, Decimal):
            return float(value)
        return float(value)
    except (ValueError, TypeError):
        return fallback


def _safe_decimal(value, fallback: Decimal = Decimal("0")) -> Decimal:
    """Convierte a Decimal de forma segura"""
    if value is None:
        return fallback
    try:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
    except (ValueError, TypeError):
        return fallback


def _today_date() -> date:
    """Retorna la fecha de hoy sin hora"""
    return datetime.utcnow().date()


def parse_to_date(value) -> date:
    """Convierte string/datetime/date a date"""
    if value is None:
        raise ValueError("Date value is None")
    
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    
    if isinstance(value, datetime):
        return value.date()
    
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00')).date()
        except ValueError:
            try:
                return datetime.strptime(value, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError(f"Invalid date format: {value}")
    
    raise TypeError(f"Unsupported date type: {type(value)}")


class InvoiceCalculation:
    """Resultado del cálculo de invoice"""
    
    def __init__(self):
        # Fechas y noches
        self.checkin_date: Optional[date] = None
        self.checkout_candidate_date: Optional[date] = None
        self.checkout_planned_date: Optional[date] = None
        self.planned_nights: int = 0
        self.calculated_nights: int = 0
        self.final_nights: int = 0
        self.nights_override_applied: bool = False
        
        # Habitación y tarifa
        self.room_id: Optional[int] = None
        self.room_numero: Optional[str] = None
        self.room_type_name: Optional[str] = None
        self.nightly_rate: Decimal = Decimal("0")
        self.rate_source: str = "missing"
        self.tarifa_override_applied: bool = False
        
        # Subtotales
        self.room_subtotal: Decimal = Decimal("0")
        self.charges_total: Decimal = Decimal("0")
        self.taxes_total: Decimal = Decimal("0")
        self.discounts_total: Decimal = Decimal("0")
        
        # Total y pagos
        self.grand_total: Decimal = Decimal("0")
        self.payments_total: Decimal = Decimal("0")
        self.balance: Decimal = Decimal("0")
        
        # Detalles
        self.charges_breakdown: List[Dict[str, Any]] = []
        self.payments_breakdown: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, str]] = []
        
        # Metadata
        self.readonly: bool = False
        self.cliente_nombre: Optional[str] = None


def compute_invoice(
    stay: Stay,
    db: Session,
    checkout_date_override: Optional[str] = None,
    nights_override: Optional[int] = None,
    tarifa_override: Optional[float] = None,
    discount_pct_override: Optional[float] = None,
    tax_mode_override: Optional[str] = None,
    tax_value_override: Optional[float] = None,
) -> InvoiceCalculation:
    """
    MOTOR ÚNICO DE CÁLCULO DE INVOICE
    
    Calcula totales, saldo y genera warnings.
    Usado por invoice-preview y checkout.
    
    Args:
        stay: Estadía a calcular
        db: Sesión de base de datos
        checkout_date_override: Fecha de checkout candidata (YYYY-MM-DD o ISO)
        nights_override: Override de noches a cobrar
        tarifa_override: Override de tarifa por noche
        discount_pct_override: Descuento adicional en % (0-100)
        tax_mode_override: 'normal' | 'exento' | 'custom'
        tax_value_override: Valor personalizado de impuesto
    
    Returns:
        InvoiceCalculation con todos los cálculos
    """
    result = InvoiceCalculation()
    
    # =====================================================================
    # 1) VALIDACIONES BÁSICAS
    # =====================================================================
    if not stay:
        raise ValueError("Stay es None")
    
    reservation = stay.reservation
    if not reservation:
        raise ValueError("Stay sin reserva asociada")
    
    result.readonly = (stay.estado == "cerrada")
    
    # =====================================================================
    # 2) CLIENTE
    # =====================================================================
    if reservation.cliente:
        result.cliente_nombre = f"{reservation.cliente.nombre} {reservation.cliente.apellido}".strip()
    elif reservation.empresa:
        result.cliente_nombre = (reservation.empresa.nombre or "").strip()
    elif getattr(reservation, "nombre_temporal", None):
        result.cliente_nombre = (reservation.nombre_temporal or "").strip()
    else:
        result.cliente_nombre = f"Stay #{stay.id}"
    
    # =====================================================================
    # 3) OCUPACIÓN + HABITACIÓN
    # =====================================================================
    occupancy = None
    if stay.occupancies:
        active = [o for o in stay.occupancies if not o.hasta]
        occupancy = active[0] if active else stay.occupancies[-1]
    
    if not occupancy or not occupancy.room:
        raise ValueError("Stay sin ocupación/habitación registrada")
    
    room = occupancy.room
    room_type = getattr(room, "tipo", None)
    
    result.room_id = room.id
    result.room_numero = str(room.numero)
    result.room_type_name = (getattr(room_type, "nombre", None) or "No especificado")
    
    # =====================================================================
    # 4) TARIFA
    # =====================================================================
    if tarifa_override is not None and tarifa_override >= 0:
        result.nightly_rate = _safe_decimal(tarifa_override, Decimal("0"))
        result.rate_source = "override"
        result.tarifa_override_applied = True
    elif (stay_rate := getattr(stay, "nightly_rate", None) or getattr(stay, "nightly_rate_snapshot", None)):
        result.nightly_rate = _safe_decimal(stay_rate, Decimal("0"))
        result.rate_source = "stay_snapshot"
    elif room_type and getattr(room_type, "precio_base", None):
        result.nightly_rate = _safe_decimal(room_type.precio_base, Decimal("0"))
        result.rate_source = "room_type"
    else:
        result.nightly_rate = Decimal("0")
        result.rate_source = "missing"
    
    # =====================================================================
    # 5) FECHAS + NOCHES
    # =====================================================================
    # Check-in real
    raw_checkin = stay.checkin_real or occupancy.desde
    if not raw_checkin:
        raise ValueError("Stay sin fecha de check-in real")
    
    result.checkin_date = parse_to_date(raw_checkin)
    
    # Checkout planificado
    raw_checkout_planned = getattr(stay, "checkout_planned", None) or reservation.fecha_checkout
    if not raw_checkout_planned:
        raise ValueError("No existe checkout planificado")
    
    result.checkout_planned_date = parse_to_date(raw_checkout_planned)
    
    # Checkout candidato
    if checkout_date_override:
        result.checkout_candidate_date = parse_to_date(checkout_date_override)
    elif result.readonly and stay.checkout_real:
        result.checkout_candidate_date = parse_to_date(stay.checkout_real)
    else:
        result.checkout_candidate_date = _today_date()
    
    if result.checkout_candidate_date < result.checkin_date:
        raise ValueError(f"Checkout ({result.checkout_candidate_date}) anterior a checkin ({result.checkin_date})")
    
    # Planned nights
    raw_plan_checkin = getattr(stay, "checkin_planned", None) or reservation.fecha_checkin
    try:
        plan_checkin_date = parse_to_date(raw_plan_checkin) if raw_plan_checkin else result.checkin_date
    except Exception:
        plan_checkin_date = result.checkin_date
    
    result.planned_nights = max(0, (result.checkout_planned_date - plan_checkin_date).days)
    
    # Calculated nights
    raw_diff = (result.checkout_candidate_date - result.checkin_date).days
    result.calculated_nights = max(1, raw_diff) if not result.readonly else max(0, raw_diff)
    
    suggested_to_charge = max(1, result.calculated_nights) if not result.readonly else max(0, result.calculated_nights)
    
    # Final nights
    result.nights_override_applied = nights_override is not None
    result.final_nights = int(nights_override) if result.nights_override_applied else int(suggested_to_charge)
    
    # =====================================================================
    # 6) CÁLCULO DE TOTALES
    # =====================================================================
    
    # --- Subtotal de alojamiento ---
    result.room_subtotal = result.nightly_rate * Decimal(str(result.final_nights))
    
    # --- Cargos / Consumos ---
    charges_total = Decimal("0")
    discount_from_charges = Decimal("0")
    fee_from_charges = Decimal("0")
    
    for charge in (stay.charges or []):
        c_type = getattr(charge, "tipo", None) or "charge"
        c_desc = getattr(charge, "descripcion", None) or f"Cargo {c_type}"
        c_total = _safe_decimal(getattr(charge, "monto_total", None), Decimal("0"))
        c_qty = _safe_decimal(getattr(charge, "cantidad", None), Decimal("1"))
        c_unit = _safe_decimal(getattr(charge, "monto_unitario", None), c_total)
        
        if c_type == "discount":
            discount_from_charges += abs(c_total)
            result.charges_breakdown.append({
                "type": "discount",
                "description": c_desc,
                "quantity": float(c_qty),
                "unit_price": -float(abs(c_total)),
                "total": -float(abs(c_total)),
                "charge_id": charge.id,
            })
            continue
        
        if c_type == "fee":
            fee_from_charges += c_total
            result.charges_breakdown.append({
                "type": "fee",
                "description": c_desc,
                "quantity": float(c_qty),
                "unit_price": float(c_total),
                "total": float(c_total),
                "charge_id": charge.id,
            })
            continue
        
        charges_total += c_total
        result.charges_breakdown.append({
            "type": c_type,
            "description": c_desc,
            "quantity": float(c_qty),
            "unit_price": float(c_unit),
            "total": float(c_total),
            "charge_id": charge.id,
        })
        
        if c_total == 0:
            result.warnings.append({
                "code": "UNPRICED_CHARGE",
                "message": f"Cargo sin precio: {c_desc}",
                "severity": "warning",
            })
    
    result.charges_total = charges_total
    
    # --- Impuestos ---
    taxes_total = fee_from_charges
    
    # IVA automático
    should_apply_auto_iva = True
    if any((getattr(c, "tipo", None) == "fee" and "iva" in (getattr(c, "descripcion", "") or "").lower()) 
           for c in (stay.charges or [])):
        should_apply_auto_iva = False
    
    iva_rate = Decimal("0")
    iva_alojamiento = Decimal("0")
    tax_override_applied = False
    
    if tax_mode_override:
        tax_override_applied = True
        if tax_mode_override.lower() == "exento":
            iva_rate = Decimal("0")
            iva_alojamiento = Decimal("0")
        elif tax_mode_override.lower() == "normal":
            iva_rate = Decimal(str(IVA_RATE_DEFAULT))
            iva_alojamiento = (result.room_subtotal * iva_rate) if should_apply_auto_iva else Decimal("0")
        elif tax_mode_override.lower() == "custom" and tax_value_override is not None:
            iva_alojamiento = _safe_decimal(tax_value_override, Decimal("0"))
    else:
        iva_rate = Decimal(str(IVA_RATE_DEFAULT))
        iva_alojamiento = (result.room_subtotal * iva_rate) if should_apply_auto_iva else Decimal("0")
    
    taxes_total += iva_alojamiento
    result.taxes_total = taxes_total
    
    # --- Descuentos ---
    discounts_total = discount_from_charges
    discount_override_amount = Decimal("0")
    
    if discount_pct_override is not None and discount_pct_override > 0:
        discount_override_amount = result.room_subtotal * Decimal(str(discount_pct_override)) / Decimal("100")
        discounts_total += discount_override_amount
    
    result.discounts_total = discounts_total
    
    # --- Total ---
    result.grand_total = result.room_subtotal + result.charges_total + result.taxes_total - result.discounts_total
    
    # --- Pagos ---
    payments_total = Decimal("0")
    
    for pago in (stay.payments or []):
        if getattr(pago, "es_reverso", False):
            continue
        
        amount = _safe_decimal(getattr(pago, "monto", None), Decimal("0"))
        if amount <= 0:
            continue
        
        payments_total += amount
        result.payments_breakdown.append({
            "id": pago.id,
            "monto": float(amount),
            "metodo": getattr(pago, "metodo", "") or "desconocido",
            "referencia": getattr(pago, "referencia", "") or "",
            "timestamp": (pago.timestamp.isoformat() if getattr(pago, "timestamp", None) else None),
            "usuario": getattr(pago, "usuario", None),
        })
    
    result.payments_total = payments_total
    
    # --- Saldo ---
    result.balance = result.grand_total - result.payments_total
    
    # =====================================================================
    # 7) WARNINGS
    # =====================================================================
    if result.rate_source == "missing" or result.nightly_rate <= 0:
        result.warnings.append({
            "code": "MISSING_RATE",
            "message": f"No hay tarifa configurada para {result.room_type_name}",
            "severity": "error",
        })
    
    if result.tarifa_override_applied:
        result.warnings.append({
            "code": "TARIFA_OVERRIDE",
            "message": f"Tarifa modificada: ${float(result.nightly_rate):.2f}/noche",
            "severity": "info",
        })
    
    if result.nights_override_applied:
        result.warnings.append({
            "code": "NIGHTS_OVERRIDE",
            "message": f"Override de noches: {result.final_nights} (calculado: {result.calculated_nights})",
            "severity": "info",
        })
    
    if discount_pct_override is not None and discount_pct_override > 0:
        result.warnings.append({
            "code": "DISCOUNT_OVERRIDE",
            "message": f"Descuento aplicado: {discount_pct_override}% = ${float(discount_override_amount):.2f}",
            "severity": "info",
        })
    
    if tax_override_applied:
        result.warnings.append({
            "code": "TAX_OVERRIDE",
            "message": f"Régimen de impuesto modificado",
            "severity": "info",
        })
    
    if result.planned_nights != result.calculated_nights and result.planned_nights > 0:
        result.warnings.append({
            "code": "NIGHTS_DIFFER",
            "message": f"Noches calculadas ({result.calculated_nights}) difieren de planificadas ({result.planned_nights})",
            "severity": "warning",
        })
    
    if not result.readonly and raw_diff == 0:
        result.warnings.append({
            "code": "SAME_DAY_CANDIDATE",
            "message": "Checkout el mismo día del check-in. Se cobra mínimo 1 noche.",
            "severity": "info",
        })
    
    if result.balance > 0:
        result.warnings.append({
            "code": "BALANCE_DUE",
            "message": f"Saldo pendiente: ${float(result.balance):.2f}",
            "severity": "warning",
        })
    elif result.balance < 0:
        result.warnings.append({
            "code": "OVERPAYMENT",
            "message": f"Sobrepago: ${float(abs(result.balance)):.2f}",
            "severity": "info",
        })
    
    return result
