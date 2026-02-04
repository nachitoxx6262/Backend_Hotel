import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

conn = psycopg2.connect(
    dbname=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT')
)

cur = conn.cursor()

# Ver qué valores hay en transaction_categories
print("=" * 60)
print("VALORES ACTUALES EN transaction_categories:")
print("=" * 60)
cur.execute("SELECT id, nombre, tipo FROM transaction_categories LIMIT 20;")
rows = cur.fetchall()
for row in rows:
    print(f"ID: {row[0]}, Nombre: {row[1]}, Tipo: {row[2]} (representación: {repr(row[2])})")

# Corregir los valores a minúsculas
print("\n" + "=" * 60)
print("CORRIGIENDO VALORES A MINÚSCULAS...")
print("=" * 60)
cur.execute("UPDATE transaction_categories SET tipo = LOWER(tipo::text)::transaction_type;")
conn.commit()
print("✅ Actualización completada")

# Verificar nuevamente
print("\n" + "=" * 60)
print("VALORES DESPUÉS DE LA CORRECCIÓN:")
print("=" * 60)
cur.execute("SELECT id, nombre, tipo FROM transaction_categories LIMIT 20;")
rows = cur.fetchall()
for row in rows:
    print(f"ID: {row[0]}, Nombre: {row[1]}, Tipo: {row[2]}")

cur.close()
conn.close()
