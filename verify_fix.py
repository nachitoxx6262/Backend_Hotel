"""Script para verificar si la modificación funcionó correctamente"""
from database.conexion import SessionLocal
from models.reservations import Reservation
from models.stays import Stay
from models.clientes import Cliente
from models.reservation_guests import ReservationGuest

db = SessionLocal()

try:
    # Buscar la estancia recién creada
    stay = db.query(Stay).filter(Stay.id == 178).first()
    
    if not stay:
        print("❌ Stay 178 no encontrada")
    else:
        print(f"\n=== STAY 178 ===")
        print(f"Stay ID: {stay.id}")
        print(f"Reservation ID: {stay.reservation_id}")
        print(f"Estado: {stay.estado}")
        
        # Verificar la reserva asociada
        reservation = db.query(Reservation).filter(Reservation.id == stay.reservation_id).first()
        
        if reservation:
            print(f"\n=== RESERVATION {reservation.id} ===")
            print(f"Reservation ID: {reservation.id}")
            print(f"Cliente ID: {reservation.cliente_id}")
            print(f"Nombre Temporal: {reservation.nombre_temporal}")
            
            # Verificar los huéspedes
            guests = db.query(ReservationGuest).filter(
                ReservationGuest.reservation_id == reservation.id
            ).all()
            
            print(f"\n=== GUESTS ({len(guests)}) ===")
            for guest in guests:
                print(f"Guest ID: {guest.id}")
                print(f"  Cliente ID: {guest.cliente_id}")
                print(f"  Rol: {guest.rol}")
                print(f"  Nombre: {guest.nombre} {guest.apellido}")
                print(f"  Documento: {guest.numero_documento}")
            
            # Verificar el cliente
            if reservation.cliente_id:
                cliente = db.query(Cliente).filter(Cliente.id == reservation.cliente_id).first()
                if cliente:
                    print(f"\n=== CLIENTE {cliente.id} ===")
                    print(f"ID: {cliente.id}")
                    print(f"Nombre: {cliente.nombre} {cliente.apellido}")
                    print(f"Documento: {cliente.numero_documento}")
                    
                    # Verificar estancias del cliente
                    client_stays = db.query(Stay).join(Reservation).filter(
                        Reservation.cliente_id == cliente.id
                    ).all()
                    
                    print(f"\n=== STAYS DEL CLIENTE ({len(client_stays)}) ===")
                    for cs in client_stays:
                        print(f"Stay ID: {cs.id}, Reservation: {cs.reservation_id}, Estado: {cs.estado}")
                    
                    if len(client_stays) == 0:
                        print("\n❌ PROBLEMA: El cliente NO tiene estancias vinculadas")
                        print("   Esto indica que reservation.cliente_id NO está siendo seteado correctamente")
                    else:
                        print("\n✅ ÉXITO: El cliente tiene estancias vinculadas")
                else:
                    print(f"\n❌ Cliente {reservation.cliente_id} no encontrado en BD")
            else:
                print("\n❌ PROBLEMA CRÍTICO: reservation.cliente_id es NULL")
                print("   La modificación NO funcionó - el cliente_id no se asignó durante el check-in")
        else:
            print(f"❌ Reservation {stay.reservation_id} no encontrada")
            
finally:
    db.close()
