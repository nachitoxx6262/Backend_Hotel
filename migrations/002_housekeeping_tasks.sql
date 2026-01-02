-- Crear tabla de tareas de housekeeping (daily / checkout)
CREATE TABLE IF NOT EXISTS housekeeping_tasks (
    id SERIAL PRIMARY KEY,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE RESTRICT,
    stay_id INTEGER REFERENCES stays(id) ON DELETE SET NULL,
    reservation_id INTEGER REFERENCES reservations(id) ON DELETE SET NULL,
    assigned_to_user_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    task_date DATE NOT NULL,
    task_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    done_at TIMESTAMP WITHOUT TIME ZONE,
    notes TEXT,
    meta JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    CONSTRAINT ck_hk_task_type CHECK (task_type IN ('daily','checkout','maintenance')),
    CONSTRAINT ck_hk_task_status CHECK (status IN ('pending','in_progress','done','skipped'))
);

-- Una limpieza diaria por habitación por día
CREATE UNIQUE INDEX IF NOT EXISTS uq_hk_task_daily
    ON housekeeping_tasks(room_id, task_date, task_type);

-- Una limpieza de checkout por estadía
CREATE UNIQUE INDEX IF NOT EXISTS uq_hk_task_checkout_stay
    ON housekeeping_tasks(stay_id)
    WHERE task_type = 'checkout';

-- Índices de apoyo
CREATE INDEX IF NOT EXISTS idx_hk_task_room_date
    ON housekeeping_tasks(room_id, task_date);

CREATE INDEX IF NOT EXISTS idx_hk_task_status_date
    ON housekeeping_tasks(status, task_date);
