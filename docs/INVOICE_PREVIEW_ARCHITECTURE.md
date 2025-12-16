# 🏗️ Invoice Preview - Arquitectura Técnica

## Diagrama de Flujo

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND REQUEST                             │
│  GET /api/calendar/stays/{stay_id}/invoice-preview                  │
│  Query: checkout_date?, nights_override?, include_items?             │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      1. VALIDACIÓN                                   │
│  ─ Stay existe?                                                      │
│  ─ checkout_date >= checkin_real?                                   │
│  ─ Stay cerrada? → readonly=true                                    │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 2. CARGA DE DATOS (DB)                               │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │ Stay (joinedload)                                        │       │
│  │  ├─ reservation                                          │       │
│  │  │   ├─ cliente                                          │       │
│  │  │   └─ empresa                                          │       │
│  │  ├─ occupancies                                          │       │
│  │  │   └─ room                                             │       │
│  │  │       └─ room_type                                    │       │
│  │  ├─ charges                                              │       │
│  │  └─ payments                                             │       │
│  └──────────────────────────────────────────────────────────┘       │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│               3. RESOLVER TARIFA (Prioridad)                         │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │ if stay.nightly_rate → use it (source="stay")           │       │
│  │ elif room_type.precio_base → use it (source="room_type")│       │
│  │ else → 0.0 (source="missing") ⚠️ WARNING                │       │
│  └──────────────────────────────────────────────────────────┘       │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│              4. CALCULAR NOCHES                                      │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │ planned = (checkout_planned - checkin_planned).days      │       │
│  │ calculated = (checkout_candidate - checkin_real).days    │       │
│  │ suggested = max(1, calculated)  ← Lógica de negocio      │       │
│  │ final = nights_override if override else suggested       │       │
│  └──────────────────────────────────────────────────────────┘       │
│                                                                      │
│  Warnings:                                                           │
│  ─ NIGHTS_OVERRIDE si se usó override                               │
│  ─ NIGHTS_DIFFER si calculated ≠ planned                            │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│            5. CONSTRUIR LÍNEAS (si include_items=true)               │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │ A. ALOJAMIENTO                                           │       │
│  │    line_type="room"                                      │       │
│  │    total = nightly_rate × final_nights                   │       │
│  │                                                           │       │
│  │ B. CARGOS/CONSUMOS                                       │       │
│  │    for charge in charges:                                │       │
│  │      if tipo not in ["discount", "fee"]:                 │       │
│  │        line_type="charge"                                │       │
│  │        total = charge.monto_total                        │       │
│  │        ⚠️ WARNING si total == 0                          │       │
│  │                                                           │       │
│  │ C. IMPUESTOS                                             │       │
│  │    C1. Impuestos explícitos (tipo="fee")                │       │
│  │        line_type="tax"                                   │       │
│  │    C2. IVA sobre alojamiento (21%)                       │       │
│  │        line_type="tax"                                   │       │
│  │        total = room_subtotal × 0.21                      │       │
│  │                                                           │       │
│  │ D. DESCUENTOS                                            │       │
│  │    for charge in charges where tipo="discount":          │       │
│  │      line_type="discount"                                │       │
│  │      total = -abs(charge.monto_total)                    │       │
│  │                                                           │       │
│  │ E. PAGOS                                                 │       │
│  │    for payment in payments:                              │       │
│  │      if not es_reverso:                                  │       │
│  │        line_type="payment"                               │       │
│  │        total = -payment.monto                            │       │
│  └──────────────────────────────────────────────────────────┘       │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    6. CALCULAR TOTALES                               │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │ room_subtotal = nightly_rate × final_nights              │       │
│  │ charges_total = Σ charges (excl. discount, fee)          │       │
│  │ taxes_total = IVA + Σ fee_charges                        │       │
│  │ discounts_total = Σ abs(discount_charges)                │       │
│  │ grand_total = room_subtotal + charges_total              │       │
│  │               + taxes_total - discounts_total            │       │
│  │ payments_total = Σ payments (non-reversed)               │       │
│  │ balance = grand_total - payments_total                   │       │
│  └──────────────────────────────────────────────────────────┘       │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   7. GENERAR WARNINGS                                │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │ MISSING_RATE → tarifa = 0                                │       │
│  │ NIGHTS_OVERRIDE → override aplicado                      │       │
│  │ NIGHTS_DIFFER → calculated ≠ planned                     │       │
│  │ BALANCE_DUE → balance > 0                                │       │
│  │ OVERPAYMENT → balance < 0                                │       │
│  │ PAYMENTS_EXCEED_TOTAL → payments > grand_total           │       │
│  │ UNPRICED_CHARGE → cargo con monto = 0                    │       │
│  └──────────────────────────────────────────────────────────┘       │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  8. CONSTRUIR RESPUESTA                              │
│  InvoicePreviewResponse {                                            │
│    stay_id, reservation_id, cliente_nombre, currency                │
│    period, nights, room                                              │
│    breakdown_lines[], totals, payments[], warnings[]                │
│    readonly, generated_at                                            │
│  }                                                                   │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      RESPONSE JSON → FRONTEND                        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Modelos de Base de Datos

### Stay
```python
Stay {
    id: int
    reservation_id: int  → FK Reservation
    estado: str  # "pendiente_checkin" | "ocupada" | "pendiente_checkout" | "cerrada"
    checkin_real: datetime
    checkout_real: datetime?
    nightly_rate: Decimal?  ← Tarifa específica para esta estadía
    notas_internas: str?
    
    # Relaciones
    reservation: Reservation
    occupancies: List[StayRoomOccupancy]
    charges: List[StayCharge]
    payments: List[StayPayment]
}
```

### StayRoomOccupancy
```python
StayRoomOccupancy {
    id: int
    stay_id: int → FK Stay
    room_id: int → FK Room
    desde: datetime
    hasta: datetime?  ← null si todavía ocupa
    motivo: str?
    
    # Relaciones
    stay: Stay
    room: Room
}
```

### StayCharge
```python
StayCharge {
    id: int
    stay_id: int → FK Stay
    tipo: str  # "night" | "product" | "service" | "fee" | "discount"
    descripcion: str
    cantidad: Decimal
    monto_unitario: Decimal
    monto_total: Decimal
    creado_por: str
    created_at: datetime
}
```

### StayPayment
```python
StayPayment {
    id: int
    stay_id: int → FK Stay
    monto: Decimal
    metodo: str  # "efectivo" | "tarjeta" | "transferencia"
    referencia: str?
    es_reverso: bool  ← True si es anulación
    usuario: str
    timestamp: datetime
}
```

### Room
```python
Room {
    id: int
    numero: str
    room_type_id: int → FK RoomType
    estado_operativo: str
    
    # Relaciones
    room_type: RoomType
}
```

### RoomType
```python
RoomType {
    id: int
    nombre: str
    precio_base: Decimal?  ← Tarifa por defecto
}
```

---

## Decisiones de Diseño

### 1. **No Modifica DB**
El endpoint es **read-only**. Genera preview sin persistir cambios.

**Ventajas:**
- Seguro: no hay efectos secundarios
- Performance: solo queries SELECT
- Permite simulaciones con `nights_override`

### 2. **Tarifa con Prioridad**
```
stay.nightly_rate > room_type.precio_base > 0 (missing)
```

**Razón:** Permite tarifas negociadas por stay sin alterar el room_type.

### 3. **Noches Mínimo = 1**
```python
suggested_to_charge = max(1, calculated_nights)
```

**Razón:** Política hotelera estándar (check-in/out el mismo día = 1 noche).

### 4. **IVA Automático**
El endpoint calcula IVA 21% sobre alojamiento automáticamente.

**TODO:** Hacer configurable por hotel (tabla `HotelSettings`).

### 5. **Líneas como Objetos**
Impuestos y descuentos se representan como líneas (no números agregados).

**Ventajas:**
- Trazabilidad completa
- Facilita renderizado en UI
- Permite múltiples impuestos/descuentos

### 6. **Warnings en Lugar de Errores**
Casos como "tarifa faltante" devuelven warning pero no error 400.

**Razón:** Permite generar preview para corregir datos en checkout.

---

## Performance

### Query Optimization
```python
stay = (
    db.query(Stay)
    .options(
        joinedload(Stay.reservation).joinedload(Reservation.cliente),
        joinedload(Stay.reservation).joinedload(Reservation.empresa),
        joinedload(Stay.occupancies).joinedload(StayRoomOccupancy.room).joinedload(Room.room_type),
        joinedload(Stay.charges),
        joinedload(Stay.payments)
    )
    .first()
)
```

**1 query** con eager loading de todas las relaciones (evita N+1).

### Caching (TODO)
```python
# Cache por 30 segundos (suficiente para evitar re-renders innecesarios)
@lru_cache(maxsize=100)
def get_invoice_preview_cached(stay_id, checkout_date, nights_override):
    ...
```

---

## Testing

### Unit Tests

```python
def test_invoice_preview_basic():
    """Caso normal con tarifa y cargos"""
    response = client.get(f"/api/calendar/stays/{stay_id}/invoice-preview")
    assert response.status_code == 200
    data = response.json()
    assert data["totals"]["balance"] == expected_balance

def test_invoice_preview_missing_rate():
    """Tarifa faltante genera warning"""
    response = client.get(f"/api/calendar/stays/{stay_no_rate}/invoice-preview")
    assert response.status_code == 200
    data = response.json()
    assert any(w["code"] == "MISSING_RATE" for w in data["warnings"])
    assert data["room"]["rate_source"] == "missing"

def test_invoice_preview_nights_override():
    """Override de noches funciona"""
    response = client.get(
        f"/api/calendar/stays/{stay_id}/invoice-preview",
        params={"nights_override": 10}
    )
    data = response.json()
    assert data["nights"]["override_applied"] == True
    assert data["nights"]["override_value"] == 10

def test_invoice_preview_invalid_checkout():
    """checkout_date anterior a checkin_real → error"""
    response = client.get(
        f"/api/calendar/stays/{stay_id}/invoice-preview",
        params={"checkout_date": "2020-01-01"}
    )
    assert response.status_code == 400

def test_invoice_preview_readonly_stay():
    """Stay cerrada marca readonly=true"""
    response = client.get(f"/api/calendar/stays/{stay_cerrada}/invoice-preview")
    data = response.json()
    assert data["readonly"] == True
```

---

## Seguridad

### 1. **Validación de Inputs**
```python
checkout_date: Optional[str] = Query(None, description="YYYY-MM-DD")
nights_override: Optional[int] = Query(None, ge=0)
```

FastAPI valida tipos automáticamente.

### 2. **SQL Injection**
No hay riesgo: usa SQLAlchemy ORM (queries parametrizadas).

### 3. **Autorización (TODO)**
Agregar dependency para verificar que el usuario tiene permiso:
```python
def get_invoice_preview(
    stay_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)  ← TODO
):
    # Verificar que current_user puede ver esta stay
    ...
```

---

## Métricas de Negocio

### KPIs que se pueden derivar

1. **Tasa de warnings por tipo**
   - MISSING_RATE → Mide falta de configuración
   - NIGHTS_DIFFER → Mide precisión de reservas

2. **Tiempo promedio de generación**
   - Benchmark: < 100ms

3. **Tasa de overrides aplicados**
   - Identifica casos de ajustes manuales

4. **Distribución de saldos**
   - balance > 0: pendiente
   - balance == 0: pagado
   - balance < 0: sobrepago

---

## Extensiones Futuras

### 1. **Tarifas Diarias Variables**
```python
class DailyRate(BaseModel):
    date: str
    rate: float

# En request
daily_rates: Optional[List[DailyRate]] = None
```

### 2. **Multi-Currency**
```python
currency: str = Query("ARS", description="ISO currency code")
exchange_rate: Optional[float] = None
```

### 3. **Dry-Run Adjustments**
```python
class DryRunAdjustment(BaseModel):
    tipo: str  # "discount" | "tax"
    monto: float

dry_run_adjustments: Optional[List[DryRunAdjustment]] = None
```

Permite simular descuentos/impuestos sin crearlos en DB.

### 4. **PDF Export**
```python
format: str = Query("json", enum=["json", "pdf"])

if format == "pdf":
    return generate_invoice_pdf(invoice_data)
```

### 5. **Breakdown Agrupado**
```python
group_charges_by: Optional[str] = Query(None, enum=["tipo", "date"])
```

Agrupa líneas de cargos por categoría o fecha.

---

## Logs y Auditoría

```python
log_event(
    "invoice_preview",
    current_user.username,
    "Generar preview",
    f"stay_id={stay_id} balance={balance:.2f}"
)
```

**Registra:**
- Usuario que generó el preview
- Stay ID
- Balance calculado
- Timestamp

**No registra:**
- Query params (para evitar log spam)
- Líneas completas (demasiado verboso)

---

## Integración Frontend

### Service Layer
```javascript
// src/services/roomsService.js
export const staysService = {
  async getInvoicePreview(stayId, options = {}) {
    const params = new URLSearchParams()
    
    if (options.checkoutDate) {
      params.append('checkout_date', options.checkoutDate)
    }
    if (options.nightsOverride !== undefined) {
      params.append('nights_override', options.nightsOverride)
    }
    if (options.includeItems !== undefined) {
      params.append('include_items', options.includeItems)
    }
    
    const url = `${BASE_URL}/stays/${stayId}/invoice-preview?${params}`
    const response = await fetch(url)
    
    if (!response.ok) {
      const error = await response.json()
      return { success: false, error: error.detail }
    }
    
    return { success: true, data: await response.json() }
  }
}
```

### Componente de Factura
```javascript
function InvoicePreview({ stayId }) {
  const [invoice, setInvoice] = useState(null)
  const [loading, setLoading] = useState(false)
  
  useEffect(() => {
    loadInvoice()
  }, [stayId])
  
  const loadInvoice = async () => {
    setLoading(true)
    const result = await staysService.getInvoicePreview(stayId)
    
    if (result.success) {
      setInvoice(result.data)
    }
    
    setLoading(false)
  }
  
  if (loading) return <CircularProgress />
  if (!invoice) return null
  
  return (
    <Box>
      {/* Warnings */}
      {invoice.warnings.map(w => (
        <Alert severity={w.severity === 'error' ? 'error' : 'warning'}>
          {w.message}
        </Alert>
      ))}
      
      {/* Líneas */}
      {invoice.breakdown_lines.map(line => (
        <InvoiceLine key={line.metadata.id} line={line} />
      ))}
      
      {/* Totales */}
      <InvoiceTotals totals={invoice.totals} />
    </Box>
  )
}
```

---

## Conclusión

El endpoint `invoice-preview` es el **cerebro del checkout profesional**:

✅ Calcula todo (frontend no hace cuentas)  
✅ Maneja edge cases con warnings  
✅ Optimizado para performance  
✅ Extensible para features futuros  
✅ Diseñado para UX (readonly, warnings, metadata)  

**El frontend solo renderiza y reacciona a warnings.**

---

**Última actualización:** 2025-12-15  
**Autor:** Backend Architecture Team
