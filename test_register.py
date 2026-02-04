"""
Script para probar el registro de empresa usuario
"""
import requests
import json

url = "http://localhost:8000/auth/register-empresa-usuario"

data = {
    "nombre_hotel": "Hotel Test",
    "cuit": "20304050607",
    "contacto_nombre": "Juan Perez",
    "contacto_email": "juan@test.com",
    "contacto_telefono": "1234567890",
    "direccion": "Calle Falsa 123",
    "ciudad": "Buenos Aires",
    "provincia": "Buenos Aires",
    "admin_username": "admin_test",
    "admin_email": "admin@test.com",
    "admin_password": "Admin123"
}

try:
    response = requests.post(url, json=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, 'response'):
        print(f"Response text: {e.response.text}")
