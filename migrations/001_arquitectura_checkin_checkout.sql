-- =====================================================
-- MIGRACIONES PARA ARQUITECTURA CHECK-IN/CHECK-OUT
-- Versión: 1.0 | Fecha: Dic 2025
-- =====================================================

-- PASO 1: Actualizar tabla 'reservas' con nuevos campos
-- (Asumir que existe con estructura base)

ALTER TABLE reservas ADD COLUMN IF NOT EXISTS
    estado VARCHAR(50) DEFAULT 'pendiente_checkin'
    CHECK (estado IN ('pendiente_checkin', 'ocupada', 'pendiente_checkout', 'cerrada'));

ALTER TABLE reservas ADD COLUMN IF NOT EXISTS 
    fecha_checkin_real TIMESTAMP NULL;

ALTER TABLE reservas ADD COLUMN IF NOT EXISTS 
    fecha_checkout_real TIMESTAMP NULL;

ALTER TABLE reservas ADD COLUMN IF NOT EXISTS 
    monto_pagado NUMERIC(12, 2) DEFAULT 0.00;

ALTER TABLE reservas ADD COLUMN IF NOT EXISTS 
    saldo_pendiente NUMERIC(12, 2) DEFAULT 0.00;

ALTER TABLE reservas ADD COLUMN IF NOT EXISTS 
    estado_habitacion VARCHAR(50) DEFAULT NULL 
    CHECK (estado_habitacion IS NULL OR estado_habitacion IN ('limpia', 'revisar', 'en_uso', 'sucia'));

ALTER TABLE reservas ADD COLUMN IF NOT EXISTS 
    usuario_actual VARCHAR(50) NULL;

ALTER TABLE reservas ADD COLUMN IF NOT EXISTS 
    notas_internas TEXT NULL;

ALTER TABLE reservas ADD COLUMN IF NOT EXISTS 
    actualizado_por VARCHAR(50) NULL;

-- PASO 2: Actualizar tabla 'clientes' con campos de auditoría

ALTER TABLE clientes ADD COLUMN IF NOT EXISTS 
    documento_hash VARCHAR(64) NULL;

ALTER TABLE clientes ADD COLUMN IF NOT EXISTS 
    es_duplicado_potencial BOOLEAN DEFAULT FALSE;

ALTER TABLE clientes ADD COLUMN IF NOT EXISTS 
    flags TEXT[] DEFAULT ARRAY[]::TEXT[];  -- ['vip', 'problema', 'preferente']

ALTER TABLE clientes ADD COLUMN IF NOT EXISTS 
    ultima_reserva DATE NULL;

ALTER TABLE clientes ADD COLUMN IF NOT EXISTS 
    total_noches INTEGER DEFAULT 0;

ALTER TABLE clientes ADD COLUMN IF NOT EXISTS 
    gasto_total NUMERIC(12, 2) DEFAULT 0.00;

-- PASO 3: CREAR tabla 'reservas_huespedes' (relación N:N)

CREATE TABLE IF NOT EXISTS reservas_huespedes (
    id SERIAL PRIMARY KEY,
    reserva_id INTEGER NOT NULL REFERENCES reservas(id) ON DELETE CASCADE,
    cliente_id INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
    rol VARCHAR(50) NOT NULL CHECK (rol IN ('principal', 'adulto', 'menor')),
    habitacion_id INTEGER NULL REFERENCES habitaciones(id) ON DELETE SET NULL,
    orden_registro INTEGER NOT NULL,  -- Para mantener orden de registro
    fecha_agregado TIMESTAMP DEFAULT NOW(),
    creado_por VARCHAR(50) NOT NULL,
    UNIQUE(reserva_id, cliente_id),
    UNIQUE(reserva_id, orden_registro)
);

CREATE INDEX IF NOT EXISTS idx_reservas_huespedes_reserva_id 
    ON reservas_huespedes(reserva_id);
CREATE INDEX IF NOT EXISTS idx_reservas_huespedes_cliente_id 
    ON reservas_huespedes(cliente_id);

-- PASO 4: CREAR tabla 'reserva_eventos' (auditoría inmutable)

CREATE TABLE IF NOT EXISTS reserva_eventos (
    id SERIAL PRIMARY KEY,
    reserva_id INTEGER NOT NULL REFERENCES reservas(id) ON DELETE CASCADE,
    tipo_evento VARCHAR(50) NOT NULL 
        CHECK (tipo_evento IN (
            'CHECKIN', 'ADD_GUEST', 'UPDATE_GUEST', 'DELETE_GUEST',
            'ROOM_MOVE', 'EXTEND_STAY', 'PAYMENT', 'CHECKOUT',
            'NOTE', 'STATE_CHANGE', 'CORRECTION', 'PAYMENT_REVERSAL'
        )),
    usuario VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),
    payload JSONB NULL,  -- Contenido detallado del evento
    cambios_anteriores JSONB NULL,  -- Para rollback
    ip_address VARCHAR(45) NULL,
    descripcion TEXT NULL,  -- Resumen legible para UI
    CONSTRAINT reserva_eventos_timestamp_unique 
        UNIQUE(reserva_id, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_reserva_eventos_reserva_id 
    ON reserva_eventos(reserva_id);
CREATE INDEX IF NOT EXISTS idx_reserva_eventos_timestamp 
    ON reserva_eventos(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_reserva_eventos_tipo 
    ON reserva_eventos(tipo_evento);

-- PASO 5: CREAR tabla 'reserva_pagos' (transacciones)

CREATE TABLE IF NOT EXISTS reserva_pagos (
    id SERIAL PRIMARY KEY,
    reserva_id INTEGER NOT NULL REFERENCES reservas(id) ON DELETE CASCADE,
    monto NUMERIC(12, 2) NOT NULL,
    metodo VARCHAR(50) NOT NULL 
        CHECK (metodo IN ('efectivo', 'tarjeta', 'transferencia', 'otro')),
    referencia VARCHAR(100) NULL,  -- Ticket, cheque, referencia bancaria
    timestamp TIMESTAMP DEFAULT NOW(),
    usuario VARCHAR(50) NOT NULL,
    notas TEXT NULL,
    es_reverso BOOLEAN DEFAULT FALSE,
    creado_en TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reserva_pagos_reserva_id 
    ON reserva_pagos(reserva_id);
CREATE INDEX IF NOT EXISTS idx_reserva_pagos_timestamp 
    ON reserva_pagos(timestamp DESC);

-- PASO 6: CREAR tabla 'reserva_room_moves' (historial de cambios)

CREATE TABLE IF NOT EXISTS reserva_room_moves (
    id SERIAL PRIMARY KEY,
    reserva_id INTEGER NOT NULL REFERENCES reservas(id) ON DELETE CASCADE,
    habitacion_anterior_id INTEGER REFERENCES habitaciones(id) ON DELETE SET NULL,
    habitacion_nueva_id INTEGER NOT NULL REFERENCES habitaciones(id) ON DELETE RESTRICT,
    razon VARCHAR(200) NOT NULL,  -- upgrade, queja, error, mantenimiento
    timestamp TIMESTAMP DEFAULT NOW(),
    usuario VARCHAR(50) NOT NULL,
    UNIQUE(reserva_id, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_reserva_room_moves_reserva_id 
    ON reserva_room_moves(reserva_id);

-- PASO 7: Vista auxiliar para resumir detalles de reserva

CREATE OR REPLACE VIEW v_reserva_detalle AS
SELECT 
    r.id,
    r.estado,
    r.fecha_checkin,
    r.fecha_checkout,
    r.fecha_checkin_real,
    r.fecha_checkout_real,
    r.cantidad_adultos,
    r.cantidad_menores,
    r.monto_total,
    r.monto_pagado,
    r.monto_total - r.monto_pagado AS saldo_pendiente,
    COUNT(DISTINCT rh.id) FILTER (WHERE rh.rol = 'principal') AS huespedes_principal,
    COUNT(DISTINCT rh.id) FILTER (WHERE rh.rol = 'adulto') AS huespedes_adultos,
    COUNT(DISTINCT rh.id) FILTER (WHERE rh.rol = 'menor') AS huespedes_menores,
    COUNT(DISTINCT rh.id) AS huespedes_total,
    STRING_AGG(DISTINCT h.numero::TEXT, ', ' ORDER BY h.numero::TEXT) AS habitaciones,
    MAX(re.timestamp) AS ultimo_evento,
    COUNT(DISTINCT re.id) AS total_eventos
FROM reservas r
LEFT JOIN reservas_huespedes rh ON r.id = rh.reserva_id
LEFT JOIN habitaciones h ON rh.habitacion_id = h.id
LEFT JOIN reserva_eventos re ON r.id = re.reserva_id
WHERE r.deleted = FALSE
GROUP BY r.id;

-- PASO 8: Función para calcular y actualizar saldo_pendiente

CREATE OR REPLACE FUNCTION actualizar_saldo_reserva()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE reservas
    SET 
        monto_pagado = COALESCE((
            SELECT SUM(monto) FROM reserva_pagos 
            WHERE reserva_id = NEW.reserva_id AND es_reverso = FALSE
        ), 0),
        saldo_pendiente = monto_total - COALESCE((
            SELECT SUM(monto) FROM reserva_pagos 
            WHERE reserva_id = NEW.reserva_id AND es_reverso = FALSE
        ), 0)
    WHERE id = NEW.reserva_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- PASO 9: Trigger para auto-actualizar saldo al insertar/actualizar pagos

CREATE TRIGGER trigger_actualizar_saldo_pagos
AFTER INSERT OR UPDATE ON reserva_pagos
FOR EACH ROW
EXECUTE FUNCTION actualizar_saldo_reserva();

-- PASO 10: Índices adicionales para performance

CREATE INDEX IF NOT EXISTS idx_reservas_estado 
    ON reservas(estado) WHERE deleted = FALSE;

CREATE INDEX IF NOT EXISTS idx_reservas_cliente_id 
    ON reservas(cliente_id) WHERE deleted = FALSE;

CREATE INDEX IF NOT EXISTS idx_clientes_numero_documento 
    ON clientes(tipo_documento, numero_documento) WHERE deleted = FALSE;

-- PASO 11: Comentarios en tablas para documentación

COMMENT ON TABLE reservas_huespedes IS 'Relación N:N entre reservas y clientes, permite múltiples huéspedes por reserva con roles específicos';
COMMENT ON TABLE reserva_eventos IS 'Auditoría inmutable de todos los eventos en una reserva. Base para rollback y compliance.';
COMMENT ON TABLE reserva_pagos IS 'Transacciones de dinero por reserva. Permite pagos parciales y reversas.';
COMMENT ON TABLE reserva_room_moves IS 'Historial de cambios de habitación con razon y usuario.';

-- =====================================================
-- FIN DE MIGRACIONES
-- =====================================================
