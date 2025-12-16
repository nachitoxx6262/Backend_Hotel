# Migración: cancelled_by a INTEGER

## Fecha: 2025-12-16

## Cambio Realizado

Se actualizó el campo `cancelled_by` de la tabla `reservations` de `VARCHAR(50)` a `INTEGER` para guardar el **ID del usuario autenticado** en lugar del username.

## Archivos Modificados

### Backend

1. **models/core.py**
   - `cancelled_by` cambiado de `String(50)` a `Integer`
   - Ahora guarda el ID del usuario que canceló la reserva

2. **endpoints/hotel_calendar.py**
   - Import agregado: `get_current_user_optional`
   - Schema `CancelReservationRequest` ya no recibe `cancelled_by` del frontend
   - Endpoint `cancel_reservation()` ahora es `async` y recibe `current_user`
   - Se guarda automáticamente `current_user.id` en `reservation.cancelled_by`
   - Auditoría usa `current_user.username` o "sistema" como fallback

### Frontend

3. **services/hotelCalendar.js**
   - Método `cancelReservation()` ahora solo envía `reason`
   - Ya no envía `cancelled_by` (se maneja automáticamente en backend)

4. **components/Reservas/HotelScheduler.jsx**
   - Llamada actualizada para solo pasar `reason`

## Migración de Base de Datos

**IMPORTANTE**: Debes ejecutar manualmente el script SQL:

```bash
psql -U postgres -d hotel_db -f migrations/001_update_cancelled_by_to_integer.sql
```

O ejecutar desde pgAdmin/DBeaver el contenido del archivo:
- `Backend_Hotel/migrations/001_update_cancelled_by_to_integer.sql`

## Comportamiento Nuevo

### Con Usuario Autenticado

```python
# Usuario logueado: Juan Pérez (id=5)
# Frontend hace: POST /cancel con { reason: "Cliente canceló" }
# Backend guarda:
#   - cancelled_by = 5
#   - cancelled_at = 2025-12-16 10:30:00
#   - cancel_reason = "Cliente canceló"
# Auditoría: usuario = "juan.perez"
```

### Sin Usuario Autenticado

```python
# Usuario NO autenticado (current_user = None)
# Frontend hace: POST /cancel con { reason: "Cancelada automáticamente" }
# Backend guarda:
#   - cancelled_by = NULL
#   - cancelled_at = 2025-12-16 10:30:00
#   - cancel_reason = "Cancelada automáticamente"
# Auditoría: usuario = "sistema"
```

## Ventajas del Cambio

1. ✅ **Trazabilidad**: Ahora podemos hacer joins con la tabla `usuarios`
2. ✅ **Consistencia**: Todos los campos `*_by` usan IDs, no strings
3. ✅ **Integridad**: Si el usuario cambia su username, el historial no se pierde
4. ✅ **Seguridad**: El frontend no puede falsificar quién canceló

## Consultas Útiles

### Ver cancelaciones con información del usuario

```sql
SELECT 
  r.id,
  r.estado,
  r.cancel_reason,
  r.cancelled_at,
  u.username as cancelled_by_username,
  u.nombre as cancelled_by_nombre
FROM reservations r
LEFT JOIN usuarios u ON r.cancelled_by = u.id
WHERE r.estado = 'cancelada'
ORDER BY r.cancelled_at DESC;
```

### Contar cancelaciones por usuario

```sql
SELECT 
  u.username,
  COUNT(r.id) as total_cancelaciones
FROM usuarios u
LEFT JOIN reservations r ON r.cancelled_by = u.id AND r.estado = 'cancelada'
GROUP BY u.id, u.username
ORDER BY total_cancelaciones DESC;
```

## Testing

1. **Crear una reserva**
2. **Autenticarse como usuario**
3. **Cancelar la reserva** (click derecho → Cancelar)
4. **Verificar en BD**:
   ```sql
   SELECT id, estado, cancelled_by FROM reservations WHERE id = <reservation_id>;
   ```
   - Debe mostrar el **ID del usuario**, no el username

## Rollback (si es necesario)

Si necesitas revertir el cambio:

```sql
ALTER TABLE reservations ADD COLUMN cancelled_by_old VARCHAR(50);
UPDATE reservations SET cancelled_by_old = (SELECT username FROM usuarios WHERE id = cancelled_by) WHERE cancelled_by IS NOT NULL;
ALTER TABLE reservations DROP COLUMN cancelled_by;
ALTER TABLE reservations RENAME COLUMN cancelled_by_old TO cancelled_by;
```

Y revertir los cambios de código con git.
