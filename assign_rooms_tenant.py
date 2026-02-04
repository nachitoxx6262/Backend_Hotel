#!/usr/bin/env python
"""
Script para asignar empresa_usuario_id a las rooms
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Verificar rooms sin empresa_usuario_id
    cursor.execute('''
        SELECT COUNT(*) FROM rooms WHERE empresa_usuario_id IS NULL
    ''')
    count_null = cursor.fetchone()[0]
    print(f'Rooms sin empresa_usuario_id: {count_null}')
    
    # Asignar empresa_usuario_id basado en su room_type
    if count_null > 0:
        cursor.execute('''
            UPDATE rooms r
            SET empresa_usuario_id = rt.empresa_usuario_id
            FROM room_types rt
            WHERE r.room_type_id = rt.id
            AND r.empresa_usuario_id IS NULL
        ''')
        updated_count = cursor.rowcount
        conn.commit()
        print(f'✓ {updated_count} rooms actualizados')
    
    # Verificar resultado
    cursor.execute('''
        SELECT COUNT(*) FROM rooms WHERE empresa_usuario_id = 17
    ''')
    count_demo = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT COUNT(*) FROM rooms WHERE empresa_usuario_id IS NULL
    ''')
    count_null_after = cursor.fetchone()[0]
    
    print(f'✓ Rooms con empresa_usuario_id=17: {count_demo}')
    print(f'✓ Rooms sin empresa_usuario_id (NULL): {count_null_after}')
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f'✗ Error: {e}')
