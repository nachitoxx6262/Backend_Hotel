#!/usr/bin/env python
"""
Script para limpiar hotel_settings y aplicar migración 012
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    print("=== Plan de limpieza ===")
    
    # Desactivar FK temporalmente
    print("1. Desactivando constraints de FK temporalmente...")
    cursor.execute('ALTER TABLE hotel_settings DISABLE TRIGGER ALL')
    print("   ✓ Hecho")
    
    # Eliminar registros con empresa_id inválido
    print("2. Eliminando registros con empresa_id inválido...")
    cursor.execute('DELETE FROM hotel_settings WHERE empresa_id NOT IN (SELECT id FROM empresa_usuarios)')
    deleted = cursor.rowcount
    print(f"   ✓ {deleted} registros eliminados")
    
    # Reactivar constraints
    print("3. Reactivando constraints...")
    cursor.execute('ALTER TABLE hotel_settings ENABLE TRIGGER ALL')
    print("   ✓ Hecho")
    
    conn.commit()
    
    # Ahora aplicar la migración 012
    print("\n=== Aplicando migración 012 ===")
    
    print("4. Copiando empresa_id a empresa_usuario_id...")
    cursor.execute('''
        UPDATE hotel_settings
        SET empresa_usuario_id = empresa_id
        WHERE empresa_usuario_id IS NULL
    ''')
    updated = cursor.rowcount
    print(f"   ✓ {updated} registros actualizados")
    
    # Hacer NOT NULL
    print("5. Haciendo empresa_usuario_id NOT NULL...")
    cursor.execute('''
        ALTER TABLE hotel_settings
        ALTER COLUMN empresa_usuario_id SET NOT NULL
    ''')
    print("   ✓ Hecho")
    
    # Eliminar columna empresa_id
    print("6. Eliminando columna empresa_id...")
    cursor.execute('''
        ALTER TABLE hotel_settings
        DROP COLUMN empresa_id CASCADE
    ''')
    print("   ✓ Eliminado")
    
    conn.commit()
    
    # Verificar
    print("\n=== Verificación final ===")
    cursor.execute('''
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'hotel_settings'
        ORDER BY ordinal_position
    ''')
    
    for row in cursor.fetchall():
        print(f'{row[0]:30s} | {row[1]:20s} | nullable={row[2]}')
    
    print("\n✓ Migración completada exitosamente")
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f'✗ Error: {e}')
    import traceback
    traceback.print_exc()
