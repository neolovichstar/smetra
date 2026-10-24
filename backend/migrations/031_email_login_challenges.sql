CREATE TABLE IF NOT EXISTS email_login_challenges (
 id TEXT PRIMARY KEY,
 email TEXT NOT NULL,
 code_hash TEXT NOT NULL,
 intent TEXT NOT NULL CHECK (intent IN ('register','login')),
 name TEXT NOT NULL DEFAULT '',
 legal_version TEXT NOT NULL DEFAULT '',
 attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 5),
 expires_at INTEGER NOT NULL,
 created_at INTEGER NOT NULL,
 consumed_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_email_login_email ON email_login_challenges(email,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_login_expiration ON email_login_challenges(expires_at);
