#!/usr/bin/env python
"""
Script para ejecutar la migración de room_types sin tenant
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Ejecutar UPDATE
    cursor.execute('UPDATE room_types SET empresa_usuario_id = 17 WHERE empresa_usuario_id IS NULL')
    updated_rows = cursor.rowcount
    conn.commit()
    
    print(f'✓ {updated_rows} room_types actualizados')
    
    # Verificar
    cursor.execute('SELECT id, nombre, empresa_usuario_id FROM room_types')
    for row in cursor.fetchall():
        print(f'  ID {row[0]}: {row[1]}, empresa_usuario_id={row[2]}')
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f'✗ Error: {e}')
