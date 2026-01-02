-- 003_daily_clean_logs.sql
-- Crear tabla para registrar limpiezas diarias sin persistir tareas

CREATE TABLE daily_clean_logs (
    id SERIAL PRIMARY KEY,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE RESTRICT,
    date DATE NOT NULL,
    user_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    completed_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL,
    notes TEXT,
    CONSTRAINT uq_daily_clean_room_date UNIQUE(room_id, date)
);

CREATE INDEX idx_daily_clean_room ON daily_clean_logs(room_id);
CREATE INDEX idx_daily_clean_date ON daily_clean_logs(date);
