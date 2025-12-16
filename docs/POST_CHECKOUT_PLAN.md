# 📝 POST /checkout Implementation Plan

## Overview

Después de que el usuario ajusta los overrides y confirma el checkout en el wizard, debe ocurrir:

1. **Frontend:** Captura todos los overrides + motivo
2. **POST /checkout:** Envía datos al backend
3. **Backend:** Persiste la factura final, líneas, auditoría
4. **Response:** Confirma éxito (cierra la estadía, genera recibo)

---

## 📡 API Endpoint Specification

### POST /api/calendar/stays/{stay_id}/checkout

**Request Body:**
```json
{
  "nights_override": 7,                               // Optional
  "tarifa_override": 18000.0,                         // Optional
  "discount_override_pct": 15.0,                      // Optional
  "tax_override_mode": "exento",                      // Optional: normal|exento|custom
  "tax_override_value": null,                         // Optional: if mode=custom
  "motivo_override": "Cliente VIP - Tarifa especial", // Required: reason for overrides
  "housekeeping": true,                               // Optional: housekeeping charge?
  "payments": [                                        // Optional: payments applied
    {
      "monto": 50000,
      "metodo": "tarjeta",
      "referencia": "TXID-12345"
    }
  ]
}
```

**Query Parameters:**
```
include_pdf: bool (default: false)  # Generate PDF receipt
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Checkout completado",
  "stay_id": 1,
  "invoice": {
    "id": "INV-2025-00001",
    "date_created": "2025-12-16T10:30:00Z",
    "stay_id": 1,
    "client": { ... },
    "total": 107100.0,
    "paid": 50000.0,
    "balance": 57100.0,
    "lines": [ ... ],
    "overrides_applied": [
      {
        "type": "tarifa",
        "original": 20000,
        "override": 18000,
        "reason": "Cliente VIP - Tarifa especial"
      },
      ...
    ],
    "audit": {
      "modified_by": "user@hotel.com",
      "modified_at": "2025-12-16T10:30:00Z",
      "notes": "Cliente VIP - Tarifa especial"
    }
  },
  "pdf_url": "/api/invoices/INV-2025-00001.pdf"  // if include_pdf=true
}
```

---

## 🗄️ Database Changes Needed

### 1. Create `InvoiceHeader` Table
```python
class InvoiceHeader(Base):
    __tablename__ = "invoice_headers"
    
    id = Column(Integer, primary_key=True)
    invoice_number = Column(String(20), unique=True)
    date_created = Column(DateTime, default=datetime.utcnow)
    stay_id = Column(Integer, ForeignKey("stays.id"))
    
    total = Column(Float)  # Grand total
    paid = Column(Float)   # Amount paid
    balance = Column(Float)  # Still due
    
    status = Column(String(20), default="draft")  # draft|final|paid
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    # Relations
    stay = relationship("Stay", back_populates="invoice")
    lines = relationship("InvoiceLine", back_populates="invoice")
    overrides = relationship("InvoiceOverride", back_populates="invoice")
```

### 2. Create `InvoiceLine` Table
```python
class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoice_headers.id"))
    
    description = Column(String(255))
    line_type = Column(String(30))  # room|charge|discount|tax|payment
    
    quantity = Column(Float)
    unit_price = Column(Float)
    amount = Column(Float)
    
    # Metadata
    metadata = Column(JSON)  # Override info, etc
    
    # Relation
    invoice = relationship("InvoiceHeader", back_populates="lines")
```

### 3. Create `InvoiceOverride` Table
```python
class InvoiceOverride(Base):
    __tablename__ = "invoice_overrides"
    
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoice_headers.id"))
    
    override_type = Column(String(30))  # tarifa|nights|discount|tax
    original_value = Column(Float)
    override_value = Column(Float)
    reason = Column(String(255))
    
    # Audit
    applied_by = Column(String(100))
    applied_at = Column(DateTime, default=datetime.utcnow)
    
    # Relation
    invoice = relationship("InvoiceHeader", back_populates="overrides")
```

### 4. Modify `Stay` Table
```python
# Add to Stay model:
invoice_id = Column(Integer, ForeignKey("invoice_headers.id"))
closed_by = Column(String(100))  # User who closed
closed_at = Column(DateTime)

# Add relation
invoice = relationship("InvoiceHeader", back_populates="stay")
```

---

## 🔧 Backend Implementation Steps

### Step 1: Create Migration
```bash
# In Backend_Hotel/
alembic revision --autogenerate -m "Add invoice tables for checkout"
alembic upgrade head
```

### Step 2: Create Schemas
```python
# schemas/invoices.py

class InvoiceLineResponse(BaseModel):
    description: str
    line_type: str
    quantity: float
    unit_price: float
    amount: float
    metadata: Optional[Dict] = None

class InvoiceOverrideResponse(BaseModel):
    override_type: str
    original_value: float
    override_value: float
    reason: str
    applied_at: datetime

class InvoiceResponse(BaseModel):
    id: str
    invoice_number: str
    stay_id: int
    total: float
    paid: float
    balance: float
    lines: List[InvoiceLineResponse]
    overrides: List[InvoiceOverrideResponse]
    created_at: datetime
    
class CheckoutRequest(BaseModel):
    nights_override: Optional[int] = None
    tarifa_override: Optional[float] = None
    discount_override_pct: Optional[float] = None
    tax_override_mode: Optional[str] = None
    tax_override_value: Optional[float] = None
    motivo_override: str  # REQUIRED
    housekeeping: Optional[bool] = False
    payments: Optional[List[PaymentCreate]] = []

class CheckoutResponse(BaseModel):
    success: bool
    message: str
    stay_id: int
    invoice: InvoiceResponse
    pdf_url: Optional[str] = None
```

### Step 3: Implement Endpoint
```python
# endpoints/hotel_calendar.py

@router.post("/stays/{stay_id}/checkout", response_model=CheckoutResponse)
def checkout_stay(
    stay_id: int = Path(..., gt=0),
    request: CheckoutRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    🧾 CHECKOUT (Finalize Stay & Persist Invoice)
    
    - Validates all override parameters
    - Recalculates invoice (same logic as GET preview)
    - Persists invoice to database
    - Records audit trail
    - Closes the stay
    - Returns invoice and optional PDF
    """
    
    # 1. Load stay + validate
    stay = db.query(Stay).filter(Stay.id == stay_id).first()
    if not stay:
        raise HTTPException(404, f"Stay {stay_id} not found")
    
    if stay.estado == "cerrada":
        raise HTTPException(400, "Stay already closed")
    
    # 2. Validate motivo_override
    if not request.motivo_override or not request.motivo_override.strip():
        raise HTTPException(400, "motivo_override is required")
    
    # 3. Get invoice preview with overrides
    preview = _calculate_invoice_preview(
        stay=stay,
        db=db,
        nights_override=request.nights_override,
        tarifa_override=request.tarifa_override,
        discount_override_pct=request.discount_override_pct,
        tax_override_mode=request.tax_override_mode,
        tax_override_value=request.tax_override_value,
        include_items=True
    )
    
    # 4. Create InvoiceHeader
    invoice_number = _generate_invoice_number(db)
    invoice = InvoiceHeader(
        invoice_number=invoice_number,
        stay_id=stay_id,
        total=preview.totals.grand_total,
        paid=sum(p.monto for p in request.payments or []),
        balance=preview.totals.balance,
        status="final"
    )
    db.add(invoice)
    db.flush()
    
    # 5. Create InvoiceLines from preview.breakdown_lines
    for line in preview.breakdown_lines:
        invoice_line = InvoiceLine(
            invoice_id=invoice.id,
            description=line.description,
            line_type=line.type,
            quantity=line.quantity,
            unit_price=line.unit_price,
            amount=line.amount,
            metadata=line.metadata
        )
        db.add(invoice_line)
    
    # 6. Record InvoiceOverrides
    if request.nights_override:
        override = InvoiceOverride(
            invoice_id=invoice.id,
            override_type="nights",
            original_value=stay.nights_calculated,
            override_value=request.nights_override,
            reason=request.motivo_override,
            applied_by=current_user.get("email")
        )
        db.add(override)
    
    if request.tarifa_override:
        override = InvoiceOverride(
            invoice_id=invoice.id,
            override_type="tarifa",
            original_value=stay.nightly_rate or 0,
            override_value=request.tarifa_override,
            reason=request.motivo_override,
            applied_by=current_user.get("email")
        )
        db.add(override)
    
    # ... similar for discount and tax overrides ...
    
    # 7. Record payments
    for payment_req in request.payments or []:
        payment = StayPayment(
            stay_id=stay_id,
            monto=payment_req.monto,
            metodo_pago=payment_req.metodo,
            referencia=payment_req.referencia,
            fecha=datetime.utcnow()
        )
        db.add(payment)
    
    # 8. Update stay status
    stay.estado = "cerrada"
    stay.invoice_id = invoice.id
    stay.closed_by = current_user.get("email")
    stay.closed_at = datetime.utcnow()
    
    # 9. Commit everything
    db.commit()
    
    # 10. Generate PDF if requested
    pdf_url = None
    if Query.include_pdf:
        pdf_url = _generate_invoice_pdf(invoice, db)
    
    # 11. Return response
    return CheckoutResponse(
        success=True,
        message="Checkout completado",
        stay_id=stay_id,
        invoice=InvoiceResponse.from_orm(invoice),
        pdf_url=pdf_url
    )
```

---

## 💻 Frontend Implementation Steps

### Step 1: Add Motivo Input Field
En CheckoutDrawer Step 3 (Confirmación), agregar:

```jsx
// Antes del botón "Confirmar"
<div className="form-group mb-3">
  <label className="form-label fw-bold">Motivo del ajuste</label>
  <textarea
    className="form-control"
    rows="3"
    placeholder="Ej: Cliente VIP, tarifa especial por largo plazo, etc."
    value={motivoOverride}
    onChange={(e) => setMotivoOverride(e.target.value)}
    required
  />
  <small className="text-muted">
    Requerido si aplicó algún override
  </small>
</div>
```

### Step 2: Create POST Call
```javascript
const handleCheckout = async () => {
  // Validar que hay motivo si hay overrides
  const hasOverrides = 
    nochesCobradas !== stayBlock.nights ||
    tarifaNoche ||
    discountPercentage ||
    taxMode !== 'normal'
  
  if (hasOverrides && !motivoOverride.trim()) {
    showAlert('Checkout', 'Ingresa el motivo del ajuste', 'warning')
    return
  }
  
  // Construir request
  const checkoutData = {
    nights_override: nochesCobradas,
    tarifa_override: tarifaNoche ? parseFloat(tarifaNoche) : null,
    discount_override_pct: discountPercentage,
    tax_override_mode: taxMode,
    tax_override_value: taxCustomValue,
    motivo_override: motivoOverride || 'Sin especificar',
    housekeeping: housekeeping,
    payments: payments
  }
  
  // Enviar POST
  try {
    const result = await staysService.checkout(stayId, checkoutData)
    if (result.success) {
      showAlert('Checkout', 'Estadía cerrada exitosamente', 'success')
      // Descargar PDF si está disponible
      if (result.pdf_url) {
        window.open(result.pdf_url, '_blank')
      }
      onClose() // Cerrar drawer
    } else {
      showAlert('Error', result.error, 'danger')
    }
  } catch (error) {
    showAlert('Error', error.message, 'danger')
  }
}
```

### Step 3: Add Service Method
```javascript
// roomsService.js

async checkout(stayId, checkoutData) {
  try {
    const response = await axios.post(
      `${CALENDAR_BASE}/stays/${stayId}/checkout`,
      checkoutData
    )
    return { success: true, ...response.data }
  } catch (error) {
    return { 
      success: false, 
      error: error.response?.data?.detail || error.message 
    }
  }
}
```

---

## 📊 Testing Plan

### Backend Test
```python
# test_checkout_endpoint.py

def test_checkout_with_overrides():
    """Verify checkout persists overrides correctly"""
    
    # 1. POST /checkout with all overrides
    response = client.post(
        f"/api/calendar/stays/1/checkout",
        json={
            "nights_override": 7,
            "tarifa_override": 18000,
            "discount_override_pct": 15,
            "tax_override_mode": "exento",
            "motivo_override": "Cliente VIP",
            "payments": [{"monto": 50000, "metodo": "tarjeta"}]
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["success"] == True
    assert data["invoice"]["total"] == 107100.0
    assert data["invoice"]["paid"] == 50000.0
    assert len(data["invoice"]["overrides"]) == 4
    
    # 2. Verify stay is closed
    stay = db.query(Stay).get(1)
    assert stay.estado == "cerrada"
    assert stay.invoice_id == data["invoice"]["id"]
    
    print("✅ Checkout test passed")
```

---

## 🚀 Implementation Timeline

| Tarea | Duración | Status |
|-------|----------|--------|
| Crear migrations | 15 min | ⏳ |
| Crear schemas | 30 min | ⏳ |
| Implementar endpoint | 45 min | ⏳ |
| Testing backend | 30 min | ⏳ |
| Frontend motivo field | 15 min | ⏳ |
| POST call implementation | 30 min | ⏳ |
| Testing frontend | 20 min | ⏳ |
| **TOTAL** | **3.25 hrs** | ⏳ |

---

## 📋 Checklist

- [ ] Database migrations created
- [ ] Models updated (InvoiceHeader, InvoiceLine, InvoiceOverride)
- [ ] Schemas created (InvoiceResponse, CheckoutRequest, etc)
- [ ] Endpoint implemented (POST /checkout)
- [ ] Override recording logic working
- [ ] Audit trail implemented
- [ ] Backend tests passing
- [ ] Frontend motivo field added
- [ ] Service method added
- [ ] Frontend tests passing
- [ ] PDF generation (optional)
- [ ] Email notification (optional)

---

## 🔐 Security Considerations

1. **Permission Check:** Only managers/admin can apply overrides
2. **Motivo Required:** Must provide reason for audit trail
3. **Validation:** All overrides validated (ranges, types)
4. **Audit Trail:** Who, when, what, why - all recorded
5. **Stay Status:** Can't checkout a closed stay
6. **User Context:** Record which user made the adjustment

---

## 📚 Related Documentation

- `OVERRIDE_SYSTEM.md` - System overview
- `OVERRIDE_IMPLEMENTATION_SUMMARY.md` - Current status
- `INVOICE_PREVIEW_ENDPOINT.md` - Preview endpoint details

---

**Status:** 🟡 NOT STARTED  
**Priority:** HIGH  
**Blocking:** Final invoice persistence, audit trail  
**Next Step:** Start with database migrations
