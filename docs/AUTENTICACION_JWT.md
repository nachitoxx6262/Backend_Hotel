# 🔐 Sistema de Autenticación JWT y Autorización por Roles

## 📋 Tabla de Contenidos
- [Descripción General](#descripción-general)
- [Roles del Sistema](#roles-del-sistema)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Endpoints de Autenticación](#endpoints-de-autenticación)
- [Uso de Tokens JWT](#uso-de-tokens-jwt)
- [Protección de Endpoints](#protección-de-endpoints)
- [Ejemplos de Uso](#ejemplos-de-uso)

---

## 📝 Descripción General

Sistema completo de autenticación basado en JWT (JSON Web Tokens) con autorización por roles para el sistema de gestión hotelera.

### Características Principales

- ✅ Autenticación con JWT (Access Token + Refresh Token)
- ✅ 4 niveles de roles con permisos diferenciados
- ✅ Protección contra fuerza bruta (bloqueo temporal)
- ✅ Gestión de contraseñas seguras con bcrypt
- ✅ Validación de contraseñas robustas
- ✅ Tokens de refresco para sesiones extendidas
- ✅ Soft delete de usuarios
- ✅ Auditoría completa de accesos

---

## 👥 Roles del Sistema

### 1. **Admin** (Administrador)
- ✅ Acceso total al sistema
- ✅ Crear, editar y eliminar usuarios
- ✅ Modificar cualquier configuración
- ✅ Acceso a todos los endpoints

### 2. **Gerente** (Manager)
- ✅ Gestión de operaciones del hotel
- ✅ Ver y modificar reservas
- ✅ Gestión de clientes y empresas
- ✅ Ver estadísticas y reportes
- ✅ Crear usuarios de nivel inferior (recepcionista, readonly)
- ❌ No puede modificar administradores

### 3. **Recepcionista**
- ✅ Operaciones diarias del hotel
- ✅ Crear y modificar reservas
- ✅ Check-in y check-out
- ✅ Gestión de clientes
- ✅ Consulta de disponibilidad
- ❌ No puede eliminar registros permanentemente
- ❌ No puede acceder a estadísticas financieras completas

### 4. **Readonly** (Solo Lectura)
- ✅ Consulta de información
- ✅ Ver reservas, clientes, habitaciones
- ✅ Consultar disponibilidad
- ❌ No puede crear ni modificar nada

---

## 🚀 Instalación

### 1. Instalar Dependencias

```bash
pip install -r requirements.txt
```

### Dependencias clave agregadas:
- `python-jose[cryptography]` - JWT
- `passlib[bcrypt]` - Hashing de contraseñas
- `python-multipart` - Para forms OAuth2

### 2. Configurar Variables de Entorno

Copie `.env.example` a `.env` y configure:

```bash
cp .env.example .env
```

**⚠️ IMPORTANTE**: Cambie `SECRET_KEY` en producción:

```python
# Generar una clave segura
import secrets
print(secrets.token_urlsafe(32))
```

### 3. Crear Tablas en la Base de Datos

```bash
# El sistema creará las tablas automáticamente al iniciar
python main.py
```

### 4. Crear Usuario Administrador

```bash
python create_admin.py
```

Este script:
- ✅ Crea el usuario admin inicial
- ✅ Opcionalmente crea usuarios demo para todos los roles

---

## ⚙️ Configuración

### Archivo de Configuración de Seguridad

En `utils/auth.py`:

```python
SECRET_KEY = "tu-clave-secreta"  # Cargar desde .env en producción
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # Token de acceso válido por 30 min
REFRESH_TOKEN_EXPIRE_DAYS = 7     # Token de refresco válido por 7 días
```

### Configuración Dinámica

```python
from utils.auth import configurar_seguridad

configurar_seguridad(
    secret_key=os.getenv("SECRET_KEY"),
    access_token_expire_minutes=60
)
```

---

## 🔑 Endpoints de Autenticación

### 1. Login (Inicio de Sesión)

**POST** `/auth/login`

```json
// Request (form-data)
{
  "username": "admin",
  "password": "Admin123"
}

// Response
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

**Características:**
- ✅ Bloqueo temporal después de 5 intentos fallidos (30 min)
- ✅ Registro de último login
- ✅ Reset de intentos fallidos en login exitoso

### 2. Registrar Usuario

**POST** `/auth/register` 🔒 *Requiere: Admin*

```json
// Request
{
  "username": "nuevo_usuario",
  "email": "usuario@hotel.com",
  "password": "Password123",
  "nombre": "Juan",
  "apellido": "Pérez",
  "rol": "recepcionista"
}

// Response
{
  "id": 5,
  "username": "nuevo_usuario",
  "email": "usuario@hotel.com",
  "nombre": "Juan",
  "apellido": "Pérez",
  "rol": "recepcionista",
  "activo": true,
  "fecha_creacion": "2025-12-03T10:30:00"
}
```

**Validaciones de Password:**
- ✅ Mínimo 8 caracteres
- ✅ Al menos 1 mayúscula
- ✅ Al menos 1 minúscula
- ✅ Al menos 1 número

### 3. Renovar Token

**POST** `/auth/refresh`

```json
// Request
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}

// Response
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### 4. Ver Perfil

**GET** `/auth/me` 🔒 *Requiere: Autenticación*

```json
// Response
{
  "id": 1,
  "username": "admin",
  "email": "admin@hotel.com",
  "nombre": "Administrador",
  "apellido": "Sistema",
  "rol": "admin",
  "activo": true,
  "fecha_creacion": "2025-12-01T00:00:00",
  "ultimo_login": "2025-12-03T10:30:00"
}
```

### 5. Actualizar Perfil

**PUT** `/auth/me` 🔒 *Requiere: Autenticación*

```json
// Request
{
  "email": "nuevo_email@hotel.com",
  "nombre": "Nuevo Nombre"
}

// Response: Usuario actualizado
```

### 6. Cambiar Contraseña

**POST** `/auth/change-password` 🔒 *Requiere: Autenticación*

```json
// Request
{
  "current_password": "Password123",
  "new_password": "NuevoPassword456"
}

// Response
{
  "message": "Contraseña actualizada exitosamente"
}
```

### 7. Listar Usuarios

**GET** `/auth/usuarios` 🔒 *Requiere: Admin o Gerente*

### 8. Obtener Usuario por ID

**GET** `/auth/usuarios/{usuario_id}` 🔒 *Requiere: Admin o Gerente*

### 9. Actualizar Usuario

**PUT** `/auth/usuarios/{usuario_id}` 🔒 *Requiere: Admin o Gerente*

### 10. Eliminar Usuario

**DELETE** `/auth/usuarios/{usuario_id}` 🔒 *Requiere: Admin*

---

## 🔐 Uso de Tokens JWT

### Estructura del Token

```json
{
  "sub": "admin",           // Username
  "user_id": 1,             // ID del usuario
  "rol": "admin",           // Rol del usuario
  "exp": 1701614400,        // Timestamp de expiración
  "iat": 1701612600,        // Timestamp de emisión
  "type": "access"          // Tipo de token
}
```

### Usar Token en Requests

```bash
# Header de autorización
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Con cURL:

```bash
curl -X GET "http://localhost:8000/auth/me" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### Con Python requests:

```python
import requests

headers = {
    "Authorization": f"Bearer {access_token}"
}

response = requests.get("http://localhost:8000/auth/me", headers=headers)
```

### Con JavaScript/Fetch:

```javascript
fetch('http://localhost:8000/auth/me', {
  headers: {
    'Authorization': `Bearer ${accessToken}`
  }
})
```

---

## 🛡️ Protección de Endpoints

### Importar Dependencias

```python
from utils.dependencies import (
    require_admin,
    require_admin_or_manager,
    require_staff,
    require_authenticated,
    get_current_user
)
```

### Ejemplo 1: Solo Admin

```python
@router.delete("/habitaciones/{id}")
def eliminar_habitacion(
    id: int,
    current_user: Usuario = Depends(require_admin)
):
    # Solo usuarios con rol "admin" pueden acceder
    pass
```

### Ejemplo 2: Admin o Gerente

```python
@router.get("/estadisticas/ingresos")
def ver_ingresos(
    current_user: Usuario = Depends(require_admin_or_manager)
):
    # Admin o gerente pueden acceder
    pass
```

### Ejemplo 3: Staff (Admin, Gerente, Recepcionista)

```python
@router.post("/reservas")
def crear_reserva(
    datos: ReservaCreate,
    current_user: Usuario = Depends(require_staff)
):
    # Cualquier miembro del staff puede crear reservas
    pass
```

### Ejemplo 4: Usuario Autenticado (cualquier rol)

```python
@router.get("/disponibilidad/habitaciones")
def consultar_disponibilidad(
    current_user: Usuario = Depends(require_authenticated)
):
    # Cualquier usuario autenticado puede consultar
    pass
```

### Ejemplo 5: Roles Personalizados
Ahora también puedes proteger por permisos específicos usando RBAC dinámico:

```python
from utils.dependencies import require_permission, require_any_permission

@router.post("/clientes")
def crear_cliente(
    payload: ClienteCreate,
    current_user: Usuario = Depends(require_permission("clientes:create"))
):
    # Requiere permiso clientes:create
    pass

@router.get("/estadisticas/dashboard")
def ver_dashboard(
    current_user: Usuario = Depends(require_any_permission(["estadisticas:view", "admin:all"]))
):
    pass
```

Ver sección “Roles y permisos dinámicos (RBAC)” para administrar roles y permisos mediante los endpoints `/roles`.

```python
from utils.dependencies import require_roles

@router.post("/reportes/especiales")
def generar_reporte_especial(
    current_user: Usuario = Depends(require_roles(["admin", "gerente"]))
):
    # Solo admin y gerente
    pass
```

### Ejemplo 6: Obtener Usuario Actual

```python
@router.post("/reservas")
def crear_reserva(
    datos: ReservaCreate,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Acceso a información del usuario actual
    print(f"Usuario: {current_user.username}")
    print(f"Rol: {current_user.rol}")
    print(f"Email: {current_user.email}")
    
    # Registrar quién creó la reserva
    nueva_reserva.creado_por = current_user.id
    pass
```

---

## 💡 Ejemplos de Uso

### Ejemplo Completo: Login y Uso de API

```python
import requests

BASE_URL = "http://localhost:8000"

# 1. Login
login_response = requests.post(
    f"{BASE_URL}/auth/login",
    data={
        "username": "admin",
        "password": "Admin123"
    }
)

tokens = login_response.json()
access_token = tokens["access_token"]
refresh_token = tokens["refresh_token"]

# 2. Headers para requests autenticados
headers = {
    "Authorization": f"Bearer {access_token}"
}

# 3. Obtener perfil
perfil = requests.get(f"{BASE_URL}/auth/me", headers=headers)
print(perfil.json())

# 4. Crear una reserva (ejemplo)
nueva_reserva = requests.post(
    f"{BASE_URL}/reservas",
    headers=headers,
    json={
        "cliente_id": 1,
        "fecha_checkin": "2025-12-10",
        "fecha_checkout": "2025-12-15",
        # ... más datos
    }
)

# 5. Renovar token cuando expire
if access_token_expirado():
    refresh_response = requests.post(
        f"{BASE_URL}/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    nuevos_tokens = refresh_response.json()
    access_token = nuevos_tokens["access_token"]
```

### Ejemplo con Manejo de Errores

```python
def hacer_request_autenticado(url, method="GET", data=None):
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 401:
            # Token expirado, renovar
            nuevos_tokens = renovar_token(refresh_token)
            # Reintentar con nuevo token
            return hacer_request_autenticado(url, method, data)
        
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            print("Acceso denegado: permisos insuficientes")
        elif e.response.status_code == 404:
            print("Recurso no encontrado")
        else:
            print(f"Error: {e}")
```

---

## 🔒 Seguridad y Mejores Prácticas

### 1. Almacenamiento de Tokens

**Frontend:**
```javascript
// ❌ NO usar localStorage para tokens sensibles
localStorage.setItem('token', accessToken)  // INSEGURO

// ✅ Usar httpOnly cookies o sessionStorage
sessionStorage.setItem('token', accessToken)

// Mejor aún: cookies httpOnly desde el backend
```

### 2. Rotación de Tokens

```python
# Implementar renovación automática antes de expirar
if token_expira_en < 5_minutos:
    renovar_token()
```

### 3. Variables de Entorno

```python
# ✅ Usar variables de entorno en producción
import os
SECRET_KEY = os.getenv("SECRET_KEY")

# ❌ NO hardcodear claves
SECRET_KEY = "mi-clave-123"  # PELIGROSO
```

### 4. HTTPS en Producción

```python
# Asegurar que todos los endpoints usen HTTPS
if not request.url.scheme == "https" and not DEBUG:
    raise HTTPException(403, "HTTPS requerido")
```

---

## 📊 Matriz de Permisos

| Acción | Admin | Gerente | Recepcionista | Readonly |
|--------|-------|---------|---------------|----------|
| Login | ✅ | ✅ | ✅ | ✅ |
| Ver perfil propio | ✅ | ✅ | ✅ | ✅ |
| Cambiar su password | ✅ | ✅ | ✅ | ✅ |
| Crear usuarios | ✅ | ✅* | ❌ | ❌ |
| Editar usuarios | ✅ | ✅* | ❌ | ❌ |
| Eliminar usuarios | ✅ | ❌ | ❌ | ❌ |
| Ver estadísticas | ✅ | ✅ | ❌ | ❌ |
| Crear reservas | ✅ | ✅ | ✅ | ❌ |
| Check-in/out | ✅ | ✅ | ✅ | ❌ |
| Ver reservas | ✅ | ✅ | ✅ | ✅ |
| Eliminar reservas | ✅ | ✅ | ❌ | ❌ |

\* Gerente solo puede crear/editar recepcionistas y readonly

---

## 🐛 Troubleshooting

### Error: "No se pudo validar las credenciales"

```python
# Verificar que el token se envía correctamente
headers = {"Authorization": "Bearer YOUR_TOKEN"}  # Notar "Bearer "
```

### Error: "Usuario bloqueado temporalmente"

```python
# Esperar 30 minutos o contactar admin para desbloquear
# Admin puede resetear manualmente en la BD:
UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL WHERE username = 'usuario';
```

### Error: "Token expirado"

```python
# Usar el refresh token para obtener nuevo access token
POST /auth/refresh
```

---

## 📚 Referencias

- [JWT.io](https://jwt.io) - Decodificador de JWT
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [OAuth2 Password Flow](https://oauth.net/2/grant-types/password/)
- [Bcrypt](https://en.wikipedia.org/wiki/Bcrypt) - Algoritmo de hashing

---

**Desarrollado por:** Sistema Hotel Management  
**Versión:** 2.0  
**Fecha:** Diciembre 2025
