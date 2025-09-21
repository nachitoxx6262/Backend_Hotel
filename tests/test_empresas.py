import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from fastapi.testclient import TestClient
from uuid import uuid4
from main import app

client = TestClient(app)
empresa_id = None  # compartido entre tests
cuit_guardado = ""

def test_01_crear_empresa():
    global empresa_id,cuit_guardado
    response = client.post("/empresas", json={
        "nombre": "Empresa Test",
        "cuit": f"{uuid4().hex[:11]}",
        "email": f"empresa{uuid4().hex[:5]}@mail.com",
        "telefono": "1133445566",
        "direccion": "Calle Falsa 123"
    })
    assert response.status_code == 201
    data = response.json()
    empresa_id = data["id"]
    cuit_guardado = data["cuit"]
    assert data["nombre"] == "Empresa Test"


def test_02_listar_empresas():
    response = client.get("/empresas")
    assert response.status_code == 200
    assert any(e["id"] == empresa_id for e in response.json())


def test_03_buscar_empresa_por_nombre():
    response = client.get("/empresas/buscar", params={"nombre": "Empresa Test"})
    assert response.status_code == 200
    assert any(e["id"] == empresa_id for e in response.json())


def test_04_buscar_empresa_exacta():
    response = client.get("/empresas/buscar-exacta", params={"nombre": "Empresa Test"})
    assert response.status_code == 200
    assert response.json()["id"] == empresa_id


def test_05_verificar_existencia_por_cuit():
    response = client.get("/empresas/existe", params={"cuit": cuit_guardado})
    assert response.status_code == 200
    assert response.json()["existe"] is True


def test_06_poner_en_blacklist():
    response = client.put(f"/empresas/{empresa_id}/blacklist")
    assert response.status_code == 200
    assert response.json()["blacklist"] is True


def test_07_listar_empresas_blacklist():
    response = client.get("/empresas/blacklist")
    assert response.status_code == 200
    assert any(e["id"] == empresa_id for e in response.json())


def test_08_quitar_de_blacklist():
    response = client.put(f"/empresas/{empresa_id}/quitar-blacklist")
    assert response.status_code == 200
    assert response.json()["blacklist"] is False


def test_09_eliminar_logico():
    response = client.delete(f"/empresas/{empresa_id}")
    assert response.status_code == 204


def test_10_listar_empresas_eliminadas():
    response = client.get("/empresas/eliminadas")
    assert response.status_code == 200
    assert any(e["id"] == empresa_id for e in response.json())


def test_11_restaurar_empresa():
    response = client.put(f"/empresas/{empresa_id}/restaurar")
    assert response.status_code == 200
    assert response.json()["deleted"] is False


def test_12_resumen_empresas():
    response = client.get("/empresas/resumen")
    assert response.status_code == 200
    assert "total" in response.json()


def test_13_eliminar_fisico():
    response = client.delete(f"/empresas/{empresa_id}/eliminar-definitivo", params={"superadmin": True})
    assert response.status_code == 204


def test_14_empresa_ya_no_existe():
    response = client.get(f"/empresas/{empresa_id}")
    assert response.status_code == 404
