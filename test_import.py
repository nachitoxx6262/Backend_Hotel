import sys
sys.path.insert(0, '.')

try:
    print("Importando main...", flush=True)
    import main
    print("✓ main importado correctamente", flush=True)
    print("✓ app.routes:", len(main.app.routes), flush=True)
except Exception as e:
    print(f"✗ Error al importar main: {e}", flush=True)
    import traceback
    traceback.print_exc()
