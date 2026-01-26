from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session
from models.core import Stay, HousekeepingTask

def generate_checkout_tasks(stay: Stay, db: Session) -> Optional[HousekeepingTask]:
    """
    Genera una tarea de limpieza de tipo 'checkout' al cerrar una estadía.
    Valida si ya existe una tarea para esta estadía para evitar duplicados.
    
    Args:
        stay: La estadía que se está cerrando.
        db: Sesión de base de datos.
        
    Returns:
        HousekeepingTask creado o None si ya existía.
    """
    
    # Check uniqueness by stay_id and task_type='checkout'
    existing_task = db.query(HousekeepingTask).filter(
        HousekeepingTask.stay_id == stay.id,
        HousekeepingTask.task_type == "checkout"
    ).first()
    
    if existing_task:
        # Ya existe, no hacemos nada (o podríamos reactivarla si estaba cancelada?)
        # Por seguridad e idempotencia, retornamos la existente sin cambios.
        return existing_task

    # Determine room_id from stay
    # Stay has occupancies. We usually clean all rooms involved?
    # In this simplified model, stay usually maps to one main room/occupancy for the task purpose,
    # or we iterate occupancies.
    # Current Stay model relates to Room via occupancy.
    # Let's assume the task is for the room currently occupied.
    
    # We iterate over occupancies to find the rooms. 
    # Usually a stay has one room, but might have moved. 
    # Valid logic: Create task for the last room occupied (or all active occupancies?).
    # Stay.occupancies links StayRoomOccupancy.
    
    if not stay.occupancies:
        # Fallback if no data, logic error
        return None

    # Get the latest or main room. 
    # Assuming one room per stay for now or generating for all rooms involved in "checkout"
    # Logic: Generate task for unique rooms in occupancies that are "current" or just simply all distinct rooms?
    # A checkout implies leaving the room. The room needs cleaning.
    # If a stay involved moving rooms, the previous room should have had a "daily" or "move" clean, 
    # but let's stick to the last room or unique active rooms.
    
    target_rooms = set()
    for occ in stay.occupancies:
        target_rooms.add(occ.room_id)
        
    created_tasks = []
    
    for room_id in target_rooms:
         # Double check if we already made a task for this room + stay + type (though the query above was stay-wide)
         # The constraint `uq_hk_task_checkout_stay` is UNIQUE(stay_id) WHERE task_type='checkout'.
         # This implies DB only allows ONE checkout task per stay, regardless of room count.
         # LIMITATION: If stay spans multiple rooms simultaneously (unlikely in this model) or sequential, 
         # we can only attach ONE task to the stay_id.
         # FIX: We should probably create one task linked to stay_id.
         # If multiple rooms, the model constraint might be too strict if we wanted one task per room.
         # BUT, `HousekeepingTask` has `room_id` nullable=False.
         # So we MUST pick a room.
         
         # Given the constraint, we pick the last occupancy's room.
         
         pass

    # Re-evaluating constraint:
    # Index("uq_hk_task_checkout_stay", "stay_id", unique=True, postgresql_where=text("task_type = 'checkout'"))
    # This means exactly ONE checkout task per stay. 
    # So we should pick the LAST room occupied (the one being checked out from).
    
    last_occupancy = sorted(stay.occupancies, key=lambda x: x.desde)[-1]
    room_id = last_occupancy.room_id
    
    new_task = HousekeepingTask(
        room_id=room_id,
        stay_id=stay.id,
        reservation_id=stay.reservation_id,
        task_date=date.today(), # Checkout cleaning is for TODAY
        task_type="checkout",
        status="pending",
        priority="alta",
        meta={"source": "auto_checkout", "checkout_time": datetime.now().isoformat()}
    )
    
    db.add(new_task)
    # We don't commit here, let the caller transaction handle it.
    
    return new_task
