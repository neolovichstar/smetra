-- Partner ledger: isolated from invite bonuses and payment entitlement state.
CREATE TABLE IF NOT EXISTS partner_accounts (
 id TEXT PRIMARY KEY,
 code TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL,
 allowed_host TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 commission_bps INTEGER NOT NULL DEFAULT 2000 CHECK(commission_bps BETWEEN 0 AND 3000),
 term_days INTEGER NOT NULL DEFAULT 365 CHECK(term_days BETWEEN 30 AND 730),
 created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS partner_api_tokens (
 id TEXT PRIMARY KEY,
 partner_id TEXT NOT NULL REFERENCES partner_accounts(id) ON DELETE CASCADE,
 token_hash TEXT NOT NULL UNIQUE,
 created_at INTEGER NOT NULL,
 revoked_at INTEGER
);
CREATE TABLE IF NOT EXISTS partner_clicks (
 id TEXT PRIMARY KEY,
 partner_id TEXT NOT NULL REFERENCES partner_accounts(id) ON DELETE CASCADE,
 token_hash TEXT NOT NULL UNIQUE,
 created_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_partner_clicks_age ON partner_clicks(expires_at);
CREATE TABLE IF NOT EXISTS partner_attributions (
 user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 partner_id TEXT NOT NULL REFERENCES partner_accounts(id),
 click_id TEXT NOT NULL UNIQUE REFERENCES partner_clicks(id),
 rate_bps INTEGER NOT NULL CHECK(rate_bps BETWEEN 0 AND 3000),
 term_days INTEGER NOT NULL CHECK(term_days BETWEEN 30 AND 730),
 created_at INTEGER NOT NULL,
 first_paid_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_partner_attributions_partner ON partner_attributions(partner_id,created_at);
CREATE TABLE IF NOT EXISTS partner_commissions (
 id TEXT PRIMARY KEY,
 partner_id TEXT NOT NULL REFERENCES partner_accounts(id),
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 payment_id TEXT NOT NULL UNIQUE REFERENCES payments(id),
 gross_kopecks INTEGER NOT NULL CHECK(gross_kopecks>0),
 commission_kopecks INTEGER NOT NULL CHECK(commission_kopecks>0),
 rate_bps INTEGER NOT NULL CHECK(rate_bps BETWEEN 1 AND 3000),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','reversed')),
 created_at INTEGER NOT NULL,
 ready_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_partner_commissions_partner ON partner_commissions(partner_id,status,created_at DESC);
CREATE TABLE IF NOT EXISTS partner_products (
 id TEXT PRIMARY KEY,
 partner_id TEXT NOT NULL REFERENCES partner_accounts(id) ON DELETE CASCADE,
 sku TEXT NOT NULL,
 name TEXT NOT NULL,
 price_kopecks INTEGER NOT NULL CHECK(price_kopecks>=0),
 url TEXT NOT NULL,
 available INTEGER NOT NULL DEFAULT 1 CHECK(available IN (0,1)),
 updated_at INTEGER NOT NULL,
 UNIQUE(partner_id,sku)
);
CREATE INDEX IF NOT EXISTS idx_partner_products_available ON partner_products(available,price_kopecks);
CREATE TABLE IF NOT EXISTS partner_outbound_clicks (
 id TEXT PRIMARY KEY,
 partner_id TEXT NOT NULL REFERENCES partner_accounts(id),
 product_id TEXT NOT NULL REFERENCES partner_products(id),
 user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
 created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_partner_outbound_age ON partner_outbound_clicks(partner_id,created_at DESC);
