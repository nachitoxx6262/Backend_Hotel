-- Migración 006: Agregar empresa_usuario_id a tablas operacionales
-- Este es un paso crítico: añade FK a todas las tablas que necesitan aislamiento por tenant

-- ============================================================
-- 1. USUARIOS: Agregar FK a empresa_usuario + es_super_admin
-- ============================================================

ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS empresa_usuario_id INTEGER;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS es_super_admin BOOLEAN NOT NULL DEFAULT FALSE;

-- FK con ON DELETE SET NULL (los usuarios pueden sobrevivir si se borra el tenant)
ALTER TABLE usuarios 
    ADD CONSTRAINT fk_usuario_empresa_usuario 
    FOREIGN KEY (empresa_usuario_id)
    REFERENCES empresa_usuarios(id)
    ON DELETE SET NULL;

CREATE INDEX idx_usuario_empresa_usuario ON usuarios(empresa_usuario_id);

-- ============================================================
-- 2. ROOM_TYPES: Agregar FK empresa_usuario_id + actualizar UNIQUE
-- ============================================================

ALTER TABLE room_types ADD COLUMN IF NOT EXISTS empresa_usuario_id INTEGER;

ALTER TABLE room_types 
    ADD CONSTRAINT fk_room_type_empresa_usuario 
    FOREIGN KEY (empresa_usuario_id)
    REFERENCES empresa_usuarios(id)
    ON DELETE CASCADE;

-- Cambiar UNIQUE de solo nombre a (empresa_usuario_id, nombre)
ALTER TABLE room_types DROP CONSTRAINT IF EXISTS uq_roomtype_nombre;
DROP INDEX IF EXISTS uq_roomtype_nombre;
CREATE UNIQUE INDEX uq_roomtype_empresa_nombre ON room_types(empresa_usuario_id, nombre);
CREATE INDEX idx_roomtype_empresa ON room_types(empresa_usuario_id);

-- ============================================================
-- 3. ROOMS: Agregar FK empresa_usuario_id + actualizar UNIQUE
-- ============================================================

ALTER TABLE rooms ADD COLUMN IF NOT EXISTS empresa_usuario_id INTEGER;

ALTER TABLE rooms 
    ADD CONSTRAINT fk_room_empresa_usuario 
    FOREIGN KEY (empresa_usuario_id)
    REFERENCES empresa_usuarios(id)
    ON DELETE CASCADE;

-- Cambiar UNIQUE de solo numero a (empresa_usuario_id, numero)
ALTER TABLE rooms DROP CONSTRAINT IF EXISTS uq_room_numero;
DROP INDEX IF EXISTS uq_room_numero;
CREATE UNIQUE INDEX uq_room_empresa_numero ON rooms(empresa_usuario_id, numero);
CREATE INDEX idx_room_empresa ON rooms(empresa_usuario_id);

-- ============================================================
-- 4. DAILY_RATES: Agregar FK empresa_usuario_id
-- ============================================================

ALTER TABLE daily_rates ADD COLUMN IF NOT EXISTS empresa_usuario_id INTEGER;

ALTER TABLE daily_rates 
    ADD CONSTRAINT fk_daily_rate_empresa_usuario 
    FOREIGN KEY (empresa_usuario_id)
    REFERENCES empresa_usuarios(id)
    ON DELETE CASCADE;

ALTER TABLE daily_rates DROP CONSTRAINT IF EXISTS uq_rate_day;
DROP INDEX IF EXISTS uq_rate_day;
CREATE UNIQUE INDEX uq_rate_day_empresa ON daily_rates(empresa_usuario_id, room_type_id, fecha, rate_plan_id);
CREATE INDEX idx_rate_empresa ON daily_rates(empresa_usuario_id);

-- ============================================================
-- 5. RESERVATIONS: Agregar FK empresa_usuario_id
-- ============================================================

ALTER TABLE reservations ADD COLUMN IF NOT EXISTS empresa_usuario_id INTEGER;

ALTER TABLE reservations 
    ADD CONSTRAINT fk_reservation_empresa_usuario 
    FOREIGN KEY (empresa_usuario_id)
    REFERENCES empresa_usuarios(id)
    ON DELETE CASCADE;

CREATE INDEX idx_res_empresa ON reservations(empresa_usuario_id);

-- ============================================================
-- 6. STAYS: Agregar FK empresa_usuario_id
-- ============================================================

ALTER TABLE stays ADD COLUMN IF NOT EXISTS empresa_usuario_id INTEGER;

ALTER TABLE stays 
    ADD CONSTRAINT fk_stay_empresa_usuario 
    FOREIGN KEY (empresa_usuario_id)
    REFERENCES empresa_usuarios(id)
    ON DELETE CASCADE;

CREATE INDEX idx_stay_empresa ON stays(empresa_usuario_id);

-- ============================================================
-- 7. HOUSEKEEPING_TASKS: Agregar FK empresa_usuario_id
-- ============================================================

ALTER TABLE housekeeping_tasks ADD COLUMN IF NOT EXISTS empresa_usuario_id INTEGER;

ALTER TABLE housekeeping_tasks 
    ADD CONSTRAINT fk_hk_task_empresa_usuario 
    FOREIGN KEY (empresa_usuario_id)
    REFERENCES empresa_usuarios(id)
    ON DELETE CASCADE;

CREATE INDEX idx_hk_task_empresa ON housekeeping_tasks(empresa_usuario_id);

-- ============================================================
-- 8. ROLES: Agregar FK empresa_usuario_id (opcional, nullable)
-- ============================================================

ALTER TABLE roles ADD COLUMN IF NOT EXISTS empresa_usuario_id INTEGER;

ALTER TABLE roles 
    ADD CONSTRAINT fk_role_empresa_usuario 
    FOREIGN KEY (empresa_usuario_id)
    REFERENCES empresa_usuarios(id)
    ON DELETE CASCADE;

-- Cambiar UNIQUE de solo nombre a (empresa_usuario_id, nombre) para permitir roles globales
ALTER TABLE roles DROP CONSTRAINT IF EXISTS roles_nombre_key;
DROP INDEX IF EXISTS roles_nombre_key;
CREATE UNIQUE INDEX uq_rol_empresa_nombre ON roles(nombre, empresa_usuario_id);
CREATE INDEX idx_rol_empresa ON roles(empresa_usuario_id);

-- ============================================================
-- 9. HOTEL_SETTINGS: Cambiar FK de empresa_id a empresa_usuario_id
-- ============================================================

-- Crear columna nueva
ALTER TABLE hotel_settings ADD COLUMN IF NOT EXISTS empresa_usuario_id INTEGER;

-- Migrar datos si existen (FK de empresa_id a empresa_usuario_id)
-- Nota: Esto requiere que ya exista una tabla empresa_usuarios mapeada con empresas
-- Por ahora dejamos NULL y será rellenado en script de migración de datos
-- UPDATE hotel_settings SET empresa_usuario_id = <mapeo de empresa_id> WHERE empresa_usuario_id IS NULL;

-- Agregar FK nuevo
ALTER TABLE hotel_settings 
    ADD CONSTRAINT fk_hotel_settings_empresa_usuario 
    FOREIGN KEY (empresa_usuario_id)
    REFERENCES empresa_usuarios(id)
    ON DELETE CASCADE;

-- Cambiar UNIQUE constraint
ALTER TABLE hotel_settings DROP CONSTRAINT IF EXISTS uq_hotel_settings_empresa;
DROP INDEX IF EXISTS uq_hotel_settings_empresa;
CREATE UNIQUE INDEX uq_hotel_settings_empresa_usuario ON hotel_settings(empresa_usuario_id);
CREATE INDEX idx_hotel_settings_empresa ON hotel_settings(empresa_usuario_id);

-- Opcionalmente, mantener FK antigua para compatibilidad temporal
-- ALTER TABLE hotel_settings ADD CONSTRAINT fk_hotel_settings_empresa_legacy 
--     FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE SET NULL;

COMMIT;
