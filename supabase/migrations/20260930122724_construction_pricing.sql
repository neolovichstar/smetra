BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

ALTER TABLE smetra.construction_quantities
 ADD COLUMN IF NOT EXISTS price_coefficient TEXT NOT NULL DEFAULT '1',
 ADD COLUMN IF NOT EXISTS markup_percent TEXT NOT NULL DEFAULT '0',
 ADD COLUMN IF NOT EXISTS discount_percent TEXT NOT NULL DEFAULT '0',
 ADD COLUMN IF NOT EXISTS coefficient_reason TEXT NOT NULL DEFAULT '';

INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(10,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
