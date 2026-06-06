#!/usr/bin/env python
"""
Script para verificar estado final de rooms y room_types
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    print("=== Room Types ===")
    cursor.execute('SELECT id, nombre, empresa_usuario_id, activo FROM room_types')
    for row in cursor.fetchall():
        print(f'ID {row[0]}: {row[1]} (empresa={row[2]}, activo={row[3]})')
    
    print("\n=== Rooms ===")
    cursor.execute('''
        SELECT r.id, r.numero, r.room_type_id, rt.nombre, rt.empresa_usuario_id
        FROM rooms r
        JOIN room_types rt ON r.room_type_id = rt.id
        ORDER BY r.id
    ''')
    count = 0
    for row in cursor.fetchall():
        print(f'Room {row[0]:2d}: #{row[1]:5s} | type_id={row[2]} ({row[3]}) | empresa={row[4]}')
        count += 1
        if count >= 15:
            print("... (mostrados primeros 15)")
            break
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f'✗ Error: {e}')
