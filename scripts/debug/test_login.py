from sqlalchemy.orm import Session
from database.conexion import engine
from models.usuario import Usuario
from utils.auth import verify_password

db = Session(engine)
user = db.query(Usuario).filter(Usuario.email == 'admin@hotel.com').first()

if user:
    print(f'Usuario: {user.username}')
    print(f'Email: {user.email}')
    print(f'Hash: {user.hashed_password[:60]}...')
    print(f'Activo: {user.activo}')
    print(f'Es super admin: {user.es_super_admin}')
    
    # Probar contraseña
    resultado = verify_password('admin123', user.hashed_password)
    print(f'\nVerificación con "admin123": {resultado}')
else:
    print('Usuario no encontrado')
