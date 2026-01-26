-- Migración 004: Crear tabla HotelSettings
-- Esta tabla almacena las configuraciones personalizadas de cada hotel

CREATE TABLE IF NOT EXISTS hotel_settings (
    id SERIAL PRIMARY KEY,
    empresa_id INTEGER NOT NULL UNIQUE,
    checkout_hour INTEGER NOT NULL DEFAULT 12,
    checkout_minute INTEGER NOT NULL DEFAULT 0,
    cleaning_start_hour INTEGER NOT NULL DEFAULT 10,
    cleaning_end_hour INTEGER NOT NULL DEFAULT 12,
    auto_extend_stays BOOLEAN NOT NULL DEFAULT TRUE,
    overstay_price NUMERIC(10, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_hotel_settings_empresa 
        FOREIGN KEY (empresa_id) 
        REFERENCES empresas(id) 
        ON DELETE CASCADE,
    
    CONSTRAINT check_checkout_hour 
        CHECK (checkout_hour >= 0 AND checkout_hour <= 23),
    
    CONSTRAINT check_checkout_minute 
        CHECK (checkout_minute >= 0 AND checkout_minute <= 59),
    
    CONSTRAINT check_cleaning_start_hour 
        CHECK (cleaning_start_hour >= 0 AND cleaning_start_hour <= 23),
    
    CONSTRAINT check_cleaning_end_hour 
        CHECK (cleaning_end_hour >= 0 AND cleaning_end_hour <= 23),
    
    CONSTRAINT check_overstay_price 
        CHECK (overstay_price IS NULL OR overstay_price >= 0)
);

-- Crear índice para búsquedas rápidas por empresa
CREATE INDEX IF NOT EXISTS idx_hotel_settings_empresa_id ON hotel_settings(empresa_id);

-- Crear trigger para actualizar updated_at automáticamente
-- (Si la base de datos lo soporta)
CREATE OR REPLACE FUNCTION update_hotel_settings_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_hotel_settings_updated_at ON hotel_settings;

CREATE TRIGGER trigger_hotel_settings_updated_at
BEFORE UPDATE ON hotel_settings
FOR EACH ROW
EXECUTE FUNCTION update_hotel_settings_timestamp();
