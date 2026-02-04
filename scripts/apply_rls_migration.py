"""
Aplica la migración RLS (007_enable_rls_security.sql) en la base de datos.
"""
import os
from pathlib import Path
from database.conexion import engine


def main():
    sql_path = Path(__file__).resolve().parents[1] / "migrations" / "007_enable_rls_security.sql"
    if not sql_path.exists():
        print(f"❌ No se encontró el archivo: {sql_path}")
        return

    sql_script = sql_path.read_text(encoding="utf-8")
    print(f"📄 Ejecutando migración: {sql_path.name}")

    policy_names = [
        ("empresa_usuarios", "rls_empresa_usuarios_access"),
        ("usuarios", "rls_usuarios_access"),
        ("cliente_corporativo", "rls_cliente_corporativo_access"),
        ("clientes", "rls_clientes_access"),
        ("room_types", "rls_room_types_access"),
        ("rooms", "rls_rooms_access"),
        ("daily_rates", "rls_daily_rates_access"),
        ("reservations", "rls_reservations_access"),
        ("reservation_rooms", "rls_reservation_rooms_access"),
        ("reservation_guests", "rls_reservation_guests_access"),
        ("stays", "rls_stays_access"),
        ("stay_room_occupancies", "rls_stay_room_occupancies_access"),
        ("stay_charges", "rls_stay_charges_access"),
        ("stay_payments", "rls_stay_payments_access"),
        ("housekeeping_tasks", "rls_housekeeping_tasks_access"),
        ("roles", "rls_roles_access"),
        ("subscriptions", "rls_subscriptions_access"),
        ("payment_attempts", "rls_payment_attempts_access"),
        ("hotel_settings", "rls_hotel_settings_access"),
    ]

    try:
        with engine.begin() as conn:
            for table, policy in policy_names:
                conn.exec_driver_sql(f"DROP POLICY IF EXISTS {policy} ON {table};")

            raw_conn = conn.connection
            cursor = raw_conn.cursor()
            cursor.execute(sql_script)
            raw_conn.commit()

        print("✅ RLS habilitado exitosamente")
    except Exception as exc:
        print(f"❌ Error aplicando migración RLS: {exc}")
        raise


if __name__ == "__main__":
    main()
