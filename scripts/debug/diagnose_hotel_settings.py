#!/usr/bin/env python
"""
Script para diagnosticar la situación de hotel_settings
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    print("=== Hotel Settings ===")
    cursor.execute('SELECT id, empresa_id, empresa_usuario_id FROM hotel_settings')
    for row in cursor.fetchall():
        print(f'ID {row[0]}: empresa_id={row[1]}, empresa_usuario_id={row[2]}')
    
    print("\n=== Empresa Usuarios (primeros 5) ===")
    cursor.execute('SELECT id FROM empresa_usuarios ORDER BY id')
    for row in cursor.fetchall():
        print(f'ID {row[0]}')
    
    # Verificar si existe FK constraint
    print("\n=== Constraints de hotel_settings ===")
    cursor.execute('''
        SELECT constraint_name, constraint_type
        FROM information_schema.table_constraints
        WHERE table_name = 'hotel_settings'
    ''')
    for row in cursor.fetchall():
        print(f'{row[0]}: {row[1]}')
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f'✗ Error: {e}')
