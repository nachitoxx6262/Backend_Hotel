"""
Simple command-line client for interacting with the Backend Hotel API.

Features:
- List clients
- List companies
- Create a company
- Create a client

Usage:
    python client_app.py --base-url http://localhost:8000

The base URL can also be provided through the HOTEL_API_URL environment variable.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict

DEFAULT_BASE_URL = "http://localhost:8000"


def _build_request(base_url: str, path: str, method: str, payload: Dict[str, Any] | None = None) -> urllib.request.Request:
    url = f"{base_url}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    return urllib.request.Request(url, data=data, headers=headers, method=method.upper())


def _perform_request(request: urllib.request.Request) -> Dict[str, Any] | Any:
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return {}
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {exc.reason}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"No se pudo conectar con el servidor: {exc}") from exc


def listar_clientes(base_url: str) -> None:
    request = _build_request(base_url, "/clientes", "GET")
    clientes = _perform_request(request)
    if not clientes:
        print("No hay clientes registrados.")
        return
    print("Clientes:")
    print(json.dumps(clientes, indent=2, ensure_ascii=False))


def listar_empresas(base_url: str) -> None:
    request = _build_request(base_url, "/empresas", "GET")
    empresas = _perform_request(request)
    if not empresas:
        print("No hay empresas registradas.")
        return
    print("Empresas:")
    print(json.dumps(empresas, indent=2, ensure_ascii=False))


def crear_empresa(base_url: str) -> None:
    print("Datos para nueva empresa")
    nombre = input("Nombre: ").strip()
    cuit = input("CUIT: ").strip()
    email = input("Email: ").strip()
    telefono = input("Telefono: ").strip()
    direccion = input("Direccion (opcional): ").strip() or None

    payload = {
        "nombre": nombre,
        "cuit": cuit,
        "email": email,
        "telefono": telefono,
        "direccion": direccion,
    }
    request = _build_request(base_url, "/empresas", "POST", payload)
    empresa = _perform_request(request)
    print("Empresa creada:")
    print(json.dumps(empresa, indent=2, ensure_ascii=False))


def crear_cliente(base_url: str) -> None:
    print("Datos para nuevo cliente")
    nombre = input("Nombre: ").strip()
    apellido = input("Apellido: ").strip()
    tipo_doc = input("Tipo de documento: ").strip()
    num_doc = input("Numero de documento: ").strip()
    nacionalidad = input("Nacionalidad: ").strip()
    email = input("Email: ").strip()
    telefono = input("Telefono: ").strip()
    empresa_id_str = input("ID de empresa (opcional): ").strip()
    empresa_id = int(empresa_id_str) if empresa_id_str else None

    payload = {
        "nombre": nombre,
        "apellido": apellido,
        "tipo_documento": tipo_doc,
        "numero_documento": num_doc,
        "nacionalidad": nacionalidad,
        "email": email,
        "telefono": telefono,
        "empresa_id": empresa_id,
    }
    request = _build_request(base_url, "/clientes", "POST", payload)
    cliente = _perform_request(request)
    print("Cliente creado:")
    print(json.dumps(cliente, indent=2, ensure_ascii=False))


def ejecutar_menu(base_url: str) -> None:
    opciones = {
        "1": ("Listar clientes", listar_clientes),
        "2": ("Listar empresas", listar_empresas),
        "3": ("Crear empresa", crear_empresa),
        "4": ("Crear cliente", crear_cliente),
        "0": ("Salir", None),
    }

    while True:
        print("\n--- Menu ---")
        for clave, (descripcion, _) in opciones.items():
            print(f"{clave}. {descripcion}")
        eleccion = input("Selecciona una opcion: ").strip()
        if eleccion == "0":
            print("Hasta luego.")
            return
        accion = opciones.get(eleccion)
        if not accion:
            print("Opcion no valida.")
            continue
        try:
            accion[1](base_url)  # type: ignore[index]
        except RuntimeError as exc:
            print(f"Error: {exc}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cliente simple para Backend Hotel")
    parser.add_argument(
        "--base-url",
        default=os.getenv("HOTEL_API_URL", DEFAULT_BASE_URL),
        help="URL base del API (por defecto http://localhost:8000)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])
    base_url = args.base_url.rstrip("/")
    try:
        ejecutar_menu(base_url)
    except KeyboardInterrupt:
        print("\nOperacion cancelada.")


if __name__ == "__main__":
    main()
