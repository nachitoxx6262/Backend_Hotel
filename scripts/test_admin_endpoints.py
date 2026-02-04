"""
Smoke test de endpoints (GET/POST) con cuenta admin para validar scopes.
"""
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

BASE_URL = "http://127.0.0.1:8000"
USERNAME = "admin"
FALLBACK_EMAIL = "admin@hotel.com"
PASSWORDS = ["admin123", "admin123456"]


def request_json(method, path, token=None, body=None, query=None):
    url = f"{BASE_URL}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)

    data = None
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw) if raw else None
            return resp.status, payload
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = raw
        return e.code, payload


def login_admin():
    last_error = None
    for username in (USERNAME, FALLBACK_EMAIL):
        for password in PASSWORDS:
            data = urllib.parse.urlencode({"username": username, "password": password}).encode("utf-8")
            req = urllib.request.Request(
                f"{BASE_URL}/auth/login",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                    print(f"✅ Login OK con usuario {username}")
                    return payload["access_token"]
            except urllib.error.HTTPError as e:
                last_error = e
    raise last_error if last_error else RuntimeError("No se pudo loguear con credenciales conocidas")


def main():
    token = login_admin()

    # 1) Rooms / Types
    status, data = request_json("GET", "/api/rooms/types", token=token)
    print("GET /api/rooms/types", status)

    status, data = request_json(
        "POST",
        "/api/rooms/types",
        token=token,
        body={"nombre": "Tipo Test", "descripcion": "Test", "capacidad": 2, "precio_base": 100, "amenidades": ["wifi"], "activo": True},
    )
    print("POST /api/rooms/types", status)
    room_type_id = data.get("id") if isinstance(data, dict) else None

    status, data = request_json("GET", "/api/rooms", token=token)
    print("GET /api/rooms", status)

    room_id = None
    if room_type_id:
        status, data = request_json(
            "POST",
            "/api/rooms",
            token=token,
            body={"numero": "101", "room_type_id": room_type_id, "estado_operativo": "disponible", "piso": 1, "activo": True},
        )
        print("POST /api/rooms", status)
        if isinstance(data, dict):
            room_id = data.get("id")

    # 2) Calendar (reservations/stays)
    today = datetime.utcnow().date()
    from_date = today.isoformat()
    to_date = (today + timedelta(days=2)).isoformat()

    status, data = request_json("GET", "/api/calendar/calendar", token=token, query={"from": from_date, "to": to_date})
    print("GET /api/calendar/calendar", status)

    reservation_id = None
    if room_id:
        status, data = request_json(
            "POST",
            "/api/calendar/reservations",
            token=token,
            body={
                "fecha_checkin": from_date,
                "fecha_checkout": to_date,
                "room_ids": [room_id],
                "estado": "confirmada",
                "origen": "api_test",
                "nombre_temporal": "Huesped Test",
                "huespedes": [],
            },
        )
        print("POST /api/calendar/reservations", status)
        if isinstance(data, dict):
            reservation_id = data.get("id")

    stay_id = None
    if reservation_id:
        status, data = request_json(
            "POST",
            f"/api/calendar/stays/from-reservation/{reservation_id}/checkin",
            token=token,
            body={"notas": "checkin test", "huespedes": []},
        )
        print("POST /api/calendar/stays/from-reservation/{id}/checkin", status)
        if isinstance(data, dict):
            stay_id = data.get("stay_id") or data.get("id")

    if stay_id:
        status, data = request_json("GET", f"/api/calendar/stays/{stay_id}/summary", token=token)
        print("GET /api/calendar/stays/{id}/summary", status)

    # 3) Housekeeping (PMS)
    if room_id:
        status, data = request_json(
            "POST",
            "/api/pms/housekeeping/tasks",
            token=token,
            body={
                "room_id": room_id,
                "task_names": ["Cambiar sábanas"],
                "description": "Test limpieza",
                "priority": "media",
                "status": "pending",
                "block_room": False,
            },
        )
        print("POST /api/pms/housekeeping/tasks", status)

    status, data = request_json("GET", "/api/pms/housekeeping/board", token=token, query={"date": from_date})
    print("GET /api/pms/housekeeping/board", status)

    # 4) Productos / Servicios
    status, data = request_json("GET", "/api/calendar/productos-servicios", token=token)
    print("GET /api/calendar/productos-servicios", status)

    status, data = request_json(
        "POST",
        "/api/calendar/productos-servicios",
        token=token,
        body={"nombre": "Agua", "tipo": "producto", "precio_unitario": 10, "descripcion": "Test", "activo": True},
    )
    print("POST /api/calendar/productos-servicios", status)


if __name__ == "__main__":
    main()
