# 🏨 ERS — Sistema de Gestión Hotelera

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
