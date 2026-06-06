from database.conexion import engine
from sqlalchemy import text

conn = engine.connect()
result = conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'clientes' ORDER BY ordinal_position"))
for row in result:
    print(f"{row[0]}: {row[1]}")
conn.close()
