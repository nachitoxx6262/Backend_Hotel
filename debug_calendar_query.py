"""Simulate calendar endpoint query to debug why reservation 241 is not showing"""
from database.conexion import get_db
from models.core import Stay, Reservation, ReservationRoom, Room
from sqlalchemy.orm import joinedload
from datetime import datetime, date

def main():
    db = next(get_db())
    
    # Simulate endpoint parameters
    from_date = "2026-01-27"
    to_date = "2026-02-27"
    include_cancelled = False
    include_no_show = False
    tenant_id = 17
    
    fecha_desde = date.fromisoformat(from_date)
    fecha_hasta = date.fromisoformat(to_date)
    
    print(f"\n=== SIMULATING CALENDAR ENDPOINT ===")
    print(f"from={from_date}, to={to_date}")
    print(f"tenant_id={tenant_id}")
    print(f"include_cancelled={include_cancelled}, include_no_show={include_no_show}")
    
    # Step 1: Query Stays
    print("\n=== STEP 1: Query Stays ===")
    stays_query = db.query(Stay).filter(
        Stay.empresa_usuario_id == tenant_id
    )
    stays = stays_query.all()
    print(f"Total stays for tenant: {len(stays)}")
    
    reservation_ids_with_stay = set()
    for stay in stays:
        if stay.reservation_id:
            reservation_ids_with_stay.add(stay.reservation_id)
    
    print(f"Reservation IDs with stay: {reservation_ids_with_stay}")
    
    # Step 2: Build reservation estados filter
    print("\n=== STEP 2: Build estados filter ===")
    reservation_estados = ["draft", "confirmada"]
    if include_cancelled:
        reservation_estados.append("cancelada")
    if include_no_show:
        reservation_estados.append("no_show")
    
    estados_query = reservation_estados + ["ocupada"]
    print(f"Estados to query: {estados_query}")
    
    # Step 3: Query Reservations
    print("\n=== STEP 3: Query Reservations ===")
    reservations_query = (
        db.query(Reservation)
        .options(
            joinedload(Reservation.rooms).joinedload(ReservationRoom.room),
            joinedload(Reservation.cliente),
            joinedload(Reservation.empresa),
            joinedload(Reservation.guests)
        )
        .filter(
            Reservation.empresa_usuario_id == tenant_id,
            Reservation.estado.in_(estados_query),
            Reservation.fecha_checkin < fecha_hasta,
            Reservation.fecha_checkout > fecha_desde
        )
    )
    
    print("SQL Query filters:")
    print(f"  empresa_usuario_id == {tenant_id}")
    print(f"  estado IN {estados_query}")
    print(f"  fecha_checkin < {fecha_hasta}")
    print(f"  fecha_checkout > {fecha_desde}")
    
    # Exclude reservations with stay
    if reservation_ids_with_stay:
        reservations_query = reservations_query.filter(
            Reservation.id.notin_(reservation_ids_with_stay)
        )
        print(f"  id NOT IN {reservation_ids_with_stay}")
    
    reservations = reservations_query.all()
    print(f"\nTotal reservations found: {len(reservations)}")
    
    # Step 4: Check each reservation
    print("\n=== STEP 4: Process Reservations ===")
    for res in reservations:
        print(f"\nReservation {res.id}:")
        print(f"  estado: {res.estado}")
        print(f"  fecha_checkin: {res.fecha_checkin}")
        print(f"  fecha_checkout: {res.fecha_checkout}")
        print(f"  rooms count: {len(res.rooms)}")
        print(f"  cliente: {res.cliente}")
        print(f"  empresa: {res.empresa}")
        print(f"  nombre_temporal: {res.nombre_temporal}")
        
        # Check if it would be filtered
        if res.estado == "ocupada":
            stay_exists = db.query(Stay.id).filter(Stay.reservation_id == res.id).first()
            print(f"  ocupada check: stay_exists={stay_exists is not None}")
            if stay_exists:
                print("  ❌ WOULD BE SKIPPED (has stay)")
                continue
        
        if res.estado == "finalizada":
            print("  ❌ WOULD BE SKIPPED (finalizada)")
            continue
        
        if res.estado == "cancelada" and not include_cancelled:
            print("  ❌ WOULD BE SKIPPED (cancelada)")
            continue
        
        if res.estado == "no_show" and not include_no_show:
            print("  ❌ WOULD BE SKIPPED (no_show)")
            continue
        
        print(f"  ✅ WOULD BE INCLUDED IN BLOCKS ({len(res.rooms)} blocks)")
    
    # Summary
    print("\n=== SUMMARY ===")
    if len(reservations) == 0:
        print("❌ NO RESERVATIONS MATCH THE QUERY")
        print("\nPossible reasons:")
        print("  1. No reservations in date range")
        print("  2. All reservations have excluded estados")
        print("  3. Date range filter is incorrect")
        print("  4. Tenant filter is incorrect")
        
        # Check without filters
        print("\n=== CHECKING WITHOUT DATE FILTERS ===")
        all_res = db.query(Reservation).filter(
            Reservation.empresa_usuario_id == tenant_id
        ).all()
        print(f"Total reservations for tenant (any date): {len(all_res)}")
        for r in all_res:
            print(f"  Res {r.id}: estado={r.estado}, checkin={r.fecha_checkin}, checkout={r.fecha_checkout}")
    else:
        print(f"✅ {len(reservations)} RESERVATIONS FOUND")
    
    db.close()

if __name__ == "__main__":
    main()
