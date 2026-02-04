# 🚀 Phase 3B Quick Reference - Stripe Integration

## ✅ What Was Done

### 1. Configuration Management
```python
# Backend_Hotel/config.py
from os import getenv

STRIPE_SECRET_KEY = getenv("STRIPE_SECRET_KEY", "sk_test_dummy_key")
STRIPE_PUBLISHABLE_KEY = getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_dummy_key")
STRIPE_WEBHOOK_SECRET = getenv("STRIPE_WEBHOOK_SECRET", "whsec_test_dummy_secret")

def get_stripe_client():
    """Returns Stripe client if configured"""
    if is_stripe_configured():
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        return stripe
    return None

def is_stripe_configured():
    """Check if Stripe keys are valid"""
    return (STRIPE_SECRET_KEY and not STRIPE_SECRET_KEY.startswith("sk_test_dummy"))
```

### 2. Payment Intent Endpoint
```python
# Backend_Hotel/endpoints/billing.py

@router.post("/payment-intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    request_data: PaymentIntentRequest,  # { "plan_type": "basico" }
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(conexion.get_db)
):
    # 1. Validate user is tenant (not super admin)
    # 2. Get plan details
    # 3. Calculate amount
    # 4. Create Stripe PaymentIntent (or return demo data)
    # 5. Return client_secret + publishable_key
    return PaymentIntentResponse(...)
```

### 3. Webhook Endpoint
```python
@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(conexion.get_db)
):
    # 1. Get payload and signature
    # 2. Verify signature (HMAC-SHA256)
    # 3. Parse event
    # 4. Dispatch based on event type:
    #    - payment_intent.succeeded → upgrade subscription
    #    - payment_intent.payment_failed → log failure
    #    - charge.refunded → log refund
    # 5. Return 200 OK
    return {"status": "received", "event_type": event["type"]}
```

### 4. Event Handlers
```python
async def _handle_payment_succeeded(intent, db):
    # Update subscription to new plan (ACTIVO status)
    # Set renewal date 30 days from now
    # Create PaymentAttempt record
    # Log success event

async def _handle_payment_failed(intent, db):
    # Create PaymentAttempt record with FAILED status
    # Keep subscription on current plan (no downgrade)
    # Log failure for support

async def _handle_refund(charge, db):
    # Log refund event
    # Update audit trail
```

## 📋 Files Changed

### Created (2)
- ✅ `config.py` - Stripe configuration
- ✅ `test_stripe_integration.py` - Integration tests

### Updated (1)
- ✅ `endpoints/billing.py` - Added payment endpoints (+390 lines)

### Documentation (3)
- ✅ `PHASE_3B_COMPLETE.md` - Full implementation guide
- ✅ `PHASE_3B_SUMMARY.md` - Executive summary
- ✅ `PHASE_3B_VERIFICATION.md` - Verification checklist

## 🔌 API Reference

### Request: Create Payment Intent
```http
POST /billing/payment-intent
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json

{
  "plan_type": "basico"
}
```

### Response: Payment Intent
```json
{
  "client_secret": "pi_1234567890_secret_abcdef",
  "publishable_key": "pk_test_1234567890abcdef",
  "amount": 29.99,
  "currency": "usd",
  "plan": {
    "id": 2,
    "nombre": "BASICO",
    "tipo": "basico",
    "precio_mensual": 29.99,
    "limite_habitaciones": 50,
    "limite_usuarios": 10,
    "permite_facturacion": true,
    "permite_reportes": true,
    "soporte_email": true
  },
  "billing_period_days": 30
}
```

### Webhook: Stripe Event
```http
POST /billing/webhook/stripe
stripe-signature: t=1234567890,v1=abc123...

{
  "id": "evt_1234567890",
  "type": "payment_intent.succeeded",
  "data": {
    "object": {
      "id": "pi_1234567890",
      "amount": 2999,
      "currency": "usd",
      "metadata": {
        "empresa_usuario_id": "1",
        "plan_type": "basico",
        "user_id": "5",
        "usuario_email": "admin@hotel.com"
      }
    }
  }
}
```

## 🛠️ Environment Setup

### Development (without Stripe)
```bash
# Leave defaults or set dummy values
export STRIPE_SECRET_KEY=sk_test_dummy
export STRIPE_PUBLISHABLE_KEY=pk_test_dummy
export STRIPE_WEBHOOK_SECRET=whsec_test_dummy

python main.py
# Payment intents work but use demo mode
```

### Production (with Stripe)
```bash
# Get from Stripe Dashboard
export STRIPE_SECRET_KEY=sk_live_abc123xyz789...
export STRIPE_PUBLISHABLE_KEY=pk_live_abc123xyz789...
export STRIPE_WEBHOOK_SECRET=whsec_1234567890abc...

# Configure Stripe Dashboard webhook URL
# https://yourdomain.com/billing/webhook/stripe
```

## 🧪 Testing

### Test Payment Intent Creation
```bash
curl -X POST http://localhost:8000/billing/payment-intent \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"plan_type":"basico"}'

# Should return client_secret in demo mode
```

### Test Webhook Locally (Stripe CLI)
```bash
# Terminal 1: Run backend
python main.py

# Terminal 2: Setup Stripe CLI forwarding
stripe listen --forward-to localhost:8000/billing/webhook/stripe

# Terminal 3: Trigger test event
stripe trigger payment_intent.succeeded

# Check backend logs for "Payment succeeded" event
```

## 📊 Database Impact

### New Records Created
- **PaymentAttempt** records on each payment attempt
  - Created with EXITOSO status on success
  - Created with FALLIDO status on failure
  - Contains: subscription_id, monto, estado, proveedor, external_id, response_json

### Updated Records
- **Subscription** on successful payment
  - plan_id updated to new plan
  - estado set to ACTIVO
  - fecha_proxima_renovacion updated to +30 days

### Unchanged
- **EmpresaUsuario** (no changes)
- **Plan** (no changes)
- **Usuario** (no changes)

## 🔒 Security Notes

### Webhook Security
- All Stripe events verified with HMAC-SHA256 signature
- Invalid signatures rejected (400 Bad Request)
- Prevents webhook spoofing attacks

### Payment Security
- Card data never stored in database
- Stripe handles PCI DSS compliance
- Only payment intent IDs stored
- Error messages don't leak card numbers

### Tenant Isolation
- Each payment tied to empresa_usuario_id
- Subscription queries filtered by tenant
- No cross-tenant payment processing

## 🐛 Error Handling

### Common Errors

| Status | Error | Cause | Fix |
|--------|-------|-------|-----|
| 400 | Invalid payload | Malformed webhook JSON | Verify Stripe event format |
| 400 | Invalid signature | Wrong STRIPE_WEBHOOK_SECRET | Check .env variables |
| 403 | Super admin cannot create intent | User is super_admin | Use tenant account |
| 404 | Plan not found | Invalid plan_type | Use DEMO, BASICO, or PREMIUM |
| 404 | Subscription not found | No subscription for tenant | Run registration endpoint first |
| 500 | Error creating payment intent | Stripe API error | Check Stripe keys, retry |

## 📈 Monitoring

### Events to Monitor
- `payment_intent.succeeded` - Track successful upgrades
- `payment_intent.payment_failed` - Track failed payments
- Webhook errors in logs - Track webhook issues

### Key Metrics
- Payment success rate (EXITOSO / total attempts)
- Average payment amount by plan
- Webhook response time
- Plan upgrade frequency

## ✅ Checklist Before Going Live

- [ ] STRIPE_SECRET_KEY set in production
- [ ] STRIPE_PUBLISHABLE_KEY set in production
- [ ] STRIPE_WEBHOOK_SECRET set in production
- [ ] Webhook URL configured in Stripe Dashboard
- [ ] HTTPS enabled on production domain
- [ ] Database migrated (models/migrations applied)
- [ ] Email notifications configured (for future)
- [ ] Logging monitored for errors
- [ ] Stripe test payments verified
- [ ] Invoice generation configured (optional)
- [ ] Dunning management configured (optional)
- [ ] Refund handling tested
- [ ] Trial period enforcement verified

## 🚀 Next Steps

1. **Phase 3C**: Plan limits enforcement on existing endpoints
2. **Phase 4**: Frontend payment UI with Stripe.js
3. **Phase 5**: End-to-end testing and QA
4. **Phase 6**: Email notifications (optional)
5. **Phase 7**: Analytics dashboard (optional)

---

**Quick Links:**
- Stripe Docs: https://stripe.com/docs
- PaymentIntent API: https://stripe.com/docs/api/payment_intents
- Webhook Events: https://stripe.com/docs/api/events
- Testing: https://stripe.com/docs/testing

**Status**: ✅ COMPLETE - Ready for frontend integration

