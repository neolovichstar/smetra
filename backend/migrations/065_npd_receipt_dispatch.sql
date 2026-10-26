-- Production Supabase private schema. Applied via the authenticated Supabase migration API.
-- No public Data API grants; only the trusted backend may update receipt state.
CREATE TABLE IF NOT EXISTS smetra.npd_receipt_deliveries (
  payment_id text PRIMARY KEY REFERENCES smetra.payments(id),
  receipt_url text,
  status text NOT NULL DEFAULT 'awaiting_tax',
  attempts integer NOT NULL DEFAULT 0,
  next_attempt_at bigint,
  sent_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  last_error text,
  CONSTRAINT npd_receipt_status_check CHECK (status IN ('awaiting_tax','queued','sending','sent','needs_review','refunded')),
  CONSTRAINT npd_receipt_url_required CHECK (status='awaiting_tax' OR status='refunded' OR receipt_url IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS npd_receipts_pending_idx ON smetra.npd_receipt_deliveries(next_attempt_at,payment_id)
 WHERE status IN ('queued','sending');
ALTER TABLE smetra.npd_receipt_deliveries ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON smetra.npd_receipt_deliveries FROM PUBLIC, anon, authenticated;
