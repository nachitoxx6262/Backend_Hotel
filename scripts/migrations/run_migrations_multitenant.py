#!/usr/bin/env python3
"""
Script para ejecutar migraciones SQL en la base de datos PostgreSQL
Uso: python run_migrations_multitenant.py [--from 005 --to 008]
"""

import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from database.conexion import engine
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migrations.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Migraciones en orden
MIGRATIONS = {
    "005": "005_multitenant_core.sql",
    "006": "006_add_tenant_id_all_tables.sql",
    "007": "007_enable_rls_security.sql",
    "008": "008_rename_subscription_metadata.sql",
}

def get_db_credentials():
    """Obtiene credenciales de la base de datos del .env"""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "hotel_db"),
    }

def execute_migration_with_psql(migration_num: str, credentials: dict):
    """Ejecuta migración usando psql directamente"""
    migration_file = MIGRATIONS_DIR / MIGRATIONS[migration_num]
    
    if not migration_file.exists():
        logger.error(f"Migration file not found: {migration_file}")
        return False
    
    logger.info(f"Executing migration {migration_num}: {migration_file.name}")
    
    # Construir comando psql
    cmd = [
        "psql",
        f"-h {credentials['host']}",
        f"-p {credentials['port']}",
        f"-U {credentials['user']}",
        f"-d {credentials['database']}",
        f"-f {str(migration_file)}"
    ]
    
    try:
        # Pasar password a través de PGPASSWORD env var
        env = os.environ.copy()
        if credentials['password']:
            env['PGPASSWORD'] = credentials['password']
        
        result = subprocess.run(
            " ".join(cmd),
            shell=True,
            env=env,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            logger.info(f"Migration {migration_num} completed successfully")
            if result.stdout:
                logger.info(f"Output: {result.stdout}")
            return True
        else:
            logger.error(f"Migration {migration_num} failed")
            logger.error(f"Error: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error executing migration {migration_num}: {str(e)}")
        return False

def execute_migration_with_sqlalchemy(migration_num: str):
    """Ejecuta migración usando SQLAlchemy engine"""
    migration_file = MIGRATIONS_DIR / MIGRATIONS[migration_num]
    
    if not migration_file.exists():
        logger.error(f"Migration file not found: {migration_file}")
        return False
    
    logger.info(f"Executing migration {migration_num}: {migration_file.name}")
    
    try:
        with open(migration_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # Ejecutar SQL usando conexión raw para permitir múltiples statements y bloques $$
        with engine.connect() as connection:
            raw_conn = connection.connection
            raw_conn.autocommit = True
            with raw_conn.cursor() as cursor:
                cursor.execute(sql_content)
        
        logger.info(f"Migration {migration_num} completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Migration {migration_num} failed: {str(e)}")
        return False

def run_migrations(from_num: str = "005", to_num: str = "008"):
    """Ejecuta migraciones en rango"""
    logger.info("=" * 70)
    logger.info("STARTING MULTI-TENANT MIGRATIONS")
    logger.info(f"   Migrations: {from_num} to {to_num}")
    logger.info(f"   Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 70)
    
    credentials = get_db_credentials()
    logger.info(f"Database: {credentials['database']} @ {credentials['host']}:{credentials['port']}")
    
    migration_nums = sorted([k for k in MIGRATIONS.keys() if from_num <= k <= to_num])
    
    if not migration_nums:
        logger.error(f"No migrations found in range {from_num} to {to_num}")
        return False
    
    failed = []
    
    for mig_num in migration_nums:
        # Intentar con psql primero (más compatible con RLS)
        # Si falla, usar SQLAlchemy
        success = execute_migration_with_psql(mig_num, credentials)
        
        if not success:
            logger.info(f"Retrying migration {mig_num} with SQLAlchemy...")
            success = execute_migration_with_sqlalchemy(mig_num)
        
        if not success:
            failed.append(mig_num)
            logger.error(f"Migration {mig_num} FAILED - stopping here")
            break
    
    logger.info("=" * 70)
    if failed:
        logger.error(f"MIGRATIONS FAILED: {', '.join(failed)}")
        return False
    else:
        logger.info("ALL MIGRATIONS COMPLETED SUCCESSFULLY")
        logger.info("=" * 70)
        return True

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Execute multi-tenant migrations")
    parser.add_argument("--from", dest="from_num", default="005", 
                        help="Starting migration number (default: 005)")
    parser.add_argument("--to", dest="to_num", default="008",
                        help="Ending migration number (default: 008)")
    parser.add_argument("--only", dest="only_num", 
                        help="Execute only this migration (e.g., 005)")
    
    args = parser.parse_args()
    
    if args.only_num:
        success = run_migrations(args.only_num, args.only_num)
    else:
        success = run_migrations(args.from_num, args.to_num)
    
    sys.exit(0 if success else 1)
