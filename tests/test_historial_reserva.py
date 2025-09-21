
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient
from main import app
from datetime import datetime, timedelta

client = TestClient(app)

@pytest.fixture(scope="module")
def crear_reserva_valida():
    checkin = datetime.now().date()
    checkout = checkin + timedelta(days=5)
    payload = {
        "cliente_id": None,
        "empresa_id": None,
        "fecha_checkin": str(checkin),
        "fecha_checkout": str(checkout),
        "estado": "reservada",
        "habitaciones": [
            {"habitacion_id": 1, "precio_noche": 100.00}
        ],
        "items": [
            {"descripcion": "Servicio Spa", "cantidad": 1, "monto_total": 200.00, "tipo_item": "servicio"}
        ]
    }
    response = client.post("/reservas", json=payload)
    assert response.status_code == 201
    return response.json()

def test_historial_creado_al_crear_reserva(crear_reserva_valida):
    reserva_id = crear_reserva_valida["id"]
    response = client.get(f"/reservas/{reserva_id}/historial")
    assert response.status_code == 200
    historial = response.json()
    assert isinstance(historial, list)
    assert any(h["estado"] == "reservada" for h in historial)

def test_actualizar_estado_y_verificar_historial(crear_reserva_valida):
    reserva_id = crear_reserva_valida["id"]
    response = client.put(f"/reservas/{reserva_id}/estado", params={"nuevo_estado": "ocupada"})
    assert response.status_code == 200
    assert response.json()["estado"] == "ocupada"

    historial = client.get(f"/reservas/{reserva_id}/historial").json()
    estados = [h["estado"] for h in historial]
    assert "reservada" in estados
    assert "ocupada" in estados
