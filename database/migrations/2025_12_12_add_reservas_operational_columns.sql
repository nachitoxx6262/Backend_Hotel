-- Adds operational columns introduced in Fase 2/3
-- Safe to run multiple times using IF NOT EXISTS guards

BEGIN;

-- estado_operacional: workflow status for reservation
ALTER TABLE reservas
    ADD COLUMN IF NOT EXISTS estado_operacional VARCHAR(32) DEFAULT 'PENDIENTE' NOT NULL;

-- estado_habitacion: current room state used in checkout
ALTER TABLE reservas
    ADD COLUMN IF NOT EXISTS estado_habitacion VARCHAR(32) DEFAULT 'EN_USO' NOT NULL;

-- tracking current user operating on reservation
ALTER TABLE reservas
    ADD COLUMN IF NOT EXISTS usuario_actual VARCHAR(64);

-- financial summaries introduced in frontend
ALTER TABLE reservas
    ADD COLUMN IF NOT EXISTS monto_pagado NUMERIC(12,2) DEFAULT 0 NOT NULL,
    ADD COLUMN IF NOT EXISTS saldo_pendiente NUMERIC(12,2) DEFAULT 0 NOT NULL;

-- notas internas for operational comments
ALTER TABLE reservas
    ADD COLUMN IF NOT EXISTS notas_internas TEXT;

-- auditing base columns (if not present)
ALTER TABLE reservas
    ADD COLUMN IF NOT EXISTS creado_en TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    ADD COLUMN IF NOT EXISTS actualizado_en TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    ADD COLUMN IF NOT EXISTS creado_por VARCHAR(64),
    ADD COLUMN IF NOT EXISTS actualizado_por VARCHAR(64);

-- keep an index for common filters
CREATE INDEX IF NOT EXISTS ix_reservas_estado_operacional ON reservas (estado_operacional);
CREATE INDEX IF NOT EXISTS ix_reservas_estado_habitacion ON reservas (estado_habitacion);

COMMIT;
