-- Partner console access through Smetra accounts: members, invitations and one-time sign-in codes.
CREATE TABLE IF NOT EXISTS partner_members (
 partner_id TEXT NOT NULL REFERENCES partner_accounts(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 role TEXT NOT NULL CHECK(role IN ('owner','admin','analyst','catalog')),
 invited_by TEXT REFERENCES users(id) ON DELETE SET NULL,
 created_at INTEGER NOT NULL,
 PRIMARY KEY(partner_id,user_id)
);
CREATE INDEX IF NOT EXISTS idx_partner_members_user ON partner_members(user_id);
CREATE TABLE IF NOT EXISTS partner_invites (
 id TEXT PRIMARY KEY,
 partner_id TEXT NOT NULL REFERENCES partner_accounts(id) ON DELETE CASCADE,
 email TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('owner','admin','analyst','catalog')),
 created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
 created_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,
 accepted_at INTEGER,
 accepted_by TEXT REFERENCES users(id) ON DELETE SET NULL,
 revoked_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_partner_invites_email ON partner_invites(email,accepted_at,revoked_at);
CREATE INDEX IF NOT EXISTS idx_partner_invites_partner ON partner_invites(partner_id,created_at);
CREATE TABLE IF NOT EXISTS partner_sso_codes (
 code_hash TEXT PRIMARY KEY,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 created_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,
 used_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_partner_sso_codes_expires ON partner_sso_codes(expires_at);
