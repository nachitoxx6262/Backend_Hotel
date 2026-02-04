"""
Script para ejecutar la migración 017 del sistema de caja
"""
import psycopg2
from psycopg2 import sql
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de la base de datos
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'hotelbeta_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'admin'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432')
}

def execute_migration():
    """Ejecuta el archivo de migración SQL"""
    try:
        # Conectar a la base de datos
        print(f"🔌 Conectando a la base de datos {DB_CONFIG['dbname']}...")
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        cursor = conn.cursor()
        
        # Leer el archivo de migración
        migration_file = 'migrations/017_caja_system.sql'
        print(f"📄 Leyendo migración: {migration_file}")
        
        with open(migration_file, 'r', encoding='utf-8') as f:
            migration_sql = f.read()
        
        # Ejecutar la migración
        print("⚙️  Ejecutando migración...")
        cursor.execute(migration_sql)
        
        # Commit
        conn.commit()
        print("✅ Migración 017 ejecutada exitosamente")
        
        # Verificar que las tablas fueron creadas
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('transaction_categories', 'transactions', 'cash_closings')
            ORDER BY table_name;
        """)
        
        tables = cursor.fetchall()
        print(f"\n📊 Tablas creadas ({len(tables)}/3):")
        for table in tables:
            print(f"  ✓ {table[0]}")
        
        # Verificar enums creados
        cursor.execute("""
            SELECT typname 
            FROM pg_type 
            WHERE typname IN ('transaction_type', 'payment_method')
            ORDER BY typname;
        """)
        
        enums = cursor.fetchall()
        print(f"\n🏷️  Enums creados ({len(enums)}/2):")
        for enum in enums:
            print(f"  ✓ {enum[0]}")
        
        # Verificar políticas RLS
        cursor.execute("""
            SELECT tablename, policyname 
            FROM pg_policies 
            WHERE tablename IN ('transaction_categories', 'transactions', 'cash_closings')
            ORDER BY tablename, policyname;
        """)
        
        policies = cursor.fetchall()
        print(f"\n🔒 Políticas RLS creadas ({len(policies)}/3):")
        for policy in policies:
            print(f"  ✓ {policy[0]}.{policy[1]}")
        
        cursor.close()
        conn.close()
        print("\n✨ Migración completada con éxito")
        
    except Exception as e:
        print(f"\n❌ Error ejecutando migración: {e}")
        if conn:
            conn.rollback()
            conn.close()
        raise

if __name__ == '__main__':
    execute_migration()
