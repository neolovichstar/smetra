CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 name TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
 blocked INTEGER NOT NULL DEFAULT 0 CHECK(blocked IN (0,1)),
 plan TEXT NOT NULL DEFAULT 'free', entitlement_until INTEGER NOT NULL DEFAULT 0,
 created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 token_hash TEXT NOT NULL UNIQUE, expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS quotes (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 title TEXT NOT NULL, client TEXT NOT NULL, description TEXT NOT NULL,
 amount_kopecks INTEGER NOT NULL CHECK(amount_kopecks > 0),
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','sent','accepted','declined','completed')),
 public_token TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quotes_user_created ON quotes(user_id,created_at DESC);
CREATE TABLE IF NOT EXISTS payments (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 provider_id TEXT NOT NULL UNIQUE, plan TEXT NOT NULL,
 amount_kopecks INTEGER NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending','succeeded','canceled')),
 idempotency_key TEXT NOT NULL, confirmation_url TEXT NOT NULL, created_at INTEGER NOT NULL,
 UNIQUE(user_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id,created_at DESC);
CREATE TABLE IF NOT EXISTS events (
 id TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
 name TEXT NOT NULL,created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_name ON events(name,created_at);
CREATE TABLE IF NOT EXISTS support (
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 message TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('open','closed')),created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
 id TEXT PRIMARY KEY,actor_id TEXT,action TEXT NOT NULL,target TEXT NOT NULL,
 detail TEXT NOT NULL DEFAULT '',created_at INTEGER NOT NULL
);
