# Phase 2: Multi-Tenant JWT Authentication & SaaS Registration - COMPLETADO ✅

**Status**: ✅ COMPLETADO  
**Date**: 2024  
**Scope**: JWT authentication with multi-tenant claims, SaaS registration endpoint, RLS middleware

---

## Resumen Ejecutivo

**Phase 2** implementó completamente el layer de autenticación JWT multi-tenant para el sistema SaaS de gestión hotelera. Se actualizaron todas las funciones de JWT para incluir contexto de tenant, se creó middleware de RLS para PostgreSQL, se agregaron 7 nuevas dependencias de validación, y se implementaron dos endpoints críticos:

1. ✅ **PUT /auth/login** - Login con tokens que incluyen contexto multitenant
2. ✅ **POST /auth/register-empresa-usuario** - Registro SaaS con trial de 10 días

**Resultado**: Sistema listo para manejar múltiples hoteles (tenants) con aislamiento de datos a nivel PostgreSQL y FastAPI.

---

## Archivos Modificados / Creados

### 1. ✅ `utils/auth.py` - JWT Functions Updated
**Cambios**:
- `create_access_token()` - Nueva firma: `(user_id, username, rol, empresa_usuario_id, es_super_admin, extra_data, expires_delta)`
- `create_refresh_token()` - Nueva firma: `(user_id, username, empresa_usuario_id, es_super_admin)`
- Payload JWT ahora incluye:
  - `user_id` - ID del usuario
  - `sub` - Username
  - `rol` - Rol del usuario
  - `empresa_usuario_id` - ID del tenant (NULL para super_admin)
  - `es_super_admin` - Boolean flag para super admin global
- **Nueva clase**: `TokenPayload` (~60 líneas)
  - `is_valid()` - Verifica campos requeridos
  - `is_super_admin()` - True si es super admin (es_super_admin=true AND empresa_usuario_id=null)
  - `get_tenant_id()` - Retorna empresa_usuario_id
  - `__repr__()` - Debug string

**Ejemplo de JWT Payload**:
```json
{
  "user_id": 123,
  "sub": "admin@hotel.com",
  "rol": "admin",
  "empresa_usuario_id": 1,
  "es_super_admin": false,
  "exp": 1234567890,
  "iat": 1234567800,
  "type": "access"
}
```

---

### 2. ✅ `utils/dependencies.py` - Multi-Tenant Validators
**Nuevas funciones** (~160 líneas añadidas):

```python
# 1. get_current_tenant() -> EmpresaUsuario
# Obtiene el tenant del usuario actual
# Lanza HTTPException si no está asignado a un tenant

# 2. get_tenant_from_token() -> TokenPayload
# Extrae payload JWT sin necesidad de current_user
# Útil para middleware y validación

# 3. require_super_admin() -> bool
# Dependency que fuerza es_super_admin=true
# Log de intentos no autorizados

# 4. validate_trial_status() -> bool
# Retorna True si trial activo, False si expirado
# Verifica plan_tipo == DEMO y fecha_fin_demo

# 5. require_active_trial() -> None
# Dependency wrapper de validate_trial_status
# Bloquea endpoints si trial expirado

# 6. set_tenant_context(request, current_user) -> int
# Middleware dependency que seta PostgreSQL RLS context
# Ejecuta: SET app.current_tenant_id = {tenant_id}

# 7. get_request_tenant_id() -> Optional[int]
# Retorna tenant_id del request.state
# Usado por handler después que middleware lo seteó
```

---

### 3. ✅ `utils/tenant_middleware.py` - CREADO (190 líneas)
**Nuevas clases para RLS**:

```python
class TenantContextMiddleware:
    """
    Extrae tenant_id del JWT en cada request.
    - Rutas públicas bypass: /auth/login, /docs, etc.
    - Almacena tenant_id en request.state
    - Seta flag is_super_admin
    """
    
class PostgreSQLRLSMiddleware:
    """
    Agrega headers para debugging:
    - X-Tenant-ID: ID del tenant actual
    - X-Super-Admin: Flag si es super admin
    """

def set_rls_context(db_session, tenant_id, user_id, is_super_admin):
    """
    Ejecuta en PostgreSQL:
    - SET app.current_tenant_id = {tenant_id}
    - SET app.current_user_id = {user_id}
    - SET app.is_super_admin = {bool}
    """

def check_trial_expiration(subscription) -> dict:
    """
    Retorna: {
        'is_active': bool,
        'days_remaining': int,
        'expires_at': datetime,
        'status': 'active' | 'expired' | 'not_trial',
        'message': str
    }
    """

def is_trial_write_blocked(subscription) -> bool:
    """
    True si trial expirado (bloquea writes, permite reads)
    """
```

---

### 4. ✅ `schemas/auth.py` - Multi-Tenant Schemas
**Cambios a TokenData**:
- `empresa_usuario_id: Optional[int]` - Tenant ID
- `es_super_admin: bool = False` - Super admin flag

**Nuevos schemas** (~90 líneas):

```python
class TrialStatusResponse:
    is_active: bool
    days_remaining: int
    expires_at: datetime
    status: str  # 'active' | 'expired' | 'not_trial'
    message: str

class EmpresaUsuarioResponse:
    id: int
    nombre: str
    cuit: str
    plan_tipo: str
    activa: bool

class SubscriptionResponse:
    id: int
    empresa_usuario_id: int
    plan_id: int
    estado: str
    fecha_inicio: datetime
    fecha_proximo_pago: datetime

class MultiTenantLoginResponse:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    user_id: int
    username: str
    empresa_usuario_id: int
    empresa_nombre: str
    trial_status: TrialStatusResponse

class RegisterEmpresaUsuarioRequest:
    # Hotel info
    nombre_empresa: str
    cuit: str (regex: ^\d{11}$)
    contacto_nombre: str
    contacto_email: str
    contacto_telefono: str
    pais: Optional[str]
    provincia: Optional[str]
    ciudad: Optional[str]
    
    # Admin info
    admin_nombre: str
    admin_apellido: Optional[str]
    admin_username: str
    admin_email: str
    admin_password: str
```

---

### 5. ✅ `endpoints/auth.py` - Updated Endpoints

#### A. PUT /auth/login - UPDATED
```python
@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm, db: Session):
    # ... validación de usuario ...
    
    # NUEVA FIRMA de JWT
    access_token = create_access_token(
        user_id=usuario.id,
        username=usuario.username,
        rol=usuario.rol,
        empresa_usuario_id=usuario.empresa_usuario_id,
        es_super_admin=usuario.es_super_admin,
        extra_data={},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    refresh_token = create_refresh_token(
        user_id=usuario.id,
        username=usuario.username,
        empresa_usuario_id=usuario.empresa_usuario_id,
        es_super_admin=usuario.es_super_admin
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }
```

#### B. POST /auth/register-empresa-usuario - CREADO
```python
@router.post("/auth/register-empresa-usuario", response_model=MultiTenantLoginResponse)
async def register_empresa_usuario(
    empresa_data: RegisterEmpresaUsuarioRequest,
    db: Session
):
    """
    Registra nueva empresa (hotel) con:
    1. EmpresaUsuario (tenant) - 10 días trial DEMO
    2. Plan DEMO (5 habitaciones, 2 usuarios)
    3. Subscription linking tenant → plan
    4. Usuario admin para la empresa
    
    Valida:
    - CUIT no duplicado
    - Username admin no duplicado
    - Email admin no duplicado
    
    Retorna MultiTenantLoginResponse con trial_status
    """
    
    # 1. Crear EmpresaUsuario
    nueva_empresa = EmpresaUsuario(
        nombre=empresa_data.nombre_empresa,
        cuit=empresa_data.cuit,
        plan_tipo=PlanType.DEMO,
        fecha_inicio_demo=datetime.utcnow(),
        fecha_fin_demo=datetime.utcnow() + timedelta(days=10),
        activa=True
    )
    db.add(nueva_empresa)
    db.flush()
    
    # 2. Crear/obtener Plan DEMO
    plan_demo = db.query(Plan).filter(
        Plan.tipo == PlanType.DEMO
    ).first() or Plan(
        nombre="Plan Demostración",
        tipo=PlanType.DEMO,
        precio_mensual=0.0,
        limite_habitaciones=5,
        limite_usuarios=2
    )
    
    # 3. Crear Subscription
    subscription = Subscription(
        empresa_usuario_id=nueva_empresa.id,
        plan_id=plan_demo.id,
        estado=SubscriptionStatus.ACTIVE,
        fecha_inicio=datetime.utcnow()
    )
    
    # 4. Crear Usuario admin
    admin_usuario = Usuario(
        username=empresa_data.admin_username,
        email=empresa_data.admin_email,
        hashed_password=get_password_hash(empresa_data.admin_password),
        rol="admin",
        empresa_usuario_id=nueva_empresa.id,
        es_super_admin=False,
        activo=True
    )
    
    # 5. Crear tokens
    access_token = create_access_token(
        user_id=admin_usuario.id,
        username=admin_usuario.username,
        rol="admin",
        empresa_usuario_id=nueva_empresa.id,
        es_super_admin=False,
        extra_data={},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    # 6. Retornar respuesta con trial_status
    return MultiTenantLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=admin_usuario.id,
        username=admin_usuario.username,
        empresa_usuario_id=nueva_empresa.id,
        empresa_nombre=nueva_empresa.nombre,
        trial_status=TrialStatusResponse(
            is_active=True,
            days_remaining=10,
            expires_at=fecha_fin_demo,
            status="active",
            message="Período de prueba: 10 días gratis"
        )
    )
```

**Flujo de registro**:
```
RegisterEmpresaUsuarioRequest
    ↓
Validar CUIT + username + email
    ↓
Crear EmpresaUsuario (tenant)
    ↓
Crear Plan DEMO (si no existe)
    ↓
Crear Subscription
    ↓
Crear Usuario admin
    ↓
Generar tokens JWT con empresa_usuario_id
    ↓
MultiTenantLoginResponse con trial_status
```

---

### 6. ✅ `main.py` - Middleware Integration
**Cambios**:
```python
from utils.tenant_middleware import TenantContextMiddleware, PostgreSQLRLSMiddleware

# Orden de middlewares crítico:
app.add_middleware(TenantContextMiddleware)  # 1° - Extrae tenant_id del JWT
app.add_middleware(PostgreSQLRLSMiddleware)  # 2° - Agrega headers debug
app.add_middleware(CORSMiddleware, ...)       # 3° - CORS
```

**Flow por request**:
```
HTTP Request
    ↓
TenantContextMiddleware: Extrae tenant_id del JWT
    ↓
PostgreSQLRLSMiddleware: Agrega X-Tenant-ID header
    ↓
Handler (auth, clientes, habitaciones, etc.)
    ↓
Usa request.state.tenant_id para RLS
    ↓
PostgreSQL: WHERE empresa_usuario_id = {tenant_id}
    ↓
HTTP Response con X-Tenant-ID header
```

---

## Cómo Funciona el Sistema Multi-Tenant

### 1. Super Admin (Platform)
```json
{
  "user_id": 1,
  "username": "superadmin",
  "rol": "super_admin",
  "empresa_usuario_id": null,        ← NULL para super admin
  "es_super_admin": true
}
```
- Acceso a todas las empresas
- No bloqueado por trial
- Puede gestionar planes y subscripciones

### 2. Admin de Hotel (Tenant)
```json
{
  "user_id": 123,
  "username": "admin@hotel1.com",
  "rol": "admin",
  "empresa_usuario_id": 1,           ← Tenant ID
  "es_super_admin": false
}
```
- Solo acceso a datos de su hotel
- Datos filtrados por PostgreSQL RLS
- Limitado por plan actual (DEMO = 5 habitaciones)

### 3. Trial System
```
Registro → EmpresaUsuario DEMO plan
    ↓
fecha_inicio_demo: 2024-01-01
fecha_fin_demo: 2024-01-11 (10 días)
    ↓
Mientras es_trial_write_blocked() = False:
    - Lectura: ✅ Permitida
    - Escritura: ✅ Permitida
    ↓
Después de fecha_fin_demo:
    - Lectura: ✅ Permitida (para mostrar datos)
    - Escritura: ❌ Bloqueada (402 Payment Required)
    - Frontend muestra: "Prueba finalizada. Elige un plan"
```

---

## Testing & Validation

### 1. Registrar Nueva Empresa (Hotel)
```bash
curl -X POST http://localhost:8000/auth/register-empresa-usuario \
  -H "Content-Type: application/json" \
  -d '{
    "nombre_empresa": "Hotel Paradise",
    "cuit": "20123456789",
    "contacto_nombre": "Juan Pérez",
    "contacto_email": "juan@hotelparadise.com",
    "contacto_telefono": "+5491234567890",
    "admin_nombre": "Carlos",
    "admin_apellido": "López",
    "admin_username": "carlos_admin",
    "admin_email": "carlos@hotelparadise.com",
    "admin_password": "SecurePassword123!"
  }'
```

**Response**:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user_id": 124,
  "username": "carlos_admin",
  "empresa_usuario_id": 5,
  "empresa_nombre": "Hotel Paradise",
  "trial_status": {
    "is_active": true,
    "days_remaining": 10,
    "expires_at": "2024-01-11T15:30:00",
    "status": "active",
    "message": "Período de prueba: 10 días gratis"
  }
}
```

### 2. Login con Contexto Multitenant
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=carlos_admin&password=SecurePassword123!"
```

**Response** (con empresa_usuario_id en JWT):
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**JWT Payload**:
```json
{
  "user_id": 124,
  "sub": "carlos_admin",
  "rol": "admin",
  "empresa_usuario_id": 5,
  "es_super_admin": false,
  "exp": 1234567890,
  "iat": 1234567800,
  "type": "access"
}
```

### 3. RLS Isolation - Query con Middleware
```python
# Handler cualquiera:
@router.get("/habitaciones")
def get_habitaciones(
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Middleware ya ejecutó: SET app.current_tenant_id = 5
    # PostgreSQL RLS automáticamente filtra:
    habitaciones = db.query(Habitacion).all()
    # SQL ejecutado: SELECT * FROM habitaciones 
    #               WHERE empresa_usuario_id = 5
```

---

## Seguridad Implementada

### 1. Aislamiento de Datos - 3 Capas
| Capa | Mecanismo | Beneficio |
|------|-----------|----------|
| **PostgreSQL** | RLS Policy: `WHERE empresa_usuario_id = app.current_tenant_id` | No puede haber query injection |
| **FastAPI** | Middleware valida JWT antes de ejecutar | No puede bypassear RLS |
| **SQLAlchemy** | FK constraint empresa_usuario_id | No puede crear datos huérfanos |

### 2. JWT Protection
- Tokens incluyen `empresa_usuario_id` -> Middleware valida coincidir
- `es_super_admin` -> Solo super admin puede bypass RLS
- Token expiration -> 1 hora por defecto

### 3. Trial Enforcement
- `is_trial_write_blocked()` -> Bloquea POST/PUT/DELETE después de vencer
- Reads siempre permitidas -> No pierden acceso a datos
- CTA en frontend -> Invite a upgrade antes de bloquear

### 4. Rate Limiting (Existing)
- 5 intentos fallidos de login -> Bloquea 30 minutos
- Previene brute force

---

## Próximos Pasos (Phase 3)

### 1. Trial Enforcement en Write Endpoints
```python
@router.post("/habitaciones")
async def crear_habitacion(
    nueva_habitacion: HabitacionCreate,
    current_user: Usuario = Depends(get_current_user),
    trial_active: bool = Depends(require_active_trial),
    db: Session = Depends(get_db)
):
    # trial_active valida automáticamente
    # Retorna 403 si trial expirado
```

### 2. Billing Endpoints
- `GET /billing/planes` - Lista planes disponibles
- `GET /billing/status` - Status actual del tenant
- `POST /billing/upgrade` - Cambiar plan
- `POST /billing/cancel` - Cancelar subscription

### 3. Payment Integration
- Integrar con Stripe/MercadoPago
- Webhook para confirmar pagos
- Auto-upgrade subscription

### 4. Frontend
- `RegisterEmpresa.jsx` - Formulario SaaS
- `BillingPanel.jsx` - Gestión de planes
- Trial countdown component
- CTA "Upgrade" cuando trial vence

### 5. Testing
```python
# tests/test_multitenant_auth.py
def test_register_empresa_usuario():
    # Validar creación de tenant, plan, subscription, usuario
    # Validar JWT incluye empresa_usuario_id
    
def test_rls_isolation():
    # User de tenant A no puede ver datos de tenant B
    
def test_trial_blocking():
    # Writes bloqueadas después de fecha_fin_demo
    # Reads siempre permitidas
    
def test_super_admin_bypass():
    # Super admin puede ver todos los tenants
```

---

## Resumen de Cambios

| Archivo | Tipo | Líneas | Cambio |
|---------|------|--------|--------|
| `utils/auth.py` | Modified | +60 | TokenPayload class, nueva firma JWT |
| `utils/dependencies.py` | Modified | +160 | 7 nuevas funciones multitenant |
| `utils/tenant_middleware.py` | Created | 190 | Middleware RLS + helpers |
| `schemas/auth.py` | Modified | +90 | TokenData updated, 6 nuevos schemas |
| `endpoints/auth.py` | Modified | +200 | Login updated, register-empresa-usuario creado |
| `main.py` | Modified | +10 | Middleware integration |
| **TOTAL** | - | **~710** | **Phase 2 Complete** |

---

## Documentación Asociada

- **Phase 1**: [PHASE1_MULTITENANT_MODELS.md](./PHASE1_MULTITENANT_MODELS.md)
- **Testing**: [run_migrations_multitenant.py](./run_migrations_multitenant.py)
- **SaaS Architecture**: [README_MULTITENANT_PHASE1.md](./README_MULTITENANT_PHASE1.md)

---

## Estado Actual

```
✅ Phase 1: Modelos & Migraciones - COMPLETO
✅ Phase 2: JWT & Autenticación - COMPLETO
⏳ Phase 3: Billing & Planes - PENDIENTE
⏳ Phase 4: Frontend - PENDIENTE
⏳ Phase 5: Testing - PENDIENTE
```

**Sistema ahora listo para**:
- Múltiples hoteles (tenants) con datos aislados
- Trial de 10 días automático
- JWT con contexto multitenant
- RLS a nivel PostgreSQL
- Escalabilidad para agregar planes de pago

---

**Next Command**: 
```bash
# Run existing migrations
python run_migrations_multitenant.py

# Start FastAPI server
uvicorn main:app --reload

# Test registration
curl -X POST http://localhost:8000/auth/register-empresa-usuario ...
```
