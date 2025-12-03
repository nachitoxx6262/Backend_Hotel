# API de Clientes y Empresas

Documentación detallada de los endpoints relacionados con la gestión de clientes y empresas del Backend Hotel. Todos los ejemplos asumen que la aplicación corre en `http://localhost:8000`.

## Clientes

### Listar clientes
- **Endpoint:** `GET /clientes`
- **Descripción:** Recupera todos los clientes activos (no eliminados).
- **Respuesta 200:** Lista de objetos `ClienteRead`.

### Búsqueda avanzada
- **Endpoint:** `GET /clientes/buscar`
- **Query params opcionales:**
  - `nombre`, `apellido` (1-60 caracteres)
  - `tipo_documento` (2-20 caracteres)
  - `numero_documento` (2-40 caracteres)
  - `empresa_id` (entero > 0)
- **Descripción:** Filtra clientes activos usando coincidencias parciales (ILIKE) y empresa exacta.
- **Respuesta 200:** Lista de clientes que cumplen con los filtros.

### Listar clientes sin empresa
- **Endpoint:** `GET /clientes/sin-empresa`
- **Descripción:** Devuelve clientes activos con `empresa_id` nulo.

### Verificar existencia
- **Endpoint:** `GET /clientes/existe`
- **Query params requeridos:** `tipo_documento`, `numero_documento`
- **Descripción:** Indica si existe un cliente activo con la combinación tipo/número de documento.
- **Respuesta 200:** `{ "existe": true|false }`.

### Resumen administrativo
- **Endpoint:** `GET /clientes/resumen`
- **Descripción:** Estadísticas globales (`total`, `activos`, `eliminados`, `blacklist`).

### Obtener por ID
- **Endpoint:** `GET /clientes/{cliente_id}`
- **Descripción:** Devuelve un cliente activo por ID.
- **Errores:** 404 si no existe o está eliminado.

### Crear cliente
- **Endpoint:** `POST /clientes`
- **Body (JSON):**
  ```json
  {
    "nombre": "string",
    "apellido": "string",
    "tipo_documento": "string",
    "numero_documento": "string",
    "nacionalidad": "string",
    "email": "email",
    "telefono": "string",
    "empresa_id": 1
  }
  ```
- **Validaciones clave:**
  - Tipo/número únicos entre clientes activos.
  - Empresa asociada debe existir, estar activa y no en blacklist.
- **Respuesta 201:** Objeto `ClienteRead`.
- **Errores:** 409 (duplicado), 400/404 (empresa inválida).

### Actualizar cliente
- **Endpoint:** `PUT /clientes/{cliente_id}`
- **Body:** Campos parciales del modelo `ClienteUpdate` (todos opcionales).
- **Validaciones:**
  - Requiere al menos un campo.
  - Mantiene unicidad de documento.
  - Verifica empresa como en creación.
- **Respuesta 200:** Cliente actualizado.

### Eliminar lógico
- **Endpoint:** `DELETE /clientes/{cliente_id}`
- **Descripción:** Marca `deleted=true` si no tiene reservas activas.
- **Errores:** 404 (no encontrado), 409 (reservas `reservada` u `ocupada`).

### Restaurar
- **Endpoint:** `PUT /clientes/{cliente_id}/restaurar`
- **Descripción:** Reactiva un cliente previamente eliminado.
- **Errores:** 404 si no está eliminado.

### Eliminación definitiva
- **Endpoint:** `DELETE /clientes/{cliente_id}/eliminar-definitivo`
- **Query param requerido:** `superadmin=true`
- **Descripción:** Elimina físicamente un cliente sin reservas asociadas.
- **Errores:** 403 (sin permiso), 404 (no existe), 409 (reservas presentes).

### Blacklist
- **Listar:** `GET /clientes/blacklist`
- **Agregar:** `PUT /clientes/{cliente_id}/blacklist`
- **Quitar:** `PUT /clientes/{cliente_id}/quitar-blacklist`
- **Reglas:**
  - Solo clientes activos.
  - 404 si no existe, 409 si ya está/no está en blacklist según corresponda.

### Listar eliminados
- **Endpoint:** `GET /clientes/eliminados`
- **Descripción:** Clientes marcados como eliminados.

## Empresas

### Listar empresas
- **Endpoint:** `GET /empresas`
- **Descripción:** Devuelve empresas activas.

### Búsqueda avanzada
- **Endpoint:** `GET /empresas/buscar`
- **Query opcionales:** `nombre`, `cuit`, `email`
- **Descripción:** Coincidencias parciales (ILIKE) en campos alfanuméricos.

### Búsqueda exacta
- **Endpoint:** `GET /empresas/buscar-exacta`
- **Query opcionales:** `nombre`, `cuit`
- **Descripción:** Coincidencia exacta en nombre o CUIT.

### Verificar existencia por CUIT
- **Endpoint:** `GET /empresas/existe`
- **Query requerido:** `cuit`
- **Respuesta 200:** `{ "existe": true|false }`.

### Resumen
- **Endpoint:** `GET /empresas/resumen`
- **Resultado:** `total`, `activas`, `eliminadas`, `blacklist`.

### Obtener por ID
- **Endpoint:** `GET /empresas/{empresa_id}`
- **Errores:** 404 si no existe o está eliminada.

### Crear empresa
- **Endpoint:** `POST /empresas`
- **Body mínimo:**
  ```json
  {
    "nombre": "string",
    "cuit": "string",
    "email": "email",
    "telefono": "string",
    "direccion": "string"
  }
  ```
- **Validaciones:** CUIT único entre empresas activas.
- **Respuesta 201:** `EmpresaRead`.

### Actualizar empresa
- **Endpoint:** `PUT /empresas/{empresa_id}`
- **Body:** Campos opcionales de `EmpresaUpdate`.
- **Reglas:**
  - Al menos un campo.
  - CUIT nuevo mantiene unicidad.
  - Ignora cambios directos en `deleted` y `blacklist`.

### Eliminar lógico
- **Endpoint:** `DELETE /empresas/{empresa_id}`
- **Condición:** No debe tener reservas activas (`reservada`, `ocupada`).
- **Errores:** 404 o 409 según corresponda.

### Restaurar
- **Endpoint:** `PUT /empresas/{empresa_id}/restaurar`
- **Descripción:** Reactiva empresa eliminada.

### Eliminación definitiva
- **Endpoint:** `DELETE /empresas/{empresa_id}/eliminar-definitivo`
- **Query requerido:** `superadmin=true`
- **Condiciones:** Sin reservas asociadas ni clientes asignados.
- **Errores:** 403, 404 o 409.

### Blacklist
- **Listar:** `GET /empresas/blacklist`
- **Agregar:** `PUT /empresas/{empresa_id}/blacklist`
- **Quitar:** `PUT /empresas/{empresa_id}/quitar-blacklist`
- **Restricciones:** Solo empresas activas; 409 si estado redundante.

### Listar eliminadas
- **Endpoint:** `GET /empresas/eliminadas`
- **Descripción:** Empresas marcadas como eliminadas.

## Convenciones generales
- Todas las rutas devuelven errores con detalles JSON (`{"detail": "mensaje"}`).
- Registro de acciones en `hotel_logs.txt` mediante logger compartido.
- Validaciones estructurales manejadas por Pydantic v2 (`model_validator`).

Para escenarios completos (reservas, habitaciones, etc.) consulta la documentación adicional del proyecto.
