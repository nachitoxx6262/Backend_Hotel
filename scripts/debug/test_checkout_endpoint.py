#!/usr/bin/env python
"""
Test checkout endpoint para verificar fix de enum
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import requests
import json

# Configuración
BASE_URL = "http://localhost:8000"
STAY_ID = 180

def get_auth_token():
    """Login y obtener token"""
    login_url = f"{BASE_URL}/api/auth/login"
    # Usar credenciales de administrador
    payload = {
        "email": "admin@hotel.com",
        "password": "admin123"
    }
    
    try:
        response = requests.post(login_url, json=payload)
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            print(f"✅ Login exitoso")
            return token
        else:
            print(f"❌ Login fallido: {response.status_code}")
            print(response.text)
            return None
    except Exception as e:
        print(f"❌ Error en login: {e}")
        return None

def test_checkout(token):
    """Test del endpoint de checkout"""
    checkout_url = f"{BASE_URL}/api/calendar/stays/{STAY_ID}/checkout/confirm"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "nights_override": None,
        "tarifa_override": None,
        "discount_override_pct": None,
        "tax_override_mode": None,
        "tax_override_value": None,
        "notes": "",
        "housekeeping": False,
        "allow_close_with_debt": False,
        "debt_reason": ""
    }
    
    try:
        print(f"\n🔄 Probando checkout de Stay #{STAY_ID}...")
        response = requests.post(checkout_url, json=payload, headers=headers)
        
        print(f"\n📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ CHECKOUT EXITOSO!")
            print(f"   - Stay ID: {data.get('stay_id')}")
            print(f"   - Estado: {data.get('status')}")
            print(f"   - Total: ${data.get('grand_total')}")
            if 'transaction_id' in data:
                print(f"   - Transacción creada: ID {data['transaction_id']}")
            print(f"\n✅ FIX DE ENUM VERIFICADO - No hay error 'INGRESO'")
            return True
        elif response.status_code == 400:
            print(f"⚠️ Petición inválida: {response.json()}")
            return False
        elif response.status_code == 404:
            print(f"⚠️ Stay #{STAY_ID} no encontrado")
            print(f"   Prueba con otro Stay ID que esté en estado 'in'")
            return False
        elif response.status_code == 500:
            print(f"\n❌ ERROR 500 - El enum sigue fallando")
            print(f"Response: {response.text[:500]}")
            return False
        else:
            print(f"⚠️ Status inesperado: {response.status_code}")
            print(response.text[:500])
            return False
            
    except Exception as e:
        print(f"\n❌ Error en request: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_available_stays(token):
    """Obtener stays disponibles para checkout"""
    url = f"{BASE_URL}/api/calendar/stays?status=in"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            stays = response.json()
            print(f"\n📋 Stays disponibles para checkout (status='in'):")
            for stay in stays[:5]:
                print(f"   - Stay #{stay.get('id')}")
            return stays
        else:
            print(f"⚠️ No se pudieron obtener stays: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Error obteniendo stays: {e}")
        return []

if __name__ == "__main__":
    print("=" * 60)
    print("TEST DE CHECKOUT - Verificación de Fix de Enum")
    print("=" * 60)
    
    # 1. Login
    token = get_auth_token()
    if not token:
        print("\n❌ No se pudo obtener token de autenticación")
        sys.exit(1)
    
    # 2. Ver stays disponibles
    stays = get_available_stays(token)
    
    # 3. Test checkout
    success = test_checkout(token)
    
    print("\n" + "=" * 60)
    if success:
        print("✅ TEST PASÓ - Enum fix funcionando correctamente")
    else:
        print("❌ TEST FALLÓ - Revisar logs del servidor")
    print("=" * 60)
    
    sys.exit(0 if success else 1)
