-- Migración 023: Backfill del fin de período en subscriptions (Fase A suscripciones)
-- Ejecutar: python scripts/run_migration.py migrations/023_backfill_subscription_periodo.sql
--
-- Contexto: a partir de la Fase A, `subscriptions.fecha_proxima_renovacion` es la ÚNICA
-- fuente de verdad del "fin del período vigente" (trial o pago). El resolver de acceso
-- (utils/subscription_service.resolve_access) lo usa para derivar el vencimiento.
--
-- Datos legados: algunos tenants demo podían tener el fin de trial sólo en
-- empresa_usuarios.fecha_fin_demo y NULL en subscriptions.fecha_proxima_renovacion.
-- Este backfill copia esa fecha a la suscripción para que el período quede bien definido.
-- No hay cambios de esquema (sólo UPDATE), es idempotente.

-- ============================================================
-- 1. Tenants DEMO sin fin de período en la suscripción: copiar fecha_fin_demo
-- ============================================================
UPDATE subscriptions s
SET fecha_proxima_renovacion = e.fecha_fin_demo
FROM empresa_usuarios e
WHERE s.empresa_usuario_id = e.id
  AND s.fecha_proxima_renovacion IS NULL
  AND e.fecha_fin_demo IS NOT NULL
  AND e.plan_tipo = 'demo';

-- ============================================================
-- 2. Coherencia del espejo: si una suscripción quedó en un plan pago pero la empresa
--    seguía marcada como 'demo' (desync histórico previo a apply_plan_change), alinear
--    el espejo plan_tipo al plan real de la suscripción y limpiar fecha_fin_demo.
-- ============================================================
UPDATE empresa_usuarios e
SET plan_tipo = p.nombre,
    fecha_fin_demo = NULL
FROM subscriptions s
JOIN planes p ON p.id = s.plan_id
WHERE s.empresa_usuario_id = e.id
  AND p.nombre <> 'demo'
  AND e.plan_tipo = 'demo'
  AND s.estado = 'activo';
