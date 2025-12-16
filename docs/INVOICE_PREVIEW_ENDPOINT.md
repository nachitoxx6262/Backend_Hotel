# 🧾 Invoice Preview Endpoint - Documentación Profesional

## Descripción

Endpoint especializado para generar previsualizaciones de factura en el proceso de checkout. Diseñado para que el frontend **NO calcule nada** y solo renderice datos.

---

## Definición del Endpoint

### Ruta
```
GET /api/calendar/stays/{stay_id}/invoice-preview
```

### Método
`GET`

### Autenticación
Requerida (según middleware del hotel)

---

## Query Parameters

| Parámetro | Tipo | Requerido | Default | Descripción |
|-----------|------|-----------|---------|-------------|
| `checkout_date` | string (YYYY-MM-DD) | No | `today` o `checkout_planned` | Fecha candidata de checkout para calcular noches |
| `nights_override` | integer | No | `null` | Forzar noches a cobrar (solo para preview) |
| `include_items` | boolean | No | `true` | Incluir líneas detalladas en breakdown |

### Ejemplos de uso

```bash
# Preview básico (usa hoy como checkout)
GET /api/calendar/stays/123/invoice-preview

# Preview con fecha específica
GET /api/calendar/stays/123/invoice-preview?checkout_date=2025-12-20

# Preview con override de noches
GET /api/calendar/stays/123/invoice-preview?nights_override=3

# Preview solo totales (sin líneas)
GET /api/calendar/stays/123/invoice-preview?include_items=false
```

---

## Lógica de Negocio (paso a paso)

### 1. **Validación**
- Verificar que `stay_id` exista
- Si la estadía está cerrada (`estado="cerrada"`), marcar `readonly=true`
- Validar que `checkout_date >= checkin_real`

### 2. **Cálculo de Noches**

Tres valores calculados:

```python
planned_nights = (checkout_planned - fecha_checkin).days
calculated_nights = (checkout_candidate - checkin_real).days
suggested_to_charge = max(1, calculated_nights)  # Mínimo 1 noche
```

**Lógica de prioridad:**
1. Si viene `nights_override` → usar ese valor
2. Si no → usar `suggested_to_charge`

**Warnings:**
- `NIGHTS_OVERRIDE` si se aplicó override
- `NIGHTS_DIFFER` si `calculated != planned`

### 3. **Resolución de Tarifa**

Orden de prioridad:

```python
if stay.nightly_rate:
    rate = stay.nightly_rate
    source = "stay"
elif room_type.precio_base:
    rate = room_type.precio_base
    source = "room_type"
else:
    rate = 0.0
    source = "missing"
    # ⚠️ WARNING: MISSING_RATE
```

### 4. **Cargos / Consumos**

```python
for charge in stay.charges:
    if charge.tipo not in ["discount", "fee"]:
        charges_total += charge.monto_total
        if include_items:
            breakdown_lines.append({
                "line_type": "charge",
                "description": charge.descripcion,
                "quantity": charge.cantidad,
                "unit_price": charge.monto_unitario,
                "total": charge.monto_total
            })
```

**Warning:** `UNPRICED_CHARGE` si `monto_total == 0`

### 5. **Impuestos**

Se calculan como **líneas separadas**:

```python
# 1. Impuestos explícitos (tipo="fee")
for tax_charge in stay.charges where tipo="fee":
    taxes_total += tax_charge.monto_total

# 2. IVA sobre alojamiento (configurable)
iva_rate = 0.21  # 21%
iva_alojamiento = room_subtotal * iva_rate
taxes_total += iva_alojamiento
```

### 6. **Descuentos**

```python
for discount in stay.charges where tipo="discount":
    discount_amount = abs(discount.monto_total)
    discounts_total += discount_amount
    # Se agrega como línea negativa
```

### 7. **Pagos**

```python
for payment in stay.payments:
    if not payment.es_reverso:
        payments_total += payment.monto
```

### 8. **Gran Total**

```python
room_subtotal = nightly_rate * final_nights
grand_total = room_subtotal + charges_total + taxes_total - discounts_total
balance = grand_total - payments_total
```

**Warnings:**
- `BALANCE_DUE` si `balance > 0`
- `OVERPAYMENT` si `balance < 0`
- `PAYMENTS_EXCEED_TOTAL` si `payments_total > grand_total`

---

## Formato de Respuesta

### Schema Completo

```json
{
  "stay_id": 123,
  "reservation_id": 456,
  "cliente_nombre": "Juan Pérez",
  "currency": "ARS",
  
  "period": {
    "checkin_real": "2025-12-15T14:30:00",
    "checkout_candidate": "2025-12-20",
    "checkout_planned": "2025-12-21"
  },
  
  "nights": {
    "planned": 6,
    "calculated": 5,
    "suggested_to_charge": 5,
    "override_applied": false,
    "override_value": null
  },
  
  "room": {
    "room_id": 101,
    "numero": "201",
    "room_type_name": "Doble Superior",
    "nightly_rate": 15000.0,
    "rate_source": "room_type"
  },
  
  "breakdown_lines": [
    {
      "line_type": "room",
      "description": "Alojamiento - Doble Superior #201",
      "quantity": 5.0,
      "unit_price": 15000.0,
      "total": 75000.0,
      "metadata": {
        "nights": 5,
        "room_id": 101,
        "rate_source": "room_type"
      }
    },
    {
      "line_type": "charge",
      "description": "Minibar - Gaseosa",
      "quantity": 2.0,
      "unit_price": 800.0,
      "total": 1600.0,
      "metadata": {
        "charge_id": 789,
        "tipo": "product",
        "created_at": "2025-12-17T10:00:00"
      }
    },
    {
      "line_type": "tax",
      "description": "IVA 21% sobre alojamiento",
      "quantity": 1.0,
      "unit_price": 15750.0,
      "total": 15750.0,
      "metadata": {
        "tax_type": "iva",
        "rate": 0.21,
        "base": 75000.0
      }
    },
    {
      "line_type": "discount",
      "description": "Descuento cliente frecuente",
      "quantity": 1.0,
      "unit_price": -5000.0,
      "total": -5000.0,
      "metadata": {
        "charge_id": 790,
        "tipo": "discount"
      }
    },
    {
      "line_type": "payment",
      "description": "Pago (tarjeta)",
      "quantity": 1.0,
      "unit_price": -50000.0,
      "total": -50000.0,
      "metadata": {
        "payment_id": 321,
        "metodo": "tarjeta",
        "referencia": "AUTH123456"
      }
    }
  ],
  
  "totals": {
    "room_subtotal": 75000.0,
    "charges_total": 1600.0,
    "taxes_total": 15750.0,
    "discounts_total": 5000.0,
    "grand_total": 87350.0,
    "payments_total": 50000.0,
    "balance": 37350.0
  },
  
  "payments": [
    {
      "id": 321,
      "monto": 50000.0,
      "metodo": "tarjeta",
      "referencia": "AUTH123456",
      "timestamp": "2025-12-16T18:00:00",
      "usuario": "recepcion"
    }
  ],
  
  "warnings": [
    {
      "code": "NIGHTS_DIFFER",
      "message": "Noches calculadas (5) difieren de planificadas (6)",
      "severity": "warning"
    },
    {
      "code": "BALANCE_DUE",
      "message": "Saldo pendiente: 37350.00",
      "severity": "warning"
    }
  ],
  
  "readonly": false,
  "generated_at": "2025-12-15T20:30:45"
}
```

---

## Warnings (Códigos)

| Código | Severidad | Descripción |
|--------|-----------|-------------|
| `MISSING_RATE` | error | No hay tarifa configurada para la habitación |
| `NIGHTS_OVERRIDE` | info | Se aplicó override manual de noches |
| `NIGHTS_DIFFER` | warning | Noches calculadas ≠ planificadas |
| `BALANCE_DUE` | warning | Saldo pendiente de pago |
| `OVERPAYMENT` | info | Pagos superan el total |
| `PAYMENTS_EXCEED_TOTAL` | warning | Alerta de sobrepago |
| `UNPRICED_CHARGE` | warning | Cargo sin precio válido |

---

## Edge Cases

### ❌ Casos de Error

1. **Stay no existe**
```json
{
  "detail": "Stay 999 no encontrado"
}
```
Status: `404 Not Found`

2. **checkout_date anterior a checkin_real**
```json
{
  "detail": "checkout_date (2025-12-10) no puede ser anterior a checkin_real (2025-12-15)"
}
```
Status: `400 Bad Request`

3. **checkout_date formato inválido**
```json
{
  "detail": "checkout_date inválido: 2025/12/32"
}
```
Status: `400 Bad Request`

4. **Stay sin ocupaciones**
```json
{
  "detail": "Stay sin ocupaciones registradas"
}
```
Status: `400 Bad Request`

### ✅ Casos Especiales Manejados

1. **Tarifa faltante**
```json
{
  "room": {
    "nightly_rate": 0.0,
    "rate_source": "missing"
  },
  "warnings": [
    {
      "code": "MISSING_RATE",
      "message": "No hay tarifa configurada para Doble Superior",
      "severity": "error"
    }
  ],
  "totals": {
    "room_subtotal": 0.0,
    ...
  }
}
```

2. **Cargos negativos (descuentos mal cargados)**
→ Se toman como descuentos y se invierten

3. **Pagos > total**
```json
{
  "totals": {
    "grand_total": 50000.0,
    "payments_total": 60000.0,
    "balance": -10000.0
  },
  "warnings": [
    {
      "code": "OVERPAYMENT",
      "message": "Sobrepago: 10000.00",
      "severity": "info"
    },
    {
      "code": "PAYMENTS_EXCEED_TOTAL",
      "message": "Los pagos (60000.00) superan el total (50000.00)",
      "severity": "warning"
    }
  ]
}
```

4. **Stay ya cerrada**
```json
{
  "readonly": true,
  "warnings": []
}
```
→ El preview sigue funcionando pero se marca como readonly

5. **Noches = 0 (checkin y checkout el mismo día)**
```json
{
  "nights": {
    "calculated": 0,
    "suggested_to_charge": 1
  }
}
```
→ Se cobra mínimo 1 noche por lógica de negocio

---

## Uso desde el Frontend

### HotelScheduler.jsx - CheckoutDrawer

```javascript
// Cargar preview al abrir drawer
useEffect(() => {
  if (open && stayBlock) {
    const stayId = stayBlock.kind === 'stay' ? stayBlock.id : stayBlock.stayId
    
    if (stayId) {
      loadInvoicePreview(stayId)
    }
  }
}, [open, stayBlock])

const loadInvoicePreview = async (stayId) => {
  setLoadingInvoice(true)
  
  const result = await staysService.getInvoicePreview(stayId)
  
  if (result.success) {
    setInvoicePreview(result.data)
    
    // Auto-completar campos del wizard
    setNochesOcupadas(result.data.nights.suggested_to_charge)
    
    // Mostrar warnings
    result.data.warnings.forEach(w => {
      if (w.severity === 'error') {
        console.error(w.message)
      } else if (w.severity === 'warning') {
        console.warn(w.message)
      }
    })
  } else {
    console.error('Error cargando preview:', result.error)
  }
  
  setLoadingInvoice(false)
}
```

### Renderizado de Líneas

```javascript
{invoicePreview?.breakdown_lines.map((line, idx) => {
  const isNegative = line.total < 0
  const icon = {
    room: '🏨',
    charge: '🛒',
    tax: '📋',
    discount: '🎁',
    payment: '💳'
  }[line.line_type]
  
  return (
    <Box key={idx} sx={{
      display: 'flex',
      justifyContent: 'space-between',
      py: 1,
      borderBottom: '1px solid #eee',
      opacity: line.line_type === 'payment' ? 0.7 : 1
    }}>
      <Box>
        <Typography variant="body2">
          {icon} {line.description}
        </Typography>
        {line.quantity > 1 && (
          <Typography variant="caption" color="text.secondary">
            {line.quantity} × ${line.unit_price.toLocaleString()}
          </Typography>
        )}
      </Box>
      <Typography
        variant="body2"
        fontWeight={line.line_type === 'room' ? 'bold' : 'normal'}
        color={isNegative ? 'success.main' : 'inherit'}
      >
        ${Math.abs(line.total).toLocaleString()}
      </Typography>
    </Box>
  )
})}
```

### Renderizado de Totales

```javascript
<Box sx={{ mt: 2, pt: 2, borderTop: '2px solid #333' }}>
  <Stack spacing={1}>
    <Box display="flex" justifyContent="space-between">
      <Typography variant="body2">Alojamiento</Typography>
      <Typography variant="body2">
        ${invoicePreview.totals.room_subtotal.toLocaleString()}
      </Typography>
    </Box>
    
    {invoicePreview.totals.charges_total > 0 && (
      <Box display="flex" justifyContent="space-between">
        <Typography variant="body2">Consumos</Typography>
        <Typography variant="body2">
          ${invoicePreview.totals.charges_total.toLocaleString()}
        </Typography>
      </Box>
    )}
    
    <Box display="flex" justifyContent="space-between">
      <Typography variant="body2">Impuestos</Typography>
      <Typography variant="body2">
        ${invoicePreview.totals.taxes_total.toLocaleString()}
      </Typography>
    </Box>
    
    {invoicePreview.totals.discounts_total > 0 && (
      <Box display="flex" justifyContent="space-between">
        <Typography variant="body2" color="success.main">Descuentos</Typography>
        <Typography variant="body2" color="success.main">
          -${invoicePreview.totals.discounts_total.toLocaleString()}
        </Typography>
      </Box>
    )}
    
    <Divider />
    
    <Box display="flex" justifyContent="space-between">
      <Typography variant="h6">Total</Typography>
      <Typography variant="h6">
        ${invoicePreview.totals.grand_total.toLocaleString()}
      </Typography>
    </Box>
    
    {invoicePreview.totals.payments_total > 0 && (
      <Box display="flex" justifyContent="space-between">
        <Typography variant="body2">Pagado</Typography>
        <Typography variant="body2" color="success.main">
          -${invoicePreview.totals.payments_total.toLocaleString()}
        </Typography>
      </Box>
    )}
    
    <Box display="flex" justifyContent="space-between">
      <Typography variant="h6" color={
        invoicePreview.totals.balance > 0 ? 'error.main' : 'success.main'
      }>
        Saldo
      </Typography>
      <Typography variant="h6" color={
        invoicePreview.totals.balance > 0 ? 'error.main' : 'success.main'
      }>
        ${invoicePreview.totals.balance.toLocaleString()}
      </Typography>
    </Box>
  </Stack>
</Box>
```

### Manejo de Warnings

```javascript
{invoicePreview?.warnings.map((warning, idx) => (
  <Alert
    key={idx}
    severity={warning.severity === 'error' ? 'error' : 'warning'}
    sx={{ mb: 1 }}
  >
    <AlertTitle>{warning.code}</AlertTitle>
    {warning.message}
  </Alert>
))}
```

---

## Ventajas del Diseño

✅ **Frontend no calcula nada** - Solo renderiza  
✅ **Warnings para UX** - Alertas claras para el usuario  
✅ **Readonly mode** - Detecta stays cerradas  
✅ **Override flexible** - Permite simular escenarios  
✅ **Líneas detalladas opcionales** - Performance optimizada  
✅ **Edge cases manejados** - Robusto ante datos inconsistentes  
✅ **Profesional** - Estructura clara tipo invoice real  

---

## TODO / Mejoras Futuras

🔹 Soportar tarifas diarias variables (`daily_rates`)  
🔹 Configurar IVA y tasas por hotel (tabla `HotelSettings`)  
🔹 Agregar `dry_run_adjustments` para simular descuentos/cargos  
🔹 Exportar PDF directamente desde el endpoint  
🔹 Multi-currency support  
🔹 Histórico de previews generados (auditoría)  

---

**Última actualización:** 2025-12-15  
**Versión:** 1.0.0  
**Autor:** Backend Team - Hotel PMS
