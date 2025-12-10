# 🏨 ERS — Sistema de Gestión Hotelera

## 📋 Descripción

Sistema administrativo completo para hoteles con gestión de reservas, habitaciones, clientes, empresas y servicios. Incluye autenticación JWT, autorización por roles, estadísticas avanzadas y operaciones de check-in/check-out.

**Versión:** 2.0 - Con endpoints robustos y auditoría completa

## ✨ Características Principales

### 🔐 Autenticación y Seguridad
- ✅ Sistema JWT con Access Token y Refresh Token
- ✅ 4 niveles de roles (Admin, Gerente, Recepcionista, Readonly)
- ✅ Protección contra fuerza bruta (intentos fallidos, bloqueos)
- ✅ Passwords hasheadas con bcrypt
- ✅ Auditoría completa de accesos
- ✅ Timestamps automáticos en cambios

### 📊 Módulos Principales
- ✅ Gestión de Clientes (con preferencias, auditoría completa)
- ✅ Gestión de Empresas (con términos comerciales)
- ✅ Gestión de Habitaciones (con categorías y historial de mantenimiento)
- ✅ Sistema de Reservas (breakdown financiero, estados detallados)
- ✅ Check-in / Check-out automatizado
- ✅ Estadísticas y reportes
- ✅ Consulta de disponibilidad
- ✅ Historial de cambios con trazabilidad

### 🚀 Características Avanzadas
- ✅ Soft delete en todas las entidades
- ✅ Validaciones exhaustivas con manejo robusto de errores
- ✅ Logging detallado de operaciones
- ✅ Descuentos automáticos (7+ noches)
- ✅ Gestión de productos/servicios adicionales
- ✅ Dashboard con métricas en tiempo real
- ✅ Cascading relationships y referential integrity
- ✅ Enums para type-safety

## 🆕 Mejoras en v2.0

### Modelos Mejorados
```
✅ Cliente: campos personales, auditoría, preferencias JSON
✅ Empresa: contacto desagregado, términos comerciales
✅ Reserva: breakdown financiero, historial con estados
✅ Habitación: categorías, mantenimiento con historial
✅ Usuario: roles dinámicos, seguridad mejorada
✅ Servicios: auditoría y control de estado
```

### Endpoints Robustos
```
✅ Validaciones exhaustivas (50+ nuevas)
✅ Manejo de errores específicos (IntegrityError, SQLAlchemyError)
✅ Prevención de duplicados
✅ Auditoría automática (creado_en, actualizado_en)
✅ Transacciones ACID con rollback
✅ Logs detallados por operación
```

## 📦 Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/nachitoxx6262/Backend_Hotel.git
cd Backend_Hotel
```

### 2. Instalar dependencias base

```bash
pip install -r requirements.txt
```

### 3. Instalar sistema de autenticación

**Windows (PowerShell):**
```powershell
.\install_auth.ps1
```

**Linux/Mac:**
```bash
chmod +x install_auth.sh
./install_auth.sh
```

### 4. Configurar variables de entorno

```bash
# Copiar plantilla
cp .env.example .env

# Editar .env y configurar
# Especialmente cambiar SECRET_KEY en producción
```

### 5. Crear usuario administrador

```bash
python create_admin.py
```

### 6. Iniciar el servidor

```bash
uvicorn main:app --reload
```

Acceder a:
- **API Docs:** http://localhost:8000/docs
- **API:** http://localhost:8000

## 🎯 Endpoints Disponibles

### 🔐 Autenticación (`/auth`)
- `POST /auth/login` - Iniciar sesión
- `POST /auth/register` - Registrar usuario (admin)
- `POST /auth/refresh` - Renovar token
- `GET /auth/me` - Obtener perfil
- `PUT /auth/me` - Actualizar perfil
- `POST /auth/change-password` - Cambiar contraseña
- `GET /auth/usuarios` - Listar usuarios (admin/gerente)
- `GET /auth/usuarios/{id}` - Obtener usuario
- `PUT /auth/usuarios/{id}` - Actualizar usuario
- `DELETE /auth/usuarios/{id}` - Eliminar usuario (admin)

### 👥 Clientes (`/clientes`)
- CRUD completo de clientes
- Búsqueda por nombre, apellido, documento
- Gestión de blacklist
- Soft delete y restauración
- Resumen de clientes

### 🏢 Empresas (`/empresas`)
- CRUD completo de empresas
- Búsqueda por nombre, CUIT, email
- Gestión de blacklist
- Soft delete y restauración
- Resumen de empresas

### 🛏️ Habitaciones (`/habitaciones`)
- CRUD completo de habitaciones
- Estados: libre, ocupada, reservada, mantenimiento
- Validación de número único

### 📅 Reservas (`/reservas`)
- Crear, modificar, consultar reservas
- Estados: reservada, ocupada, finalizada, cancelada
- Gestión de habitaciones y servicios adicionales
- Cálculo automático de totales
- Descuentos por estadía prolongada
- Historial de cambios de estado
- Filtros por estado, cliente, empresa, fechas

### ✅ Check-In/Check-Out (`/checkin-checkout`)
- `GET /checkin-checkout/pendientes-checkin` - Listar pendientes entrada
- `GET /checkin-checkout/pendientes-checkout` - Listar pendientes salida
- `POST /checkin-checkout/{id}/checkin` - Realizar check-in
- `POST /checkin-checkout/{id}/checkout` - Realizar check-out
- `POST /checkin-checkout/{id}/checkin-express` - Check-in rápido
- `POST /checkin-checkout/{id}/checkout-express` - Check-out rápido
- `GET /checkin-checkout/resumen` - Resumen diario

### 📊 Estadísticas (`/estadisticas`)
- `GET /estadisticas/dashboard` - Dashboard general
- `GET /estadisticas/ocupacion` - Ocupación por período
- `GET /estadisticas/ingresos` - Ingresos agrupados
- `GET /estadisticas/top-clientes` - Mejores clientes
- `GET /estadisticas/habitaciones-populares` - Habitaciones más reservadas

### 🔍 Disponibilidad (`/disponibilidad`)
- `GET /disponibilidad/habitaciones` - Consultar disponibilidad
- `GET /disponibilidad/calendario` - Calendario por habitación
- `GET /disponibilidad/resumen` - Resumen por fecha

## 1. Objetivo General
Desarrollar un sistema administrativo para hoteles, permitiendo la gestión eficiente de reservas, habitaciones, clientes, empresas y servicios, asegurando la integridad y trazabilidad de los datos y facilitando el trabajo del personal.

## 2. Requerimientos Funcionales

### 2.1. Gestión de Clientes
- Alta, baja lógica (columna `deleted`), modificación y consulta de clientes particulares y corporativos.
- Cada cliente puede estar asociado o no a una empresa.
- Validación de unicidad de la combinación `tipo_documento` + `numero_documento`.
- Imposibilidad de eliminar físicamente un cliente con reservas activas.

### 2.2. Gestión de Empresas
- CRUD completo de empresas.
- Validación de CUIT único.
- Baja lógica (`deleted`).
- No eliminar empresas con reservas activas.

### 2.3. Gestión de Habitaciones
- CRUD completo de habitaciones.
- Validación de número único.
- Estados posibles: `libre`, `reservada`, `ocupada`, `mantenimiento`.
- Columna de observaciones.
- Baja lógica (`deleted`).
- No eliminar habitaciones con reservas activas o futuras.

### 2.4. Gestión de Reservas
- Alta, baja lógica, modificación y consulta de reservas.
- Estados posibles: `reservada`, `ocupada`, `finalizada`, `cancelada`.
- Al crear una reserva, la habitación pasa a estado `reservada`.
- Al hacer check-in (cuando llegan los huéspedes), la reserva pasa a estado `ocupada`, y la habitación también.
- Al hacer check-out (cuando se retiran), la reserva pasa a estado `finalizada` y la habitación vuelve a `libre` (o `mantenimiento` si corresponde).
- No se permite reservar una habitación en fechas donde ya está ocupada o reservada.
- Cálculo automático del total (habitaciones, ítems, descuentos).
- Permite agregar productos/servicios extra.
- No permitir reservas con fechas inválidas (check-in >= check-out).
- No se elimina físicamente una reserva: solo se marca como eliminada (`deleted`) salvo acción directa del administrador.

### 2.5. Gestión de Productos y Servicios
- CRUD de productos y servicios.
- Pueden asociarse a reservas como ítems extra.

### 2.6. Gestión de Mantenimiento
- Permitir marcar habitaciones en mantenimiento (no reservables).
- Registrar observaciones de mantenimiento.

### 2.7. Panel Administrativo
- Solo usuarios autorizados pueden acceder al sistema.
- El acceso requiere autenticación (login/password). Debe haber al menos dos tipos de usuario: administrador y operador.
- Panel para visualizar, filtrar, crear, modificar, finalizar o cancelar reservas y habitaciones.
- Reportes y estadísticas sobre ocupación, ingresos, mantenimiento.

## 3. Requerimientos No Funcionales

- **Logs/Auditoría:**  
  Registrar todas las acciones clave: creación, modificación, eliminación lógica, cambios de estado. (Se puede implementar después del MVP, pero la estructura debe pensarse desde el principio).

- **Integridad:**  
  Validaciones server-side para prevenir datos inconsistentes o duplicados.

- **Escalabilidad y rendimiento:**  
  Capacidad para operar con cientos de habitaciones y reservas sin demoras.

- **Baja lógica (`deleted`):**  
  Toda entidad principal (clientes, empresas, habitaciones, reservas) debe tener columna `deleted` (boolean). El sistema no elimina registros físicamente por defecto.

- **Backups y recuperación:**  
  El sistema debe permitir o facilitar la realización de copias de seguridad periódicas y la recuperación de datos en caso de pérdida.

- **Configurabilidad:**  
  Estados posibles y reglas de negocio clave (horarios, penalizaciones, etc.) deben ser configurables desde el backend o la base de datos.

- **Internacionalización:**  
  El sistema debe poder adaptarse fácilmente a distintos formatos de fecha, moneda e idioma.

## 4. Restricciones

- No se pueden eliminar entidades (clientes, habitaciones, empresas) si están asociadas a reservas activas o futuras, salvo acción explícita del administrador con permisos especiales.
- No se pueden crear reservas solapadas para la misma habitación.
- Las habitaciones en mantenimiento no pueden ser reservadas.

## 5. Casos de Uso Principales

- Registrar reserva (con validación de disponibilidad)
- Realizar check-in (cambio de estado a ocupada)
- Realizar check-out (finalizar reserva y liberar habitación)
- Cancelar reserva (cambia estado, no elimina)
- Baja lógica de clientes, habitaciones, reservas, empresas
- CRUD de productos y servicios
- Filtro y consulta de habitaciones por estado
- Reporte de reservas y ocupación
- Registro de acciones para auditoría

## 6. Notas y Futuras Mejoras

- Implementar logs/auditoría desde el principio o dejar preparado el sistema para hacerlo sin refactor mayor.
- Eliminar físico solo como acción administrativa especial, con registro en logs.
- Restringir acciones según permisos de usuario en el sistema.
- Posibilidad de expandir a multi-sucursal.
- Implementar notificaciones y recordatorios internos (alertas de reservas próximas, habitaciones a liberar, etc.).








 Sugerencias Adicionales Documentadas
Autenticación JWT y autorización por roles
Sistema de facturación
Notificaciones email/SMS
Precios dinámicos
Reportes avanzados (PDF/Excel)
Sistema de reviews
Gestión de mantenimiento programado
Integración con pasarelas de pago
Webhooks para eventos
Y más...