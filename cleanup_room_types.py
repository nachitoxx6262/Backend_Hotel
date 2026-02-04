#!/usr/bin/env python
"""
Script para borrar room_types sin tenant (son datos obsoletos)
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Verificar si hay rooms asociados a estos room_types
    cursor.execute('''
        SELECT rt.id, rt.nombre, COUNT(r.id) as room_count
        FROM room_types rt
        LEFT JOIN rooms r ON r.room_type_id = rt.id
        WHERE rt.empresa_usuario_id IS NULL
        GROUP BY rt.id, rt.nombre
    ''')
    print("=== Room_types sin tenant y sus rooms asociados ===")
    for row in cursor.fetchall():
        print(f'ID {row[0]}: {row[1]} - {row[2]} rooms asociados')
    
    # Borrar room_types sin tenant
    cursor.execute('DELETE FROM room_types WHERE empresa_usuario_id IS NULL')
    deleted_count = cursor.rowcount
    conn.commit()
    
    print(f'\n✓ {deleted_count} room_types sin tenant eliminados')
    
    # Verificar resultado
    print("\n=== Room_types restantes ===")
    cursor.execute('SELECT id, nombre, empresa_usuario_id FROM room_types ORDER BY id')
    for row in cursor.fetchall():
        print(f'ID {row[0]}: {row[1]} (empresa_usuario_id={row[2]})')
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f'✗ Error: {e}')
