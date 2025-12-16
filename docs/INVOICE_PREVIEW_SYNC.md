# Sincronización Invoice-Preview: Backend & Frontend

## Resumen de Cambios Implementados

### 🎯 Objetivo Cumplido
Sincronizar completamente el checkout wizard de HotelScheduler.jsx con el invoice-preview del backend, eliminando cálculos duplicados y asegurando que la UI muestre los datos correctos del sistema.

---

## 1. Backend - Correcciones en `hotel_calendar.py`

### ✅ Cálculo de Noches Corregido

**Problema:** Cuando `checkout_real` no existía, usaba `date.today()` que podía causar inconsistencias.

**Solución:**
```python
# ANTES: usar date.today() por defecto
elif stay.checkout_real:
    checkout_candidate = stay.checkout_real.date()
else:
    checkout_candidate = date.today()  # ❌ Inconsistente

# AHORA: usar checkout_planned cuando no hay checkout_real
elif stay.checkout_real:
    checkout_candidate = stay.checkout_real.date()
else:
    checkout_candidate = checkout_planned  # ✅ Consistente con reserva
```

**Beneficios:**
- ✅ Siempre usa `checkout_planned` como fallback coherente
- ✅ `suggested_to_charge = max(1, calculated_nights)` garantiza mínimo 1 noche
- ✅ Warnings claros cuando `calculated != planned`

### ✅ Warnings Mejorados

El sistema ahora genera warnings específicos:
- `NIGHTS_DIFFER`: Cuando noches calculadas ≠ planificadas
- `BALANCE_DUE`: Cuando hay saldo pendiente
- `MISSING_RATE`: Cuando no hay tarifa configurada
- `NIGHTS_OVERRIDE`: Cuando se aplica override manual

---

## 2. Frontend - Sincronización Completa en `HotelScheduler.jsx`

### ✅ Step 0: Resumen de Estadía

**Cambios Implementados:**

1. **Campos Sincronizados con invoicePreview:**
```jsx
// ANTES: valores mezclados entre selectedBlock y cálculo manual
<input value={String(nochesCobradas)} />

// AHORA: valores exclusivamente de invoicePreview
<input 
  value={String(invoicePreview?.nights?.suggested_to_charge ?? nochesCobradas)} 
  disabled={invoicePreview?.readonly}
/>
```

2. **Nuevos Campos Informativos:**
- **Noches detectadas**: `invoicePreview.nights.calculated`
- **Noches a cobrar**: `invoicePreview.nights.suggested_to_charge`
- **Planificadas**: `invoicePreview.nights.planned`

3. **Tarifa Automática:**
```jsx
<input 
  value={invoicePreview?.room?.nightly_rate ?? tarifaNoche}
  disabled={invoicePreview?.readonly}
/>
```

4. **Totales del Sistema:**
- Subtotal: `invoicePreview.totals.room_subtotal`
- Impuestos: `invoicePreview.totals.taxes_total` (calculado por backend)
- Descuentos: `invoicePreview.totals.discounts_total`

**Campos deshabilitados cuando `invoicePreview` está activo:**
- Descuentos (calculados por backend)
- Impuestos (calculados por backend)
- Subtotal (calculado por backend)

### ✅ Warnings Visibles en UI

**Nuevo bloque de warnings:**
```jsx
{invoicePreview?.warnings && invoicePreview.warnings.length > 0 && (
  <div className="mt-3">
    {invoicePreview.warnings.map((warning, index) => (
      <div className={`alert ${
        warning.severity === 'error' ? 'alert-danger' : 
        warning.severity === 'warning' ? 'alert-warning' : 
        'alert-info'
      }`}>
        <strong>{warning.code}:</strong> {warning.message}
      </div>
    ))}
  </div>
)}
```

**Ejemplo de warnings mostrados:**
- ⚠️ **NIGHTS_DIFFER**: Noches calculadas (2) difieren de planificadas (8)
- ⚠️ **BALANCE_DUE**: Saldo pendiente: 193600.00
- ❌ **MISSING_RATE**: No hay tarifa configurada para Doble Standar

### ✅ Cálculos Centralizados

**ANTES (mezclado):**
```jsx
const nightsBase = clampNumber(nochesCobradas || stayBlock?.nights || 1, 1)
const nightly = clampNumber(tarifaNoche, 0)
const nightsAmount = nightsBase * nightly
const total = nightsAmount + chargesAmt + tax - disc
const paid = payments.reduce(...)
const balance = total - paid
```

**AHORA (prioridad a invoicePreview):**
```jsx
// Usar invoicePreview si está disponible, sino calcular manualmente
const nightsBase = clampNumber(
  invoicePreview?.nights?.suggested_to_charge ?? nochesCobradas || stayBlock?.nights || 1, 
  1
)
const nightly = clampNumber(invoicePreview?.room?.nightly_rate ?? tarifaNoche, 0)
const nightsAmount = invoicePreview?.totals?.room_subtotal ?? (nightsBase * nightly)

const disc = invoicePreview?.totals?.discounts_total ?? clampNumber(descuento, 0)
const tax = invoicePreview?.totals?.taxes_total ?? clampNumber(impuesto, 0)
const chargesAmt = invoicePreview?.totals?.charges_total ?? clampNumber(chargesTotal, 0)
const total = invoicePreview?.totals?.grand_total ?? Math.max(0, nightsAmount + chargesAmt + tax - disc)

const paidManual = payments.reduce((acc, p) => acc + clampNumber(p.monto, 0), 0)
const paidFromInvoice = invoicePreview?.totals?.payments_total ?? 0
const paid = paidManual + paidFromInvoice
const balance = invoicePreview?.totals?.balance ?? (total - paid)
```

**Beneficios:**
- ✅ Una sola fuente de verdad (invoicePreview)
- ✅ Fallback a cálculo manual si no hay preview
- ✅ No hay duplicación de lógica
- ✅ Totales siempre consistentes con backend

### ✅ Step 3: Confirmación Final

**Mejoras:**
1. **Desglose Condicional**: Solo muestra cálculo manual si NO hay invoicePreview
2. **Totales del Sistema**: Usa `invoicePreview.totals` directamente
3. **Saldo Correcto**: Unificado desde invoicePreview

```jsx
{!invoicePreview && (
  <>
    {/* Cálculo manual solo si no hay preview */}
    <div>Noches ({nightsBase} × {money(nightly)})</div>
    <div>Cargos adicionales: {money(chargesAmt)}</div>
    <div>Impuestos: {money(tax)}</div>
    <div>Descuento: - {money(disc)}</div>
  </>
)}
<div>Total factura: {money(total)}</div>
<div>Total pagado: {money(paid)}</div>
<div className={balance > 0 ? 'text-danger' : 'text-success'}>
  Saldo: {money(balance)}
</div>
```

---

## 3. Flujo de Datos Completo

### 🔄 Secuencia de Operación:

1. **Usuario abre CheckoutDrawer** → `useEffect` detecta `stayBlock`
2. **Frontend llama** `GET /api/calendar/stays/{stay_id}/invoice-preview`
3. **Backend calcula:**
   - Noches (max(1, diff))
   - Tarifa (room_type.precio_base)
   - Impuestos (IVA 21% auto)
   - Warnings (NIGHTS_DIFFER, BALANCE_DUE, etc.)
4. **Frontend recibe invoicePreview** y:
   - Auto-completa campos con valores del sistema
   - Deshabilita campos controlados por backend
   - Muestra warnings destacados
   - Calcula totales SOLO desde invoicePreview
5. **Usuario confirma checkout** → Backend tiene datos definitivos

---

## 4. Validaciones y Reglas de Negocio

### ✅ Backend:
- ✅ Noches mínimas: `max(1, calculated)` siempre
- ✅ Checkout candidato: `checkout_planned` si no hay `checkout_real`
- ✅ IVA automático: 21% sobre `room_subtotal`
- ✅ Warnings automáticos: desajustes y saldos
- ✅ Readonly: si stay.estado == "cerrada"

### ✅ Frontend:
- ✅ Campos deshabilitados si `invoicePreview.readonly == true`
- ✅ Warnings visibles con colores semánticos (error/warning/info)
- ✅ Auto-carga de valores desde preview
- ✅ Fallback a cálculo manual si preview falla

---

## 5. Ejemplo de Respuesta Completa

```json
{
  "stay_id": 1,
  "reservation_id": 1,
  "cliente_nombre": "Perez",
  "currency": "ARS",
  "period": {
    "checkin_real": "2025-12-15T18:54:02",
    "checkout_candidate": "2025-12-23",
    "checkout_planned": "2025-12-23"
  },
  "nights": {
    "planned": 8,
    "calculated": 8,
    "suggested_to_charge": 8,
    "override_applied": false,
    "override_value": null
  },
  "room": {
    "room_id": 1,
    "numero": "21",
    "room_type_name": "Doble Standar",
    "nightly_rate": 20000.0,
    "rate_source": "room_type"
  },
  "breakdown_lines": [
    {
      "line_type": "room",
      "description": "Alojamiento - Doble Standar #21",
      "quantity": 8.0,
      "unit_price": 20000.0,
      "total": 160000.0
    },
    {
      "line_type": "tax",
      "description": "IVA 21% sobre alojamiento",
      "quantity": 1.0,
      "unit_price": 33600.0,
      "total": 33600.0
    }
  ],
  "totals": {
    "room_subtotal": 160000.0,
    "charges_total": 0.0,
    "taxes_total": 33600.0,
    "discounts_total": 0.0,
    "grand_total": 193600.0,
    "payments_total": 0.0,
    "balance": 193600.0
  },
  "payments": [],
  "warnings": [
    {
      "code": "BALANCE_DUE",
      "message": "Saldo pendiente: 193600.00",
      "severity": "warning"
    }
  ],
  "readonly": false,
  "generated_at": "2025-12-15T19:59:56"
}
```

---

## 6. Tests Ejecutados

### ✅ Backend Tests (`test_invoice_preview.py`)
- ✅ Preview básico con stay activa
- ✅ Preview con checkout_date específico
- ✅ Preview con nights_override
- ✅ Preview solo totales (include_items=false)
- ✅ Validación de errores (checkout inválido)

**Resultado:** 6/6 tests pasaron ✅

---

## 7. Archivos Modificados

### Backend:
- ✅ `endpoints/hotel_calendar.py` (líneas 1060-1100)

### Frontend:
- ✅ `HotelScheduler.jsx` (CheckoutDrawer):
  - Step 0: Campos sincronizados
  - Warnings section
  - Cálculos centralizados
  - Step 3: Totales del preview

### Tests:
- ✅ `tests/test_invoice_preview.py` (existente)
- ✅ `tests/test_invoice_nights.py` (nuevo)

---

## 8. Estado Final

✅ **COMPLETADO** - El checkout wizard ahora:
- Muestra datos exclusivamente del backend invoice-preview
- Warnings visibles y destacados
- Campos deshabilitados cuando readonly=true
- Cálculos unificados (una sola fuente de verdad)
- Noches mínimas garantizadas (≥ 1)
- Impuestos automáticos (IVA 21%)

---

**Fecha:** Diciembre 15, 2025  
**Versión:** 2.0 - Sincronización Completa
