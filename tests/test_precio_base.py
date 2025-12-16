"""
Test rápido para verificar que el campo precio_base funciona correctamente
"""
import requests
import json

BASE_URL = "http://localhost:8000/api/rooms"

def test_room_type_with_precio_base():
    print("=" * 60)
    print("TEST: Crear y actualizar RoomType con precio_base")
    print("=" * 60)
    
    # 1. Crear nuevo tipo con precio_base
    nuevo_tipo = {
        "nombre": "Suite Premium Test",
        "descripcion": "Suite de lujo con precio base",
        "capacidad": 2,
        "precio_base": 15000.50,
        "amenidades": ["WiFi", "TV", "Minibar", "Jacuzzi"],
        "activo": True
    }
    
    print("\n1. Creando nuevo tipo de habitación...")
    response = requests.post(f"{BASE_URL}/types", json=nuevo_tipo)
    
    if response.status_code == 201:
        created = response.json()
        print(f"✅ Tipo creado exitosamente:")
        print(f"   ID: {created['id']}")
        print(f"   Nombre: {created['nombre']}")
        print(f"   Precio Base: ${created.get('precio_base', 'N/A')}")
        print(f"   Capacidad: {created['capacidad']}")
        type_id = created['id']
    else:
        print(f"❌ Error al crear: {response.status_code}")
        print(response.text)
        return
    
    # 2. Listar tipos y verificar
    print("\n2. Listando tipos de habitación...")
    response = requests.get(f"{BASE_URL}/types")
    
    if response.status_code == 200:
        tipos = response.json()
        print(f"✅ Encontrados {len(tipos)} tipo(s)")
        for tipo in tipos:
            if tipo['id'] == type_id:
                print(f"   → {tipo['nombre']}: ${tipo.get('precio_base', 'N/A')} / noche")
    else:
        print(f"❌ Error al listar: {response.status_code}")
    
    # 3. Actualizar precio_base
    print("\n3. Actualizando precio_base...")
    update_data = {
        "precio_base": 18500.00
    }
    
    response = requests.put(f"{BASE_URL}/types/{type_id}", json=update_data)
    
    if response.status_code == 200:
        updated = response.json()
        print(f"✅ Tipo actualizado:")
        print(f"   Nuevo precio base: ${updated.get('precio_base', 'N/A')}")
    else:
        print(f"❌ Error al actualizar: {response.status_code}")
        print(response.text)
    
    # 4. Eliminar tipo de prueba
    print("\n4. Eliminando tipo de prueba...")
    response = requests.delete(f"{BASE_URL}/types/{type_id}")
    
    if response.status_code == 200:
        print("✅ Tipo eliminado exitosamente")
    else:
        print(f"❌ Error al eliminar: {response.status_code}")
        print(response.text)
    
    print("\n" + "=" * 60)
    print("TEST COMPLETADO")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_room_type_with_precio_base()
    except requests.exceptions.ConnectionError:
        print("❌ Error: No se puede conectar al backend.")
        print("   Asegúrate de que uvicorn esté corriendo en http://localhost:8000")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
