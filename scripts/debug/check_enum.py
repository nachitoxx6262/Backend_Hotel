from sqlalchemy import text
from database.conexion import engine

with engine.connect() as conn:
    result = conn.execute(text("SELECT unnest(enum_range(NULL::plan_type_enum))"))
    print([r[0] for r in result])
