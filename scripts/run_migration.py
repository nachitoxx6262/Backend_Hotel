#!/usr/bin/env python3
"""
Ejecuta una migración SQL contra la base de datos configurada en .env
Uso: python scripts/run_migration.py migrations/018_fase3_nuevas_columnas.sql
"""
import sys
import os
from pathlib import Path

# Agregar el root del proyecto al path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import psycopg2


def run_migration(sql_file: str):
    db_url = (
        os.getenv("DATABASE_URL")
        or f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
           f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME')}"
    )

    if "None" in db_url or not os.getenv("DB_USER"):
        print("❌ Variables de entorno de DB no configuradas.")
        print("   Configurá DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME en .env")
        sys.exit(1)

    sql_path = ROOT / sql_file
    if not sql_path.exists():
        print(f"❌ Archivo no encontrado: {sql_path}")
        sys.exit(1)

    sql = sql_path.read_text(encoding="utf-8")
    print(f"🔄 Ejecutando migración: {sql_file}")

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print("✅ Migración aplicada exitosamente.")
    except Exception as e:
        conn.rollback()
        print(f"❌ Error durante la migración: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/run_migration.py <archivo.sql>")
        sys.exit(1)
    run_migration(sys.argv[1])
