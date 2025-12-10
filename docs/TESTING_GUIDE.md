# 🧪 Testing Guide - Endpoints Mejorados

## 📝 Recomendaciones de Testing

Este documento guía cómo validar los endpoints mejorados y sus nuevas funcionalidades.

---

## 🔧 Configuración Previa

### 1. Iniciar el servidor
```bash
cd Backend_Hotel
uvicorn main:app --reload
```

### 2. Crear usuario administrador
```bash
python create_admin.py
# Seguir prompts para crear admin
```

### 3. Obtener token JWT
```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "tu_password"}'
```

---

## ✅ Test Cases - Clientes

### Test 1: Crear Cliente Básico
```bash
curl -X POST "http://localhost:8000/clientes" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Juan",
    "apellido": "Pérez",
    "tipo_documento": "DNI",
    "numero_documento": "12345678",
    "nacionalidad": "Argentina",
    "email": "juan@example.com",
    "telefono": "+5491234567890"
  }'

# Respuesta esperada: 201 Created
# Con campos: id, creado_en, actualizado_en
```

### Test 2: Crear Cliente Completo (Nuevos Campos)
```bash
curl -X POST "http://localhost:8000/clientes" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "María",
    "apellido": "García",
    "tipo_documento": "DNI",
    "numero_documento": "87654321",
    "nacionalidad": "Argentina",
    "email": "maria@example.com",
    "telefono": "+5491234567890",
    "telefono_alternativo": "+5491198765432",
    "fecha_nacimiento": "1990-01-15",
    "genero": "F",
    "direccion": "Av. Corrientes 123",
    "ciudad": "Buenos Aires",
    "provincia": "CABA",
    "codigo_postal": "1425",
    "tipo_cliente": "vip",
    "preferencias": "{\"piso\": 2}",
    "nota_interna": "VIP"
  }'

# ✓ Validar que devuelve todos los campos
# ✓ Validar timestamps automáticos
```

### Test 3: Validar Género
```bash
curl -X POST "http://localhost:8000/clientes" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Test",
    "apellido": "Test",
    "tipo_documento": "DNI",
    "numero_documento": "11111111",
    "nacionalidad": "Argentina",
    "email": "test1@example.com",
    "telefono": "+5491234567890",
    "genero": "X"
  }'

# Respuesta esperada: 400 Bad Request
# "El género debe ser M, F u O"
```

### Test 4: Detectar Documento Duplicado
```bash
# Crear primer cliente
POST /clientes
{
  "nombre": "Test1",
  "apellido": "Test1",
  "tipo_documento": "DNI",
  "numero_documento": "99999999",
  "nacionalidad": "Argentina",
  "email": "test@example.com",
  "telefono": "+5491234567890"
}

# Intentar crear otro con el mismo documento
POST /clientes
{
  "nombre": "Test2",
  "apellido": "Test2",
  "tipo_documento": "DNI",
  "numero_documento": "99999999",
  "nacionalidad": "Argentina",
  "email": "test2@example.com",
  "telefono": "+5491234567890"
}

# Respuesta esperada: 409 Conflict
# "Ya existe un cliente activo con ese tipo y número de documento"
```

### Test 5: Actualizar Cliente (Parcial)
```bash
# Asumir cliente ID=1
curl -X PUT "http://localhost:8000/clientes/1" \
  -H "Content-Type: application/json" \
  -d '{
    "ciudad": "La Plata",
    "tipo_cliente": "corporativo"
  }'

# ✓ Validar que solo actualiza campos proporcionados
# ✓ Validar que no cambian otros campos
# ✓ Validar que actualizado_en se actualiza
```

### Test 6: Email Duplicado
```bash
curl -X POST "http://localhost:8000/clientes" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Test",
    "apellido": "Test",
    "tipo_documento": "OTRO",
    "numero_documento": "88888888",
    "nacionalidad": "Argentina",
    "email": "juan@example.com",  // Ya existe
    "telefono": "+5491234567890"
  }'

# Respuesta esperada: 409 Conflict
# "Violación de restricción de integridad (posible email duplicado)"
```

---

## ✅ Test Cases - Empresas

### Test 1: Crear Empresa Básica
```bash
curl -X POST "http://localhost:8000/empresas" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Hotel XYZ",
    "cuit": "30123456789",
    "tipo_empresa": "Hotel",
    "contacto_principal_nombre": "Carlos López",
    "contacto_principal_email": "carlos@hotelxyz.com",
    "contacto_principal_telefono": "+5491234567890",
    "direccion": "Av. Rivadavia 1234",
    "ciudad": "Buenos Aires"
  }'

# Respuesta esperada: 201 Created
```

### Test 2: Crear Empresa Completa (Términos Comerciales)
```bash
curl -X POST "http://localhost:8000/empresas" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Hotel Premium",
    "cuit": "30987654321",
    "tipo_empresa": "Cadena Hotelera",
    "contacto_principal_nombre": "Juan Smith",
    "contacto_principal_titulo": "Gerente General",
    "contacto_principal_email": "juan@hotelpremium.com",
    "contacto_principal_telefono": "+5491234567890",
    "contacto_principal_celular": "+5491198765432",
    "direccion": "Av. Acoyte 500",
    "ciudad": "Buenos Aires",
    "provincia": "CABA",
    "codigo_postal": "1425",
    "dias_credito": 45,
    "limite_credito": 50000.00,
    "tasa_descuento": 10.50
  }'

# ✓ Validar todos los campos nuevos
# ✓ Validar tipos de datos (Decimal, int)
# ✓ Validar que tasa_descuento está entre 0-100
```

### Test 3: Validar CUIT Único
```bash
# Intentar crear empresa con CUIT duplicado
curl -X POST "http://localhost:8000/empresas" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Otra Empresa",
    "cuit": "30123456789",  // Ya existe
    "tipo_empresa": "Hotel",
    "contacto_principal_nombre": "Test",
    "contacto_principal_email": "test@example.com",
    "contacto_principal_telefono": "+5491234567890",
    "direccion": "Test",
    "ciudad": "Test"
  }'

# Respuesta esperada: 409 Conflict
# "Ya existe una empresa activa con ese CUIT"
```

### Test 4: Validar Términos Comerciales
```bash
curl -X POST "http://localhost:8000/empresas" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Test",
    "cuit": "30111111111",
    "tipo_empresa": "Test",
    "contacto_principal_nombre": "Test",
    "contacto_principal_email": "test@test.com",
    "contacto_principal_telefono": "+5491234567890",
    "direccion": "Test",
    "ciudad": "Test",
    "tasa_descuento": 150  // > 100
  }'

# Respuesta esperada: 422 Unprocessable Entity
# Validación de rango
```

### Test 5: Actualizar Empresa
```bash
curl -X PUT "http://localhost:8000/empresas/1" \
  -H "Content-Type: application/json" \
  -d '{
    "contacto_principal_nombre": "Nuevo Contacto",
    "contacto_principal_titulo": "Director",
    "dias_credito": 60,
    "limite_credito": 100000.00
  }'

# ✓ Validar actualización de contacto
# ✓ Validar actualización de términos
# ✓ Validar que no se puede sobrescribir deleted/blacklist
```

---

## ✅ Test Cases - Habitaciones

### Test 1: Crear Habitación sin Categoría
```bash
# Primero crear una categoría
curl -X POST "http://localhost:8000/categorias-habitacion" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Habitación Simple",
    "descripcion": "Habitación básica para 1 persona",
    "capacidad_personas": 1,
    "precio_base_noche": 100.00
  }'

# Asumir categoria_id = 1

# Crear habitación
curl -X POST "http://localhost:8000/habitaciones" \
  -H "Content-Type: application/json" \
  -d '{
    "numero": 101,
    "estado": "disponible",
    "categoria_id": 1
  }'

# Respuesta esperada: 201 Created
```

### Test 2: Validar Número Único
```bash
curl -X POST "http://localhost:8000/habitaciones" \
  -H "Content-Type: application/json" \
  -d '{
    "numero": 101,  // Ya existe
    "estado": "disponible"
  }'

# Respuesta esperada: 409 Conflict
# "Ya existe una habitación con ese número"
```

### Test 3: Validar Categoría Activa
```bash
curl -X POST "http://localhost:8000/habitaciones" \
  -H "Content-Type: application/json" \
  -d '{
    "numero": 102,
    "estado": "disponible",
    "categoria_id": 999  // No existe
  }'

# Respuesta esperada: 404 Not Found
# "La categoría de habitación especificada no existe o está inactiva"
```

### Test 4: Actualizar Habitación
```bash
curl -X PUT "http://localhost:8000/habitaciones/1" \
  -H "Content-Type: application/json" \
  -d '{
    "estado": "en_mantenimiento",
    "piso": 1,
    "fotos_url": "https://example.com/fotos"
  }'

# ✓ Validar actualización de estado
# ✓ Validar timestamp actualizado_en
```

---

## 📊 Test Cases - Validaciones Generales

### Test: Campos Vacíos
```bash
curl -X POST "http://localhost:8000/clientes" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "",
    "apellido": "Test",
    "tipo_documento": "DNI",
    "numero_documento": "12345678",
    "nacionalidad": "Argentina",
    "email": "test@example.com",
    "telefono": "+5491234567890"
  }'

# Respuesta esperada: 400 Bad Request
# Pydantic validation error
```

### Test: Campos Requeridos
```bash
curl -X POST "http://localhost:8000/clientes" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Test",
    "apellido": "Test",
    "tipo_documento": "DNI"
    // Falta numero_documento
  }'

# Respuesta esperada: 422 Unprocessable Entity
# Missing required field
```

### Test: Email Inválido
```bash
curl -X POST "http://localhost:8000/clientes" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Test",
    "apellido": "Test",
    "tipo_documento": "DNI",
    "numero_documento": "12345678",
    "nacionalidad": "Argentina",
    "email": "invalid-email",
    "telefono": "+5491234567890"
  }'

# Respuesta esperada: 422 Unprocessable Entity
# Email validation error
```

---

## 🔍 Test Cases - Auditoría

### Test: Verificar Timestamps
```bash
# Crear cliente
curl -X POST "http://localhost:8000/clientes" -d "{...}"
# Guardar: creado_en = "2025-12-04T10:30:00"
# Guardar: actualizado_en = "2025-12-04T10:30:00"

# Actualizar cliente
curl -X PUT "http://localhost:8000/clientes/1" -d "{...}"
# Validar: creado_en = "2025-12-04T10:30:00" (NO CAMBIÓ)
# Validar: actualizado_en = "2025-12-04T10:45:00" (CAMBIÓ)
```

### Test: Verificar Soft Delete
```bash
# Crear cliente
POST /clientes -> id=1, deleted=false

# Eliminar
DELETE /clientes/1

# Verificar que NO aparece en listado
GET /clientes -> [no incluye id=1]

# Pero existe en tabla eliminados
GET /clientes/eliminados -> [incluye id=1]

# Y se puede restaurar
PUT /clientes/1/restaurar -> deleted=false, deleted ahora en listado
```

---

## 🛠️ Herramientas Recomendadas

### Postman
```bash
# Importar colección
Archivo -> Importar -> URL o archivo
```

### cURL (línea de comandos)
```bash
# Guardar en archivo
curl -X POST ... > response.json
cat response.json | jq .
```

### Pytest (testing automatizado)
```bash
# Ejecutar tests
pytest tests/ -v

# Con coverage
pytest tests/ --cov=endpoints/ --cov-report=html
```

---

## 📋 Checklist de Validación

- [ ] Crear cliente con campos mínimos
- [ ] Crear cliente con todos los campos
- [ ] Validar género (M/F/O)
- [ ] Detectar documento duplicado
- [ ] Detectar email duplicado
- [ ] Actualizar cliente parcialmente
- [ ] Verificar timestamps automáticos
- [ ] Crear empresa con campos mínimos
- [ ] Crear empresa con términos comerciales
- [ ] Validar CUIT único
- [ ] Validar rango tasa_descuento (0-100)
- [ ] Actualizar empresa
- [ ] Crear habitación con categoría
- [ ] Validar categoría activa
- [ ] Validar número de habitación único
- [ ] Actualizar habitación
- [ ] Verificar soft delete
- [ ] Verificar auditoría (creado_en, actualizado_en)

---

**Última actualización:** Diciembre 4, 2025
