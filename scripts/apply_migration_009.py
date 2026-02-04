"""
Aplica la migración 009_add_deleted_to_empresa_usuarios.sql
"""
from pathlib import Path
from database.conexion import engine


def main():
    sql_path = Path(__file__).resolve().parents[1] / "migrations" / "009_add_deleted_to_empresa_usuarios.sql"
    if not sql_path.exists():
        print(f"❌ No se encontró el archivo: {sql_path}")
        return

    sql_script = sql_path.read_text(encoding="utf-8")
    print(f"📄 Ejecutando migración: {sql_path.name}")

    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(sql_script)
        print("✅ Migración 009 aplicada exitosamente")
    except Exception as exc:
        print(f"❌ Error aplicando migración 009: {exc}")
        raise


if __name__ == "__main__":
    main()
