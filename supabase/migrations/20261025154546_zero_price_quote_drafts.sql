-- A draft must accept unknown prices (0 kopecks) so the AI can propose
-- work items without fabricating rates. Published quotes must stay positive.
-- Publishing also validates each item and recomputes totals in backend.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
ALTER TABLE smetra.quotes DROP CONSTRAINT quotes_amount_kopecks_check;
ALTER TABLE smetra.quotes ADD CONSTRAINT quotes_amount_kopecks_check
  CHECK (amount_kopecks >= 0 AND (status='draft' OR amount_kopecks > 0));
INSERT INTO smetra.schema_migrations(version,applied_at)
VALUES (59,extract(epoch FROM now())::bigint)
ON CONFLICT (version) DO NOTHING;
COMMIT;
