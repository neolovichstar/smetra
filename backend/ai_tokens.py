"""AI usage is metered in model tokens instead of requests.

Every account gets a monthly token allowance from its plan tier; extra tokens
(admin top-ups, rewarded video, legacy purchase bonuses) live in a wallet that
does not reset. Spending takes the monthly allowance first, then the wallet.
Each change is written to a ledger, so balances can be audited and explained.

Usage comes from the provider's reported token counts. When a provider does not
report usage, the request and answer size are used as a conservative estimate.
The client never sends a token count.
"""
import contextvars
import datetime as dt
import hashlib
import json

from backend.business import DomainError, identity, stamp

# Monthly allowance per plan tier (see backend/entitlements.py tiers).
MONTHLY_TOKENS = {"starter": 60_000, "pro_solo": 2_000_000, "pro_plus": 4_000_000, "team": 8_000_000}
# One legacy "request" (referral, purchase bonus, ad credit) is worth this many tokens.
REQUEST_TOKENS = 15_000
AD_REWARD_TOKENS = 3 * REQUEST_TOKENS
# A new request needs at least this much left so an answer is not cut off.
MIN_START_TOKENS = 1_500
ADMIN_ADJUST_LIMIT = 100_000_000

_metered = contextvars.ContextVar("smetra_ai_tokens", default=None)


def ensure_schema(con):
    if getattr(con, "is_postgres", False):
        return
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_token_wallets (
          user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          balance INTEGER NOT NULL DEFAULT 0,
          updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ai_token_ledger (
          id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          bucket TEXT NOT NULL,
          delta INTEGER NOT NULL,
          reason TEXT NOT NULL,
          note TEXT NOT NULL DEFAULT '',
          ref TEXT,
          actor_id TEXT,
          created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ai_token_ledger_user ON ai_token_ledger(user_id, created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_token_ledger_ref ON ai_token_ledger(user_id, ref) WHERE ref IS NOT NULL;
        """
    )


# ---------- metering ----------

def start_meter():
    """Begin counting provider usage for the current request."""
    _metered.set({"tokens": 0, "calls": 0})


def note_usage(usage, payload=None, output=""):
    """Add one model call to the current meter (provider usage or an estimate)."""
    meter = _metered.get()
    if meter is None:
        return
    tokens = 0
    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if isinstance(total, int) and total >= 0:
            tokens = total
        else:
            prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
            if isinstance(prompt, int) and isinstance(completion, int):
                tokens = max(0, prompt) + max(0, completion)
    if not tokens:
        tokens = estimate(payload, output)
    meter["tokens"] += min(tokens, 1_000_000)
    meter["calls"] += 1


def estimate(payload, output=""):
    """About 3.5 characters per token for mixed Russian text and JSON."""
    try:
        size = len(json.dumps(payload, ensure_ascii=False)) if payload is not None else 0
    except (TypeError, ValueError):
        size = 0
    return int((size + len(output or "")) / 3.5) + 1


def metered():
    meter = _metered.get()
    return meter["tokens"] if meter else 0


# ---------- balances ----------

def period():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")


def month_key(user_id, month=None):
    return hashlib.sha256(f"assistant:tokens:{month or period()}:{user_id}".encode()).hexdigest()


def tier_of(service):
    from backend.entitlements import workspace_plan_row, evaluate_workspace_plan
    if getattr(service, "wid", None):
        return evaluate_workspace_plan(workspace_plan_row(service.con, service.wid, stamp()), "clean_export", stamp())["tier"]
    user = service.user
    paid = user["plan"] == "pro" and (user["entitlement_until"] or 0) > stamp()
    return "pro_solo" if paid else "starter"


def wallet_balance(con, user_id):
    row = con.execute("SELECT balance FROM ai_token_wallets WHERE user_id=?", (user_id,)).fetchone()
    return int(row["balance"]) if row else 0


def _wallet_add(con, user_id, delta, reason, note="", ref=None, actor_id=None):
    """Change the wallet and record why; idempotent when ref is given."""
    if ref and con.execute("SELECT 1 FROM ai_token_ledger WHERE user_id=? AND ref=?", (user_id, ref)).fetchone():
        return False
    now = stamp()
    con.execute(
        "INSERT INTO ai_token_wallets(user_id,balance,updated_at) VALUES(?,0,?) ON CONFLICT(user_id) DO NOTHING",
        (user_id, now),
    )
    if delta < 0:
        # Never below zero: record what was actually taken.
        current = wallet_balance(con, user_id)
        delta = -min(-delta, current)
    con.execute("UPDATE ai_token_wallets SET balance=balance+?,updated_at=? WHERE user_id=?", (delta, now, user_id))
    con.execute(
        "INSERT INTO ai_token_ledger(id,user_id,bucket,delta,reason,note,ref,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (identity(), user_id, "wallet", delta, reason, note[:200], ref, actor_id, now),
    )
    return True


def credit(con, user_id, tokens, reason, note="", ref=None, actor_id=None):
    if tokens <= 0:
        raise ValueError("credit must be positive")
    return _wallet_add(con, user_id, int(tokens), reason, note, ref, actor_id)


def adjust(con, user_id, delta, actor_id, note):
    """Administrator change of the wallet balance, positive or negative."""
    if not isinstance(delta, int) or isinstance(delta, bool) or delta == 0 or abs(delta) > ADMIN_ADJUST_LIMIT:
        raise DomainError(400, "Укажите изменение баланса от 1 до 100 000 000 токенов")
    _wallet_add(con, user_id, delta, "admin_adjust", note, None, actor_id)
    return wallet_balance(con, user_id)


def absorb_legacy_credits(con, user_id):
    """Unused request-based bonuses become wallet tokens once."""
    now = stamp()
    for table, reason in (("assistant_bonus_grants", "legacy_purchase_bonus"), ("assistant_ad_reward_credits", "legacy_ad_reward")):
        rows = con.execute(
            f"SELECT id,remaining FROM {table} WHERE user_id=? AND remaining>0 AND expires_at>?", (user_id, now)
        ).fetchall()
        for row in rows:
            taken = con.execute(
                f"UPDATE {table} SET remaining=0 WHERE id=? AND remaining=? RETURNING id", (row["id"], row["remaining"])
            ).fetchone()
            if taken:
                _wallet_add(con, user_id, int(row["remaining"]) * REQUEST_TOKENS, reason, "", f"{table}:{row['id']}")


def revoke_purchase_bonus(con, user_id, payment_id):
    """A refunded purchase takes back the tokens its gift bonus became."""
    for grant in con.execute("SELECT id FROM assistant_bonus_grants WHERE payment_id=?", (payment_id,)).fetchall():
        moved = con.execute(
            "SELECT delta FROM ai_token_ledger WHERE user_id=? AND ref=?", (user_id, "assistant_bonus_grants:" + grant["id"])
        ).fetchone()
        if moved and int(moved["delta"]) > 0:
            _wallet_add(con, user_id, -int(moved["delta"]), "refund_revoke", "", "refund:" + grant["id"])


def balance(service):
    """Monthly allowance, usage this month and the wallet, in tokens."""
    con, user_id = service.con, service.user["id"]
    absorb_legacy_credits(con, user_id)
    tier = tier_of(service)
    month = period()
    from backend.revenue import referral_bonus
    allowance = MONTHLY_TOKENS.get(tier, MONTHLY_TOKENS["starter"]) + referral_bonus(con, user_id, month) * REQUEST_TOKENS
    row = con.execute("SELECT count FROM rate_limits WHERE key=?", (month_key(user_id, month),)).fetchone()
    used = int(row["count"]) if row else 0
    wallet = wallet_balance(con, user_id)
    now = dt.datetime.now(dt.timezone.utc)
    next_month = (now.replace(day=28) + dt.timedelta(days=4)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_left = max(0, allowance - used)
    return {
        "unit": "tokens",
        "plan": "free" if tier == "starter" else "pro",
        "tier": tier,
        "period": month,
        "monthly_limit": allowance,
        "monthly_used": used,
        "monthly_remaining": monthly_left,
        "wallet": wallet,
        "limit": allowance + wallet,
        "used": min(used, allowance),
        "remaining": monthly_left + wallet,
        "resets_at": int(next_month.timestamp()),
        "key": month_key(user_id, month),
    }


def require_tokens(service):
    current = balance(service)
    if current["remaining"] < MIN_START_TOKENS:
        raise DomainError(
            429,
            "Токены ассистента закончились. Они обновятся в начале месяца; больше токенов — в тарифе Про.",
        )
    return current


def charge(service, tokens, reason="assistant", ref=None):
    """Spend tokens: monthly allowance first, then the wallet. Returns what was charged."""
    tokens = int(tokens or 0)
    if tokens <= 0:
        return 0
    con, user_id = service.con, service.user["id"]
    current = balance(service)
    from_month = min(tokens, current["monthly_remaining"])
    over = tokens - from_month
    now = stamp()
    if from_month:
        con.execute(
            "INSERT INTO rate_limits(key,count,started) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET count=rate_limits.count+excluded.count",
            (current["key"], from_month, now),
        )
        con.execute(
            "INSERT INTO ai_token_ledger(id,user_id,bucket,delta,reason,note,ref,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (identity(), user_id, "monthly", -from_month, reason, "", ref, None, now),
        )
    if over:
        _wallet_add(con, user_id, -over, reason, "", None, None)
    return tokens
