"""
Script de Verificación de Correcciones Urgentes
Verifica que todas las correcciones críticas estén aplicadas correctamente
"""

import os
import sys

def check_env_file():
    """Verificar que .env existe y tiene JWT_SECRET_KEY"""
    print("\n🔍 Verificando archivo .env...")
    env_path = "c:\\Users\\ignac\\OneDrive\\Escritorio\\SISTEMA HOTEL\\Backend_Hotel\\.env"
    
    if not os.path.exists(env_path):
        print("❌ FALLO: Archivo .env no existe")
        return False
    
    with open(env_path, 'r') as f:
        content = f.read()
        
    if 'JWT_SECRET_KEY=' in content:
        # Extraer el valor
        for line in content.split('\n'):
            if line.startswith('JWT_SECRET_KEY='):
                key = line.split('=', 1)[1].strip()
                if key and len(key) > 20:
                    print(f"✅ JWT_SECRET_KEY configurado (longitud: {len(key)} caracteres)")
                    return True
                else:
                    print("⚠️ WARNING: JWT_SECRET_KEY es muy corto o está vacío")
                    return False
    
    print("❌ FALLO: JWT_SECRET_KEY no encontrado en .env")
    return False

def check_auth_py():
    """Verificar que utils/auth.py usa os.getenv"""
    print("\n🔍 Verificando utils/auth.py...")
    auth_path = "c:\\Users\\ignac\\OneDrive\\Escritorio\\SISTEMA HOTEL\\Backend_Hotel\\utils\\auth.py"
    
    with open(auth_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'SECRET_KEY = os.getenv("JWT_SECRET_KEY")' in content:
        print("✅ SECRET_KEY usa os.getenv()")
        if 'secrets.token_urlsafe' in content:
            print("✅ Tiene fallback con secrets.token_urlsafe()")
            return True
        else:
            print("⚠️ WARNING: No tiene fallback seguro")
            return False
    else:
        print("❌ FALLO: SECRET_KEY sigue hardcodeado")
        return False

def check_cors_main():
    """Verificar que main.py tiene CORS configurado"""
    print("\n🔍 Verificando CORS en main.py...")
    main_path = "c:\\Users\\ignac\\OneDrive\\Escritorio\\SISTEMA HOTEL\\Backend_Hotel\\main.py"
    
    with open(main_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'from fastapi.middleware.cors import CORSMiddleware' in content:
        print("✅ Import de CORSMiddleware encontrado")
        if 'app.add_middleware(CORSMiddleware' in content or 'app.add_middleware(\n    CORSMiddleware' in content:
            print("✅ CORSMiddleware agregado al app")
            return True
        else:
            print("⚠️ WARNING: CORSMiddleware importado pero no agregado")
            return False
    else:
        print("❌ FALLO: CORS no configurado")
        return False

def check_plantype_bug():
    """Verificar que admin.py usa PlanType.DEMO.value"""
    print("\n🔍 Verificando bug PlanType en admin.py...")
    admin_path = "c:\\Users\\ignac\\OneDrive\\Escritorio\\SISTEMA HOTEL\\Backend_Hotel\\endpoints\\admin.py"
    
    with open(admin_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Buscar la línea problemática
    if 'EmpresaUsuario.plan_tipo == PlanType.DEMO.value' in content:
        print("✅ PlanType.DEMO.value corregido")
        return True
    elif 'EmpresaUsuario.plan_tipo == PlanType.DEMO,' in content:
        print("❌ FALLO: Todavía usa PlanType.DEMO sin .value")
        return False
    else:
        print("⚠️ WARNING: No se encontró la línea esperada")
        return False

def check_logger_js():
    """Verificar que logger.js existe"""
    print("\n🔍 Verificando logger.js...")
    logger_path = "c:\\Users\\ignac\\OneDrive\\Escritorio\\SISTEMA HOTEL\\Cliente_hotel\\src\\utils\\logger.js"
    
    if not os.path.exists(logger_path):
        print("❌ FALLO: logger.js no existe")
        return False
    
    with open(logger_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'import.meta.env.MODE' in content and 'export const logger' in content:
        print("✅ logger.js creado correctamente")
        return True
    else:
        print("❌ FALLO: logger.js tiene estructura incorrecta")
        return False

def check_hotelscheduler_logger():
    """Verificar que HotelScheduler usa logger en lugar de console.log"""
    print("\n🔍 Verificando HotelScheduler.jsx...")
    scheduler_path = "c:\\Users\\ignac\\OneDrive\\Escritorio\\SISTEMA HOTEL\\Cliente_hotel\\src\\pages\\Reservas\\HotelScheduler.jsx"
    
    with open(scheduler_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if "import { logger } from '../../utils/logger'" in content:
        print("✅ Import de logger encontrado")
        
        # Contar console.log activos (no comentados)
        active_console_logs = 0
        for line in content.split('\n'):
            if 'console.log' in line and not line.strip().startswith('//'):
                active_console_logs += 1
        
        # Contar logger.log
        logger_calls = content.count('logger.log')
        logger_warns = content.count('logger.warn')
        
        print(f"   - console.log activos: {active_console_logs}")
        print(f"   - logger.log: {logger_calls}")
        print(f"   - logger.warn: {logger_warns}")
        
        if active_console_logs == 0 and logger_calls > 0:
            print("✅ Todos los console.log reemplazados por logger")
            return True
        elif active_console_logs > 0:
            print(f"⚠️ WARNING: Todavía hay {active_console_logs} console.log activos")
            return False
        else:
            print("❌ FALLO: No se encontraron llamadas a logger")
            return False
    else:
        print("❌ FALLO: Logger no importado")
        return False

def main():
    print("=" * 60)
    print("   VERIFICACIÓN DE CORRECCIONES URGENTES")
    print("=" * 60)
    
    results = {
        "SECRET_KEY en .env": check_env_file(),
        "auth.py corregido": check_auth_py(),
        "CORS configurado": check_cors_main(),
        "Bug PlanType corregido": check_plantype_bug(),
        "logger.js creado": check_logger_js(),
        "HotelScheduler usa logger": check_hotelscheduler_logger()
    }
    
    print("\n" + "=" * 60)
    print("   RESUMEN DE VERIFICACIÓN")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Total: {passed}/{len(results)} correcciones verificadas")
    print("=" * 60)
    
    if failed == 0:
        print("\n🎉 ¡TODAS LAS CORRECCIONES APLICADAS CORRECTAMENTE!")
        return 0
    else:
        print(f"\n⚠️ {failed} correcciones necesitan atención")
        return 1

if __name__ == "__main__":
    sys.exit(main())
