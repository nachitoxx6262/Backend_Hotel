#!/usr/bin/env python
"""
Script para verificar estructura de la tabla hotel_settings
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Ver estructura de hotel_settings
    cursor.execute('''
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'hotel_settings'
        ORDER BY ordinal_position
    ''')
    
    print("=== Columnas de hotel_settings ===")
    for row in cursor.fetchall():
        print(f'{row[0]:30s} | {row[1]:20s} | nullable={row[2]}')
    
    # Ver registros de hotel_settings
    print("\n=== Registros de hotel_settings ===")
    cursor.execute('SELECT id, empresa_usuario_id FROM hotel_settings LIMIT 5')
    for row in cursor.fetchall():
        print(f'ID {row[0]}: empresa_usuario_id={row[1]}')
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f'✗ Error: {e}')
