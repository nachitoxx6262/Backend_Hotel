"""Verificar vinculación de Reservation.cliente_id"""
import sys
sys.path.append('c:\\Users\\ignac\\OneDrive\\Escritorio\\SISTEMA HOTEL\\Backend_Hotel')

from database.conexion import SessionLocal
from models.core import Reservation, Stay

db = SessionLocal()

try:
    # Verificar Reservation 246
    reservation = db.query(Reservation).filter(Reservation.id == 246).first()
    
    if reservation:
        print(f"\n=== RESERVATION 246 ===")
        print(f"ID: {reservation.id}")
        print(f"Cliente ID: {reservation.cliente_id}")
        print(f"Nombre Temporal: {reservation.nombre_temporal}")
        
        # Verificar Stay 180
        stay = db.query(Stay).filter(Stay.id == 180).first()
        if stay:
            print(f"\n=== STAY 180 ===")
            print(f"ID: {stay.id}")
            print(f"Reservation ID: {stay.reservation_id}")
            print(f"Estado: {stay.estado}")
            
            # Verificar que el reservation_id match
            if stay.reservation_id == reservation.id:
                print("\n✓ Stay está correctamente vinculado a Reservation")
            else:
                print(f"\n✗ ERROR: Stay.reservation_id ({stay.reservation_id}) != Reservation.id ({reservation.id})")
        else:
            print("\n✗ Stay 180 no encontrado")
        
        # Test de la query del endpoint
        print("\n=== TEST DE QUERY (como en el endpoint) ===")
        query_stays = db.query(Stay).join(Reservation).filter(
            Reservation.cliente_id == 70
        ).all()
        print(f"Stays encontrados para cliente_id=70: {len(query_stays)}")
        if len(query_stays) > 0:
            print("✓✓✓ ¡ÉXITO! La query encuentra el stay")
            for s in query_stays:
                print(f"  - Stay ID: {s.id}, Reservation ID: {s.reservation_id}")
        else:
            print("✗✗✗ FALLO: La query NO encuentra stays")
            print(f"Motivo probable: Reservation.cliente_id = {reservation.cliente_id} (debería ser 70)")
            if reservation.cliente_id is None:
                print("  → EL BUG NO SE CORRIGIÓ: cliente_id sigue siendo NULL")
            elif reservation.cliente_id != 70:
                print(f"  → ERROR: cliente_id apunta a otro cliente ({reservation.cliente_id})")
    else:
        print("✗ Reservation 246 no encontrada")
        
finally:
    db.close()
