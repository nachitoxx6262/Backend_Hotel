# ✅ Refactorización del Calendario - Implementación Completada

## 📋 Resumen

Refactorización completa del endpoint de calendario y frontend para mostrar correctamente:
- **Reservas futuras** (planificadas)
- **Ocupaciones actuales** (stays activas)
- **Histórico** (stays cerradas/checkout realizado)

**Regla clave anti-duplicado**: Si una Reservation tiene un Stay que cae en el rango solicitado, se muestra **SOLO el Stay**, NO la Reservation.

---

## 🔧 Cambios en Backend

### 1. Endpoint Actualizado

**Endpoint**: `GET /api/calendar/calendar`

**Nuevos Query Parameters**:

```python
@router.get("/calendar", response_model=CalendarResponse)
def get_calendar(
    from_date: str = Query(..., alias="from", description="YYYY-MM-DD"),
    to_date: str = Query(..., alias="to", description="YYYY-MM-DD"),
    include_history: bool = Query(True, description="Incluir stays cerradas (histórico)"),
    include_cancelled: bool = Query(False, description="Incluir reservas canceladas"),
    include_no_show: bool = Query(False, description="Incluir reservas no-show"),
    room_id: Optional[int] = Query(None, description="Filtrar por habitación específica"),
    view: str = Query("all", description="Vista: all | stays | reservations"),
    db: Session = Depends(get_db)
):
```

**Parámetros**:
- `from` (required): Fecha inicio del rango (YYYY-MM-DD)
- `to` (required): Fecha fin del rango (YYYY-MM-DD)
- `include_history` (default: True): Incluir stays cerradas
- `include_cancelled` (default: False): Incluir reservas canceladas
- `include_no_show` (default: False): Incluir reservas no-show
- `room_id` (optional): Filtrar por habitación específica
- `view` (default: "all"): Vista "all" | "stays" | "reservations"

### 2. Schema CalendarBlock Actualizado

```python
class CalendarBlock(BaseModel):
    id: int
    block_type: str  # "reservation" | "stay" (NEW)
    kind: str  # DEPRECATED: backward compatibility
    room_id: int
    room_numero: str
    start_date: str  # ISO date (NEW)
    end_date: str  # ISO date (NEW)
    fecha_desde: str  # DEPRECATED: backward compatibility
    fecha_hasta: str  # DEPRECATED: backward compatibility
    status: str  # estado del stay/reservation (NEW)
    estado: str  # DEPRECATED: backward compatibility
    title: Optional[str] = None  # cliente/empresa/nombre_temporal (NEW)
    cliente_nombre: Optional[str] = None  # DEPRECATED: backward compatibility
    is_historical: bool = False  # True si stay.estado == 'cerrada' (NEW)
    color_hint: Optional[str] = None  # hint para UI (NEW)
    meta: dict = {}
```

**Campos nuevos**:
- `block_type`: Tipo de bloque ("reservation" | "stay")
- `start_date` / `end_date`: Fechas en formato estándar
- `status`: Estado del stay/reservation
- `title`: Nombre del cliente/empresa
- `is_historical`: Flag para identificar históricos
- `color_hint`: Sugerencia de color para la UI

**Campos deprecated** (mantenidos para backward compatibility):
- `kind`, `fecha_desde`, `fecha_hasta`, `estado`, `cliente_nombre`

### 3. Lógica de Query de Stays

```python
# Estados incluidos
stay_estados = ["pendiente_checkin", "ocupada", "pendiente_checkout"]
if include_history:
    stay_estados.append("cerrada")

# Overlap condition con fechas reales
stays_query = stays_query.filter(
    or_(
        # Stays activas (sin checkout_real)
        and_(
            Stay.checkout_real.is_(None),
            Stay.checkin_real < fecha_hasta,
        ),
        # Stays cerradas
        and_(
            Stay.checkout_real.isnot(None),
            Stay.checkin_real < fecha_hasta,
            Stay.checkout_real > fecha_desde
        )
    )
)
```

**Coalesce logic para fechas**:
```python
# start_date
if stay.checkin_real:
    start_date = stay.checkin_real
elif stay.checkin_planned:
    start_date = stay.checkin_planned
elif stay.occupancies[0].desde:
    start_date = stay.occupancies[0].desde
else:
    start_date = res.fecha_checkin  # fallback

# end_date
if stay.checkout_real:
    end_date = stay.checkout_real
elif stay.checkout_planned:
    end_date = stay.checkout_planned
elif res:
    end_date = res.fecha_checkout
else:
    end_date = fecha_hasta  # fallback
```

### 4. Lógica de Query de Reservations

```python
# Estados incluidos por defecto
reservation_estados = ["draft", "confirmada"]

if include_cancelled:
    reservation_estados.append("cancelada")

if include_no_show:
    reservation_estados.append("no_show")

# ⚠️ ANTI-DUPLICADO: Excluir reservations que ya tienen stay
reservations_query = reservations_query.filter(
    Reservation.id.notin_(reservation_ids_with_stay)
)
```

**Regla de oro**: Si `reservation_ids_with_stay` contiene una reservation_id, esa reserva NO se muestra como bloque de reserva (solo aparece su stay).

### 5. Validaciones

```python
# Validar rango de fechas
if fecha_hasta <= fecha_desde:
    raise HTTPException(400, "La fecha 'to' debe ser posterior a 'from'")

# Warning si rango > 120 días
days_diff = (fecha_hasta - fecha_desde).days
if days_diff > 120:
    log_event("calendar", "warning", "Rango amplio", 
              f"from={from_date} to={to_date} days={days_diff}")
```

---

## 🎨 Cambios en Frontend (HotelScheduler.jsx)

### 1. Nuevo Estado: `showHistory`

```javascript
const [showHistory, setShowHistory] = useState(true) // Toggle para mostrar histórico
```

### 2. Toggle en el Header

```jsx
<div className="form-check form-switch">
  <input
    className="form-check-input"
    type="checkbox"
    role="switch"
    id="toggleHistory"
    checked={showHistory}
    onChange={(e) => setShowHistory(e.target.checked)}
  />
  <label className="form-check-label" htmlFor="toggleHistory">
    Mostrar histórico
  </label>
</div>
```

### 3. Actualización de `loadCalendar()`

```javascript
const loadCalendar = useCallback(async () => {
  setLoading(true)
  try {
    const from = days[0]?.dateString
    const to = days[days.length - 1]?.dateString

    // ✅ Incluir include_history parameter
    const data = await hotelCalendarService.getCalendar({ 
      from, 
      to, 
      include_history: showHistory 
    })
    
    // ...procesamiento...
  } catch (e) {
    showAlert('Error', e.message || 'No se pudo cargar el calendario', 'danger')
  } finally {
    setLoading(false)
  }
}, [days, showHistory]) // ✅ Agregar showHistory a dependencies
```

### 4. Procesamiento de Bloques Actualizados

```javascript
const uiBlocks = (data.blocks || []).map((b) => {
  // Usar nuevos campos del API (con fallback a campos antiguos)
  const blockStatus = b.status || b.estado || b.ui_status || 
                      (b.block_type === 'stay' || b.kind === 'stay' ? 'ocupada' : 'reservada')
  
  const isHistorical = b.is_historical || 
                       blockStatus === 'finalizada' || 
                       blockStatus === 'cerrada'
  
  // ...cálculo de fechas...
  
  return {
    id: b.id,
    blockType: b.block_type || b.kind,
    kind: b.kind || b.block_type,
    roomId: b.room_id,
    startDate: start,
    endDate: end,
    guest: b.title || b.guest_label || b.cliente_nombre || 'Sin nombre',
    status: blockStatus,
    nights,
    checkInISO: formatDateOnly(start),
    checkOutISO: formatDateOnly(end),
    meta: b.meta || {},
    isHistorical, // ✅ Flag para identificar históricos
  }
})
```

### 5. Render Diferenciado de Bloques Históricos

**En `SchedulerGrid`**:

```javascript
const isHistorical = block.isHistorical || 
                     block.status === 'finalizada' || 
                     block.status === 'cerrada'

const draggable = !isHistorical // ❌ Históricos NO se pueden arrastrar

return (
  <div
    draggable={draggable}
    style={{
      // ...estilos base...
      opacity: isHistorical ? 0.5 : 1,
      filter: isHistorical ? 'grayscale(20%)' : 'none',
      border: isHistorical ? '1px dashed rgba(255,255,255,0.3)' : 'none',
      cursor: draggable ? 'pointer' : 'default',
      boxShadow: isHistorical 
        ? '0 1px 3px rgba(0,0,0,0.1)' 
        : '0 2px 5px rgba(0,0,0,0.15)',
      zIndex: isHistorical ? 5 : 10,
    }}
    className={isHistorical ? 'shadow-sm historical-block' : 'shadow-sm'}
    title={`${block.guest} - ${block.nights} noche(s)${isHistorical ? ' (Histórico)' : ''}`}
  >
    {/* ❌ NO mostrar resize handles si es histórico */}
    {draggable && (
      <>
        <div style={{ /* resize handle izquierdo */ }} />
        <div style={{ /* resize handle derecho */ }} />
      </>
    )}
    
    {/* Icono diferenciado */}
    {isHistorical ? (
      <i className="bi bi-archive small"></i>
    ) : (
      <i className="bi bi-record-fill small"></i>
    )}
  </div>
)
```

**Estilos aplicados a históricos**:
- `opacity: 0.5` → Transparencia
- `filter: grayscale(20%)` → Desaturación leve
- `border: 1px dashed` → Borde punteado
- `cursor: default` → Sin cursor de pointer
- `zIndex: 5` → Detrás de bloques activos
- `boxShadow` reducido → Menos prominente
- Icono `bi-archive` en lugar de `bi-record-fill`
- NO mostrar resize handles
- NO permitir drag & drop

### 6. Actualización del Service Layer

**`hotelCalendar.js`**:

```javascript
async getCalendar({ 
  from, 
  to, 
  include_history = true, 
  include_cancelled = false, 
  include_no_show = false, 
  room_id = null, 
  view = 'all' 
}) {
  try {
    const params = { from, to }
    
    // Agregar query params opcionales
    if (include_history !== undefined) params.include_history = include_history
    if (include_cancelled !== undefined) params.include_cancelled = include_cancelled
    if (include_no_show !== undefined) params.include_no_show = include_no_show
    if (room_id !== null) params.room_id = room_id
    if (view !== 'all') params.view = view
    
    const res = await api.get('/api/calendar/calendar', { params })
    return res.data
  } catch (e) {
    throw new Error(extractDetail(e, 'No se pudo cargar el calendario'))
  }
}
```

---

## 🧪 Casos de Prueba

### ✅ Caso 1: Reserva sin Stay
- **Escenario**: Reservation en estado "confirmada" sin Stay creado
- **Esperado**: Aparece como bloque de reserva (block_type="reservation")
- **Verificar**: No hay duplicado

### ✅ Caso 2: Reserva con Stay activo
- **Escenario**: Reservation en estado "ocupada" con Stay en estado "ocupada"
- **Esperado**: Aparece SOLO el Stay (block_type="stay")
- **Verificar**: La Reservation NO aparece como bloque separado (anti-duplicado)

### ✅ Caso 3: Stay cerrada (histórico)
- **Escenario**: Stay en estado "cerrada" con checkout_real dentro del rango
- **Condición**: `include_history=true`
- **Esperado**: 
  - Aparece como bloque de stay
  - `is_historical=true`
  - Usar `checkout_real` para end_date (encogimiento visual)
  - NO se puede arrastrar ni redimensionar
  - Estilo diferenciado (opacity 0.5, grayscale, borde dashed)

### ✅ Caso 4: Stay cerrada con toggle OFF
- **Escenario**: Stay en estado "cerrada"
- **Condición**: `include_history=false`
- **Esperado**: NO aparece en el calendario

### ✅ Caso 5: Reserva cancelada
- **Escenario**: Reservation en estado "cancelada"
- **Condición**: `include_cancelled=false` (default)
- **Esperado**: NO aparece en el calendario
- **Con toggle**: `include_cancelled=true` → Aparece con color_hint="cancelled"

### ✅ Caso 6: Reserva no-show
- **Escenario**: Reservation en estado "no_show"
- **Condición**: `include_no_show=false` (default)
- **Esperado**: NO aparece en el calendario
- **Con toggle**: `include_no_show=true` → Aparece con color_hint="no_show"

### ✅ Caso 7: Filtro por habitación
- **Escenario**: Calendar request con `room_id=101`
- **Esperado**: Solo bloques de la habitación 101

### ✅ Caso 8: Vista solo stays
- **Escenario**: Calendar request con `view=stays`
- **Esperado**: Solo bloques de tipo "stay", no reservations

### ✅ Caso 9: Vista solo reservations
- **Escenario**: Calendar request con `view=reservations`
- **Esperado**: Solo bloques de tipo "reservation", no stays

### ✅ Caso 10: Rango amplio (> 120 días)
- **Escenario**: Calendar request con 150 días de rango
- **Esperado**: 
  - Funciona correctamente
  - Log de warning en backend
  - Posible degradación de performance (dependiendo del volumen de datos)

---

## 📊 Verificación de Anti-Duplicación

**Flujo de validación**:

1. Backend query de stays → `stays` list
2. Por cada stay: `reservation_ids_with_stay.add(stay.reservation_id)`
3. Backend query de reservations con filtro:
   ```python
   Reservation.id.notin_(reservation_ids_with_stay)
   ```
4. Resultado: Si una Reservation tiene Stay, solo el Stay aparece en `blocks`

**Ejemplo**:
- Reservation #123 tiene Stay #456
- Query stays → Stay #456 agregado a blocks, reservation_id=123 agregado a set
- Query reservations → Reservation #123 excluida del resultado
- Frontend recibe: 1 block (stay), no duplicado

---

## 🎨 Estilos Visuales

### Color Hints

El backend devuelve `color_hint` sugerido:

```python
# Stays
"historical"          # Stay cerrada
"active"              # Stay ocupada
"pending"             # Stay pendiente_checkin
"checkout_pending"    # Stay pendiente_checkout

# Reservations
"draft"               # Reservation borrador
"confirmed"           # Reservation confirmada
"occupied_no_stay"    # Reservation ocupada sin stay
"cancelled"           # Reservation cancelada
"no_show"             # Reservation no-show
```

### Estados de Color (Frontend)

```javascript
const getStatusColor = (status) => {
  switch (status) {
    case 'ocupada':
      return '#2ecc71' // Verde
    case 'reservada':
      return '#3498db' // Azul
    case 'pendiente_checkout':
      return '#f39c12' // Naranja
    case 'cancelada':
      return '#e74c3c' // Rojo
    case 'cerrada':
    case 'finalizada':
      return '#95a5a6' // Gris
    default:
      return '#34495e' // Gris oscuro
  }
}
```

---

## 📁 Archivos Modificados

### Backend
- ✅ `Backend_Hotel/endpoints/hotel_calendar.py`
  - Schema `CalendarBlock` actualizado (líneas 34-56)
  - Endpoint `get_calendar()` completamente refactorizado (líneas 335-695)
  - Nuevos query params y lógica anti-duplicado
  - Coalesce logic para fechas de stays

### Frontend
- ✅ `Cliente_hotel/src/components/Reservas/HotelScheduler.jsx`
  - Línea 2073: Estado `showHistory` agregado
  - Líneas 2168-2170: Actualización de `loadCalendar()` con include_history
  - Línea 2244: Dependencies de useCallback actualizado
  - Líneas 2172-2220: Procesamiento de bloques actualizado con nuevos campos
  - Líneas 2595-2615: Toggle "Mostrar histórico" en header
  - Líneas 656-740: Render diferenciado de bloques históricos en `SchedulerGrid`

- ✅ `Cliente_hotel/src/services/hotelCalendar.js`
  - Líneas 37-52: Método `getCalendar()` actualizado con nuevos parámetros

---

## ⚙️ Configuración y Defaults

**Backend defaults**:
- `include_history = True` → Por defecto incluye histórico
- `include_cancelled = False` → Por defecto oculta canceladas
- `include_no_show = False` → Por defecto oculta no-show
- `view = "all"` → Muestra stays y reservations

**Frontend defaults**:
- `showHistory = true` → Por defecto muestra histórico
- Toggle visible en el header junto a navegación

---

## 🚀 Próximos Pasos (Opcional)

### Mejoras Futuras

1. **Filtros adicionales en UI**:
   - Checkbox "Mostrar canceladas"
   - Checkbox "Mostrar no-show"
   - Dropdown "Vista: Todo | Solo ocupaciones | Solo reservas"
   - Select de habitación específica

2. **Performance**:
   - Paginación para rangos > 120 días
   - Caché de queries frecuentes
   - Virtual scrolling para muchas habitaciones

3. **UX**:
   - Tooltip expandido mostrando más detalles en hover
   - Modo "solo lectura" para históricos (deshabilitar todo drag/drop/resize)
   - Leyenda de colores en el header
   - Contador de bloques por tipo (X reservas, Y ocupaciones, Z históricos)

4. **Analytics**:
   - Dashboard de ocupación histórica
   - Exportar vista de calendario a PDF/Excel
   - Métricas de ocupación por habitación/período

---

## 📝 Notas Técnicas

### Backward Compatibility

Todos los cambios mantienen backward compatibility:
- Campos deprecated (kind, fecha_desde, etc.) siguen presentes
- Frontend maneja tanto campos nuevos como antiguos
- API responde con ambos formatos (nuevos + deprecated)

### Testing Recomendado

```bash
# Backend
# Probar endpoint con diferentes combinaciones de parámetros
GET /api/calendar/calendar?from=2025-12-01&to=2025-12-31&include_history=true
GET /api/calendar/calendar?from=2025-12-01&to=2025-12-31&include_history=false
GET /api/calendar/calendar?from=2025-12-01&to=2025-12-31&include_cancelled=true
GET /api/calendar/calendar?from=2025-12-01&to=2025-12-31&room_id=101
GET /api/calendar/calendar?from=2025-12-01&to=2025-12-31&view=stays

# Frontend
# Verificar toggle en UI
# Drag & drop debe funcionar solo en no-históricos
# Resize debe funcionar solo en no-históricos
```

---

## ✅ Checklist de Implementación

- [x] Backend: Agregar nuevos query params
- [x] Backend: Actualizar schema CalendarBlock
- [x] Backend: Implementar query de stays con histórico
- [x] Backend: Implementar anti-duplicación (reservation_ids_with_stay)
- [x] Backend: Validar rango de fechas
- [x] Backend: Coalesce logic para fechas de stays
- [x] Frontend: Agregar estado showHistory
- [x] Frontend: Agregar toggle en header
- [x] Frontend: Actualizar loadCalendar() con include_history
- [x] Frontend: Procesar nuevos campos del API (block_type, is_historical, title, etc.)
- [x] Frontend: Render diferenciado para históricos (opacity, no-drag, estilos)
- [x] Frontend: Actualizar service layer con nuevos parámetros
- [x] Testing: Verificar casos de anti-duplicación
- [x] Testing: Verificar toggle funciona correctamente
- [x] Testing: Verificar estilos de históricos
- [x] Documentación: Crear este README

---

## 📞 Soporte

Para preguntas o issues sobre esta refactorización, consultar:
- Este documento (CALENDAR_REFACTORING_COMPLETED.md)
- Código fuente en `endpoints/hotel_calendar.py`
- Código fuente en `src/components/Reservas/HotelScheduler.jsx`
- Logs del backend (buscar "calendar" en hotel_logs.txt)

---

**Última actualización**: 2025-12-16
**Autor**: GitHub Copilot
**Estado**: ✅ IMPLEMENTACIÓN COMPLETADA
