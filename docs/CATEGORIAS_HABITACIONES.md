# Gestión de Categorías de Habitaciones

## 🎯 Descripción General
Se agregó un sistema completo para administrar categorías de habitaciones con funcionalidad CRUD (Crear, Leer, Actualizar, Eliminar). Incluye tanto backend como frontend.

## 📦 Componentes Agregados

### Backend

#### 1. **Endpoint: `/categorias_habitacion.py`**
   - **Ruta base:** `/categorias`
   - **Métodos disponibles:**
     - `GET /categorias` - Listar todas las categorías activas
     - `GET /categorias/{id}` - Obtener una categoría específica
     - `POST /categorias` - Crear nueva categoría
     - `PUT /categorias/{id}` - Actualizar categoría
     - `DELETE /categorias/{id}` - Eliminar categoría (validar que no tenga habitaciones)

   **Validaciones implementadas:**
   - Nombre obligatorio y único
   - Capacidad mínima de 1 persona
   - Precio no negativo
   - Verifica que no haya habitaciones asociadas antes de eliminar

#### 2. **Schema: `/schemas/categorias.py`**
   - `CategoriaCreate` - Para crear categorías con validación Pydantic
   - `CategoriaUpdate` - Para actualizar (todos los campos son opcionales)
   - `CategoriaRead` - Para responder con datos completos

#### 3. **Modelo Mejorado:**
   - `CategoriaHabitacion` en `models/habitacion.py`
   - Campo `amenidades` ahora es JSON (array) para mejor manejo

### Frontend

#### 1. **Servicio: `/services/categorias.js`**
   - Funciones para comunicarse con la API
   - Manejo de tokens JWT automático
   - Métodos: `listarCategorias()`, `crearCategoria()`, `actualizarCategoria()`, `eliminarCategoria()`

#### 2. **Componentes React:**
   - **`CategoriasPanel.jsx`** - Página principal de gestión
     - Lista de categorías con tabla
     - Estados de carga y notificaciones
     - Integración completa del CRUD
   
   - **`CategoriasModal.jsx`** - Modal para crear/editar
     - Formulario con validación de campos
     - Campo para amenidades (una por línea)
     - Botón para eliminar (solo en edición)
   
   - **`CategoriasTable.jsx`** - Tabla de categorías
     - Muestra todos los campos
     - Botones de editar y eliminar por fila
     - Badges para estado y capacidad

#### 3. **Actualización de componentes existentes:**
   - **`HabitacionesHeader.jsx`** - Nuevo parámetro `onCategoriesClick` y botón "Categorías"
   - **`Habitaciones.jsx`** - Integración de `CategoriasPanel` con navegación entre vistas

## 🔌 Integración

### Backend - `main.py`
```python
from endpoints import categorias_habitacion
app.include_router(categorias_habitacion.router)
```

### Models - `models/__init__.py`
```python
from .habitacion import Habitacion, CategoriaHabitacion, MantenimientoHabitacion
```

## 🎨 Interfaz de Usuario

1. **Botón "Categorías"** en el header de Habitaciones
   - Lleva a un panel separado
   - Botón "Volver a Habitaciones" para regresar

2. **Panel de Categorías:**
   - Tabla con todas las categorías
   - Botón "Nueva Categoría" en la esquina superior derecha
   - Botones de editar y eliminar en cada fila
   - Notificaciones de éxito/error

3. **Formulario:**
   - Nombre (obligatorio, único)
   - Descripción (opcional)
   - Capacidad de personas (mínimo 1)
   - Precio base por noche
   - Amenidades (textarea con una por línea)
   - Checkbox para activar/desactivar

## 📊 Campos de Categoría

| Campo | Tipo | Validación | Notas |
|-------|------|------------|-------|
| id | Integer | PK, Auto | |
| nombre | String(50) | Unique, Required | |
| descripcion | Text | Optional | |
| capacidad_personas | Integer | >= 1 | |
| precio_base_noche | Numeric(10,2) | >= 0 | |
| amenidades | JSON Array | Optional | Lista de strings |
| activo | Boolean | Default=True | |
| creado_en | DateTime | Default=Now | |
| actualizado_en | DateTime | Auto-update | |

## ✅ Ejemplo de Uso

### Crear Categoría (Frontend)
```javascript
const categoria = {
  nombre: "Suite Presidencial",
  descripcion: "Habitación de lujo con vistas al mar",
  capacidad_personas: 2,
  precio_base_noche: 250.00,
  amenidades: ["WiFi", "TV 4K", "Minibar", "Jacuzzi", "Balcón"]
};

await crearCategoria(categoria);
```

### Crear Categoría (API)
```bash
POST /categorias
Content-Type: application/json

{
  "nombre": "Suite Presidencial",
  "descripcion": "Habitación de lujo con vistas al mar",
  "capacidad_personas": 2,
  "precio_base_noche": 250.00,
  "amenidades": ["WiFi", "TV 4K", "Minibar", "Jacuzzi", "Balcón"]
}
```

## 🔒 Seguridad

- ✅ Token JWT requerido en todas las solicitudes (desde frontend)
- ✅ Validación en schema (Pydantic)
- ✅ Validación en endpoint
- ✅ Prevención de eliminación si hay habitaciones asociadas
- ✅ Manejo de errores específicos (409 para duplicados, 404 para no encontrado, etc.)

## 📝 Logging

Todos los eventos se registran:
- Creación de categoría
- Actualización de categoría
- Eliminación de categoría
- Errores durante operaciones

## 🚀 Próximos Pasos

1. ✅ Actualizar el formulario de creación de habitaciones para seleccionar categoría
2. ✅ Mostrar amenidades en la vista de habitaciones
3. ✅ Crear endpoints de mantenimiento de habitaciones
4. ✅ Agregar gestión de precios dinámicos por categoría
