"""
Archivo de inicialización del paquete models.
Expone todas las clases de los diferentes archivos para que
SQLAlchemy (Base.metadata) las detecte al importar 'models'.
"""

# 1. Autenticación y Roles (desde rol.py)
from .rol import (
    Rol,
    Permiso,
    RolPermiso,
    UsuarioRol
)

# 2. Usuarios (desde usuario.py)
from .usuario import Usuario

# 3. Productos y Servicios (desde servicios.py)
from .servicios import ProductoServicio

# 4. Core del Hotel (desde models.py)
# Incluye: Empresas, Clientes, Habitaciones, Reservas, Estadías, Housekeeping, Auditoría
from .core import (
    Empresa,
    Cliente,
    RoomType,
    Room,
    RatePlan,
    DailyRate,
    Reservation,
    ReservationRoom,
    ReservationGuest,
    Stay,
    StayRoomOccupancy,
    StayCharge,
    StayPayment,
    HKTemplate,
    HKCycle,
    HKIncident,
    HKLostItem,
    MaintenanceTicket,
    AuditEvent
)

# (Opcional) Define qué se exporta si alguien hace 'from models import *'
__all__ = [
    "Rol", "Permiso", "RolPermiso", "UsuarioRol",
    "Usuario",
    "ProductoServicio",
    "Empresa", "Cliente", "RoomType", "Room", "RatePlan", "DailyRate",
    "Reservation", "ReservationRoom", "ReservationGuest",
    "Stay", "StayRoomOccupancy", "StayCharge", "StayPayment",
    "HKTemplate", "HKCycle", "HKIncident", "HKLostItem",
    "MaintenanceTicket", "AuditEvent"
]