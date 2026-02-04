#!/usr/bin/env python
"""
Script para reasignar rooms sin tenant a room_types con tenant
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    print("=== Rooms antes de reasignar ===")
    cursor.execute('''
        SELECT r.id, r.numero, r.room_type_id, rt.nombre, rt.empresa_usuario_id
        FROM rooms r
        LEFT JOIN room_types rt ON r.room_type_id = rt.id
        WHERE rt.empresa_usuario_id IS NULL
        LIMIT 10
    ''')
    for row in cursor.fetchall():
        print(f'Room {row[0]:2d}: #{row[1]:5s} | type_id={row[2]} ({row[3]}) | empresa={row[4]}')
    
    # Obtener count de rooms con room_types sin tenant
    cursor.execute('''
        SELECT COUNT(*)
        FROM rooms r
        JOIN room_types rt ON r.room_type_id = rt.id
        WHERE rt.empresa_usuario_id IS NULL
    ''')
    count_without_tenant = cursor.fetchone()[0]
    print(f'\nTotal rooms con room_types sin tenant: {count_without_tenant}')
    
    # Actualizar rooms que apunten a room_types sin tenant
    # Ponerlos al room_type que sí tiene tenant (ID 10: Doble Standar)
    cursor.execute('''
        UPDATE rooms
        SET room_type_id = 10
        WHERE room_type_id IN (1, 6)
    ''')
    updated_count = cursor.rowcount
    conn.commit()
    
    print(f'✓ {updated_count} rooms reasignados a room_type_id=10')
    
    # Ahora borrar los room_types sin tenant
    cursor.execute('DELETE FROM room_types WHERE empresa_usuario_id IS NULL')
    deleted_count = cursor.rowcount
    conn.commit()
    
    print(f'✓ {deleted_count} room_types sin tenant eliminados')
    
    # Verificar resultado
    print("\n=== Estado final ===")
    cursor.execute('''
        SELECT r.id, r.numero, r.room_type_id, rt.nombre, rt.empresa_usuario_id
        FROM rooms r
        JOIN room_types rt ON r.room_type_id = rt.id
        WHERE rt.empresa_usuario_id = 17
        LIMIT 10
    ''')
    count_final = 0
    for row in cursor.fetchall():
        print(f'Room {row[0]:2d}: #{row[1]:5s} | type={row[3]} | empresa={row[4]}')
        count_final += 1
    
    print(f'\n✓ Total rooms con tenant=17: {count_final}')
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f'✗ Error: {e}')
