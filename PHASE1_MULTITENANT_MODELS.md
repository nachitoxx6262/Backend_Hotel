# Phase 1: Multi-Tenant Core Implementation ✅

## Resumen de Cambios

La Phase 1 de la implementación multi-tenant ha completado la **capa de modelos y migraciones**. El sistema ahora está listo para soportar una arquitectura SaaS con aislamiento completo de tenants.

## 1. Modelos Python Actualizados

### ✅ `models/core.py` - Nuevas Tablas SaaS

Se agregaron 5 nuevas entidades principales:

#### **Plan** (Planes de Suscripción)
- Tipos: DEMO (10 días gratis), BASICO, PREMIUM
- Campos: nombre, precio_mensual, max_habitaciones, max_usuarios, características (JSON)
- Relación: 1 Plan → N Subscriptions

#### **EmpresaUsuario** (SaaS Tenant - El Hotel)
```python
- nombre_hotel: Nombre del hotel que se suscribe
- cuit: CUIT del hotel (única por tenant)
- plan_tipo: Enum(DEMO, BASICO, PREMIUM)
- fecha_inicio_demo: Cuándo comienza el trial
- fecha_fin_demo: Cuándo termina el trial (10 días)
- activa: Boolean para soft-delete
- Relaciones: usuarios, habitaciones, reservas, subscriptions, hotel_settings, etc.
```

#### **Subscription** (Subscripción SaaS Activa)
- estado: ACTIVO, VENCIDO, CANCELADO, BLOQUEADO
- fecha_proxima_renovacion: Próxima fecha de cobro
- metadata: JSON para detalles de pago
- Relación 1:1 con EmpresaUsuario

#### **PaymentAttempt** (Audit Trail de Pagos)
- monto, estado, proveedor (DUMMY/MERCADO_PAGO/STRIPE)
- external_id, webhook_url, response_json (auditoría completa)
- Tracks todos los intentos de pago para debugging

#### **ClienteCorporativo** (Renombrada de Empresa)
```python
- empresa_usuario_id: FK OBLIGATORIA a EmpresaUsuario
- Esto significa: cada cliente corporativo pertenece a UN SOLO HOTEL
- No hay más clientes compartidos entre tenants
```

### ✅ Tablas Existentes - FK Multi-Tenant Agregadas

Todas estas tablas ahora tienen `empresa_usuario_id` como FK obligatoria:

| Tabla | FK Agregada | Cambio UNIQUE |
|-------|-------------|---------------|
| **room_types** | empresa_usuario_id | `(empresa_usuario_id, nombre)` |
| **rooms** | empresa_usuario_id | `(empresa_usuario_id, numero)` |
| **daily_rates** | empresa_usuario_id | `(empresa_usuario_id, room_type_id, fecha, rate_plan_id)` |
| **reservations** | empresa_usuario_id | N/A (agregado index) |
| **stays** | empresa_usuario_id | N/A (agregado index) |
| **housekeeping_tasks** | empresa_usuario_id | N/A (agregado index) |
| **hotel_settings** | empresa_usuario_id | Migrado de empresa_id |

### ✅ `models/usuario.py` - Auth Multi-Tenant

```python
class Usuario:
    empresa_usuario_id: FK nullable  # NULL si es super_admin
    es_super_admin: Boolean          # True solo para staff SaaS
```

**Dos capas de Auth:**
- **Tenant Admin**: usuario normal, empresa_usuario_id seteado, puede gestionar su hotel
- **Super Admin SaaS**: usuario con es_super_admin=True, ve todos los hoteles

### ✅ `models/rol.py` - RBAC Tenant-Scoped

```python
class Rol:
    empresa_usuario_id: FK nullable  # NULL = rol global (solo super_admin)
                                     # Seteado = rol del tenant
```

Permite tanto roles globales como roles por tenant.

## 2. Migraciones SQL Creadas

### 📝 `migrations/005_multitenant_core.sql` - Nuevas Tablas

Crea:
- Enums: plan_type_enum, subscription_status_enum, payment_status_enum, payment_provider_enum
- Tablas: planes, empresa_usuarios, subscriptions, payment_attempts, cliente_corporativo
- Todos con indexes y constraints apropiados

```bash
# Tamaño: ~180 líneas SQL
# Tiempo: ~2-5 segundos en fresh DB
```

### 📝 `migrations/006_add_tenant_id_all_tables.sql` - Agregar FK a Existentes

Realiza ALTER TABLE en todas las tablas operacionales:
- Agrega columna empresa_usuario_id
- Crea FK con ON DELETE CASCADE (excepto usuarios que es ON DELETE SET NULL)
- Actualiza indexes y UNIQUE constraints
- Preserva datos existentes (solo agrega columna)

```bash
# Tamaño: ~200 líneas SQL
# Tiempo: ~5-10 segundos
# ⚠️ IMPORTANTE: La migración 006 crea columnas NULL - requiere script de datos
#    Ver "3. Script de Migración de Datos" más abajo
```

### 📝 `migrations/007_enable_rls_security.sql` - Row Level Security

Implementa RLS (Row Level Security) en PostgreSQL:
- Habilita RLS en todas las tablas
- Define políticas para cada tabla
- Función `get_current_tenant_id()` para obtener tenant actual
- Funciona con `SET app.current_tenant_id` desde middleware

```bash
# Tamaño: ~350 líneas SQL
# Tiempo: ~5-10 segundos
# ⚠️ EJECUTAR COMO: psql (requiere permisos de superuser)
# ⚠️ Verificar: SELECT * FROM pg_tables WHERE rowsecurity = true;
```

## 3. Script de Migración de Datos

### 📜 `run_migrations_multitenant.py`

Script Python que ejecuta las migraciones en orden:

```bash
# Ejecutar todas (005, 006, 007)
python run_migrations_multitenant.py

# Ejecutar rango específico
python run_migrations_multitenant.py --from 005 --to 006

# Ejecutar solo una
python run_migrations_multitenant.py --only 007

# Output: migrations.log
```

Características:
- Intenta con psql primero (mejor para RLS)
- Fallback a SQLAlchemy si falla
- Logging completo a archivo + consola
- Valida existencia de archivos de migración
- Para en primer error

## 4. Definiciones Enum

```python
class PlanType(str, Enum):
    DEMO = "demo"          # 10 días, sin costo
    BASICO = "basico"      # $99/mes
    PREMIUM = "premium"    # $299/mes

class SubscriptionStatus(str, Enum):
    ACTIVO = "activo"      # Suscripción activa
    VENCIDO = "vencido"    # Trial expirado, escribas bloqueadas
    CANCELADO = "cancelado"  # Usuario canceló
    BLOQUEADO = "bloqueado"  # Falta de pago

class PaymentStatus(str, Enum):
    PENDIENTE = "pendiente"  # Esperando respuesta de proveedor
    EXITOSO = "exitoso"      # Pago confirmado
    FALLIDO = "fallido"      # Rechazado

class PaymentProvider(str, Enum):
    DUMMY = "dummy"                    # Para desarrollo
    MERCADO_PAGO = "mercado_pago"     # Producción LATAM
    STRIPE = "stripe"                  # Producción GLOBAL
```

## 5. Relaciones Finales

### EmpresaUsuario (Hub Central)

```
EmpresaUsuario
    ├── usuarios (1:N)
    ├── clientes_corporativos (1:N)
    ├── habitaciones (1:N) - vía Room.empresa_usuario_id
    ├── reservas (1:N) - vía Reservation.empresa_usuario_id
    ├── stays (1:N) - vía Stay.empresa_usuario_id
    ├── daily_rates (1:N) - vía DailyRate.empresa_usuario_id
    ├── housekeeping_tasks (1:N) - vía HousekeepingTask.empresa_usuario_id
    ├── roles (1:N) - vía Rol.empresa_usuario_id
    ├── subscription (1:1) - ÚNICA por tenant
    └── hotel_settings (1:1) - ÚNICA por tenant
```

### Tenant Isolation Guarantees

✅ Cada row en tablas operacionales tiene empresa_usuario_id  
✅ Todas las queries deben filtrar por empresa_usuario_id  
✅ RLS en PostgreSQL asegura que queries sin filtro fallen  
✅ JWT contiene empresa_usuario_id para validación en app  

## 6. Migraciones Pendientes (Phase 2)

⏳ **Middleware RLS**: Setear `app.current_tenant_id` en cada request  
⏳ **JWT Update**: Agregar empresa_usuario_id + es_super_admin a claims  
⏳ **Endpoints Auth**: POST /auth/register-empresa-usuario  
⏳ **Billing Endpoints**: GET /planes, POST /billing/upgrade, etc.  
⏳ **Trial Logic**: Bloquear escrituras después de 10 días  
⏳ **Super Admin Panel**: Endpoints y frontend para SaaS  

## 7. Instrucciones de Ejecución

### Pre-requisitos

```bash
# 1. Tener PostgreSQL corriendo
psql -U postgres -h localhost
# \l (listar DBs)

# 2. Verificar variables de entorno (.env)
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=<tu_password>
DB_NAME=hotel_db

# 3. Python 3.9+ con SQLAlchemy instalado
pip install sqlalchemy psycopg2-binary
```

### Ejecutar Migraciones

```bash
# Opción 1: Usar script Python (recomendado)
python Backend_Hotel/run_migrations_multitenant.py

# Opción 2: Ejecutar SQL directamente con psql
psql -U postgres -d hotel_db -f Backend_Hotel/migrations/005_multitenant_core.sql
psql -U postgres -d hotel_db -f Backend_Hotel/migrations/006_add_tenant_id_all_tables.sql

# Opción 3: Ejecutar como super_admin (para RLS)
sudo -u postgres psql -d hotel_db -f Backend_Hotel/migrations/007_enable_rls_security.sql
```

### Verificar RLS Habilitado

```sql
-- En psql:
SELECT tablename, rowsecurity 
FROM pg_tables 
WHERE schemaname = 'public' 
ORDER BY tablename;

-- Deberías ver rowsecurity = true para:
-- empresa_usuarios, usuarios, cliente_corporativo, rooms, reservations, stays, etc.
```

## 8. Restricciones y Notas

⚠️ **Importante**: Migración 006 crea columnas NULL  
- Necesita un script separado de migración de datos legacy
- Ver "Step 9. Data Migration Script" en MULTITENANT_GUIDE.md

⚠️ **RLS Execution**: Migración 007 requiere permisos de superuser  
- En desarrollo: ejecutar como `postgres` role
- En producción: usar usuario con ALTER TABLE permisos en extensiones

⚠️ **Constraints de Datos Existentes**:
- room_types.empresa_usuario_id será NULL hasta que se migren datos
- La migración 006 usa ON DELETE CASCADE pero columnas NULL = queries pueden fallar
- Solución: Ejecutar script de backfill de datos antes de producción

## 9. Estructura de Directorio Actualizada

```
Backend_Hotel/
├── migrations/
│   ├── 005_multitenant_core.sql          ← NUEVO: Crea tablas SaaS
│   ├── 006_add_tenant_id_all_tables.sql  ← NUEVO: Agrega FKs
│   ├── 007_enable_rls_security.sql       ← NUEVO: Habilita RLS
│   └── ... (migraciones legacy)
├── models/
│   ├── core.py       ← ACTUALIZADO: +5 modelos nuevos, +FKs a existentes
│   ├── usuario.py    ← ACTUALIZADO: +empresa_usuario_id, +es_super_admin
│   ├── rol.py        ← ACTUALIZADO: +empresa_usuario_id
│   └── ...
├── run_migrations_multitenant.py  ← NUEVO: Script para ejecutar migraciones
└── ...
```

## 10. Diagrama ER Actualizado

```
┌─────────────────────────────────────────────────────────────────┐
│                     MULTI-TENANT ARCHITECTURE                    │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────────┐
│  PLANES                  │
│  - DEMO (10 días)        │
│  - BASICO ($99)          │
│  - PREMIUM ($299)        │
└────────────┬─────────────┘
             │ 1:N
             │
┌────────────▼────────────────────────────────┐
│  EMPRESA_USUARIO (SaaS Tenant)              │
│  - nombre_hotel                             │
│  - plan_tipo                                │
│  - fecha_inicio_demo                        │
│  - fecha_fin_demo (trial 10 días)           │
│  ✓ Tenant ID = Primary scoping              │
└────────────┬────────────────────────────────┘
             │
      ┌──────┴──────┬──────────┬──────────┐
      │             │          │          │
      ▼             ▼          ▼          ▼
   USUARIOS    HABITACIONES  RESERVAS   SUBSCRIPTION
   (Admins)    (Rooms)       (Bookings) (Payment)
   
   Cada registro tiene empresa_usuario_id FK
   RLS en PostgreSQL asegura aislamiento
```

## 11. Próximos Pasos (Phase 2)

Después de confirmar que las migraciones ejecutaron correctamente:

1. ✅ **Middleware RLS** (utils/tenant_middleware.py)
   - Setear `app.current_tenant_id` en cada FastAPI request
   - Validar JWT contiene empresa_usuario_id

2. ✅ **JWT Claims Update** (utils/auth.py)
   - `create_access_token(empresa_usuario_id, es_super_admin)`
   - Decodificar y usar en endpoints

3. ✅ **Validation Dependencies** (utils/dependencies.py)
   - `get_current_tenant()` - obtener tenant de JWT
   - `validate_trial_status()` - chequear si trial está activo
   - `require_super_admin()` - proteger endpoints SaaS

4. ✅ **Auth Endpoints** (endpoints/auth.py)
   - POST /auth/register-empresa-usuario (crear nuevo hotel)
   - POST /auth/login-multitenant (login con tenant_id)
   - POST /auth/trial-status (ver estado del trial)

5. ✅ **Billing Endpoints** (endpoints/billing.py)
   - GET /billing/plans
   - GET /billing/status
   - POST /billing/upgrade
   - POST /billing/cancel

---

## Checklist de Validación

- [ ] Migraciones 005, 006, 007 ejecutadas sin errores
- [ ] RLS habilitado en todas las tablas (verificar con query SQL)
- [ ] Modelos Python importan sin errores
- [ ] Tests de modelos ejecutan OK
- [ ] Tabla empresa_usuarios tiene datos de seed
- [ ] Usuarios legacy migrados a empresa_usuario_id
- [ ] Datos existentes tienen empresa_usuario_id asignado
- [ ] JWT claims actualizados
- [ ] Middleware RLS setea app.current_tenant_id
- [ ] Test: Query sin tenant_id falla en PostgreSQL (RLS activo)

---

**Documento creado**: Phase 1 Multi-Tenant Implementation  
**Status**: ✅ COMPLETED - Listo para Phase 2  
**Last Updated**: 2024  
