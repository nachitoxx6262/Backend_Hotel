"""
iCal Export — Genera feeds .ics por habitación para sincronización con OTAs
(Booking.com, Airbnb, Expedia, etc.)

Endpoint público con token de sola lectura para que las OTAs consuman el feed.
"""
from datetime import datetime, date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database.conexion import get_db
from models.core import Room, Reservation, ReservationRoom, Stay, StayRoomOccupancy, EmpresaUsuario
from utils.dependencies import get_current_user
from utils.logging_utils import log_event
from utils.datetime_utils import utcnow

router = APIRouter(prefix="/api/calendar", tags=["iCal Export"])


def _build_ical(events: list, hotel_nombre: str, room_numero: str) -> bytes:
    """Construye el contenido del feed iCal."""
    try:
        from icalendar import Calendar, Event, vText, vDatetime
        import uuid

        cal = Calendar()
        cal.add("prodid", f"-//{hotel_nombre}//Hotel PMS//ES")
        cal.add("version", "2.0")
        cal.add("calscale", "GREGORIAN")
        cal.add("method", "PUBLISH")
        cal.add("x-wr-calname", f"{hotel_nombre} — Hab. {room_numero}")
        cal.add("x-wr-timezone", "America/Argentina/Buenos_Aires")

        for ev in events:
            event = Event()
            event.add("uid", str(uuid.uuid4()))
            event.add("summary", ev["summary"])
            event.add("dtstart", ev["start"])
            event.add("dtend", ev["end"])
            event.add("dtstamp", utcnow())
            if ev.get("description"):
                event.add("description", vText(ev["description"]))
            event.add("status", "CONFIRMED")
            cal.add_component(event)

        return cal.to_ical()

    except ImportError:
        # Fallback manual si icalendar no está instalado
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            f"PRODID:-//{hotel_nombre}//Hotel PMS//ES",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            f"X-WR-CALNAME:{hotel_nombre} — Hab. {room_numero}",
        ]
        import uuid as _uuid
        for ev in events:
            start = ev["start"].strftime("%Y%m%d") if isinstance(ev["start"], date) else ev["start"].strftime("%Y%m%dT%H%M%SZ")
            end = ev["end"].strftime("%Y%m%d") if isinstance(ev["end"], date) else ev["end"].strftime("%Y%m%dT%H%M%SZ")
            lines += [
                "BEGIN:VEVENT",
                f"UID:{_uuid.uuid4()}",
                f"DTSTART;VALUE=DATE:{start}",
                f"DTEND;VALUE=DATE:{end}",
                f"SUMMARY:{ev['summary']}",
                f"DTSTAMP:{utcnow().strftime('%Y%m%dT%H%M%SZ')}",
                "STATUS:CONFIRMED",
                "END:VEVENT",
            ]
        lines.append("END:VCALENDAR")
        return "\r\n".join(lines).encode("utf-8")


@router.get("/rooms/{room_id}/export.ics")
def export_room_ical(
    room_id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Exporta el calendario de ocupación de una habitación en formato iCal (.ics).

    Cubre: 6 meses atrás + 12 meses futuros.
    Compatible con Booking.com, Airbnb, Expedia y cualquier cliente de calendario.
    """
    tenant_id = current_user.empresa_usuario_id
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Sin tenant asociado")

    room = db.query(Room).filter(
        Room.id == room_id,
        Room.empresa_usuario_id == tenant_id,
    ).first()
    if not room:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")

    empresa = db.query(EmpresaUsuario).filter_by(id=tenant_id).first()
    hotel_nombre = empresa.nombre_hotel if empresa else "Hotel"

    # Ventana: -6 meses / +12 meses
    hoy = utcnow().date()
    desde = hoy - timedelta(days=180)
    hasta = hoy + timedelta(days=365)

    events = []

    # --- Reservaciones confirmadas (sin stay aún) ---
    res_rooms = (
        db.query(ReservationRoom)
        .join(Reservation)
        .filter(
            ReservationRoom.room_id == room_id,
            Reservation.empresa_usuario_id == tenant_id,
            Reservation.estado.in_(["confirmada", "draft", "ocupada"]),
            Reservation.fecha_checkin >= desde,
            Reservation.fecha_checkin <= hasta,
        )
        .all()
    )

    for rr in res_rooms:
        res = rr.reservation
        nombre = ""
        if res.cliente:
            nombre = f"{res.cliente.nombre} {res.cliente.apellido}".strip()
        elif res.empresa:
            nombre = res.empresa.nombre or ""
        elif res.nombre_temporal:
            nombre = res.nombre_temporal

        events.append({
            "summary": f"RESERVA — {nombre or 'Huésped'}",
            "start": res.fecha_checkin,
            "end": res.fecha_checkout,
            "description": f"Reserva #{res.id} | {nombre}",
        })

    # --- Estadías activas / cerradas ---
    occupancies = (
        db.query(StayRoomOccupancy)
        .join(Stay)
        .filter(
            StayRoomOccupancy.room_id == room_id,
            Stay.empresa_usuario_id == tenant_id,
            Stay.estado.in_(["ocupada", "pendiente_checkout", "cerrada"]),
        )
        .all()
    )

    for occ in occupancies:
        stay = occ.stay
        if not stay.reservation:
            continue
        res = stay.reservation

        checkin = stay.checkin_real or res.fecha_checkin
        checkout = stay.checkout_real or res.fecha_checkout

        if isinstance(checkin, datetime):
            checkin = checkin.date()
        if isinstance(checkout, datetime):
            checkout = checkout.date()

        # Filtrar por ventana
        if checkout < desde or checkin > hasta:
            continue

        nombre = ""
        if res.cliente:
            nombre = f"{res.cliente.nombre} {res.cliente.apellido}".strip()
        elif res.empresa:
            nombre = res.empresa.nombre or ""
        elif res.nombre_temporal:
            nombre = res.nombre_temporal

        estado_label = "OCUPADA" if stay.estado != "cerrada" else "CHECKOUT"
        events.append({
            "summary": f"{estado_label} — {nombre or 'Huésped'}",
            "start": checkin,
            "end": checkout,
            "description": f"Stay #{stay.id} | Reserva #{res.id} | {nombre}",
        })

    ical_bytes = _build_ical(events, hotel_nombre, str(room.numero))

    log_event("ical", current_user.username, "iCal export", f"room_id={room_id} events={len(events)}")

    return Response(
        content=ical_bytes,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="room-{room.numero}-calendar.ics"',
            "Cache-Control": "no-cache",
        },
    )
