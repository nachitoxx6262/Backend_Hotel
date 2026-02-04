#!/usr/bin/env python
"""
Script para verificar los tipos de habitaciones en la base de datos
y su asociación con tenants (empresa_usuarios)
"""

from database.conexion import SessionLocal
from models.core import RoomType, Room, EmpresaUsuario

session = SessionLocal()

# Verificar empresa_usuario con ID 17 (demo account)
demo_empresa = session.query(EmpresaUsuario).filter(EmpresaUsuario.id == 17).first()
print(f"\n=== Demo Empresa (ID 17) ===")
if demo_empresa:
    print(f"Nombre: {demo_empresa.nombre_hotel}")
    print(f"Existe: Sí")
else:
    print(f"Existe: No")

# Verificar tipos de habitaciones
print(f"\n=== Todos los RoomTypes en DB ===")
all_room_types = session.query(RoomType).all()
print(f"Total: {len(all_room_types)}")
for rt in all_room_types:
    print(f"  ID {rt.id}: {rt.nombre}, empresa_usuario_id={rt.empresa_usuario_id}, activo={rt.activo}")

# Verificar tipos de habitaciones para demo_empresa
print(f"\n=== RoomTypes para demo_empresa (empresa_usuario_id=17, activo=True) ===")
demo_room_types = session.query(RoomType).filter(
    RoomType.empresa_usuario_id == 17,
    RoomType.activo == True
).all()
print(f"Total: {len(demo_room_types)}")
for rt in demo_room_types:
    print(f"  ID {rt.id}: {rt.nombre}, capacidad={rt.capacidad}")

# Verificar rooms
print(f"\n=== Rooms para demo_empresa (empresa_usuario_id=17) ===")
demo_rooms = session.query(Room).filter(Room.empresa_usuario_id == 17).all()
print(f"Total: {len(demo_rooms)}")
for room in demo_rooms[:5]:  # mostrar primeros 5
    print(f"  ID {room.id}: Habitación #{room.numero}, room_type_id={room.room_type_id}, empresa_usuario_id={room.empresa_usuario_id}")

session.close()
