import psycopg2
from database.conexion import DATABASE_URL

# Parse connection string
# Format: postgresql://user:password@host:port/database
try:
    # Extract credentials from DATABASE_URL
    import urllib.parse
    parsed = urllib.parse.urlparse(DATABASE_URL)
    
    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=parsed.path.lstrip('/'),
        user=parsed.username,
        password=parsed.password
    )
    cur = conn.cursor()
    
    # Execute migration
    try:
        cur.execute("ALTER TABLE productos_servicios ADD COLUMN empresa_usuario_id INTEGER")
        print("✓ Added empresa_usuario_id column")
    except psycopg2.errors.DuplicateColumn:
        print("! Column empresa_usuario_id already exists")
    
    try:
        cur.execute("""
            ALTER TABLE productos_servicios 
            ADD CONSTRAINT fk_productos_empresa_usuario 
            FOREIGN KEY (empresa_usuario_id) 
            REFERENCES empresa_usuarios(id) 
            ON DELETE CASCADE
        """)
        print("✓ Added foreign key constraint")
    except Exception as e:
        print(f"! Foreign key constraint: {e}")
    
    try:
        cur.execute("CREATE INDEX idx_producto_empresa_usuario ON productos_servicios(empresa_usuario_id)")
        print("✓ Created index")
    except psycopg2.errors.DuplicateTable:
        print("! Index already exists")
    
    try:
        cur.execute("""
            UPDATE productos_servicios 
            SET empresa_usuario_id = (SELECT MIN(id) FROM empresa_usuarios)
            WHERE empresa_usuario_id IS NULL 
            AND EXISTS (SELECT 1 FROM empresa_usuarios)
        """)
        print(f"✓ Updated {cur.rowcount} existing records")
    except Exception as e:
        print(f"! Data migration: {e}")
    
    conn.commit()
    cur.close()
    conn.close()
    print("[OK] Migration completed successfully")
    
except Exception as e:
    print(f"[ERROR] {e}")
