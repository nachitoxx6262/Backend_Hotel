#!/usr/bin/env python3
"""
Script para ejecutar migraciones SQL en la base de datos
"""
import os
import sys
from pathlib import Path

# Agregar la ruta del proyecto al path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from database.conexion import engine
    import psycopg2
    from sqlalchemy import text, inspect
    
    # Leer el archivo de migración
    migration_file = project_root / "migrations" / "migrate_housekeeping_tareas.sql"
    
    if not migration_file.exists():
        print(f"✗ Archivo de migración no encontrado: {migration_file}")
        sys.exit(1)
    
    with open(migration_file, 'r', encoding='utf-8') as f:
        migration_sql = f.read()
    
    # Ejecutar la migración
    print("Ejecutando migración...")
    with engine.connect() as connection:
        # Dividir por punto y coma, pero preservar los comentarios
        statements = []
        current_statement = []
        
        for line in migration_sql.split('\n'):
            line = line.rstrip()
            
            # Ignorar líneas vacías y comentarios
            if not line or line.strip().startswith('--'):
                continue
            
            current_statement.append(line)
            
            if ';' in line:
                statements.append(' '.join(current_statement).replace(';', ''))
                current_statement = []
        
        # Agregar la última sentencia si existe
        if current_statement:
            statements.append(' '.join(current_statement))
        
        for statement in statements:
            statement = statement.strip()
            if statement:
                try:
                    print(f"Ejecutando: {statement[:60]}...")
                    connection.execute(text(statement))
                    connection.commit()
                except Exception as e:
                    print(f"Advertencia (puede ser normal si ya existe): {str(e)[:100]}")
                    connection.rollback()
                    # No lanzamos excepción para permite que continúe
    
    # Verificar que las columnas existen
    print("\nVerificando columnas...")
    inspector = inspect(engine)
    
    # Verificar housekeeping_tareas
    if 'housekeeping_tareas' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('housekeeping_tareas')]
        required_cols = ['template_id', 'es_padre', 'tarea_padre_id']
        missing = [c for c in required_cols if c not in columns]
        if missing:
            print(f"✗ Columnas faltantes en housekeeping_tareas: {missing}")
        else:
            print("✓ housekeeping_tareas tiene todas las columnas requeridas")
    
    # Verificar habitaciones
    if 'habitaciones' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('habitaciones')]
        required_cols = ['template_tareas_id', 'num_camas', 'tipo_camas', 'particularidades']
        missing = [c for c in required_cols if c not in columns]
        if missing:
            print(f"✗ Columnas faltantes en habitaciones: {missing}")
        else:
            print("✓ habitaciones tiene todas las columnas requeridas")
    
    # Verificar tabla de templates
    if 'housekeeping_tareas_templates' in inspector.get_table_names():
        print("✓ Tabla housekeeping_tareas_templates existe")
    else:
        print("✗ Tabla housekeeping_tareas_templates no existe")
    
    print("\n✓ Migración completada")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
