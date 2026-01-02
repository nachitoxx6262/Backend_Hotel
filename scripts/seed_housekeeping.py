import sys
from datetime import date, timedelta

from database.conexion import SessionLocal
from models.core import RoomType, Room, Reservation, Stay, HousekeepingTask


# Simple upsert helper

def get_or_create(db, model, defaults=None, **kwargs):
    defaults = defaults or {}
    instance = db.query(model).filter_by(**kwargs).first()
    if instance:
        changed = False
        for k, v in defaults.items():
            if getattr(instance, k) != v:
                setattr(instance, k, v)
                changed = True
        if changed:
            db.add(instance)
        return instance, False
    params = {**kwargs, **defaults}
    instance = model(**params)
    db.add(instance)
    return instance, True


def ensure_sample_data():
    db = SessionLocal()
    try:
        today = date.today()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)

        # Room type
        rt, _ = get_or_create(
            db,
            RoomType,
            nombre="Standard",
            defaults={"capacidad": 2, "precio_base": 100},
        )
        db.flush()  # ensure id is available

        # Rooms
        rooms = {}
        for num in ["101", "102", "201"]:
            room, _ = get_or_create(
                db,
                Room,
                numero=num,
                defaults={"room_type_id": rt.id, "estado_operativo": "disponible"},
            )
            rooms[num] = room
        db.flush()  # ensure room ids

        # One active reservation + stay for room 201 (checkout style)
        res, _ = get_or_create(
            db,
            Reservation,
            defaults={
                "fecha_checkin": yesterday,
                "fecha_checkout": tomorrow,
                "estado": "ocupada",
                "nombre_temporal": "Prueba HK",
            },
        )
        stay, _ = get_or_create(
            db,
            Stay,
            reservation_id=res.id,
            defaults={"estado": "pendiente_checkout"},
        )

        tasks = [
            # Daily tasks for today
            {
                "room": rooms["101"],
                "task_type": "daily",
                "status": "pending",
                "task_date": today,
                "meta": {"checklist": ["Cama", "Bano", "Pisos"]},
            },
            {
                "room": rooms["102"],
                "task_type": "daily",
                "status": "in_progress",
                "task_date": today,
                "meta": {"checklist": ["Cama", "Bano"], "suggested_time": "12:00"},
            },
            # Checkout pending
            {
                "room": rooms["201"],
                "task_type": "checkout",
                "status": "pending",
                "task_date": today,
                "stay": stay,
                "reservation": res,
                "meta": {"suggested_time": "11:00", "skip_reason": None},
            },
            # Done example for history toggle
            {
                "room": rooms["101"],
                "task_type": "daily",
                "status": "done",
                "task_date": yesterday,
                "meta": {"checklist": ["Cama", "Bano"]},
            },
        ]

        created = 0
        for payload in tasks:
            room = payload["room"]
            task_date = payload["task_date"]
            task_type = payload["task_type"]

            if task_type == "checkout" and payload.get("stay"):
                existing = db.query(HousekeepingTask).filter_by(
                    stay_id=payload.get("stay").id,
                    task_type="checkout",
                ).first()
            else:
                existing = db.query(HousekeepingTask).filter_by(
                    room_id=room.id,
                    task_date=task_date,
                    task_type=task_type,
                ).first()
            if existing:
                # Update status/meta if different
                changed = False
                for key in ["status", "meta", "stay", "reservation"]:
                    if key in payload:
                        val = payload[key]
                        if key in ["stay", "reservation"]:
                            col = f"{key}_id"
                            new_val = val.id if val else None
                            if getattr(existing, col) != new_val:
                                setattr(existing, col, new_val)
                                changed = True
                        else:
                            if getattr(existing, key) != val:
                                setattr(existing, key, val)
                                changed = True
                if changed:
                    db.add(existing)
            else:
                task = HousekeepingTask(
                    room_id=room.id,
                    stay_id=payload.get("stay").id if payload.get("stay") else None,
                    reservation_id=payload.get("reservation").id if payload.get("reservation") else None,
                    task_date=task_date,
                    task_type=task_type,
                    status=payload["status"],
                    meta=payload.get("meta"),
                )
                db.add(task)
                created += 1

        db.commit()
        print(f"Seed OK - created {created} tasks. Rooms: {list(rooms.keys())}")
    except Exception as e:
        db.rollback()
        print(f"Seed failed: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    ensure_sample_data()
