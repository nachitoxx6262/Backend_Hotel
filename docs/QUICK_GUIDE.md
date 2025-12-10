# 🚀 Quick Guide - Endpoints Mejorados

## 📋 Qué Cambió

### 1. **Schemas Ampliados**

#### Clientes
```json
// NUEVO: Campos adicionales
{
  "telefono_alternativo": "+5491234567890",
  "fecha_nacimiento": "1990-01-15",
  "genero": "M",
  "direccion": "Av. Corrientes 123",
  "ciudad": "Buenos Aires",
  "provincia": "CABA",
  "codigo_postal": "1424",
  "tipo_cliente": "vip",  // individual, corporativo, vip
  "preferencias": "{...}",
  "nota_interna": "Cliente VIP",
  "activo": true,
  "creado_en": "2025-12-04T10:30:00",
  "actualizado_en": "2025-12-04T10:30:00"
}
```

#### Empresas
```json
// NUEVO: Contacto desagregado + términos comerciales
{
  "tipo_empresa": "Hotel",
  "contacto_principal_nombre": "Carlos López",
  "contacto_principal_titulo": "Gerente",
  "contacto_principal_email": "carlos@empresa.com",
  "contacto_principal_telefono": "+5491234567890",
  "contacto_principal_celular": "+5491987654321",
  "dias_credito": 30,
  "limite_credito": "10000.00",
  "tasa_descuento": "5.50",
  "creado_en": "2025-12-04T10:30:00",
  "actualizado_en": "2025-12-04T10:30:00"
}
```

---

## ✅ Validaciones Nuevas

### Clientes
```
✓ Género: solo M, F, O
✓ Documento: única combinación (tipo + número)
✓ Email: único
✓ Empresa: debe existir y estar activa
✓ Teléfonos: formato validado
✓ Fechas: formato ISO 8601
```

### Empresas
```
✓ CUIT: único y requerido
✓ Contacto principal: todos los campos requeridos
✓ Dirección + Ciudad: requeridas
✓ Días crédito: >= 0
✓ Límite crédito: >= 0 (Decimal)
✓ Tasa descuento: 0-100 %
✓ Email contacto: válido
```

### Habitaciones
```
✓ Número: único
✓ Categoría: debe existir y estar activa
✓ Estado: válido según enum
✓ No se puede eliminar con reservas activas
```

---

## 🔄 Cambios en Comportamiento

### Crear Cliente - ANTES vs AHORA

**ANTES:**
```bash
POST /clientes
{
  "nombre": "Juan",
  "apellido": "Pérez",
  "tipo_documento": "DNI",
  "numero_documento": "12345678",
  "nacionalidad": "Argentina",
  "email": "juan@example.com",
  "telefono": "1234567890"
}
```

**AHORA (Más campos disponibles):**
```bash
POST /clientes
{
  "nombre": "Juan",
  "apellido": "Pérez",
  "tipo_documento": "DNI",
  "numero_documento": "12345678",
  "nacionalidad": "Argentina",
  "email": "juan@example.com",
  "telefono": "1234567890",
  
  # NUEVOS (opcionales):
  "telefono_alternativo": "9876543210",
  "fecha_nacimiento": "1990-01-15",
  "genero": "M",
  "direccion": "Calle 123",
  "ciudad": "Buenos Aires",
  "provincia": "CABA",
  "codigo_postal": "1424",
  "tipo_cliente": "vip",
  "preferencias": "{...}",
  "nota_interna": "VIP desde 2023"
}
```

**Respuesta incluye auditoría:**
```json
{
  "id": 1,
  "...datos...",
  "creado_en": "2025-12-04T10:30:00",
  "actualizado_en": "2025-12-04T10:30:00"
}
```

---

## 🆕 Campos por Entidad

### Cliente

| Campo | Tipo | Requerido | Validación |
|-------|------|-----------|-----------|
| nombre | string(60) | ✅ | - |
| apellido | string(60) | ✅ | - |
| tipo_documento | string(20) | ✅ | - |
| numero_documento | string(40) | ✅ | único |
| nacionalidad | string(60) | ✅ | - |
| email | string(100) | ✅ | único, email válido |
| telefono | string(30) | ✅ | - |
| **telefono_alternativo** | string(30) | ❌ | - |
| **fecha_nacimiento** | date | ❌ | - |
| **genero** | string(10) | ❌ | M/F/O |
| **direccion** | string(200) | ❌ | - |
| **ciudad** | string(100) | ❌ | - |
| **provincia** | string(100) | ❌ | - |
| **codigo_postal** | string(20) | ❌ | - |
| **tipo_cliente** | string(20) | ❌ | individual/corporativo/vip |
| **preferencias** | text | ❌ | JSON |
| **nota_interna** | text | ❌ | - |
| activo | boolean | ❌ | default=true |
| deleted | boolean | ❌ | default=false |
| blacklist | boolean | ❌ | default=false |
| **motivo_blacklist** | text | ❌ | - |
| **creado_en** | datetime | AUTO | - |
| **actualizado_en** | datetime | AUTO | - |

### Empresa

| Campo | Tipo | Requerido | Validación |
|-------|------|-----------|-----------|
| nombre | string(150) | ✅ | - |
| cuit | string(20) | ✅ | único |
| **tipo_empresa** | string(50) | ✅ | - |
| **contacto_principal_nombre** | string(100) | ✅ | - |
| **contacto_principal_email** | string(100) | ✅ | email válido |
| **contacto_principal_telefono** | string(30) | ✅ | - |
| **contacto_principal_titulo** | string(100) | ❌ | - |
| **contacto_principal_celular** | string(30) | ❌ | - |
| direccion | string(200) | ✅ | - |
| ciudad | string(100) | ✅ | - |
| **provincia** | string(100) | ❌ | - |
| **codigo_postal** | string(20) | ❌ | - |
| **dias_credito** | integer | ❌ | >= 0, default=30 |
| **limite_credito** | decimal(12,2) | ❌ | >= 0, default=0 |
| **tasa_descuento** | decimal(5,2) | ❌ | 0-100, default=0 |
| **nota_interna** | text | ❌ | - |
| activo | boolean | ❌ | default=true |
| deleted | boolean | ❌ | default=false |
| blacklist | boolean | ❌ | default=false |
| **motivo_blacklist** | text | ❌ | - |
| **creado_en** | datetime | AUTO | - |
| **actualizado_en** | datetime | AUTO | - |

---

## 🔍 Manejo de Errores

Ahora recibas respuestas más específicas:

```json
// Error: Documento duplicado
HTTP 409
{
  "detail": "Ya existe un cliente activo con ese tipo y número de documento"
}

// Error: Empresa no existe
HTTP 404
{
  "detail": "La empresa especificada no existe o está inactiva"
}

// Error: Género inválido
HTTP 400
{
  "detail": "El género debe ser M, F u O"
}

// Error: Validación de integridad
HTTP 409
{
  "detail": "Violación de restricción de integridad (posible email duplicado)"
}

// Error: Base de datos
HTTP 500
{
  "detail": "Error al crear el cliente en la base de datos"
}
```

---

## 📝 Ejemplos de API

### Crear Cliente Completo
```bash
curl -X POST "http://localhost:8000/clientes" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Juan",
    "apellido": "Pérez García",
    "tipo_documento": "DNI",
    "numero_documento": "12345678",
    "nacionalidad": "Argentina",
    "email": "juan.perez@example.com",
    "telefono": "+5491123456789",
    "telefono_alternativo": "+5491198765432",
    "fecha_nacimiento": "1990-01-15",
    "genero": "M",
    "direccion": "Av. Corrientes 123",
    "ciudad": "Buenos Aires",
    "provincia": "CABA",
    "codigo_postal": "1425",
    "tipo_cliente": "vip",
    "preferencias": "{\"piso\": 2, \"vista\": \"parque\"}",
    "nota_interna": "Cliente VIP desde 2023"
  }'
```

### Crear Empresa con Términos
```bash
curl -X POST "http://localhost:8000/empresas" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Hotel Premium S.A.",
    "cuit": "30712345678",
    "tipo_empresa": "Cadena Hotelera",
    "contacto_principal_nombre": "Carlos López",
    "contacto_principal_titulo": "Gerente General",
    "contacto_principal_email": "carlos@hotelpremium.com",
    "contacto_principal_telefono": "+5491123456789",
    "contacto_principal_celular": "+5491198765432",
    "direccion": "Av. Rivadavia 1234",
    "ciudad": "Buenos Aires",
    "provincia": "CABA",
    "codigo_postal": "1425",
    "dias_credito": 30,
    "limite_credito": 50000.00,
    "tasa_descuento": 7.50,
    "nota_interna": "Contrato especial firmado en 2025"
  }'
```

### Actualizar Cliente Parcialmente
```bash
curl -X PUT "http://localhost:8000/clientes/1" \
  -H "Content-Type: application/json" \
  -d '{
    "ciudad": "La Plata",
    "telefono": "+5491199999999",
    "tipo_cliente": "corporativo"
  }'
```

---

## ⚠️ Breaking Changes

Ninguno importante. Los campos nuevos son opcionales.

Pero algunos cambios en esquema:
- Empresa: `email` + `telefono` → `contacto_principal_email` + `contacto_principal_telefono`
- Habitación: Campo `mantenimiento` (boolean) → Tabla `MantenimientoHabitacion`

---

## 📚 Documentación Adicional

Ver:
- `CAMBIOS_ENDPOINTS.md` - Detalle técnico completo
- `RESUMEN_MEJORAS.md` - Visión general de mejoras
- Modelos en `models/` - Definiciones SQLAlchemy

---

**Última actualización:** Diciembre 4, 2025
**Versión:** 2.0
