"""
Script de prueba para el endpoint Invoice Preview
Ejecutar después de tener el backend corriendo
"""

import requests
import json
from datetime import date, timedelta

BASE_URL = "http://localhost:8000/api/calendar"

def print_section(title):
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def print_json(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))

def test_invoice_preview():
    """
    Test básico del endpoint invoice-preview
    Requiere que exista al menos una stay activa en la base de datos
    """
    
    print_section("🧾 INVOICE PREVIEW ENDPOINT - TEST")
    
    # =========================================================================
    # 1. Obtener una stay activa para testear
    # =========================================================================
    
    print_section("1. Buscando stay activa en el calendario...")
    
    today = date.today()
    from_date = (today - timedelta(days=30)).isoformat()
    to_date = (today + timedelta(days=30)).isoformat()
    
    calendar_url = f"{BASE_URL}/calendar?from={from_date}&to={to_date}"
    
    try:
        response = requests.get(calendar_url)
        response.raise_for_status()
        calendar_data = response.json()
        
        # Buscar primer bloque de tipo "stay"
        stay_blocks = [b for b in calendar_data.get("blocks", []) if b.get("kind") == "stay"]
        
        if not stay_blocks:
            print("❌ No se encontraron stays activas en el calendario")
            print("⚠️  Crea una reserva y haz check-in primero")
            return
        
        stay_block = stay_blocks[0]
        stay_id = stay_block["id"]
        
        print(f"✅ Stay encontrada: ID={stay_id}")
        print(f"   Cliente: {stay_block.get('cliente_nombre', 'N/A')}")
        print(f"   Habitación: {stay_block.get('room_numero', 'N/A')}")
        print(f"   Estado: {stay_block.get('estado', 'N/A')}")
        
    except Exception as e:
        print(f"❌ Error obteniendo calendario: {e}")
        return
    
    # =========================================================================
    # 2. Test 1: Preview básico (sin parámetros)
    # =========================================================================
    
    print_section(f"2. Test 1: Preview básico (stay_id={stay_id})")
    
    preview_url = f"{BASE_URL}/stays/{stay_id}/invoice-preview"
    
    try:
        response = requests.get(preview_url)
        response.raise_for_status()
        preview = response.json()
        
        print("✅ Preview generado exitosamente")
        print(f"\n📋 Resumen:")
        print(f"   Cliente: {preview['cliente_nombre']}")
        print(f"   Habitación: {preview['room']['numero']} ({preview['room']['room_type_name']})")
        print(f"   Tarifa: ${preview['room']['nightly_rate']:,.2f} ({preview['room']['rate_source']})")
        print(f"   Noches planificadas: {preview['nights']['planned']}")
        print(f"   Noches calculadas: {preview['nights']['calculated']}")
        print(f"   Noches a cobrar: {preview['nights']['suggested_to_charge']}")
        
        print(f"\n💰 Totales:")
        totals = preview['totals']
        print(f"   Alojamiento: ${totals['room_subtotal']:,.2f}")
        print(f"   Consumos: ${totals['charges_total']:,.2f}")
        print(f"   Impuestos: ${totals['taxes_total']:,.2f}")
        print(f"   Descuentos: -${totals['discounts_total']:,.2f}")
        print(f"   ───────────────────────")
        print(f"   Gran Total: ${totals['grand_total']:,.2f}")
        print(f"   Pagado: ${totals['payments_total']:,.2f}")
        print(f"   ═══════════════════════")
        print(f"   SALDO: ${totals['balance']:,.2f}")
        
        if preview.get('warnings'):
            print(f"\n⚠️  Warnings ({len(preview['warnings'])}):")
            for w in preview['warnings']:
                emoji = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(w['severity'], "•")
                print(f"   {emoji} [{w['code']}] {w['message']}")
        else:
            print("\n✅ Sin warnings")
        
        if preview.get('breakdown_lines'):
            print(f"\n📝 Líneas ({len(preview['breakdown_lines'])}):")
            for line in preview['breakdown_lines']:
                icon = {
                    "room": "🏨",
                    "charge": "🛒",
                    "tax": "📋",
                    "discount": "🎁",
                    "payment": "💳"
                }.get(line['line_type'], "•")
                print(f"   {icon} {line['description']}")
                if line['quantity'] > 1:
                    print(f"      {line['quantity']} × ${line['unit_price']:,.2f} = ${line['total']:,.2f}")
                else:
                    print(f"      ${line['total']:,.2f}")
        
        print("\n📄 Response JSON completo:")
        print_json(preview)
        
    except requests.exceptions.HTTPError as e:
        print(f"❌ Error HTTP {e.response.status_code}")
        print(f"   {e.response.json()}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # =========================================================================
    # 3. Test 2: Preview con checkout_date específico
    # =========================================================================
    
    print_section("3. Test 2: Preview con checkout_date específico")
    
    checkout_date = (today + timedelta(days=2)).isoformat()
    preview_url_with_date = f"{preview_url}?checkout_date={checkout_date}"
    
    try:
        response = requests.get(preview_url_with_date)
        response.raise_for_status()
        preview = response.json()
        
        print(f"✅ Preview con checkout_date={checkout_date}")
        print(f"   Noches calculadas: {preview['nights']['calculated']}")
        print(f"   Noches a cobrar: {preview['nights']['suggested_to_charge']}")
        print(f"   Total: ${preview['totals']['grand_total']:,.2f}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # =========================================================================
    # 4. Test 3: Preview con nights_override
    # =========================================================================
    
    print_section("4. Test 3: Preview con nights_override=7")
    
    preview_url_override = f"{preview_url}?nights_override=7"
    
    try:
        response = requests.get(preview_url_override)
        response.raise_for_status()
        preview = response.json()
        
        print(f"✅ Preview con override")
        print(f"   Override aplicado: {preview['nights']['override_applied']}")
        print(f"   Noches calculadas: {preview['nights']['calculated']}")
        print(f"   Noches a cobrar (override): {preview['nights']['suggested_to_charge']}")
        print(f"   Total: ${preview['totals']['grand_total']:,.2f}")
        
        # Debe tener warning NIGHTS_OVERRIDE
        override_warning = next(
            (w for w in preview['warnings'] if w['code'] == 'NIGHTS_OVERRIDE'),
            None
        )
        if override_warning:
            print(f"   ⚠️  {override_warning['message']}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # =========================================================================
    # 5. Test 4: Preview sin líneas (include_items=false)
    # =========================================================================
    
    print_section("5. Test 4: Preview solo totales (include_items=false)")
    
    preview_url_totals = f"{preview_url}?include_items=false"
    
    try:
        response = requests.get(preview_url_totals)
        response.raise_for_status()
        preview = response.json()
        
        print(f"✅ Preview solo totales")
        print(f"   Líneas: {len(preview.get('breakdown_lines', []))}")
        print(f"   Pagos: {len(preview.get('payments', []))}")
        print(f"   Total: ${preview['totals']['grand_total']:,.2f}")
        print(f"   Saldo: ${preview['totals']['balance']:,.2f}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # =========================================================================
    # 6. Test 5: Checkout inválido (fecha anterior a checkin)
    # =========================================================================
    
    print_section("6. Test 5: Checkout inválido (debe fallar)")
    
    invalid_date = "2020-01-01"
    preview_url_invalid = f"{preview_url}?checkout_date={invalid_date}"
    
    try:
        response = requests.get(preview_url_invalid)
        
        if response.status_code == 400:
            error = response.json()
            print(f"✅ Error 400 esperado")
            print(f"   Mensaje: {error.get('detail', 'N/A')}")
        else:
            print(f"❌ Se esperaba error 400, obtuve {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
    
    # =========================================================================
    # Resumen final
    # =========================================================================
    
    print_section("✅ TESTS COMPLETADOS")
    print("\n💡 Próximos pasos:")
    print("   1. Revisar warnings en los previews")
    print("   2. Agregar cargos a la stay y ver cómo se reflejan")
    print("   3. Registrar pagos y verificar balance")
    print("   4. Integrar con HotelScheduler.jsx CheckoutDrawer")


if __name__ == "__main__":
    try:
        test_invoice_preview()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrumpido por usuario")
    except Exception as e:
        print(f"\n\n❌ Error fatal: {e}")
