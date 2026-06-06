#!/usr/bin/env python
"""
Script para revisar y resolver duplicados en room_types
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    print("=== Todos los room_types ===")
    cursor.execute('SELECT id, nombre, empresa_usuario_id, activo FROM room_types ORDER BY nombre, empresa_usuario_id')
    for row in cursor.fetchall():
        print(f'ID {row[0]:2d}: {row[1]:20s} | empresa={row[2]} | activo={row[3]}')
    
    print("\n=== Tipos duplicados por nombre ===")
    cursor.execute('''
        SELECT nombre, COUNT(*) as count
        FROM room_types
        GROUP BY nombre
        HAVING COUNT(*) > 1
    ''')
    for row in cursor.fetchall():
        print(f'  {row[0]}: {row[1]} instancias')
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f'✗ Error: {e}')
