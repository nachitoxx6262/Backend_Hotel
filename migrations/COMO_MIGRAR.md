# Cómo ejecutar migraciones

## Opción 1 — Script Python (recomendado)

```bash
cd Backend_Hotel
# Asegurate de tener el .env configurado con DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
python scripts/run_migration.py migrations/018_fase3_nuevas_columnas.sql
```

## Opción 2 — psql directo

```bash
cd Backend_Hotel
psql postgresql://hotel_user:hotel_pass@localhost:5432/hotel_db \
  -f migrations/018_fase3_nuevas_columnas.sql
```

## Opción 3 — Via Docker Compose

```bash
cd Hotel
docker-compose exec db psql -U hotel_user -d hotel_db \
  -f /dev/stdin < Backend_Hotel/migrations/018_fase3_nuevas_columnas.sql
```

## Migración 018 — Qué hace

- `empresa_usuarios.invoice_counter` — Contador de facturas por hotel
- `hotel_settings` — Campos fiscales (nombre_fiscal, iva_porcentaje, moneda_simbolo, logo_url, direccion_fiscal)
- `hotel_settings` — Config SMTP por tenant (smtp_host, smtp_port, smtp_user, smtp_password_encrypted, smtp_from_email)
- `usuarios` — Reset de contraseña por email (reset_token, reset_token_expires)
