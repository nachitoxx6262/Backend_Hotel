-- Migración 005: Crear tablas multi-tenant SaaS core
-- Esta migración introduce el nuevo modelo de tenants (EmpresaUsuario) para la arquitectura SaaS

-- Enum para tipos de planes
CREATE TYPE plan_type_enum AS ENUM ('demo', 'basico', 'premium');
CREATE TYPE subscription_status_enum AS ENUM ('activo', 'vencido', 'cancelado', 'bloqueado');
CREATE TYPE payment_status_enum AS ENUM ('pendiente', 'exitoso', 'fallido');
CREATE TYPE payment_provider_enum AS ENUM ('dummy', 'mercado_pago', 'stripe');

-- Tabla: Planes de suscripción SaaS
CREATE TABLE IF NOT EXISTS planes (
    id SERIAL PRIMARY KEY,
    nombre plan_type_enum NOT NULL UNIQUE,
    descripcion TEXT,
    precio_mensual NUMERIC(12, 2) NOT NULL,
    max_habitaciones INTEGER NOT NULL DEFAULT 10,
    max_usuarios INTEGER NOT NULL DEFAULT 5,
    caracteristicas JSONB,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uq_plan_nombre UNIQUE (nombre)
);

CREATE INDEX idx_plan_nombre ON planes(nombre);

-- Tabla: Empresas usuarias (SaaS tenants - Hoteles)
CREATE TABLE IF NOT EXISTS empresa_usuarios (
    id SERIAL PRIMARY KEY,
    nombre_hotel VARCHAR(150) NOT NULL,
    cuit VARCHAR(20) NOT NULL UNIQUE,
    
    contacto_nombre VARCHAR(100),
    contacto_email VARCHAR(100),
    contacto_telefono VARCHAR(30),
    
    direccion VARCHAR(200),
    ciudad VARCHAR(100),
    provincia VARCHAR(100),
    
    plan_tipo plan_type_enum NOT NULL DEFAULT 'demo',
    
    -- Trial de 10 días (solo para plan DEMO)
    fecha_inicio_demo TIMESTAMP,
    fecha_fin_demo TIMESTAMP,
    
    activa BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uq_empresa_usuario_cuit UNIQUE (cuit)
);

CREATE INDEX idx_empresa_usuario_nombre ON empresa_usuarios(nombre_hotel);
CREATE INDEX idx_empresa_usuario_estado ON empresa_usuarios(activa);

-- Tabla: Subscripciones SaaS
CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    empresa_usuario_id INTEGER NOT NULL UNIQUE,
    plan_id INTEGER NOT NULL,
    estado subscription_status_enum NOT NULL DEFAULT 'activo',
    fecha_proxima_renovacion TIMESTAMP,
    metadata JSONB,  -- Almacena detalles de pago, campañas, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_subscription_empresa_usuario
        FOREIGN KEY (empresa_usuario_id)
        REFERENCES empresa_usuarios(id)
        ON DELETE CASCADE,
    
    CONSTRAINT fk_subscription_plan
        FOREIGN KEY (plan_id)
        REFERENCES planes(id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_subscription_estado ON subscriptions(estado);
CREATE INDEX idx_subscription_empresa_usuario ON subscriptions(empresa_usuario_id);

-- Tabla: Intentos de pago (audit trail)
CREATE TABLE IF NOT EXISTS payment_attempts (
    id SERIAL PRIMARY KEY,
    subscription_id INTEGER NOT NULL,
    
    monto NUMERIC(12, 2) NOT NULL,
    estado payment_status_enum NOT NULL DEFAULT 'pendiente',
    proveedor payment_provider_enum NOT NULL DEFAULT 'dummy',
    
    external_id VARCHAR(255),  -- ID del proveedor de pago
    webhook_url VARCHAR(500),
    response_json JSONB,  -- Respuesta completa del proveedor
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_payment_subscription
        FOREIGN KEY (subscription_id)
        REFERENCES subscriptions(id)
        ON DELETE CASCADE
);

CREATE INDEX idx_payment_subscription ON payment_attempts(subscription_id);
CREATE INDEX idx_payment_estado ON payment_attempts(estado);

-- Tabla: Clientes corporativos (renombrada de empresas)
-- Esta tabla almacena a los clientes que RESERVAN en el hotel (ej: Coca Cola, Mercedes)
-- CAMBIO: Ahora tiene FK obligatorio a empresa_usuario (no compartidos entre tenants)
CREATE TABLE IF NOT EXISTS cliente_corporativo (
    id SERIAL PRIMARY KEY,
    empresa_usuario_id INTEGER NOT NULL,
    
    nombre VARCHAR(150) NOT NULL,
    cuit VARCHAR(20) NOT NULL,
    tipo_empresa VARCHAR(50),
    
    contacto_nombre VARCHAR(100),
    contacto_email VARCHAR(100),
    contacto_telefono VARCHAR(30),
    
    direccion VARCHAR(200),
    ciudad VARCHAR(100),
    provincia VARCHAR(100),
    
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_cliente_corporativo_empresa_usuario
        FOREIGN KEY (empresa_usuario_id)
        REFERENCES empresa_usuarios(id)
        ON DELETE CASCADE,
    
    CONSTRAINT uq_cliente_corporativo_cuit UNIQUE (cuit)
);

CREATE INDEX idx_cliente_corporativo_nombre ON cliente_corporativo(nombre);
CREATE INDEX idx_cliente_corporativo_empresa_usuario ON cliente_corporativo(empresa_usuario_id);

-- Actualizar tabla clientes: cambiar FK de empresas a cliente_corporativo
-- (Esta parte será realizada en migración 006 que modifica tablas existentes)

COMMIT;
