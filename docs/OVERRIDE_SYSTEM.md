# 🧾 Override System Documentation - Hotel Management Invoice Preview

## 📋 Overview

El sistema de **Override** permite a los usuarios modificar ciertos parámetros de la factura (tarifa por noche, noches a cobrar, descuentos y modo de impuesto) durante el checkout, mientras que el **backend siempre recalcula** el preview con los nuevos valores. Este es un enfoque profesional que garantiza consistencia y auditabilidad.

---

## 🏗️ Architecture

### Backend (FastAPI)

**Endpoint:** `GET /api/calendar/stays/{stay_id}/invoice-preview`

**Query Parameters (NEW):**

| Parámetro | Tipo | Rango | Descripción |
|-----------|------|-------|-------------|
| `nights_override` | int | ≥ 1 | Número de noches a cobrar |
| `tarifa_override` | float | ≥ 0 | Tarifa por noche (override) |
| `discount_override_pct` | float | 0-100 | Descuento en porcentaje |
| `tax_override_mode` | string | enum | Modo: 'normal' \| 'exento' \| 'custom' |
| `tax_override_value` | float | ≥ 0 | Impuesto personalizado (si mode='custom') |

**Response Changes:**

La respuesta incluye:
- `totals`: Recalculados con los overrides aplicados
- `warnings`: Listado de overrides aplicados con detalles
- `breakdown_lines`: Líneas de factura con metadatos de override

**Ejemplo de Warning:**
```json
{
  "code": "TARIFA_OVERRIDE",
  "message": "Tarifa modificada: $18000.00/noche",
  "severity": "info"
}
```

---

### Frontend (React)

**Component:** `CheckoutDrawer` en `HotelScheduler.jsx`

**New State Variables:**
```javascript
const [discountPercentage, setDiscountPercentage] = useState(null)      // % descuento
const [taxMode, setTaxMode] = useState('normal')                        // modo impuesto
const [taxCustomValue, setTaxCustomValue] = useState(null)              // impuesto custom
```

**Modified State Variables:**
```javascript
const [nochesCobradas, setNochesCobradas] = useState(0)                 // ahora editable
const [tarifaNoche, setTarifaNoche] = useState('')                      // ahora editable
```

**Service Layer Update:**
```javascript
async getInvoicePreview(stayId, overrides = {}) {
  // Construye URLSearchParams con los overrides
  // Envía GET /invoice-preview?param1=val1&param2=val2
}
```

---

## 🔄 User Workflow

### Step 1: Abrir Checkout Drawer
```
Usuario abre el checkout → Se carga invoice-preview INICIAL (sin overrides)
→ Se populan noches, tarifa, impuestos con valores del backend
```

### Step 2: Editar Campos (Resumen de Estadía - Step 0)
```
Usuario cambia:
- "Noches a cobrar": 7 (era 5)
- "Tarifa por noche": 18000 (era 20000)
- "Descuentos %": 15 (nuevo)
- "Modo Impuesto": "exento" (era normal)

Cada cambio dispara un debounced recalculation (500ms)
```

### Step 3: Backend Recalcula
```
GET /invoice-preview?
  nights_override=7
  &tarifa_override=18000
  &discount_override_pct=15
  &tax_override_mode=exento

Respuesta:
{
  "nights": { "suggested_to_charge": 7 },
  "room": { "nightly_rate": 18000 },
  "totals": {
    "room_subtotal": 126000,      // 18000 * 7
    "discounts_total": 18900,      // 126000 * 15%
    "taxes_total": 0.0,            // exento
    "grand_total": 107100          // 126000 - 18900
  },
  "warnings": [
    { "code": "TARIFA_OVERRIDE", ... },
    { "code": "DISCOUNT_OVERRIDE", ... },
    { "code": "TAX_OVERRIDE", ... }
  ]
}
```

### Step 4: Frontend Muestra Totales Recalculados
```
Subtotal: $126,000
Descuentos: -$18,900 (15%)
Impuestos: $0 (exento)
Total: $107,100

⚠️ Warnings:
- ℹ️ Tarifa modificada: $18000.00/noche
- ℹ️ Descuento aplicado: 15.0% = $18900.00
- ℹ️ Régimen de impuesto modificado: Operación exenta
```

### Step 5: Confirmar Checkout
```
Usuario avanza a Steps 1-3 (cargos, pagos, confirmación)
Luego hace POST /checkout CON los overrides + motivo de cambio
(Esta funcionalidad será implementada en la próxima fase)
```

---

## 💡 Key Features

### 1️⃣ Real-Time Recalculation
- El usuario edita un campo → 500ms de debounce → Backend recalcula
- No hay cálculos en el frontend (backend siempre es fuente de verdad)
- Los totales se actualizan automáticamente en la UI

### 2️⃣ Descuentos en Porcentaje
```javascript
// En lugar de: "Descuentos: $5000" (monto fijo)
// Ahora: "Descuentos %: 15" (porcentaje)

// Backend calcula:
discount_amount = room_subtotal * (discount_pct / 100)
// Ejemplo: 100000 * (15 / 100) = $15000
```

### 3️⃣ Tres Modos de Impuesto
```javascript
taxMode = 'normal'  → 21% IVA (automático)
taxMode = 'exento'  → 0% (operación exenta)
taxMode = 'custom'  → Valor personalizado (input field)
```

### 4️⃣ Advertencias por Override
Cada override aplicado genera una advertencia específica:
```
- TARIFA_OVERRIDE: Detalla la tarifa aplicada
- DISCOUNT_OVERRIDE: Detalla % y monto calculado
- TAX_OVERRIDE: Detalla el régimen aplicado
- NIGHTS_OVERRIDE: Detalla noches override vs calculadas
```

### 5️⃣ Audit Trail Ready
Cada línea de factura contiene metadata:
```json
{
  "description": "Descuento 15%",
  "type": "discount",
  "unit_price": 0.0,
  "quantity": 1.0,
  "amount": -18900.0,
  "metadata": {
    "discount_type": "percentage_override",
    "percentage": 15.0,
    "base": 126000.0,
    "override_reason": "Customer adjustment"
  }
}
```

---

## 📊 Calculation Example

### Initial State (No Overrides)
```
Stay: 2025-01-01 → 2025-01-05 (5 noches calculadas)
Room: Tipo "Suite" con precio_base $20000/noche
Tarifa en snapshot: $20000

Preview:
- Noches sugeridas: 5
- Tarifa: $20000
- Subtotal: $100,000
- Impuestos (21%): $21,000
- Total: $121,000
```

### With Overrides Applied
```
User changes:
- Noches: 5 → 7
- Tarifa: $20000 → $18000
- Descuento: 0% → 15%
- Impuesto: Normal (21%) → Exento (0%)

Backend recalculates:
- Room subtotal = 18000 * 7 = $126,000
- Discount = 126000 * (15/100) = $18,900
- Taxes = 0 (exento)
- Total = 126000 - 18900 = $107,100

Result:
- Noches sugeridas: 7 ✓
- Tarifa: $18000 ✓
- Subtotal: $126,000 ✓
- Descuentos: -$18,900 ✓
- Impuestos: $0 ✓
- Total: $107,100 ✓
```

---

## 🔌 API Usage

### Without Overrides (Initial Load)
```bash
GET /api/calendar/stays/1/invoice-preview
→ Returns default preview based on actual stay data
```

### With Single Override
```bash
GET /api/calendar/stays/1/invoice-preview?tarifa_override=18000
→ Recalculates with custom tariff
```

### With All Overrides
```bash
GET /api/calendar/stays/1/invoice-preview?
  nights_override=7
  &tarifa_override=18000
  &discount_override_pct=15
  &tax_override_mode=custom
  &tax_override_value=5000

→ Returns completely recalculated preview with all overrides applied
```

---

## 📝 Implementation Notes

### Frontend (Client-side)
1. ✅ New state variables for overrides
2. ✅ UI fields (inputs, selectors) for each override
3. ✅ Debounced hook to trigger recalculation
4. ✅ Service layer updated to accept override parameters
5. ✅ Warning display component

### Backend (Server-side)
1. ✅ Query parameters validation
2. ✅ Override logic in tarifa resolution
3. ✅ Override logic in discount calculation
4. ✅ Override logic in tax calculation
5. ✅ Warning system
6. ✅ Metadata enrichment

### Still To Implement
- [ ] POST /checkout endpoint (persist overrides + motivo)
- [ ] Audit trail recording (save all override changes)
- [ ] History view (show past override applications)
- [ ] Permission system (who can apply overrides?)

---

## ⚠️ Important Notes

### Backend Authority
- **Frontend never calculates totals**
- Every user edit → GET request with override parameters
- Backend validates, recalculates, returns new preview
- Frontend displays exactly what backend returns

### Validation
- `discount_override_pct`: 0-100%
- `tarifa_override`: ≥ 0
- `nights_override`: ≥ 1
- `tax_override_value`: ≥ 0 (if mode='custom')

### Performance
- Debounced input (500ms) prevents excessive API calls
- Only recalculates when user stops typing
- Response includes warnings for audit trail

---

## 🧪 Testing

### Test Script: `test_override_params.py`
```bash
cd Backend_Hotel
python test_override_params.py
```

All tests passing ✓:
```
✓ Test sin overrides
✓ Test con tarifa_override
✓ Test con discount_override_pct
✓ Test con tax_override_mode=exento
✓ Test con TODOS los overrides
```

---

## 📚 References

- **Backend Endpoint:** `endpoints/hotel_calendar.py` (line ~1007)
- **Frontend Component:** `src/components/Reservas/HotelScheduler.jsx` (CheckoutDrawer)
- **Service Layer:** `src/services/roomsService.js` (staysService.getInvoicePreview)
- **Schemas:** `Backend_Hotel/schemas/` (InvoicePreviewResponse, etc.)
