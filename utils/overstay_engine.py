from datetime import datetime, time
from typing import Optional, List, Dict
from models.core import Stay, RoomType, HotelSettings, Reservation
from utils.timezone import get_hotel_now, to_hotel_time

# Status constants
OVERSTAY_DETECTED = "OVERSTAY_DETECTED"
NORMAL = "NORMAL"

def get_effective_cutoff(stay: Stay, settings: HotelSettings) -> time:
    """
    Determine the effective checkout time (cutoff) for a stay.
    Priority:
    1. Reservation/Stay Override (Not yet implemented in DB, placeholder)
    2. Room Type Policy (Not yet implemented in DB, placeholder)
    3. Hotel Global Settings (Default)
    """
    # 1. Override Check (Future feature)
    # if stay.reservation and stay.reservation.cutoff_override: ...

    # 3. Global Default
    # Default to 12:00 if settings missing
    hour = settings.checkout_hour if settings else 12
    minute = settings.checkout_minute if settings else 0
    
    return time(hour, minute)

def check_overstay_status(stay: Stay, settings: HotelSettings) -> Dict[str, any]:
    """
    Evaluates if a Stay is in OVERSTAY state.
    
    Rule:
    - Stay is active ('ocupada' or 'pendiente_checkout')
    - Today is the planned date of checkout (or past it)
    - Current Hotel Time >= Cutoff Time
    - No actual checkout performed (checkout_real is None)
    
    Returns:
        {
            "status": "OVERSTAY_DETECTED" | "NORMAL",
            "flags": ["overstay_detected", "critical_overstay"],
            "meta": { "cutoff": "11:00", "minutes_past": 45 }
        }
    """
    
    # Prerequisite: Stay must be active
    if not stay.is_active() or stay.checkout_real:
        return {"status": NORMAL, "flags": [], "meta": {}}

    hotel_now = get_hotel_now()
    today_date = hotel_now.date()
    # Assuming stay.fecha_checkout is a Date object (planned checkout)
    # We need to access reservation or stay dates.
    # From models, Stay doesn't store planned dates directly (it links to reservation or occupancy)
    # But usually API serializes it. Let's look at Reservation linked to Stay.
    
    # Stay SHOULD have planned dates or derive from Reservation.
    # In `hotel_calendar.py`, we assumed `stay.fecha_checkout`. 
    # Checking `models/core.py`, Stay DOES NOT have `fecha_checkout`.
    # It has `occupancies`. We need the active occupancy end date OR reservation end date.
    
    planned_checkout_date = None
    
    # Strategy 1: Active Occupancy
    active_occ = stay.get_active_occupancy()
    if active_occ and active_occ.hasta:
        planned_checkout_date = active_occ.hasta.date()
    elif stay.reservation:
        planned_checkout_date = stay.reservation.fecha_checkout
    
    if not planned_checkout_date:
        # Fallback/Error state
        return {"status": NORMAL, "flags": [], "meta": {}}

    # Check Logic
    
    # Case A: Past Date (Critical)
    # If today > planned_checkout_date, it's a multi-day overstay
    if today_date > planned_checkout_date:
        return {
            "status": OVERSTAY_DETECTED,
            "flags": ["overstay_detected", "critical_overstay"],
            "meta": {
                "reason": "past_date",
                "days_over": (today_date - planned_checkout_date).days
            }
        }
        
    # Case B: Same Date (Time Check)
    if today_date == planned_checkout_date:
        cutoff_time = get_effective_cutoff(stay, settings)
        current_time = hotel_now.time()
        
        if current_time >= cutoff_time:
            # Calculate minutes past
            cutoff_dt = datetime.combine(today_date, cutoff_time)
            # Make timezone aware context? hotel_now is aware. 
            # datetime.combine makes naive.
            # We compare time objects directly since they are both correctly derived?
            # Yes, if hotel_now is in Hotel TZ.
            
            return {
                "status": OVERSTAY_DETECTED,
                "flags": ["overstay_detected"],
                "meta": {
                    "reason": "time_cutoff",
                    "cutoff": cutoff_time.strftime("%H:%M")
                }
            }

    return {"status": NORMAL, "flags": [], "meta": {}}
