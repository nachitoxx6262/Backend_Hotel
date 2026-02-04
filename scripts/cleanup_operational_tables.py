"""
Limpia tablas operativas: habitaciones, tipos, reservas, stays, housekeeping y productos.
"""
from database.conexion import SessionLocal
from models.core import (
    RoomType,
    Room,
    Reservation,
    ReservationRoom,
    ReservationGuest,
    Stay,
    StayRoomOccupancy,
    StayCharge,
    StayPayment,
    HousekeepingTask,
)
from models.servicios import ProductoServicio


def main():
    session = SessionLocal()
    try:
        delete_order = [
            StayCharge,
            StayPayment,
            StayRoomOccupancy,
            HousekeepingTask,
            Stay,
            ReservationGuest,
            ReservationRoom,
            Reservation,
            Room,
            RoomType,
            ProductoServicio,
        ]

        deleted_counts = {}
        for model in delete_order:
            count = session.query(model).delete(synchronize_session=False)
            deleted_counts[model.__tablename__] = count

        session.commit()

        print("✅ Limpieza completa")
        for table, count in deleted_counts.items():
            print(f"- {table}: {count} registros eliminados")
    except Exception as exc:
        session.rollback()
        print(f"❌ Error al limpiar tablas: {exc}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
