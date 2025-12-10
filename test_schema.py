#!/usr/bin/env python
"""Test script para validar schemas v2.0"""

from schemas.habitacion import HabitacionCreate

# Test: Schema validation
print('TEST: Validación de Schema v2.0')
print('-' * 50)

payload = {
    'numero': 20,
    'categoria_id': 1,
    'estado': 'disponible',
    'piso': 1,
    'observaciones': '',
    'activo': True
}

try:
    hab = HabitacionCreate(**payload)
    print('✅ HabitacionCreate VALIDADO')
    hab_dict = hab.model_dump()
    print(f'\nDatos validados:')
    for key, value in hab_dict.items():
        print(f'  {key}: {value} ({type(value).__name__})')
    print('\n✅ SCHEMA CORRECTO - Listo para API')
except Exception as e:
    print(f'❌ Error: {e}')
