import os
import sys
import sqlalchemy as sa

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from database.conexion import engine

with engine.connect() as conn:
    rows = conn.execute(sa.text("SELECT column_name FROM information_schema.columns WHERE table_name='subscriptions' ORDER BY ordinal_position"))
    print([r[0] for r in rows])
    try:
        conn.execute(sa.text("SELECT metadata_json FROM subscriptions LIMIT 1"))
        print("metadata_json column exists")
    except Exception as exc:
        print(f"metadata_json select failed: {exc}")
