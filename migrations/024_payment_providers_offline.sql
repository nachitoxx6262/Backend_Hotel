-- Migración 024: Proveedores de pago offline (efectivo / transferencia) — Fase C suscripciones
-- Ejecutar: python scripts/run_migration.py migrations/024_payment_providers_offline.sql
--
-- Agrega los valores para soportar pagos offline (el dueño los confirma / carga a mano;
-- el tenant puede autoinformarlos).
--
-- IMPORTANTE: la columna payment_attempts.proveedor usa Enum(PaymentProvider) SIN
-- values_callable, por lo que SQLAlchemy persiste los NOMBRES del enum (MAYÚSCULAS:
-- DUMMY, MERCADO_PAGO, STRIPE). Por eso acá agregamos 'EFECTIVO' y 'TRANSFERENCIA'
-- en mayúsculas. El tipo en la base es 'paymentprovider' (lo creó SQLAlchemy create_all,
-- no la migración 005). ADD VALUE IF NOT EXISTS es idempotente; en PostgreSQL 12+ corre
-- dentro de una transacción siempre que el nuevo valor no se USE en la misma transacción.

ALTER TYPE paymentprovider ADD VALUE IF NOT EXISTS 'EFECTIVO';
ALTER TYPE paymentprovider ADD VALUE IF NOT EXISTS 'TRANSFERENCIA';
