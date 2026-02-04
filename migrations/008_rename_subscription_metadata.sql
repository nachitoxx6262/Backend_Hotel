-- Rename reserved column to avoid SQLAlchemy Declarative reserved name conflict
-- Safe to run multiple times thanks to IF EXISTS
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'subscriptions' AND column_name = 'metadata'
  ) THEN
    ALTER TABLE subscriptions RENAME COLUMN metadata TO metadata_json;
  END IF;
END $$;
