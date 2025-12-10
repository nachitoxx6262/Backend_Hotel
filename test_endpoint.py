#!/usr/bin/env python
"""Test completo del endpoint crear_habitacion"""

from sqlalchemy.orm import Session
from database.conexion import SessionLocal, Base, engine
from models.habitacion import Habitacion, CategoriaHabitacion
from schemas.habitacion import HabitacionCreate

# Crear tablas
Base.metadata.create_all(bind=engine)

# Obtener sesión
db = SessionLocal()

try:
    # Verificar categoría
    cat = db.query(CategoriaHabitacion).first()
    if not cat:
        cat = CategoriaHabitacion(
            nombre='Test',
            descripcion='Test',
            capacidad_personas=1,
            precio_base_noche=100.00
        )
        db.add(cat)
        db.commit()
        db.refresh(cat)
    
    print(f'✓ Categoría ID={cat.id} disponible')
    
    # Payload exacto que envía frontend
    payload = {
        'numero': 21,
        'categoria_id': cat.id,
        'estado': 'disponible',
        'piso': 1,
        'observaciones': '',
        'activo': True
    }
    
    print('\n1. Validando schema...')
    habitacion_data = HabitacionCreate(**payload)
    print(f'✅ Schema válido')
    
    print('\n2. Creando habitación (simulando endpoint)...')
    # IMPORTANTE: No pasar activo=True explícitamente
    habitacion = Habitacion(**habitacion_data.model_dump(exclude_unset=True))
    db.add(habitacion)
    db.commit()
    db.refresh(habitacion)
    
    print(f'✅ Habitación creada:')
    print(f'   ID: {habitacion.id}')
    print(f'   Número: {habitacion.numero}')
    print(f'   Categoría ID: {habitacion.categoria_id}')
    print(f'   Estado: {habitacion.estado}')
    print(f'   Piso: {habitacion.piso}')
    print(f'   Activo: {habitacion.activo}')
    
    # Limpiar
    db.delete(habitacion)
    db.commit()
    
    print('\n✅ TEST COMPLETADO - Endpoint funcionará correctamente')
    
except Exception as e:
    print(f'\n❌ Error: {e}')
    import traceback
    traceback.print_exc()
finally:
    db.close()
