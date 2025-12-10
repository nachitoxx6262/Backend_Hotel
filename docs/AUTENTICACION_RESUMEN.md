# 🔐 Sistema de Autenticación JWT - Resumen de Implementación

## ✅ Archivos Creados

### Modelos
- ✅ `models/usuario.py` - Modelo de Usuario con roles y seguridad

### Schemas
- ✅ `schemas/auth.py` - Schemas para autenticación (Login, Token, Usuario, etc.)

### Utilidades
- ✅ `utils/auth.py` - Funciones JWT y hashing de passwords
- ✅ `utils/dependencies.py` - Dependencias de autenticación y autorización

### Endpoints
- ✅ `endpoints/auth.py` - 10 endpoints de autenticación y gestión de usuarios

### Scripts
- ✅ `create_admin.py` - Script para crear usuario administrador inicial
- ✅ `install_auth.sh` - Script de instalación de dependencias

### Configuración
- ✅ `.env.example` - Plantilla de variables de entorno
- ✅ `requirements.txt` - Actualizado con nuevas dependencias

### Documentación
- ✅ `docs/AUTENTICACION_JWT.md` - Documentación completa del sistema

## 📦 Dependencias Agregadas

```
python-jose[cryptography]==3.3.0  # JWT
passlib[bcrypt]==1.7.4            # Hashing de passwords
python-multipart==0.0.20          # OAuth2 forms
bcrypt==4.2.1                     # Algoritmo bcrypt
```

## 🎯 Características Implementadas

### 1. Sistema de Roles
- ✅ Admin (acceso total)
- ✅ Gerente (gestión operativa)
- ✅ Recepcionista (operaciones diarias)
- ✅ Readonly (solo consulta)

### 2. Seguridad
- ✅ Tokens JWT (Access + Refresh)
- ✅ Passwords hasheadas con bcrypt
- ✅ Validación de contraseñas robustas
- ✅ Protección contra fuerza bruta (bloqueo temporal)
- ✅ Soft delete de usuarios
- ✅ Auditoría de accesos

### 3. Endpoints de Autenticación
1. `POST /auth/login` - Login con credenciales
2. `POST /auth/register` - Registro de usuario (admin)
3. `POST /auth/refresh` - Renovar access token
4. `GET /auth/me` - Obtener perfil
5. `PUT /auth/me` - Actualizar perfil
6. `POST /auth/change-password` - Cambiar contraseña
7. `GET /auth/usuarios` - Listar usuarios (admin/gerente)
8. `GET /auth/usuarios/{id}` - Obtener usuario (admin/gerente)
9. `PUT /auth/usuarios/{id}` - Actualizar usuario (admin/gerente)
10. `DELETE /auth/usuarios/{id}` - Eliminar usuario (admin)

### 4. Dependencias de Autorización
- ✅ `require_admin` - Solo administradores
- ✅ `require_admin_or_manager` - Admin o gerente
- ✅ `require_staff` - Staff del hotel
- ✅ `require_authenticated` - Usuario autenticado
- ✅ `require_roles([roles])` - Roles personalizados
- ✅ `get_current_user` - Obtener usuario actual

## 🚀 Guía de Inicio Rápido

### 1. Instalar Dependencias

**Windows (PowerShell):**
```powershell
pip install python-jose[cryptography] passlib[bcrypt] python-multipart
```

**Linux/Mac:**
```bash
chmod +x install_auth.sh
./install_auth.sh
```

### 2. Configurar Variables de Entorno

```bash
# Copiar plantilla
cp .env.example .env

# Editar .env y configurar SECRET_KEY
# Para generar una clave segura:
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. Crear Usuario Administrador

```bash
python create_admin.py
```

Este comando:
- Crea las tablas en la base de datos
- Te solicita credenciales para el admin
- Opcionalmente crea usuarios demo

### 4. Iniciar Servidor

```bash
uvicorn main:app --reload
```

### 5. Probar Autenticación

Acceder a la documentación interactiva:
```
http://localhost:8000/docs
```

**Probar login:**

1. Ir a `/auth/login`
2. Click en "Try it out"
3. Ingresar credenciales:
   ```
   username: admin
   password: [tu password]
   ```
4. Click en "Execute"
5. Copiar el `access_token` de la respuesta
6. Click en el botón "Authorize" (🔒) arriba
7. Pegar el token en el campo
8. Ahora todos los endpoints protegidos estarán accesibles

## 📝 Ejemplos de Uso

### Login con cURL

```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=Admin123"
```

### Obtener Perfil

```bash
curl -X GET "http://localhost:8000/auth/me" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### Crear Usuario (Admin)

```bash
curl -X POST "http://localhost:8000/auth/register" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "recepcionista1",
    "email": "recepcion@hotel.com",
    "password": "Password123",
    "rol": "recepcionista"
  }'
```

## 🔐 Proteger Endpoints Existentes

Para proteger cualquier endpoint existente, agregue la dependencia:

```python
from utils.dependencies import require_staff, get_current_user

@router.post("/reservas")
def crear_reserva(
    datos: ReservaCreate,
    current_user: Usuario = Depends(require_staff),  # ← Agregar esto
    db: Session = Depends(get_db)
):
    # Solo staff puede crear reservas
    log_event("reservas", current_user.username, "Crear reserva", ...)
    # ... resto del código
```

### Ejemplos por Endpoint:

**Operaciones críticas (solo admin):**
```python
@router.delete("/habitaciones/{id}")
def eliminar_habitacion(
    id: int,
    current_user: Usuario = Depends(require_admin)
):
    # Solo admin
    pass
```

**Estadísticas (admin/gerente):**
```python
@router.get("/estadisticas/ingresos")
def ver_ingresos(
    current_user: Usuario = Depends(require_admin_or_manager)
):
    # Admin o gerente
    pass
```

**Operaciones diarias (staff):**
```python
@router.post("/checkin-checkout/{id}/checkin")
def hacer_checkin(
    id: int,
    current_user: Usuario = Depends(require_staff)
):
    # Admin, gerente o recepcionista
    pass
```

**Consultas (cualquier usuario autenticado):**
```python
@router.get("/disponibilidad/habitaciones")
def consultar_disponibilidad(
    current_user: Usuario = Depends(require_authenticated)
):
    # Cualquier usuario autenticado
    pass
```

## 🎨 Integración con Frontend

### Flujo de Autenticación

1. **Login:**
   ```javascript
   const response = await fetch('http://localhost:8000/auth/login', {
     method: 'POST',
     headers: {
       'Content-Type': 'application/x-www-form-urlencoded',
     },
     body: 'username=admin&password=Admin123'
   });
   
   const { access_token, refresh_token } = await response.json();
   
   // Guardar tokens
   sessionStorage.setItem('access_token', access_token);
   sessionStorage.setItem('refresh_token', refresh_token);
   ```

2. **Hacer Requests Autenticados:**
   ```javascript
   const accessToken = sessionStorage.getItem('access_token');
   
   const response = await fetch('http://localhost:8000/auth/me', {
     headers: {
       'Authorization': `Bearer ${accessToken}`
     }
   });
   ```

3. **Renovar Token:**
   ```javascript
   const refreshToken = sessionStorage.getItem('refresh_token');
   
   const response = await fetch('http://localhost:8000/auth/refresh', {
     method: 'POST',
     headers: {
       'Content-Type': 'application/json'
     },
     body: JSON.stringify({ refresh_token: refreshToken })
   });
   
   const { access_token, refresh_token } = await response.json();
   // Actualizar tokens
   ```

## 📊 Estructura de Base de Datos

### Tabla: usuarios

```sql
CREATE TABLE usuarios (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    nombre VARCHAR(60),
    apellido VARCHAR(60),
    rol VARCHAR(20) NOT NULL DEFAULT 'readonly',
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    deleted BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT NOW(),
    fecha_ultima_modificacion TIMESTAMP,
    ultimo_login TIMESTAMP,
    intentos_fallidos INTEGER NOT NULL DEFAULT 0,
    bloqueado_hasta TIMESTAMP
);
```

## 🧪 Testing

### Probar Endpoints de Autenticación

```python
import requests

BASE_URL = "http://localhost:8000"

# 1. Login
response = requests.post(f"{BASE_URL}/auth/login", data={
    "username": "admin",
    "password": "Admin123"
})
assert response.status_code == 200
tokens = response.json()

# 2. Ver perfil
headers = {"Authorization": f"Bearer {tokens['access_token']}"}
response = requests.get(f"{BASE_URL}/auth/me", headers=headers)
assert response.status_code == 200

# 3. Renovar token
response = requests.post(f"{BASE_URL}/auth/refresh", json={
    "refresh_token": tokens['refresh_token']
})
assert response.status_code == 200

# 4. Cambiar password
response = requests.post(
    f"{BASE_URL}/auth/change-password",
    headers=headers,
    json={
        "current_password": "Admin123",
        "new_password": "NewPassword123"
    }
)
assert response.status_code == 200
```

## 🔒 Consideraciones de Seguridad

1. **Producción:**
   - ✅ Cambiar `SECRET_KEY` por una clave segura
   - ✅ Usar HTTPS
   - ✅ Configurar CORS apropiadamente
   - ✅ Implementar rate limiting
   - ✅ Usar cookies httpOnly para tokens (opcional)

2. **Passwords:**
   - ✅ Validación robusta implementada
   - ✅ Hashing con bcrypt (costo 12)
   - ✅ No almacenar passwords en logs

3. **Tokens:**
   - ✅ Access tokens de corta duración (30 min)
   - ✅ Refresh tokens de larga duración (7 días)
   - ✅ Implementar revocación de tokens (pendiente)

## 📚 Recursos Adicionales

- [Documentación completa](./AUTENTICACION_JWT.md)
- [Mejoras del sistema](./MEJORAS_IMPLEMENTADAS.md)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)

## ✅ Checklist de Implementación

- [x] Modelo de Usuario
- [x] Schemas de autenticación
- [x] Utilidades JWT
- [x] Hashing de passwords
- [x] Endpoints de autenticación
- [x] Sistema de roles
- [x] Dependencias de autorización
- [x] Protección contra fuerza bruta
- [x] Soft delete
- [x] Auditoría
- [x] Script de creación de admin
- [x] Documentación
- [x] Ejemplos de uso

## 🎉 ¡Sistema de Autenticación Completado!

El sistema ahora cuenta con:
- ✅ 10 endpoints de autenticación
- ✅ 4 niveles de roles con permisos
- ✅ Seguridad robusta con JWT
- ✅ Protección contra ataques comunes
- ✅ Documentación completa
- ✅ Scripts de configuración

**Siguiente paso:** Proteger los endpoints existentes según los requisitos de negocio.
