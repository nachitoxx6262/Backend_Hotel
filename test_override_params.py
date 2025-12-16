#!/usr/bin/env python3
"""
Test script para verificar que los parámetros de override se aceptan
en el endpoint GET /stays/{stay_id}/invoice-preview
"""

import sys
import json
from pathlib import Path

# Agregar el backend al path
sys.path.insert(0, str(Path(__file__).parent))

# Imports FastAPI
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Imports del backend
from main import app
from database.conexion import SessionLocal

def test_override_parameters():
    """Verificar que el endpoint acepta todos los parámetros de override"""
    
    client = TestClient(app)
    
    # Usar un stay_id que exista en la base de datos
    stay_id = 1
    
    print("\n" + "="*70)
    print("TEST: Verificar parámetros de override en GET /invoice-preview")
    print("="*70)
    
    # Test 1: Sin overrides
    print("\n1. Test sin overrides:")
    response = client.get(f"/api/calendar/stays/{stay_id}/invoice-preview")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Preview cargado: {len(data.get('breakdown_lines', []))} líneas")
    else:
        print(f"   ✗ Error: {response.text}")
    
    # Test 2: Con tarifa_override
    print("\n2. Test con tarifa_override:")
    response = client.get(f"/api/calendar/stays/{stay_id}/invoice-preview?tarifa_override=18000")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Preview con tarifa override: {data['room']['nightly_rate']}")
        if 'warnings' in data:
            for w in data['warnings']:
                if 'TARIFA_OVERRIDE' in w.get('code', ''):
                    print(f"   ✓ Warning: {w['message']}")
    else:
        print(f"   ✗ Error: {response.text}")
    
    # Test 3: Con descuento_override_pct
    print("\n3. Test con discount_override_pct:")
    response = client.get(f"/api/calendar/stays/{stay_id}/invoice-preview?discount_override_pct=15")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Descuentos totales: {data['totals']['discounts_total']}")
        if 'warnings' in data:
            for w in data['warnings']:
                if 'DISCOUNT_OVERRIDE' in w.get('code', ''):
                    print(f"   ✓ Warning: {w['message']}")
    else:
        print(f"   ✗ Error: {response.text}")
    
    # Test 4: Con tax_override_mode = exento
    print("\n4. Test con tax_override_mode=exento:")
    response = client.get(f"/api/calendar/stays/{stay_id}/invoice-preview?tax_override_mode=exento")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Impuestos totales: {data['totals']['taxes_total']}")
        if 'warnings' in data:
            for w in data['warnings']:
                if 'TAX_OVERRIDE' in w.get('code', ''):
                    print(f"   ✓ Warning: {w['message']}")
    else:
        print(f"   ✗ Error: {response.text}")
    
    # Test 5: Con todos los overrides
    print("\n5. Test con TODOS los overrides:")
    response = client.get(
        f"/api/calendar/stays/{stay_id}/invoice-preview?"
        "nights_override=7"
        "&tarifa_override=18000"
        "&discount_override_pct=15"
        "&tax_override_mode=custom"
        "&tax_override_value=5000"
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Preview recalculado:")
        print(f"     - Noches: {data['nights']['suggested_to_charge']}")
        print(f"     - Tarifa: {data['room']['nightly_rate']}")
        print(f"     - Subtotal: {data['totals']['room_subtotal']}")
        print(f"     - Descuentos: {data['totals']['discounts_total']}")
        print(f"     - Impuestos: {data['totals']['taxes_total']}")
        print(f"     - Total: {data['totals']['grand_total']}")
        if 'warnings' in data:
            print(f"   ✓ Warnings ({len(data['warnings'])}):")
            for w in data['warnings']:
                print(f"     - {w['code']}: {w['message']}")
    else:
        print(f"   ✗ Error: {response.text}")
    
    print("\n" + "="*70)
    print("✓ Tests completados")
    print("="*70 + "\n")


if __name__ == "__main__":
    test_override_parameters()
