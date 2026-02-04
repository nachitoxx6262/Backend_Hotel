"""
Tests for Invoice Engine
Validación del motor de cálculo financiero (invoice_engine.py)
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
        self.mock_db = Mock()
        
        # Mock Stay básico
        self.mock_stay = Mock()
        self.mock_stay.id = 1
        self.mock_stay.checkin_real = datetime(2025, 1, 10, 15, 0)
        self.mock_stay.checkout_real = None
        self.mock_stay.charges = []
        self.mock_stay.payments = []
        self.mock_stay.occupancies = []
        
        # Mock Reservation
        self.mock_reservation = Mock()
        self.mock_reservation.fecha_checkin = date(2025, 1, 10)
        self.mock_reservation.fecha_checkout = date(2025, 1, 15)
        self.mock_reservation.descuento_porcentaje = 0
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
    
    def test_compute_invoice_basic_stay(self):
        """Test cálculo básico: 5 noches, tarifa estándar, sin cargos adicionales"""
        # Configurar checkout para 5 noches
        checkout_date = date(2025, 1, 15)
        
        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=checkout_date,
            nights_override=None,
            tarifa_override=None
        )
        
        # Validaciones
        assert result.calculated_nights == 5
        assert result.final_nights == 5
        assert result.nightly_rate == Decimal("1000.00")
        assert result.room_subtotal == Decimal("5000.00")  # 5 * 1000
        assert result.charges_total == Decimal("0")
        assert result.taxes_total == Decimal("1050.00")  # 5000 * 0.21
        assert result.total == Decimal("6050.00")  # 5000 + 1050
        assert result.balance == Decimal("6050.00")  # sin pagos
        assert not result.nights_override_applied
        assert not result.tarifa_override_applied
        assert not result.is_overstay
    
    def test_compute_invoice_with_charges(self):
        """Test con cargos adicionales (minibar, room service)"""
        checkout_date = date(2025, 1, 13)  # 3 noches
        
        # Agregar cargos
        charge1 = Mock()
        charge1.tipo = "consumo"
        charge1.descripcion = "Minibar"
        charge1.monto_total = Decimal("500.00")
        
        charge2 = Mock()
        charge2.tipo = "servicio"
        charge2.descripcion = "Room Service"
        charge2.monto_total = Decimal("800.00")
        
        self.mock_stay.charges = [charge1, charge2]
        
        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=checkout_date,
            nights_override=None,
            tarifa_override=None
        )
        
        # Validaciones
        assert result.calculated_nights == 3
        assert result.room_subtotal == Decimal("3000.00")  # 3 * 1000
        assert result.charges_total == Decimal("1300.00")  # 500 + 800
        assert result.base_total == Decimal("4300.00")  # 3000 + 1300
        assert result.taxes_total == Decimal("903.00")  # 4300 * 0.21
        assert result.total == Decimal("5203.00")  # 4300 + 903
    
    def test_compute_invoice_with_payments(self):
        """Test con pagos realizados"""
        checkout_date = date(2025, 1, 12)  # 2 noches
        
        # Agregar pagos
        payment1 = Mock()
        payment1.monto = Decimal("1000.00")
        payment1.es_reverso = False
        
        payment2 = Mock()
        payment2.monto = Decimal("500.00")
        payment2.es_reverso = False
        
        # Pago revertido (no debe contar)
        payment3 = Mock()
        payment3.monto = Decimal("200.00")
        payment3.es_reverso = True
        
        self.mock_stay.payments = [payment1, payment2, payment3]
        
        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=checkout_date,
            nights_override=None,
            tarifa_override=None
        )
        
        # Validaciones
        assert result.calculated_nights == 2
        assert result.room_subtotal == Decimal("2000.00")
        assert result.taxes_total == Decimal("420.00")  # 2000 * 0.21
        assert result.total == Decimal("2420.00")
        assert result.payments_total == Decimal("1500.00")  # 1000 + 500 (sin reverso)
        assert result.balance == Decimal("920.00")  # 2420 - 1500
    
    def test_compute_invoice_with_discount(self):
        """Test con descuento porcentual"""
        checkout_date = date(2025, 1, 14)  # 4 noches
        self.mock_reservation.descuento_porcentaje = 15  # 15% descuento
        
        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=checkout_date,
            nights_override=None,
            tarifa_override=None
        )
        
        # Validaciones
        assert result.calculated_nights == 4
        assert result.room_subtotal == Decimal("4000.00")  # 4 * 1000
        assert result.discount_percent == 15
        assert result.discount_amount == Decimal("600.00")  # 4000 * 0.15
        assert result.base_total == Decimal("3400.00")  # 4000 - 600
        assert result.taxes_total == Decimal("714.00")  # 3400 * 0.21
        assert result.total == Decimal("4114.00")  # 3400 + 714
    
    def test_compute_invoice_with_nights_override(self):
        """Test con override manual de noches"""
        checkout_date = date(2025, 1, 15)  # 5 noches calculadas
        
        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=checkout_date,
            nights_override=3,  # Override a 3 noches
            tarifa_override=None
        )
        
        # Validaciones
        assert result.calculated_nights == 5
        assert result.final_nights == 3  # Override aplicado
        assert result.nights_override_applied is True
        assert result.room_subtotal == Decimal("3000.00")  # 3 * 1000 (con override)
    
    def test_compute_invoice_with_tarifa_override(self):
        """Test con override manual de tarifa"""
        checkout_date = date(2025, 1, 13)  # 3 noches
        
        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=checkout_date,
            nights_override=None,
            tarifa_override=1500.00  # Override a $1500/noche
        )
        
        # Validaciones
        assert result.calculated_nights == 3
        assert result.nightly_rate == Decimal("1500.00")  # Override aplicado
        assert result.tarifa_override_applied is True
        assert result.rate_source == "override"
        assert result.room_subtotal == Decimal("4500.00")  # 3 * 1500
    
    def test_compute_invoice_zero_nights(self):
        """Test edge case: checkout el mismo día del checkin"""
        # Checkout el mismo día
        checkout_date = date(2025, 1, 10)
        
        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=checkout_date,
            nights_override=None,
            tarifa_override=None
        )
        
        # Validaciones
        assert result.calculated_nights == 0
        assert result.final_nights == 1  # Mínimo 1 noche (política del hotel)
        assert result.room_subtotal == Decimal("1000.00")  # Cobra 1 noche mínimo
    
    def test_compute_invoice_full_payment(self):
        """Test con pago total - balance debe ser 0"""
        checkout_date = date(2025, 1, 12)  # 2 noches
        
        # Pago exacto del total
        payment = Mock()
        payment.monto = Decimal("2420.00")  # Total exacto (2000 + 420 IVA)
        payment.es_reverso = False
        self.mock_stay.payments = [payment]
        
        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=checkout_date,
            nights_override=None,
            tarifa_override=None
        )
        
        # Validaciones
        assert result.total == Decimal("2420.00")
        assert result.payments_total == Decimal("2420.00")
        assert result.balance == Decimal("0")  # Pagado totalmente
    
    def test_compute_invoice_overpayment(self):
        """Test con pago excesivo - balance negativo (a favor del cliente)"""
        checkout_date = date(2025, 1, 11)  # 1 noche
        
        # Pago excesivo
        payment = Mock()
        payment.monto = Decimal("3000.00")  # Más del total
        payment.es_reverso = False
        self.mock_stay.payments = [payment]
        
        result = compute_invoice(
            db=self.mock_db,
            stay=self.mock_stay,
            checkout_date_override=checkout_date,
            nights_override=None,
            tarifa_override=None
        )
        
        # Validaciones
        assert result.total == Decimal("1210.00")  # 1000 + 210 IVA
        assert result.payments_total == Decimal("3000.00")
        assert result.balance == Decimal("-1790.00")  # Debe devolver al cliente


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
