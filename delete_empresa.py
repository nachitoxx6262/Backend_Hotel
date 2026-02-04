"""Script para eliminar empresa y datos relacionados"""
from database.conexion import SessionLocal
from models.core import EmpresaUsuario, Subscription
from models.usuario import Usuario

db = SessionLocal()

try:
    empresa_id = 15
    empresa = db.query(EmpresaUsuario).filter(EmpresaUsuario.id == empresa_id).first()
    
    if empresa:
        # Eliminar usuarios asociados
        usuarios = db.query(Usuario).filter(Usuario.empresa_usuario_id == empresa_id).all()
        print(f"Eliminando {len(usuarios)} usuarios...")
        for u in usuarios:
            db.delete(u)
        
        # Eliminar subscriptions asociadas
        subs = db.query(Subscription).filter(Subscription.empresa_usuario_id == empresa_id).all()
        print(f"Eliminando {len(subs)} subscriptions...")
        for s in subs:
            db.delete(s)
        
        # Eliminar empresa
        print(f"Eliminando empresa id={empresa.id}, nombre={empresa.nombre_hotel}...")
        db.delete(empresa)
        
        db.commit()
        print("✓ Empresa y datos relacionados eliminados exitosamente")
    else:
        print(f"Empresa con id={empresa_id} no encontrada")
        
except Exception as e:
    db.rollback()
    print(f"Error: {e}")
finally:
    db.close()
