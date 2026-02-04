"""Quick database check for calendar data"""
from database.conexion import get_db
from models.core import Stay, Reservation, ReservationRoom, Room
from sqlalchemy import func

def main():
    db = next(get_db())
    
    print("\n=== STAYS para tenant 17 ===")
    stays = db.query(Stay).filter(Stay.empresa_usuario_id == 17).limit(10).all()
    print(f"Total stays: {len(stays)}")
    for s in stays:
        print(f"  Stay {s.id}: estado={s.estado}, reservation_id={s.reservation_id}, checkin={s.checkin_real}, checkout={s.checkout_real}")
    
    print("\n=== RESERVATIONS para tenant 17 ===")
    reservations = db.query(Reservation).filter(Reservation.empresa_usuario_id == 17).limit(10).all()
    print(f"Total reservations: {len(reservations)}")
    for r in reservations:
        print(f"  Reservation {r.id}: estado={r.estado}, checkin={r.fecha_checkin}, checkout={r.fecha_checkout}, nombre={r.nombre_temporal}")
    
    print("\n=== RESERVATION_ROOMS para tenant 17 ===")
    rr_query = db.query(ReservationRoom, Room).join(Reservation).join(Room).filter(
        Reservation.empresa_usuario_id == 17
    ).limit(10).all()
    print(f"Total reservation_rooms: {len(rr_query)}")
    for rr, room in rr_query:
        print(f"  RR {rr.id}: reservation_id={rr.reservation_id}, room_id={rr.room_id}, room_numero={room.numero}")
    
    # Summary
    total_stays = db.query(func.count(Stay.id)).filter(Stay.empresa_usuario_id == 17).scalar()
    total_reservations = db.query(func.count(Reservation.id)).filter(Reservation.empresa_usuario_id == 17).scalar()
    
    print(f"\n=== SUMMARY ===")
    print(f"Total stays: {total_stays}")
    print(f"Total reservations: {total_reservations}")
    
    if total_stays == 0 and total_reservations == 0:
        print("\n⚠️  NO HAY DATOS DE CALENDARIO para tenant 17")
        print("Esto explica por qué el array 'blocks' está vacío en la respuesta del endpoint.")
    else:
        print("\n✅ HAY DATOS - El problema puede estar en el filtrado del endpoint")
    
    db.close()

if __name__ == "__main__":
    main()
