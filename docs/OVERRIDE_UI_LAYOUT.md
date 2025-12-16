# 🎨 CheckoutDrawer UI Layout - Override System

## Overview
El **CheckoutDrawer** es un modal wizard con 4 pasos. Los cambios principales están en **Step 0: Resumen**.

---

## Step 0: Resumen (WITH OVERRIDES) ✨

```
╔════════════════════════════════════════════════════════════════════════════╗
║                     ❌ Cerrar                                          ✓   ║
║ ┌────────────────────────────────────────────────────────────────────────┐ ║
║ │ PASO 1 / 4: Resumen de estadía                                       │ ║
║ │                                                                        │ ║
║ │ Definí noches cobradas y tarifa. (Luego sumamos cargos, impuestos    │ ║
║ │ y descuentos.)                                                        │ ║
║ │                                                                        │ ║
║ │ [ℹ️] Preview de factura cargado                                       │ ║
║ │     ✓ 2 línea(s) de cargos disponibles                              │ ║
║ │                                                                        │ ║
║ │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │ ║
║ │ DATOS DE HOSPEDAJE                                                  │ ║
║ │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │ ║
║ │                                                                        │ ║
║ │ 🔒 Noches detectadas          ✏️ Noches a cobrar      ✏️ Tarifa/noche │ ║
║ │ ┌──────────────────┐         ┌──────────────────┐   ┌────────────────┐│ ║
║ │ │      [1]         │         │      [7]         │   │    18000       ││ ║
║ │ └──────────────────┘         └──────────────────┘   └────────────────┘│ ║
║ │ Desde check-in real           Planificadas: 8       Ej: 20000         │ ║
║ │                                                                        │ ║
║ │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │ ║
║ │ CÁLCULOS                                                             │ ║
║ │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │ ║
║ │                                                                        │ ║
║ │ Subtotal noches  │  ✏️ Descuentos %   │  Modo Impuesto             │ ║
║ │ ┌──────────────┐ │  ┌────────────┐   │  ┌──────────────────────┐  │ ║
║ │ │  $126,000.00 │ │  │   [15]%    │   │  │ ▼ Normal (21% IVA)  │  │ ║
║ │ │ (read-only)  │ │  │ Monto: -$1 │   │  │  Exento              │  │
║ │ └──────────────┘ │  │ (calc.)    │   │  │  Custom              │  │
║ │ del backend      │  └────────────┘   │  └──────────────────────┘  │ ║
║ │                  │  0 a 100%         │  Selecciona régimen        │ ║
║ │                  │                   │                            │ ║
║ │                  │  Impuestos        │  (Si "Custom", input:)     │ ║
║ │                  │  ┌──────────────┐ │  ┌──────────────────────┐  │ ║
║ │                  │  │    $0.00     │ │  │   [5000]             │  │ ║
║ │                  │  │ (read-only)  │ │  │ Ej: 5000             │  │
║ │                  │  └──────────────┘ │  └──────────────────────┘  │ ║
║ │                  │  Cálculo auto     │                             │ ║
║ │                                                                        │ ║
║ │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │ ║
║ │ ADVERTENCIAS (WARNINGS)                                              │ ║
║ │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │ ║
║ │                                                                        │ ║
║ │ [ℹ️] TARIFA_OVERRIDE: Tarifa modificada: $18000.00/noche             │ ║
║ │ [ℹ️] DISCOUNT_OVERRIDE: Descuento aplicado: 15.0% = $18900.00        │ ║
║ │ [ℹ️] TAX_OVERRIDE: Régimen modificado: Operación exenta               │ ║
║ │ [⚠️] NIGHTS_OVERRIDE: Override de noches aplicado: 7 (calculado: 1)  │ ║
║ │                                                                        │ ║
║ │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │ ║
║ │ TOTALES                                                              │ ║
║ │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │ ║
║ │                                                                        │ ║
║ │ Subtotal:  $126,000.00                                               │ ║
║ │ Cargos:       $0.00                                                  │ ║
║ │ Descuentos: -$18,900.00                                              │ ║
║ │ Impuestos:    $0.00  (exento)                                        │ ║
║ │ ─────────────────────────                                            │ ║
║ │ TOTAL:    $107,100.00  💰                                            │ ║
║ │                                                                        │ ║
║ │ Pagado:       $0.00                                                  │ ║
║ │ Saldo:   $107,100.00  ⚠️                                             │ ║
║ │                                                                        │ ║
║ │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │ ║
║ │                                                                        │ ║
║ │                    [◀ Anterior]  [Siguiente ▶]                      │ ║
║ │                                                                        │ ║
║ └────────────────────────────────────────────────────────────────────────┘ ║
╚════════════════════════════════════════════════════════════════════════════╝
```

---

## Field-by-Field Breakdown

### 1. Noches detectadas (Read-Only)
```
Noches detectadas
┌──────────────┐
│      1       │  ← Calculado automáticamente desde check-in real
└──────────────┘
Desde check-in real
```
- **State:** Disabled (read-only desde backend)
- **Valor:** De `invoicePreview?.nights?.calculated`
- **Nota:** No editables, solo informativo

### 2. Noches a cobrar (Editable) ✏️
```
Noches a cobrar
┌──────────────┐
│   [7]   ✏️   │  ← Usuario puede cambiar
└──────────────┘
Planificadas: 8
```
- **State:** `[nochesCobradas, setNochesCobradas]`
- **Tipo:** number input
- **onChange:** Dispara debounce → recalculation
- **Límite:** ≥ 1
- **Nota:** Este valor se envía como `nights_override` en GET

### 3. Tarifa por noche (Editable) ✏️
```
Tarifa por noche
┌──────────────┐
│ [18000]  ✏️  │  ← Usuario puede cambiar
└──────────────┘
Ej: 20000
```
- **State:** `[tarifaNoche, setTarifaNoche]`
- **Tipo:** number input
- **onChange:** Dispara debounce → recalculation
- **Límite:** ≥ 0
- **Nota:** Este valor se envía como `tarifa_override` en GET

### 4. Subtotal noches (Read-Only)
```
Subtotal noches
┌──────────────┐
│  $126,000.00 │  ← Calculado por backend: tarifa × noches
└──────────────┘
(read-only, del backend)
```
- **Valor:** De `invoicePreview?.totals?.room_subtotal`
- **Disabled:** true (siempre)
- **Función:** Mostrar resultado de: tarifa × noches

### 5. Descuentos % (Editable) ✏️ [NEW]
```
Descuentos %
┌──────────────┐
│   [15]%  ✏️  │  ← Porcentaje del subtotal
└──────────────┘
Monto: -$18,900.00
```
- **State:** `[discountPercentage, setDiscountPercentage]`
- **Tipo:** number input (0-100)
- **onChange:** Dispara debounce → recalculation
- **Display:** Muestra monto calculado por backend
- **Nota:** Se envía como `discount_override_pct` en GET

### 6. Modo Impuesto (Selector) ✏️ [NEW]
```
Modo Impuesto
┌──────────────────────────┐
│ ▼ Normal (21% IVA)       │  ← Selector dropdown
│   Exento                 │
│   Custom                 │
└──────────────────────────┘
Selecciona régimen
```
- **State:** `[taxMode, setTaxMode]`
- **Opciones:**
  - `'normal'` → 21% IVA automático
  - `'exento'` → 0% (sin impuesto)
  - `'custom'` → Valor personalizado
- **onChange:** Cambia a modo custom mostrará input adicional
- **Nota:** Se envía como `tax_override_mode` en GET

### 7. Impuesto Custom (Conditional) ✏️ [NEW]
```
(Solo visible si Modo Impuesto = "Custom")

Impuesto Custom
┌──────────────┐
│   [5000]  ✏️ │  ← Monto fijo personalizado
└──────────────┘
Ej: 5000
```
- **State:** `[taxCustomValue, setTaxCustomValue]`
- **Tipo:** number input
- **Visible:** Solo si `taxMode === 'custom'`
- **Límite:** ≥ 0
- **Nota:** Se envía como `tax_override_value` en GET

### 8. Impuestos (Conditional Read-Only)
```
Caso 1: Si taxMode ≠ 'custom'
Impuestos
┌──────────────┐
│    $0.00     │  ← Calculado: normal=21%, exento=0%
└──────────────┘
(read-only, Cálculo auto)

Caso 2: Si taxMode = 'custom'
(No se muestra - usa el input Custom arriba)
```
- **Valor:** De `invoicePreview?.totals?.taxes_total`
- **Disabled:** true (siempre)

---

## Real-Time Recalculation Flow

### Timeline de un usuario que cambia Descuentos de 0% → 15%

```
t=0.0s    Usuario hace clic en "Descuentos %" input
          ┌─ Input obtiene focus
          
t=0.1s    Usuario tipea "15"
          ┌─ setDiscountPercentage(15) → Stored in state
          ┌─ Input display: "15" ✓
          ┌─ Debounce timer reset (count: 500ms)
          
t=0.2s    Usuario sigue escribiendo (typo) "150"
          ┌─ setDiscountPercentage(150) - PERO validación: max 100
          ┌─ State no cambia (rechaza 150)
          ┌─ Input mantiene "15"
          ┌─ Debounce timer reset
          
t=0.3s    Usuario corrije borra y tipea "5"
          ┌─ setDiscountPercentage(5)
          ┌─ Input display: "5"
          ┌─ Debounce timer reset
          
t=0.8s    Usuario no tipea más (esperamos 500ms)
          ┌─ Debounce timeout activado
          ┌─ Construye override params:
             {
               discount_override_pct: 5,
               tarifa_override: 18000,
               ...
             }
          
t=0.8s    Frontend envía:
          ┌─ GET /invoice-preview?discount_override_pct=5&...
          ┌─ UI muestra: loading spinner
          
t=0.9s    Backend recibe, recalcula
          ┌─ room_subtotal = 18000 × 7 = 126000
          ┌─ discount = 126000 × (5/100) = 6300 ← NUEVO
          ┌─ total = 126000 - 6300 = 119700 ← NUEVO
          ┌─ warnings incluye: "Descuento: 5% = $6300"
          
t=1.0s    Frontend recibe respuesta
          ┌─ setInvoicePreview(response.data)
          ┌─ UI actualiza:
             ├─ "Monto Descuentos: -$6,300.00" ← CAMBIÓ
             ├─ "TOTAL: $119,700.00" ← CAMBIÓ
             └─ Warnings panel muestra nuevo warning
          ┌─ Loading spinner desaparece
          
t=1.0s+   Usuario ve totales actualizados automáticamente ✓
```

---

## Warnings Display

Cada override aplicado genera un warning que aparece bajo los cálculos:

```
ADVERTENCIAS (WARNINGS)
═════════════════════════════════════════════════════════════

[ℹ️  INFO]
TARIFA_OVERRIDE: Tarifa modificada: $18000.00/noche

[ℹ️  INFO]
DISCOUNT_OVERRIDE: Descuento aplicado: 15.0% = $18900.00

[ℹ️  INFO]
TAX_OVERRIDE: Régimen de impuesto modificado: Operación exenta

[⚠️  WARNING]
NIGHTS_OVERRIDE: Override de noches aplicado: 7 (calculado: 1)

[⚠️  WARNING]
NIGHTS_DIFFER: Noches calculadas (1) difieren de planificadas (8)
```

### Colores
- 🟢 INFO (ℹ️) → `alert-info` (azul claro)
- 🟡 WARNING (⚠️) → `alert-warning` (amarillo)
- 🔴 ERROR (❌) → `alert-danger` (rojo) - si aplica

---

## Disabled State (Si `invoicePreview?.readonly = true`)

Si la estadía ya está cerrada o marcada como read-only:

```
Noches a cobrar
┌──────────────┐
│      7       │  ← Disabled (gris)
└──────────────┘
Disabled state

Descuentos %
┌──────────────┐
│     15%      │  ← Disabled (gris)
└──────────────┘
Disabled state
```

---

## Mobile Responsiveness

```
Desktop (col-md-3, col-md-4):
┌─────────────────────────────────────────────────────────┐
│ [Noches]    [Tarifa]     [Desc%]    [Modo]  [Impuesto]  │
└─────────────────────────────────────────────────────────┘

Tablet/Mobile (responsive):
┌──────────────────────────┐
│ [Noches]                 │
├──────────────────────────┤
│ [Tarifa]                 │
├──────────────────────────┤
│ [Desc%] [Modo]           │
├──────────────────────────┤
│ [Impuesto Custom]        │
└──────────────────────────┘
```

---

## Integration with Other Steps

### Step 1: Cargos
Los cargos mostrados son del preview calculado.

### Step 2: Pagos
Los pagos se registran normalmente (no cambió).

### Step 3: Confirmación
Se muestra el total final recalculado con todos los overrides.

**Final POST /checkout enviará:**
```json
{
  "stay_id": 1,
  "nights_override": 7,
  "tarifa_override": 18000,
  "discount_override_pct": 15,
  "tax_override_mode": "exento",
  "tax_override_value": null,
  "motivo": "Cliente VIP - Tarifa especial"  ← Usuario debe ingresar
}
```

---

## Summary of Changes

| Elemento | Antes | Después | Status |
|----------|-------|---------|--------|
| Noches a cobrar | Read-only | Editable ✏️ | ✅ |
| Tarifa por noche | Read-only | Editable ✏️ | ✅ |
| Descuentos | Monto fijo | % Editable ✏️ | ✅ NEW |
| Impuestos | Fijo (21%) | Selector ✏️ | ✅ NEW |
| Recálculo | Manual | Automático | ✅ NEW |
| Warnings | No | Sí | ✅ NEW |
| Backend cálculo | No | Sí | ✅ NEW |

---

**Last Updated:** 2025-12-16  
**Component:** CheckoutDrawer in HotelScheduler.jsx  
**Status:** 🟢 Production Ready
