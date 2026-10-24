-- Local mirror of existing production subscription fields.
-- Applied by business.migrate after adding the columns it needs.
CREATE INDEX IF NOT EXISTS idx_billing_intents_workspace_payment
 ON billing_intents(workspace_id,payment_id);
