"""
Migration Script: Add Timezone Awareness to DateTime Columns
Actualiza columnas DateTime para usar timezone=True (timestamp with timezone en PostgreSQL)

NOTA: Este script es para referencia. Los cambios se aplicarán en el modelo y en futuras migraciones.
Para base de datos existente, ejecutar:

ALTER TABLE empresa_usuario ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'UTC';
ALTER TABLE empresa_usuario ALTER COLUMN fecha_inicio_demo TYPE timestamptz USING fecha_inicio_demo AT TIME ZONE 'UTC';
ALTER TABLE empresa_usuario ALTER COLUMN fecha_fin_demo TYPE timestamptz USING fecha_fin_demo AT TIME ZONE 'UTC';
ALTER TABLE empresa_usuario ALTER COLUMN updated_at TYPE timestamptz USING updated_at AT TIME ZONE 'UTC';

Y similar para todas las tablas con columnas DateTime.
"""

from sqlalchemy import text
from database.conexion import engine

# Lista de tablas y columnas a actualizar
TIMEZONE_UPDATES = [
    ("empresa_usuario", ["created_at", "fecha_inicio_demo", "fecha_fin_demo", "updated_at"]),
    ("suscripciones", ["fecha_proxima_renovacion", "created_at", "updated_at"]),
    ("facturas_suscripcion", ["created_at"]),
    ("usuarios", ["created_at", "updated_at", "bloqueado_hasta"]),
    ("reservations", ["created_at", "updated_at", "cancelled_at"]),
    ("stays", ["checkin_real", "checkout_real", "created_at"]),
    ("stay_charges", ["created_at"]),
    ("stay_payments", ["timestamp"]),
    ("audit_events", ["timestamp"]),
    ("housekeeping_tasks", ["created_at", "completed_at"]),
    ("daily_cleaning_logs", ["timestamp"]),
]


def generate_migration_sql():
    """Genera SQL para conversión de timestamp a timestamptz"""
    
    statements = []
    
    for table, columns in TIMEZONE_UPDATES:
        for column in columns:
            sql = (
                f"ALTER TABLE {table} "
                f"ALTER COLUMN {column} TYPE timestamptz "
                f"USING {column} AT TIME ZONE 'UTC';"
            )
            statements.append(sql)
    
    return "\n".join(statements)


if __name__ == "__main__":
    print("-- Migration SQL for Timezone Awareness")
    print("-- Run these statements on your PostgreSQL database:")
    print()
    print(generate_migration_sql())
    print()
    print("-- IMPORTANTE: Ejecutar después de actualizar models/core.py con timezone=True")
