-- Migración 024: Proveedores de pago offline (efectivo / transferencia) — Fase C suscripciones
-- Ejecutar: python scripts/run_migration.py migrations/024_payment_providers_offline.sql
--
-- Agrega los valores 'efectivo' y 'transferencia' al enum payment_provider_enum para soportar
-- pagos offline (el dueño los confirma / carga a mano; el tenant puede autoinformarlos).
-- ADD VALUE IF NOT EXISTS es idempotente. En PostgreSQL 12+ se puede correr dentro de una
-- transacción siempre que el nuevo valor no se USE en la misma transacción (acá sólo se agrega).

ALTER TYPE payment_provider_enum ADD VALUE IF NOT EXISTS 'efectivo';
ALTER TYPE payment_provider_enum ADD VALUE IF NOT EXISTS 'transferencia';
