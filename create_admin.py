"""
Script para crear el primer usuario administrador del sistema
Ejecutar: python create_admin.py
"""
import sys
from sqlalchemy.orm import Session
from database.conexion import SessionLocal, engine, Base
from models.usuario import Usuario
from models import Rol, UsuarioRol  # Importar para registrar los modelos
from utils.auth import get_password_hash


def crear_admin():
    """Crea el usuario administrador por defecto"""
    db = SessionLocal()
    
    try:
        # Verificar si ya existe un admin
        admin_existente = db.query(Usuario).filter(
            Usuario.username == "admin",
            Usuario.deleted.is_(False)
        ).first()
        
        if admin_existente:
            print("⚠️  Ya existe un usuario 'admin'")
            print(f"   ID: {admin_existente.id}")
            print(f"   Email: {admin_existente.email}")
            print(f"   Rol: {admin_existente.rol}")
            return
        
        # Solicitar datos
        print("\n🔧 Creación de Usuario Administrador")
        print("=" * 50)
        
        username = input("Username (default: admin): ").strip() or "admin"
        email = input("Email (default: admin@hotel.com): ").strip() or "admin@hotel.com"
        
        while True:
            password = input("Password (mínimo 8 caracteres): ").strip()
            if len(password) >= 8:
                break
            print("❌ La contraseña debe tener al menos 8 caracteres")
        
        nombre = input("Nombre (opcional): ").strip() or "Administrador"
        apellido = input("Apellido (opcional): ").strip() or "Sistema"
        
        # Crear usuario
        nuevo_admin = Usuario(
            username=username,
            email=email,
            hashed_password=get_password_hash(password),
            nombre=nombre,
            apellido=apellido,
            rol="admin",
            activo=True,
            deleted=False,
            intentos_fallidos=0
        )
        
        db.add(nuevo_admin)
        db.commit()
        db.refresh(nuevo_admin)
        
        print("\n✅ Usuario administrador creado exitosamente!")
        print(f"   ID: {nuevo_admin.id}")
        print(f"   Username: {nuevo_admin.username}")
        print(f"   Email: {nuevo_admin.email}")
        print(f"   Rol: {nuevo_admin.rol}")
        print(f"\n🔐 Puede iniciar sesión con estas credenciales en /auth/login")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error al crear usuario administrador: {str(e)}")
        sys.exit(1)
    finally:
        db.close()


def crear_usuarios_demo():
    """Crea usuarios de demostración para todos los roles"""
    db = SessionLocal()
    
    try:
        print("\n📝 ¿Desea crear usuarios de demostración? (s/n): ", end="")
        respuesta = input().strip().lower()
        
        if respuesta != 's':
            return
        
        usuarios_demo = [
            {
                "username": "gerente",
                "email": "gerente@hotel.com",
                "password": "Gerente123",
                "nombre": "Juan",
                "apellido": "García",
                "rol": "gerente"
            },
            {
                "username": "recepcionista",
                "email": "recepcion@hotel.com",
                "password": "Recepcion123",
                "nombre": "María",
                "apellido": "López",
                "rol": "recepcionista"
            },
            {
                "username": "consulta",
                "email": "consulta@hotel.com",
                "password": "Consulta123",
                "nombre": "Carlos",
                "apellido": "Martínez",
                "rol": "readonly"
            }
        ]
        
        creados = 0
        for user_data in usuarios_demo:
            # Verificar si ya existe
            existe = db.query(Usuario).filter(
                Usuario.username == user_data["username"],
                Usuario.deleted.is_(False)
            ).first()
            
            if existe:
                print(f"⚠️  Usuario '{user_data['username']}' ya existe, omitiendo...")
                continue
            
            nuevo_usuario = Usuario(
                username=user_data["username"],
                email=user_data["email"],
                hashed_password=get_password_hash(user_data["password"]),
                nombre=user_data["nombre"],
                apellido=user_data["apellido"],
                rol=user_data["rol"],
                activo=True,
                deleted=False,
                intentos_fallidos=0
            )
            
            db.add(nuevo_usuario)
            creados += 1
        
        db.commit()
        
        if creados > 0:
            print(f"\n✅ Se crearon {creados} usuarios de demostración")
            print("\nCredenciales de acceso:")
            print("-" * 50)
            for user_data in usuarios_demo:
                print(f"  {user_data['rol'].upper():15} | {user_data['username']:15} | {user_data['password']}")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error al crear usuarios demo: {str(e)}")
    finally:
        db.close()


if __name__ == "__main__":
    print("🏨 Sistema de Hotel - Inicialización de Usuarios")
    print("=" * 50)
    
    # Crear tablas si no existen
    print("\n📊 Verificando tablas de base de datos...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tablas verificadas/creadas")
    
    # Crear admin
    crear_admin()
    
    # Crear usuarios demo
    crear_usuarios_demo()
    
    print("\n🎉 Proceso completado!")
    print("\n📖 Próximos pasos:")
    print("   1. Inicie el servidor: uvicorn main:app --reload")
    print("   2. Acceda a la documentación: http://localhost:8000/docs")
    print("   3. Use /auth/login para obtener tokens JWT")
