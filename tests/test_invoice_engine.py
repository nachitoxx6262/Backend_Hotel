"""
Tests for Invoice Engine
Validación del motor de cálculo financiero (invoice_engine.py)

Las aserciones reflejan el comportamiento ACTUAL del motor:
- El total expuesto es `grand_total` (no `total`).
- El IVA (21%) se aplica solo sobre el alojamiento (`room_subtotal`), no sobre
  los cargos.
- El descuento porcentual se pasa por el parámetro `discount_pct_override`
  (el motor no lee `reservation.descuento_porcentaje`).
- Los mocks setean en None los atributos opcionales que el motor sondea con
  getattr(...), porque un Mock genera atributos automáticos (no None) y
  rompería los cálculos (Decimal/parse_to_date sobre un Mock).
"""

import sys
from pathlib import Path

# Agregar directorio raíz al PYTHONPATH para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, MagicMock

from utils.invoice_engine import (
    compute_invoice,
    _safe_decimal,
    _safe_float,
    parse_to_date,
    IVA_RATE_DEFAULT
)


class TestHelperFunctions:
    """Tests para funciones auxiliares"""

    def test_safe_decimal_with_valid_values(self):
        assert _safe_decimal(10) == Decimal("10")
        assert _safe_decimal("25.50") == Decimal("25.50")
        assert _safe_decimal(Decimal("100.99")) == Decimal("100.99")

    def test_safe_decimal_with_none(self):
        assert _safe_decimal(None) == Decimal("0")
        assert _safe_decimal(None, Decimal("10")) == Decimal("10")

    def test_safe_float_with_valid_values(self):
        assert _safe_float(10) == 10.0
        assert _safe_float(Decimal("25.50")) == 25.50
        assert _safe_float("30.75") == 30.75

    def test_safe_float_with_none(self):
        assert _safe_float(None) == 0.0
        assert _safe_float(None, 50.0) == 50.0

    def test_parse_to_date_with_string(self):
        assert parse_to_date("2025-01-15") == date(2025, 1, 15)
        assert parse_to_date("2025-12-31T23:59:59Z") == date(2025, 12, 31)

    def test_parse_to_date_with_datetime(self):
        dt = datetime(2025, 6, 20, 14, 30, 0)
        assert parse_to_date(dt) == date(2025, 6, 20)

    def test_parse_to_date_with_date(self):
        d = date(2025, 3, 10)
        assert parse_to_date(d) == date(2025, 3, 10)


class TestInvoiceEngine:
    """Tests del motor de facturación"""

    def setup_method(self):
        """Setup para cada test - crea mocks básicos"""
        # El cálculo no necesita DB: la tarifa sale de precio_base del room_type.
        # Con db=None, _get_nightly_rate_for_date va directo al fallback de precio_base.
        self.mock_db = None

        # Mock Stay básico
        self.mock_stay = Mock()
        self.mock_stay.id = 1
        self.mock_stay.estado = "abierta"
        self.mock_stay.checkin_real = datetime(2025, 1, 10, 15, 0)
        self.mock_stay.checkout_real = None
        self.mock_stay.charges = []
        self.mock_stay.payments = []
        self.mock_stay.occupancies = []
        # Atributos opcionales que el motor sondea con getattr -> deben ser None
        # (si no, el Mock devuelve un sub-Mock y rompe Decimal()/parse_to_date()).
        self.mock_stay.nightly_rate = None
        self.mock_stay.nightly_rate_snapshot = None
        self.mock_stay.checkout_planned = None
        self.mock_stay.checkin_planned = None

        # Mock Reservation
        self.mock_reservation = Mock()
        self.mock_reservation.fecha_checkin = date(2025, 1, 10)
        self.mock_reservation.fecha_checkout = date(2025, 1, 15)
        self.mock_reservation.cliente = None
        self.mock_reservation.empresa = None
        self.mock_reservation.nombre_temporal = None
        self.mock_stay.reservation = self.mock_reservation

        # Mock Room
        self.mock_room = Mock()
        self.mock_room.id = 101
        self.mock_room.numero = "101"
        self.mock_room.estado_operativo = "ocupada"

        # Mock RoomType con tarifa
        self.mock_room_type = Mock()
        self.mock_room_type.id = 1
        self.mock_room_type.nombre = "Standard"
        self.mock_room_type.precio_base = Decimal("1000.00")
        self.mock_room.tipo = self.mock_room_type

        # Mock StayRoomOccupancy
        self.mock_occupancy = Mock()
        self.mock_occupancy.room = self.mock_room
        self.mock_occupancy.desde = date(2025, 1, 10)
        self.mock_occupancy.hasta = None
        self.mock_stay.occupancies = [self.mock_occupancy]

    def _make_charge(self, tipo, descripcion, monto_total, charge_id=1):
        """Helper: crea un cargo mock con los campos que lee el motor."""
        charge = Mock()
        charge.id = charge_id
        charge.tipo = tipo
        charge.descripcion = descripcion
        charge.monto_total = monto_total
        charge.cantidad = None        # getattr(..., None) -> usa default 1
        charge.monto_unitario = None  # getattr(..., None) -> usa monto_total
        return charge

    def _make_payment(self, monto, es_reverso=False, payment_id=1):
        payment = Mock()
        payment.id = payment_id
        payment.monto = monto
        payment.es_reverso = es_reverso
        payment.timestamp = None
        return payment

    def test_compute_invoice_basic_stay(self):
        """Cálculo básico: 5 noches, tarifa estándar, sin cargos adicionales"""
        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=date(2025, 1, 15),  # 5 noches
            nights_override=None,
            tarifa_override=None,
        )

        assert result.calculated_nights == 5
        assert result.final_nights == 5
        assert result.nightly_rate == Decimal("1000.00")
        assert result.room_subtotal == Decimal("5000.00")          # 5 * 1000
        assert result.charges_total == Decimal("0")
        assert result.taxes_total == Decimal("1050.00")            # 5000 * 0.21
        assert result.grand_total == Decimal("6050.00")            # 5000 + 1050
        assert result.balance == Decimal("6050.00")                # sin pagos
        assert not result.nights_override_applied
        assert not result.tarifa_override_applied
        assert not result.is_overstay

    def test_compute_invoice_with_charges(self):
        """Con cargos adicionales. El IVA se aplica solo sobre el alojamiento."""
        self.mock_stay.charges = [
            self._make_charge("consumo", "Minibar", Decimal("500.00"), 1),
            self._make_charge("servicio", "Room Service", Decimal("800.00"), 2),
        ]

        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=date(2025, 1, 13),  # 3 noches
            nights_override=None,
            tarifa_override=None,
        )

        assert result.calculated_nights == 3
        assert result.room_subtotal == Decimal("3000.00")          # 3 * 1000
        assert result.charges_total == Decimal("1300.00")          # 500 + 800
        assert result.taxes_total == Decimal("630.00")             # IVA solo sobre 3000
        assert result.grand_total == Decimal("4930.00")            # 3000 + 1300 + 630

    def test_compute_invoice_with_payments(self):
        """Con pagos realizados (los reversos no cuentan)."""
        self.mock_stay.payments = [
            self._make_payment(Decimal("1000.00"), es_reverso=False, payment_id=1),
            self._make_payment(Decimal("500.00"), es_reverso=False, payment_id=2),
            self._make_payment(Decimal("200.00"), es_reverso=True, payment_id=3),
        ]

        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=date(2025, 1, 12),  # 2 noches
            nights_override=None,
            tarifa_override=None,
        )

        assert result.calculated_nights == 2
        assert result.room_subtotal == Decimal("2000.00")
        assert result.taxes_total == Decimal("420.00")             # 2000 * 0.21
        assert result.grand_total == Decimal("2420.00")
        assert result.payments_total == Decimal("1500.00")         # 1000 + 500 (sin reverso)
        assert result.balance == Decimal("920.00")                 # 2420 - 1500

    def test_compute_invoice_with_discount(self):
        """Descuento porcentual vía discount_pct_override (15%)."""
        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=date(2025, 1, 14),  # 4 noches
            nights_override=None,
            tarifa_override=None,
            discount_pct_override=15,
        )

        assert result.calculated_nights == 4
        assert result.room_subtotal == Decimal("4000.00")         # 4 * 1000
        assert result.discounts_total == Decimal("600.00")        # 4000 * 0.15
        assert result.taxes_total == Decimal("840.00")            # 4000 * 0.21
        assert result.grand_total == Decimal("4240.00")           # 4000 + 840 - 600

    def test_compute_invoice_with_nights_override(self):
        """Override manual de noches."""
        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=date(2025, 1, 15),  # 5 noches calculadas
            nights_override=3,                          # override a 3
            tarifa_override=None,
        )

        assert result.calculated_nights == 5
        assert result.final_nights == 3
        assert result.nights_override_applied is True
        assert result.room_subtotal == Decimal("3000.00")          # 3 * 1000

    def test_compute_invoice_with_tarifa_override(self):
        """Override manual de tarifa."""
        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=date(2025, 1, 13),  # 3 noches
            nights_override=None,
            tarifa_override=1500.00,
        )

        assert result.calculated_nights == 3
        assert result.nightly_rate == Decimal("1500.00")
        assert result.tarifa_override_applied is True
        assert result.rate_source == "override"
        assert result.room_subtotal == Decimal("4500.00")          # 3 * 1500

    def test_compute_invoice_zero_nights(self):
        """Edge case: checkout el mismo día del checkin -> mínimo 1 noche."""
        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=date(2025, 1, 10),  # mismo día
            nights_override=None,
            tarifa_override=None,
        )

        # El motor aplica mínimo 1 noche cuando la estadía está abierta.
        assert result.final_nights == 1
        assert result.room_subtotal == Decimal("1000.00")          # cobra 1 noche

    def test_compute_invoice_full_payment(self):
        """Pago total -> balance 0."""
        self.mock_stay.payments = [self._make_payment(Decimal("2420.00"))]

        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=date(2025, 1, 12),  # 2 noches
            nights_override=None,
            tarifa_override=None,
        )

        assert result.grand_total == Decimal("2420.00")
        assert result.payments_total == Decimal("2420.00")
        assert result.balance == Decimal("0")

    def test_compute_invoice_overpayment(self):
        """Sobrepago -> balance negativo (a favor del cliente)."""
        self.mock_stay.payments = [self._make_payment(Decimal("3000.00"))]

        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=date(2025, 1, 11),  # 1 noche
            nights_override=None,
            tarifa_override=None,
        )

        assert result.grand_total == Decimal("1210.00")            # 1000 + 210 IVA
        assert result.payments_total == Decimal("3000.00")
        assert result.balance == Decimal("-1790.00")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
