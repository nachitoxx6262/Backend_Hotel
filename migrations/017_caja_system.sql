-- Migración 017: Sistema de Caja - Ingresos y Egresos
-- Esta migración crea las tablas para el control de caja, ingresos y egresos

-- ============================================================
-- 1. CREAR TIPOS ENUM
-- ============================================================

-- Tipo de transacción
CREATE TYPE transaction_type AS ENUM ('ingreso', 'egreso');

-- Métodos de pago
CREATE TYPE payment_method AS ENUM ('efectivo', 'transferencia', 'tarjeta', 'cheque', 'otro');


-- ============================================================
-- 2. CREAR TABLAS
-- ============================================================

-- Tabla: transaction_categories (Categorías de ingresos y egresos)
CREATE TABLE IF NOT EXISTS transaction_categories (
    id SERIAL PRIMARY KEY,
    empresa_usuario_id INTEGER NOT NULL REFERENCES empresa_usuarios(id) ON DELETE CASCADE,
    nombre VARCHAR(100) NOT NULL,
    tipo transaction_type NOT NULL,
    descripcion TEXT,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    es_sistema BOOLEAN NOT NULL DEFAULT FALSE,  -- No editable/eliminable si es TRUE
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    CONSTRAINT uq_category_nombre_tipo UNIQUE (empresa_usuario_id, nombre, tipo)
);

-- Tabla: transactions (Registro de ingresos y egresos)
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    empresa_usuario_id INTEGER NOT NULL REFERENCES empresa_usuarios(id) ON DELETE CASCADE,
    tipo transaction_type NOT NULL,
    category_id INTEGER NOT NULL REFERENCES transaction_categories(id) ON DELETE RESTRICT,
    
    monto NUMERIC(12, 2) NOT NULL,
    metodo_pago payment_method NOT NULL,
    referencia VARCHAR(255),
    
    fecha TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    
    -- Relaciones opcionales con entidades del sistema
    stay_id INTEGER REFERENCES stays(id) ON DELETE SET NULL,
    subscription_id INTEGER REFERENCES subscriptions(id) ON DELETE SET NULL,
    cliente_id INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
    
    -- Control de anulaciones (no se permite edición, solo anulación)
    anulada BOOLEAN NOT NULL DEFAULT FALSE,
    anulada_por_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    anulada_fecha TIMESTAMP WITH TIME ZONE,
    motivo_anulacion TEXT,
    transaction_anulacion_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
    
    notas TEXT,
    es_automatica BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    CONSTRAINT chk_monto_positivo CHECK (monto > 0)
);

-- Tabla: cash_closings (Cierre de caja por turno)
CREATE TABLE IF NOT EXISTS cash_closings (
    id SERIAL PRIMARY KEY,
    empresa_usuario_id INTEGER NOT NULL REFERENCES empresa_usuarios(id) ON DELETE CASCADE,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    
    fecha_apertura TIMESTAMP WITH TIME ZONE NOT NULL,
    fecha_cierre TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Montos calculados por el sistema
    ingresos_sistema NUMERIC(12, 2) NOT NULL DEFAULT 0,
    egresos_sistema NUMERIC(12, 2) NOT NULL DEFAULT 0,
    saldo_sistema NUMERIC(12, 2) NOT NULL DEFAULT 0,
    
    -- Montos declarados por el usuario
    efectivo_declarado NUMERIC(12, 2) NOT NULL,
    diferencia NUMERIC(12, 2) NOT NULL,
    
    notas TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);


-- ============================================================
-- 3. CREAR ÍNDICES
-- ============================================================

-- Índices para transaction_categories
CREATE INDEX idx_category_empresa ON transaction_categories(empresa_usuario_id);
CREATE INDEX idx_category_tipo ON transaction_categories(tipo);
CREATE INDEX idx_category_activo ON transaction_categories(activo);

-- Índices para transactions
CREATE INDEX idx_transaction_empresa ON transactions(empresa_usuario_id);
CREATE INDEX idx_transaction_tipo ON transactions(tipo);
CREATE INDEX idx_transaction_fecha ON transactions(fecha);
CREATE INDEX idx_transaction_usuario ON transactions(usuario_id);
CREATE INDEX idx_transaction_stay ON transactions(stay_id);
CREATE INDEX idx_transaction_subscription ON transactions(subscription_id);
CREATE INDEX idx_transaction_cliente ON transactions(cliente_id);
CREATE INDEX idx_transaction_anulada ON transactions(anulada);
CREATE INDEX idx_transaction_category ON transactions(category_id);

-- Índice compuesto para consultas de rango de fechas por empresa
CREATE INDEX idx_transaction_empresa_fecha ON transactions(empresa_usuario_id, fecha DESC);

-- Índice compuesto para consultas de tipo de transacción por empresa
CREATE INDEX idx_transaction_empresa_tipo ON transactions(empresa_usuario_id, tipo);

-- Índices para cash_closings
CREATE INDEX idx_cash_closing_empresa ON cash_closings(empresa_usuario_id);
CREATE INDEX idx_cash_closing_usuario ON cash_closings(usuario_id);
CREATE INDEX idx_cash_closing_fecha ON cash_closings(fecha_cierre);
CREATE INDEX idx_cash_closing_fecha_apertura ON cash_closings(fecha_apertura);


-- ============================================================
-- 4. HABILITAR ROW LEVEL SECURITY (RLS)
-- ============================================================

-- Tabla: transaction_categories
ALTER TABLE transaction_categories ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_transaction_categories_access ON transaction_categories
    FOR ALL
    USING (
        -- Super admin puede ver todos
        (SELECT es_super_admin FROM usuarios WHERE id = NULLIF(current_setting('app.current_user_id', true), '')::INTEGER) = TRUE
        OR
        -- Usuario ve categorías de su tenant
        empresa_usuario_id = NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER
    );

-- Tabla: transactions
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_transactions_access ON transactions
    FOR ALL
    USING (
        -- Super admin puede ver todos
        (SELECT es_super_admin FROM usuarios WHERE id = NULLIF(current_setting('app.current_user_id', true), '')::INTEGER) = TRUE
        OR
        -- Usuario ve transacciones de su tenant
        empresa_usuario_id = NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER
    );

-- Tabla: cash_closings
ALTER TABLE cash_closings ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_cash_closings_access ON cash_closings
    FOR ALL
    USING (
        -- Super admin puede ver todos
        (SELECT es_super_admin FROM usuarios WHERE id = NULLIF(current_setting('app.current_user_id', true), '')::INTEGER) = TRUE
        OR
        -- Usuario ve cierres de su tenant
        empresa_usuario_id = NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER
    );


-- ============================================================
-- 5. INSERTAR CATEGORÍAS PREDEFINIDAS DEL SISTEMA
-- ============================================================

-- Nota: Estas categorías se insertarán dinámicamente cuando un tenant se registre
-- o mediante un script de seed. Aquí dejamos el template.

-- Template de categorías de sistema para ingresos:
-- - Venta de Habitación (generada automáticamente por checkout)
-- - Suscripción SaaS (generada automáticamente por Stripe)
-- - Servicios adicionales
-- - Minibar
-- - Lavandería
-- - Otros ingresos

-- Template de categorías de sistema para egresos:
-- - Sueldos
-- - Proveedores
-- - Servicios (luz, gas, agua)
-- - Limpieza
-- - Mantenimiento
-- - Impuestos
-- - Otros egresos


-- ============================================================
-- 6. COMENTARIOS DE DOCUMENTACIÓN
-- ============================================================

COMMENT ON TABLE transaction_categories IS 'Categorías de ingresos y egresos configurables por tenant';
COMMENT ON TABLE transactions IS 'Registro inmutable de todas las transacciones de caja (ingresos y egresos)';
COMMENT ON TABLE cash_closings IS 'Cierres de caja por turno para reconciliación de efectivo';

COMMENT ON COLUMN transactions.anulada IS 'Marca si la transacción fue anulada. No se permite DELETE, solo anulación.';
COMMENT ON COLUMN transactions.transaction_anulacion_id IS 'Referencia a la transacción que anula esta (movimiento de ajuste)';
COMMENT ON COLUMN transactions.es_automatica IS 'TRUE si fue generada automáticamente por checkout o Stripe';
COMMENT ON COLUMN transaction_categories.es_sistema IS 'TRUE si es categoría del sistema (no editable por usuario)';

COMMENT ON COLUMN cash_closings.diferencia IS 'Diferencia entre efectivo declarado y saldo calculado por sistema';
