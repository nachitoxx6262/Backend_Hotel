# Documentación de Relaciones ORM - Sistema Hotel

## 📋 Tabla de Contenidos
1. [Relaciones Multi-Tenant](#relaciones-multi-tenant)
2. [Relaciones Core (Reservas y Estadías)](#relaciones-core)
3. [Relaciones Financieras](#relaciones-financieras)
4. [Relaciones de Usuarios](#relaciones-de-usuarios)
5. [Relaciones de Configuración](#relaciones-de-configuración)
6. [Diagrama General](#diagrama-general)

---

## Relaciones Multi-Tenant

### 1. EmpresaUsuario (Tenant)
El núcleo del modelo multi-tenant. Representa cada hotel/empresa contratante.

```
EmpresaUsuario (1)
├── plan_tipo: PlanType (enum)
├── activa: bool
└── deleted: bool
```

**Relaciones Salientes:**
- `usuarios` (1 → M) → Usuario
  - Usuarios que trabajan en este hotel
  - ON DELETE CASCADE

- `clientes` (1 → M) → Cliente
  - Huéspedes/clientes del hotel
  - ON DELETE CASCADE

- `clientes_corporativos` (1 → M) → ClienteCorporativo
  - Empresas que reservan
  - ON DELETE CASCADE

- `habitaciones` (1 → M) → Room
  - Todas las habitaciones del hotel
  - ON DELETE CASCADE

- `reservas` (1 → M) → Reservation
  - Todas las reservas
  - ON DELETE CASCADE

- `stays` (1 → M) → Stay
  - Todas las estadías
  - ON DELETE CASCADE

- `subscription` (1 → 1) → Subscription
  - Plan de suscripción actual
  - uselist=False (relación única)

- `hotel_settings` (1 → 1) → HotelSettings
  - Configuraciones del hotel
  - uselist=False

---

## Relaciones Core (Reservas y Estadías)

### 2. Reservation (Reserva)
Contiene la planificación de una ocupación.

**Tabla:** `reservations`

```python
class Reservation(Base):
    empresa_usuario_id → EmpresaUsuario (1)
    cliente_id → Cliente (1, nullable) # Cliente directo o None
    empresa_id → ClienteCorporativo (1, nullable) # Empresa corporativa
    
    estado: enum ('draft', 'confirmada', 'ocupada', 'finalizada', 'cancelada', 'no_show')
    fecha_checkin: date
    fecha_checkout: date
```

**Relaciones Salientes:**
- `empresa_usuario` (M → 1) → EmpresaUsuario
- `cliente` (M → 1) → Cliente (nullable)
- `empresa` (M → 1) → ClienteCorporativo (nullable)
- `rooms` (1 → M) → ReservationRoom
  - Qué habitaciones se reservaron
- `guests` (1 → M) → ReservationGuest
  - Huéspedes en la reserva (puede haber múltiples)

**Relaciones Entrantes:**
- `stay` ← Stay (1 ← 1)
  - Cada reserva puede tener 1 estadía asociada

---

### 3. ReservationRoom (Tabla de Unión)
Relación muchos-a-muchos entre Reservations y Rooms.

```
ReservationRoom
├── reservation_id → Reservation
├── room_id → Room
└── metadatos adicionales (notas, etc)
```

**Permite:** Una reserva puede ocupar múltiples habitaciones

---

### 4. ReservationGuest (Huéspedes de Reserva)
Lista de huéspedes que aparecen en cada reserva.

```
ReservationGuest
├── reservation_id → Reservation
├── nombre, apellido
├── documento, tipo_documento
├── rol: enum ('principal', 'acompañante')
└── email, telefono (opcional)
```

**Propósito:** Datos de quiénes vienen en la reserva

---

### 5. Stay (Estadía)
Registro de una ocupación actual/pasada.

**Tabla:** `stays`

```python
class Stay(Base):
    reservation_id → Reservation (1)
    empresa_usuario_id → EmpresaUsuario (1)
    
    estado: enum ('pendiente_checkin', 'ocupada', 'pendiente_checkout', 'cerrada')
    checkin_real: datetime (nullable)
    checkout_real: datetime (nullable)
```

**Relaciones Salientes:**
- `reservation` (M → 1) → Reservation
- `empresa_usuario` (M → 1) → EmpresaUsuario
- `occupancies` (1 → M) → StayRoomOccupancy
  - Qué habitaciones ocupa la estadía
- `charges` (1 → M) → StayCharge
  - Cargos durante la estadía
- `payments` (1 → M) → StayPayment
  - Pagos realizados

**Relaciones Entrantes:**
- Cada Reservation → 1 Stay (creado al hacer check-in)

---

### 6. StayRoomOccupancy (Ocupación de Habitación)
Define qué habitación se usa en cada estadía y cuándo.

```
StayRoomOccupancy
├── stay_id → Stay (M)
├── room_id → Room (M)
├── desde: date
├── hasta: date (nullable si checkout_real es null)
└── motivo: str (opcional)
```

**Permite:** Una estadía puede ocupar múltiples habitaciones durante su duración

---

## Relaciones Financieras

### 7. StayCharge (Cargo a Estadía)
Representa cargos (extras, servicios, penalizaciones) a una estadía.

```
StayCharge
├── stay_id → Stay (M)
├── tipo: enum ('alojamiento', 'consumo', 'servicio', 'penalizacion')
├── descripcion: str
├── cantidad: float
├── monto_unitario: decimal
└── monto_total: decimal
```

**Propósito:** Desglose de todo lo que se cobra

---

### 8. StayPayment (Pago de Estadía)
Registro de pagos recibidos.

```
StayPayment
├── stay_id → Stay (M)
├── monto: decimal
├── metodo: enum ('efectivo', 'transferencia', 'tarjeta', 'nota_credito')
├── es_reverso: bool # True si es devolución
└── timestamp: datetime
```

**Propósito:** Auditar quién pagó qué y cuándo

---

## Relaciones de Usuarios

### 9. Usuario
Representes cada persona que accede al sistema.

```python
class Usuario(Base):
    empresa_usuario_id → EmpresaUsuario (1)
    rol_id → Rol (1, nullable)
    
    email: unique per empresa
    password_hash: bcrypt
    estado: enum ('activo', 'inactivo', 'suspendido')
    bloqueado_hasta: datetime (nullable) # Rate limiting
```

**Relaciones Salientes:**
- `empresa_usuario` (M → 1) → EmpresaUsuario
- `rol` (M → 1) → Rol (nullable)

---

### 10. Rol (Rol de Usuario)
Define permisos de acceso.

```
Rol
├── empresa_usuario_id → EmpresaUsuario (1)
├── nombre: str
├── permisos: JSONB (lista de permisos)
└── descripcion: str
```

**Relaciones Entrantes:**
- `usuarios` ← Usuario (1 ← M)

---

## Relaciones de Configuración

### 11. HotelSettings
Configuración específica del hotel.

```
HotelSettings
├── empresa_usuario_id → EmpresaUsuario (1, unique)
├── checkout_hour, checkout_minute: int
├── cleaning_start_hour, cleaning_end_hour: int
├── auto_extend_stays: bool
├── timezone: str
└── overstay_price: decimal (nullable)
```

**Propósito:** Una sola configuración por hotel

---

### 12. DailyRate (Tarifa Diaria)
Tarifas especiales por día (para cada tipo de habitación).

```
DailyRate
├── empresa_usuario_id → EmpresaUsuario (1)
├── room_id → Room (1, nullable) # O room_type_id
├── fecha: date
├── precio: decimal
└── notas: str (opcional)
```

**Propósito:** Permitir tarifas variables (temporada alta/baja, promociones)

---

### 13. Room (Habitación)
Cada habitación física del hotel.

```python
class Room(Base):
    empresa_usuario_id → EmpresaUsuario (1)
    tipo_id → RoomType (1)
    
    numero: str
    estado_operativo: enum ('operativa', 'mantenimiento', 'no_disponible')
    activo: bool
```

**Relaciones Salientes:**
- `empresa_usuario` (M → 1) → EmpresaUsuario
- `tipo` (M → 1) → RoomType

**Relaciones Entrantes:**
- `occupancies` ← StayRoomOccupancy (1 ← M)
- `reservations` ← ReservationRoom (1 ← M)

---

### 14. RoomType (Tipo de Habitación)
Categoría de habitación (suite, standard, deluxe, etc).

```
RoomType
├── empresa_usuario_id → EmpresaUsuario (1)
├── nombre: str
├── descripcion: str
├── precio_base: decimal
└── capacidad: int
```

**Relaciones Entrantes:**
- `rooms` ← Room (1 ← M)

---

## Relaciones de Clientes

### 15. Cliente (Huésped Individual)
Datos de persona que se hospeda.

```python
class Cliente(Base):
    empresa_usuario_id → EmpresaUsuario (1)
    empresa_id → ClienteCorporativo (1, nullable) # Si viene de una empresa
    
    nombre, apellido: str
    tipo_documento, numero_documento: str (unique per empresa)
    email, telefono: str (opcional)
    blacklist: bool # Denegado en el hotel
```

**Relaciones Salientes:**
- `empresa_usuario` (M → 1) → EmpresaUsuario
- `cliente_corporativo` (M → 1) → ClienteCorporativo (nullable)

**Relaciones Entrantes:**
- `reservations` ← Reservation (1 ← M)

---

### 16. ClienteCorporativo (Empresa Contratante)
Empresas que traen huéspedes (ej: viajes de negocios).

```
ClienteCorporativo
├── empresa_usuario_id → EmpresaUsuario (1)
├── nombre: str
├── cuit: str (único per empresa)
├── contacto_nombre, contacto_email, contacto_telefono: str
└── activo: bool
```

**Relaciones Entrantes:**
- `clientes` ← Cliente (1 ← M)
- `reservations` ← Reservation (1 ← M)

---

## Relaciones de Auditoría

### 17. AuditEvent (Evento de Auditoría)
Log de todas las acciones del sistema.

```
AuditEvent
├── empresa_usuario_id → EmpresaUsuario (1)
├── usuario_id: str (email del usuario)
├── accion: str (ej: 'checkin', 'cancelar_reserva')
├── entidad_tipo: str ('reservation', 'stay', etc)
├── entidad_id: int
└── timestamp: datetime
```

**Propósito:** Trazabilidad completa de todas las operaciones

---

### 18. HousekeepingTask (Tarea de Limpieza)
Tareas de housekeeping generadas automáticamente.

```
HousekeepingTask
├── empresa_usuario_id → EmpresaUsuario (1)
├── stay_id → Stay (1, nullable) # Puede no estar asociada
├── room_id → Room (1)
├── tipo: enum ('checkout_clean', 'turndown', 'urgent_clean')
├── estado: enum ('pendiente', 'en_progreso', 'completada')
└── created_at, completed_at: datetime
```

---

## Diagrama General

```
                    EmpresaUsuario (Tenant Root)
                            |
            __________________________________
            |              |              |
            ▼              ▼              ▼
        Usuario         Cliente      ClienteCorporativo
            |           /  |  \            |
            |          /   |   \           |
            ▼         ▼    ▼    ▼          |
           Rol    ReservationGuest         |
                        ▲                  |
                        |__________________|
                             |
                             ▼
                       Reservation
                         |      |
                         |      ▼
                         |   ReservationRoom
                         |      |
                         |      ▼
                         |    Room
                         |      |
                         |      ▼
                         |   RoomType
                         |
                         ▼
                        Stay
                         |
            _____________|_____________
            |             |             |
            ▼             ▼             ▼
    StayRoomOccupancy  StayCharge  StayPayment
            |
            ▼
          Room ──── DailyRate


    Servicios Transversales:
    ├── HotelSettings (Configuración)
    ├── AuditEvent (Auditoría)
    ├── HousekeepingTask (Housekeeping)
    └── Subscription (Suscripción)
```

---

## Reglas de Integridad

### ON DELETE CASCADE
- EmpresaUsuario → todos sus hijos
- Reservation → ReservationRoom, ReservationGuest
- Stay → StayRoomOccupancy, StayCharge, StayPayment

### Unicidad
- Usuario.email (por empresa)
- Cliente.numero_documento (por empresa)
- ClienteCorporativo.cuit (por empresa)
- Subscription (una por empresa)

### Validaciones
- checkout > checkin en Reservation
- occupied rooms en Stay → rooms en Reservation
- positive amounts en StayCharge/StayPayment
- estado transitions válidas (no todos los cambios son posibles)

---

## Notas para Desarrolladores

1. **Siempre filtrar por `empresa_usuario_id`** en queries
2. **Usar `joinedload()`** para evitar N+1 queries (ver optimización en high_priority_corrections.md)
3. **Transacciones ACID** para operaciones check-in/check-out
4. **Soft-deletes** para Cliente (usar `activo` flag)
5. **Audit Trail** - usar `log_event()` para cambios importantes

---

*Documento generado: 2026-02-04*
*Versión: 1.0 - Base de datos con timezone awareness*
