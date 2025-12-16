"""
Test para verificar el cálculo correcto de noches en invoice-preview
"""
import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000/api/calendar"

def test_invoice_preview_nights_calculation():
    print("=" * 80)
    print("TEST: Verificar cálculo de noches en invoice-preview")
    print("=" * 80)
    
    # Obtener una estadía existente
    print("\n1. Buscando estadías activas...")
    stays_response = requests.get(f"{BASE_URL}/stays", params={"estado": "ocupada"})
    
    if stays_response.status_code != 200:
        print(f"❌ Error al obtener estadías: {stays_response.status_code}")
        return
    
    stays = stays_response.json()
    if not stays:
        print("⚠️ No hay estadías ocupadas para probar")
        return
    
    stay_id = stays[0]['id']
    print(f"✅ Usando estadía ID: {stay_id}")
    
    # Test 1: Invoice preview sin parámetros (usa checkout_planned)
    print(f"\n2. Test 1: Invoice preview sin parámetros")
    print("-" * 80)
    response = requests.get(f"{BASE_URL}/stays/{stay_id}/invoice-preview")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Invoice preview generado")
        print(f"\n📊 Resumen de noches:")
        print(f"   Planificadas: {data['nights']['planned']}")
        print(f"   Calculadas: {data['nights']['calculated']}")
        print(f"   Sugeridas a cobrar: {data['nights']['suggested_to_charge']}")
        print(f"   Override aplicado: {data['nights']['override_applied']}")
        
        print(f"\n💰 Resumen financiero:")
        print(f"   Tarifa noche: ${data['room']['nightly_rate']}")
        print(f"   Fuente tarifa: {data['room']['rate_source']}")
        print(f"   Subtotal habitación: ${data['totals']['room_subtotal']}")
        print(f"   Impuestos: ${data['totals']['taxes_total']}")
        print(f"   Descuentos: ${data['totals']['discounts_total']}")
        print(f"   Total: ${data['totals']['grand_total']}")
        print(f"   Saldo: ${data['totals']['balance']}")
        
        if data['warnings']:
            print(f"\n⚠️ Warnings ({len(data['warnings'])}):")
            for w in data['warnings']:
                severity_icon = "❌" if w['severity'] == 'error' else "⚠️" if w['severity'] == 'warning' else "ℹ️"
                print(f"   {severity_icon} [{w['code']}] {w['message']}")
        
        # Verificar que las noches sugeridas sean >= 1
        assert data['nights']['suggested_to_charge'] >= 1, "Las noches sugeridas deben ser >= 1"
        print(f"\n✅ Validación: Noches sugeridas >= 1 ✓")
        
        # Verificar que si calculated == 0, suggested_to_charge == 1
        if data['nights']['calculated'] == 0:
            assert data['nights']['suggested_to_charge'] == 1, "Si calculated=0, suggested debe ser 1"
            print(f"✅ Validación: Check-in y checkout mismo día → mínimo 1 noche ✓")
        
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return
    
    # Test 2: Invoice preview con checkout_date = hoy
    print(f"\n3. Test 2: Invoice preview con checkout_date = hoy")
    print("-" * 80)
    today = datetime.now().date().isoformat()
    response = requests.get(
        f"{BASE_URL}/stays/{stay_id}/invoice-preview",
        params={"checkout_date": today}
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Invoice preview con checkout_date={today}")
        print(f"   Noches calculadas: {data['nights']['calculated']}")
        print(f"   Noches sugeridas: {data['nights']['suggested_to_charge']}")
        assert data['nights']['suggested_to_charge'] >= 1, "Siempre mínimo 1 noche"
        print(f"✅ Validación: Siempre >= 1 noche ✓")
    else:
        print(f"❌ Error: {response.status_code}")
    
    # Test 3: Invoice preview con nights_override
    print(f"\n4. Test 3: Invoice preview con override de noches")
    print("-" * 80)
    response = requests.get(
        f"{BASE_URL}/stays/{stay_id}/invoice-preview",
        params={"nights_override": 3}
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Invoice preview con nights_override=3")
        print(f"   Noches sugeridas (override): {data['nights']['suggested_to_charge']}")
        print(f"   Override aplicado: {data['nights']['override_applied']}")
        print(f"   Valor override: {data['nights']['override_value']}")
        assert data['nights']['override_applied'] == True, "Override debe estar aplicado"
        assert data['nights']['override_value'] == 3, "Override debe ser 3"
        print(f"✅ Validación: Override aplicado correctamente ✓")
    else:
        print(f"❌ Error: {response.status_code}")
    
    # Test 4: Verificar estructura de breakdown_lines
    print(f"\n5. Test 4: Verificar estructura de líneas")
    print("-" * 80)
    response = requests.get(f"{BASE_URL}/stays/{stay_id}/invoice-preview")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Líneas de factura: {len(data['breakdown_lines'])}")
        for i, line in enumerate(data['breakdown_lines'], 1):
            print(f"   {i}. [{line['line_type']}] {line['description']}")
            print(f"      Cantidad: {line['quantity']} × ${line['unit_price']} = ${line['total']}")
        
        # Verificar que haya al menos la línea de alojamiento
        room_lines = [l for l in data['breakdown_lines'] if l['line_type'] == 'room']
        assert len(room_lines) > 0, "Debe haber al menos 1 línea de alojamiento"
        print(f"\n✅ Validación: Línea de alojamiento presente ✓")
        
        # Verificar que haya impuestos
        tax_lines = [l for l in data['breakdown_lines'] if l['line_type'] == 'tax']
        if tax_lines:
            print(f"✅ Validación: {len(tax_lines)} línea(s) de impuestos ✓")
        
    else:
        print(f"❌ Error: {response.status_code}")
    
    print("\n" + "=" * 80)
    print("✅ TODOS LOS TESTS COMPLETADOS")
    print("=" * 80)

if __name__ == "__main__":
    try:
        test_invoice_preview_nights_calculation()
    except requests.exceptions.ConnectionError:
        print("❌ Error: No se puede conectar al backend.")
        print("   Asegúrate de que uvicorn esté corriendo en http://localhost:8000")
    except AssertionError as e:
        print(f"❌ Validación falló: {e}")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
