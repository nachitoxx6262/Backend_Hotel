#!/usr/bin/env python3
"""
Script para crear datos de seed para el sistema multi-tenant
Crea: Planes, Usuario super_admin, Empresa Usuario de demo
"""

import os
from datetime import datetime, timedelta
from sqlalchemy import text
from database.conexion import SessionLocal, engine
from models.core import Plan, PlanType
from models.usuario import Usuario
import hashlib

logger = print  # Simple logger

def create_default_plans():
    """Crea los 3 planes SaaS"""
    session = SessionLocal()
    try:
        # Verificar si ya existen
        demo_plan = session.query(Plan).filter(Plan.nombre == PlanType.DEMO).first()
        if demo_plan:
            logger.("✅ Planes ya existen")
            return
        
        logger("📝 Creando planes SaaS...")
        
        plans = [
            Plan(
                nombre=PlanType.DEMO,
                descripcion="Plan de demostración - 10 días gratis, completo",
                precio_mensual=0.0,
                max_habitaciones=20,
                max_usuarios=10,
                caracteristicas={
                    "reservations": True,
                    "guests": True,
                    "housekeeping": True,
                    "invoicing": True,
                    "reports": True,
                    "api": False,
                    "support": "email"
                },
                activo=True
            ),
            Plan(
                nombre=PlanType.BASICO,
                descripcion="Plan Básico - Perfecto para hoteles pequeños",
                precio_mensual=99.0,
                max_habitaciones=50,
                max_usuarios=5,
                caracteristicas={
                    "reservations": True,
                    "guests": True,
                    "housekeeping": True,
                    "invoicing": True,
                    "reports": True,
                    "api": False,
                    "support": "email"
                },
                activo=True
            ),
            Plan(
                nombre=PlanType.PREMIUM,
                descripcion="Plan Premium - Máximas capacidades",
                precio_mensual=299.0,
                max_habitaciones=1000,
                max_usuarios=100,
                caracteristicas={
                    "reservations": True,
                    "guests": True,
                    "housekeeping": True,
                    "invoicing": True,
                    "reports": True,
                    "custom_reports": True,
                    "api": True,
                    "integrations": True,
                    "support": "phone_email"
                },
                activo=True
            ),
        ]
        
        for plan in plans:
            session.add(plan)
        
        session.commit()
        logger(f"✅ {len(plans)} planes creados exitosamente")
        
    except Exception as e:
        logger(f"❌ Error creando planes: {str(e)}")
        session.rollback()
    finally:
        session.close()

def hash_password(password: str) -> str:
    """Hashea password (nota: usar werkzeug.security.generate_password_hash en prod)"""
    return hashlib.sha256(password.encode()).hexdigest()

def create_superadmin_user():
    """Crea usuario super_admin de prueba"""
    session = SessionLocal()
    try:
        # Verificar si ya existe
        admin = session.query(Usuario).filter(Usuario.username == "admin").first()
        if admin:
            logger("✅ Super admin ya existe")
            return admin
        
        logger("📝 Creando usuario super_admin...")
        
        admin = Usuario(
            username="admin",
            email="admin@icloudpms.com",
            hashed_password=hash_password("admin123456"),  # ⚠️ CAMBIAR EN PRODUCCIÓN
            nombre="Administrator",
            apellido="Cuenus Hotel",
            empresa_usuario_id=None,  # NULL = no pertenece a tenant específico
            es_super_admin=True,
            rol="admin",
            activo=True,
            deleted=False
        )
        
        session.add(admin)
        session.commit()
        logger(f"✅ Super admin creado: {admin.username}")
        return admin
        
    except Exception as e:
        logger(f"❌ Error creando super_admin: {str(e)}")
        session.rollback()
        return None
    finally:
        session.close()

def create_demo_empresa_usuario():
    """Crea una empresa usuario de demostración"""
    from models.core import EmpresaUsuario, Subscription
    
    session = SessionLocal()
    try:
        # Verificar si ya existe
        demo_empresa = session.query(EmpresaUsuario).filter(
            EmpresaUsuario.nombre_hotel == "Demo Hotel"
        ).first()
        
        if demo_empresa:
            logger("✅ Empresa usuario demo ya existe")
            return demo_empresa
        
        logger("📝 Creando empresa usuario de demostración...")
        
        # Obtener plan DEMO
        demo_plan = session.query(Plan).filter(Plan.nombre == PlanType.DEMO).first()
        if not demo_plan:
            logger("❌ Plan DEMO no existe - ejecutar create_default_plans() primero")
            return None
        
        # Crear empresa usuario
        now = datetime.utcnow()
        fin_demo = now + timedelta(days=10)
        
        demo_empresa = EmpresaUsuario(
            nombre_hotel="Demo Hotel",
            cuit="20123456789",
            contacto_nombre="Manager Demo",
            contacto_email="demo@hotel.com",
            contacto_telefono="+54911234567",
            direccion="Av. Example 123",
            ciudad="Buenos Aires",
            provincia="Buenos Aires",
            plan_tipo=PlanType.DEMO,
            fecha_inicio_demo=now,
            fecha_fin_demo=fin_demo,
            activa=True
        )
        
        session.add(demo_empresa)
        session.flush()  # Para obtener el ID
        
        # Crear subscription asociada
        subscription = Subscription(
            empresa_usuario_id=demo_empresa.id,
            plan_id=demo_plan.id,
            estado="activo",
            fecha_proxima_renovacion=fin_demo,
            metadata={
                "trial": True,
                "created_at": now.isoformat(),
                "tier": "demo"
            }
        )
        
        session.add(subscription)
        session.commit()
        logger(f"✅ Empresa usuario 'Demo Hotel' creada con trial de 10 días")
        logger(f"   Trial expires: {fin_demo.isoformat()}")
        return demo_empresa
        
    except Exception as e:
        logger(f"❌ Error creando empresa usuario: {str(e)}")
        session.rollback()
        return None
    finally:
        session.close()

def verify_tables_exist():
    """Verifica que las tablas SaaS existan"""
    try:
        with engine.connect() as connection:
            # Verificar que las tablas existen
            check_query = text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('planes', 'empresa_usuarios', 'subscriptions', 'payment_attempts')
            """)
            result = connection.execute(check_query)
            tables = [row[0] for row in result]
            
            required_tables = ['planes', 'empresa_usuarios', 'subscriptions', 'payment_attempts']
            missing = [t for t in required_tables if t not in tables]
            
            if missing:
                logger(f"❌ Tablas faltantes: {missing}")
                logger(f"   Ejecutar migraciones 005+ primero: python run_migrations_multitenant.py")
                return False
            
            logger(f"✅ Todas las tablas SaaS existen: {', '.join(tables)}")
            return True
            
    except Exception as e:
        logger(f"❌ Error verificando tablas: {str(e)}")
        return False

def main():
    """Ejecuta todo el seed"""
    logger("=" * 70)
    logger("🌱 MULTI-TENANT SEED DATA CREATION")
    logger("=" * 70)
    
    # Paso 1: Verificar tablas
    if not verify_tables_exist():
        logger("⚠️  Aborting - ejecutar migraciones primero")
        return False
    
    # Paso 2: Crear planes
    create_default_plans()
    
    # Paso 3: Crear super admin
    create_superadmin_user()
    
    # Paso 4: Crear demo empresa
    create_demo_empresa_usuario()
    
    logger("=" * 70)
    logger("✅ SEED COMPLETED")
    logger("=" * 70)
    logger("")
    logger("Próximos pasos:")
    logger("1. Verificar datos creados:")
    logger("   SELECT * FROM planes;")
    logger("   SELECT * FROM empresa_usuarios;")
    logger("   SELECT * FROM usuarios WHERE es_super_admin = true;")
    logger("")
    logger("2. Continuar con Phase 2: JWT + Auth endpoints")
    logger("")
    return True

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
