"""
Script para crear usuario administrador
"""
import sys
from sqlalchemy.orm import Session
from database.conexion import engine, Base
from models.usuario import Usuario
from models.rol import Rol
from models.core import EmpresaUsuario, Plan, PlanType
from utils.auth import get_password_hash

def create_admin():
    """Crea un usuario super admin"""
    Base.metadata.create_all(bind=engine)
    
    with Session(engine) as db:
        # Verificar si ya existe un super admin
        existing_admin = db.query(Usuario).filter((Usuario.es_super_admin == True) | (Usuario.email == "admin@hotel.com")).first()
        if existing_admin:
            print(f"❌ Ya existe un super admin o usuario admin: {existing_admin.email}")
            return
        
        # Crear empresa_usuario (tenant) para el super admin
        empresa_usuario = db.query(EmpresaUsuario).filter(EmpresaUsuario.nombre_hotel == "Sistema").first()
        if not empresa_usuario:
            empresa_usuario = EmpresaUsuario(
                nombre_hotel="Sistema",
                cuit="00-00000000-0",
                plan_tipo="demo",
                contacto_email="admin@sistema.com",
                activa=True
            )
            db.add(empresa_usuario)
            db.commit()
            db.refresh(empresa_usuario)
            print(f"✅ Empresa Sistema creada (ID: {empresa_usuario.id})")
        
        # Buscar rol admin
        rol_admin = db.query(Rol).filter(Rol.nombre == "Admin").first()
        if not rol_admin:
            # Crear rol Admin si no existe
            rol_admin = Rol(
                nombre="Admin",
                descripcion="Administrador del sistema",
                empresa_usuario_id=empresa_usuario.id
            )
            db.add(rol_admin)
            db.commit()
            db.refresh(rol_admin)
            print(f"✅ Rol Admin creado (ID: {rol_admin.id})")
        
        # Crear usuario super admin
        admin = Usuario(
            username="admin",
            email="admin@hotel.com",
            hashed_password=get_password_hash("admin123"),
            nombre="Super",
            apellido="Admin",
            rol="admin",
            empresa_usuario_id=empresa_usuario.id,
            es_super_admin=True,
            activo=True
        )
        
        db.add(admin)
        db.commit()
        db.refresh(admin)
        
        print("\n" + "="*50)
        print("✅ SUPER ADMIN CREADO")
        print("="*50)
        print(f"Email: {admin.email}")
        print(f"Password: admin123")
        print(f"ID: {admin.id}")
        print(f"Empresa Usuario ID: {admin.empresa_usuario_id}")
        print("="*50 + "\n")

if __name__ == "__main__":
    create_admin()
