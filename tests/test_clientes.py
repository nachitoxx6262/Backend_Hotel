import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from fastapi.testclient import TestClient
from uuid import uuid4
from main import app  # Asegúrate de que 'main' es el nombre correcto del archivo principal

client = TestClient(app)
cliente_id = None  # global temporal para compartir entre tests


def test_01_crear_cliente():
    global cliente_id
    response = client.post("/clientes", json={
        "nombre": "Ignacio",
        "apellido": "Test",
        "tipo_documento": "DNI",
        "numero_documento": f"{uuid4().hex[:8]}",
        "nacionalidad": "Argentina",
        "email": f"ignacio{uuid4().hex[:5]}@mail.com",
        "telefono": "1122334455",
        "empresa_id": None
    })
    assert response.status_code == 201
    data = response.json()
    cliente_id = data["id"]
    assert data["nombre"] == "Ignacio"
    print("📌 Cliente creado con ID:", cliente_id)


def test_02_obtener_cliente():
    global cliente_id
    response = client.get(f"/clientes/{cliente_id}")
    assert response.status_code == 200
    assert response.json()["id"] == cliente_id


def test_03_buscar_cliente_por_nombre():
    response = client.get("/clientes/buscar", params={"nombre": "Ignacio"})
    assert response.status_code == 200
    assert any(c["nombre"] == "Ignacio" for c in response.json())


def test_04_agregar_cliente_a_blacklist():
    global cliente_id
    response = client.put(f"/clientes/{cliente_id}/blacklist")
    assert response.status_code == 200
    assert response.json()["blacklist"] is True


def test_05_listar_blacklist():
    global cliente_id
    response = client.get("/clientes/blacklist")
    assert response.status_code == 200
    assert any(c["id"] == cliente_id for c in response.json())


def test_06_quitar_cliente_de_blacklist():
    global cliente_id
    response = client.put(f"/clientes/{cliente_id}/quitar-blacklist")
    assert response.status_code == 200
    assert response.json()["blacklist"] is False


def test_07_eliminar_cliente_logico():
    global cliente_id
    response = client.delete(f"/clientes/{cliente_id}")
    assert response.status_code == 204


def test_08_listar_eliminados():
    global cliente_id
    response = client.get("/clientes/eliminados")
    assert response.status_code == 200
    assert any(c["id"] == cliente_id for c in response.json())


def test_09_restaurar_cliente():
    global cliente_id
    response = client.put(f"/clientes/{cliente_id}/restaurar")
    assert response.status_code == 200
    assert response.json()["deleted"] is False


def test_10_eliminar_cliente_fisico():
    global cliente_id
    response = client.delete(f"/clientes/{cliente_id}/eliminar-definitivo", params={"superadmin": True})
    assert response.status_code == 204


def test_11_cliente_ya_no_existe():
    global cliente_id
    response = client.get(f"/clientes/{cliente_id}")
    assert response.status_code == 404
