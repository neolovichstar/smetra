"""PostgreSQL bridge for the existing parameterized repository queries.

SQLite remains the local default. All cloud tables live in a private schema;
Supavisor transaction pooling needs neither session state nor prepared queries.
"""

import hashlib
import os
import re
import sqlite3
import threading
import urllib.parse
from decimal import Decimal
from contextlib import nullcontext
from functools import lru_cache

import psycopg

try:
    from psycopg_pool import ConnectionPool
except ImportError:  # The direct-connection fallback keeps local/minimal tools usable.
    ConnectionPool = None

TABLES = frozenset(["email_login_challenges","estimate_shares","estimate_share_responses"]) | frozenset(
    "users sessions email_tokens quotes payments refunds events support audit workspaces workspace_members clients catalog_items catalog_price_history quote_items quote_versions activity projects project_stages tasks leads project_payments expenses comments notifications notification_reads custom_field_definitions estimate_templates documents files ai_usage schema_migrations file_payloads rate_limits legal_acceptances".split()
)
TABLES = TABLES | frozenset(
    "external_identities oauth_states oauth_tickets assistant_messages assistant_actions".split()
)
TABLES = TABLES | frozenset("intake_forms client_requests".split())
TABLES = TABLES | frozenset("assistant_conversations workspace_knowledge file_text_chunks".split())
TABLES = TABLES | frozenset("user_profiles assistant_memory".split())
TABLES = TABLES | frozenset("growth_events pricing_assignments billing_intents referral_links referral_rewards".split())
TABLES = TABLES | frozenset("file_versions".split())
TABLES = TABLES | frozenset("product_updates product_update_views product_update_reactions".split())
TABLES = TABLES | frozenset("construction_price_batches".split())
TABLES = TABLES | frozenset("quote_creation_requests".split())
TABLES = TABLES | frozenset(["assistant_jobs"])
TABLES = TABLES | frozenset(["creation_requests"])
TABLES = TABLES | frozenset(["assistant_ad_rewards", "assistant_ad_attempts", "assistant_ad_reward_credits", "assistant_ad_reward_usage"])
TABLES = TABLES | frozenset("push_devices push_outbox push_deliveries".split())
TABLES = TABLES | frozenset(
    "construction_objects construction_zones construction_measurements construction_quantities construction_facts construction_defects construction_daily_logs construction_log_photos construction_suppliers construction_purchases construction_changes".split()
)
TABLES = TABLES | frozenset(
    "product_sources product_price_observations cloud_connections cloud_oauth_states cloud_folder_bindings cloud_files document_processing_jobs cloud_watch_channels".split()
)
TABLES = TABLES | frozenset("object_chat_threads object_chat_messages project_cash_risks".split())
TABLES = TABLES | frozenset("partner_accounts partner_api_tokens partner_clicks partner_attributions partner_commissions partner_products partner_outbound_clicks partner_domain_verifications partner_site_events partner_console_sessions partner_members partner_invites partner_sso_codes".split())
TABLES = TABLES | frozenset("ai_token_wallets ai_token_ledger assistant_bonus_grants assistant_bonus_usage".split())
TOKENS = re.compile(r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\")")
_SIMPLE_INSERT_VALUES = re.compile(
    r"(?P<prefix>\s*INSERT\s+INTO\s+[a-z_][a-z0-9_]*(?:\s*\([^()]*\))?\s+VALUES)\s*"
    r"(?P<values>\(\s*\?\s*(?:,\s*\?\s*)*\))\s*;?\s*",
    re.I | re.S,
)
_POOL_LOCK = threading.Lock()
_POOLS = {}


def _connection_pool(database_url, local_test):
    """Return a small process-local pool; Vercel warm instances can reuse TLS sessions."""
    if ConnectionPool is None:
        return None
    key = hashlib.sha256((database_url + ("|local" if local_test else "|tls")).encode()).hexdigest()
    with _POOL_LOCK:
        pool = _POOLS.get(key)
        if pool is None:
            try:
                max_size = int(os.getenv("SMETRA_DB_POOL_MAX", "2"))
            except ValueError:
                max_size = 2
            max_size = max(1, min(4, max_size))
            pool = ConnectionPool(
                conninfo=database_url,
                min_size=0,
                max_size=max_size,
                timeout=5,
                max_idle=5,
                max_lifetime=300,
                kwargs={
                    "sslmode": "disable" if local_test else "require",
                    "connect_timeout": 5,
                    "prepare_threshold": None,
                    "autocommit": True,
                    "row_factory": row_factory,
                },
                open=True,
            )
            _POOLS[key] = pool
        return pool


class Row(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


def row_factory(cursor):
    names = [column.name for column in cursor.description] if cursor.description else []
    return lambda values: Row(
        zip(
            names,
            (
                int(value)
                if isinstance(value, Decimal) and value == int(value)
                else value
                for value in values
            ),
        )
    )


def schema_name():
    name = os.getenv("SMETRA_DB_SCHEMA", "smetra")
    if not re.fullmatch(r"smetra(?:_[a-z0-9_]+)?", name):
        raise ValueError("Invalid Smetra database schema")
    return name


def translate(sql, schema, parameters=False):
    """Cache SQL translation only, never parameters, rows or authorization state."""
    # Large bulk INSERTs are one-off statements; do not retain them in the LRU.
    translator = _translate_cached if len(sql) <= 8192 else _translate
    return translator(sql, schema, bool(parameters), TABLES)


@lru_cache(maxsize=2048)
def _translate_cached(sql, schema, parameters, tables):
    return _translate(sql, schema, parameters, tables)


def _translate(sql, schema, parameters, tables):
    """Translate our small SQL subset without touching quoted values."""
    ignore = sql.lstrip().upper().startswith("INSERT OR IGNORE")
    sql = re.sub(r"\bINSERT OR IGNORE\b", "INSERT", sql, flags=re.I)
    parts = TOKENS.split(sql)
    for index in range(0, len(parts), 2):
        part = parts[index]
        part = re.sub(r"\binstr\s*\(", "strpos(", part, flags=re.I)
        part = re.sub(r"\bINTEGER\b", "BIGINT", part, flags=re.I)
        part = re.sub(
            r"(?<![\w.])([a-z_][a-z_0-9]*)(?![\w])",
            lambda match: (
                schema + "." + match[1]
                if match[1] in tables
                and not re.search(r"\bAS\s+$", part[: match.start()], re.I)
                else match[0]
            ),
            part,
        )
        parts[index] = part
    # Psycopg percent placeholders apply inside SQL string literals too.
    if parameters:
        parts = [part.replace("%", "%%") for part in parts]
        for index in range(0, len(parts), 2):
            parts[index] = parts[index].replace("?", "%s")
    result = "".join(parts).rstrip().rstrip(";")
    if ignore:
        result += " ON CONFLICT DO NOTHING"
    return result


class Connection:
    is_postgres = True

    def __init__(self, runtime=False):
        self.schema = schema_name()
        self.runtime = runtime
        self.scoped = False
        self.nested = False
        self.pool = None
        self.raw = None
        key = "RUNTIME_DATABASE_URL" if runtime else "DATABASE_URL"
        database_url = os.environ[key].strip()
        # Some Vercel dashboards receive an accidentally pasted .env assignment
        # (DATABASE_URL=postgresql://...) as the VALUE of DATABASE_URL. libpq
        # otherwise parses DATABASE_URL as an unsupported connection option.
        # Accept only this unambiguous copy/paste error, and never log the DSN.
        if database_url.startswith(key + "="):
            database_url = database_url[len(key) + 1:].strip()
            if len(database_url) >= 2 and database_url[0] == database_url[-1] and database_url[0] in ("'", '"'):
                database_url = database_url[1:-1]
        if not database_url.startswith(("postgresql://", "postgres://")):
            raise RuntimeError("Invalid PostgreSQL connection URI: update " + key + " in deployment settings")
        # Some Supabase examples intended for Prisma append driver-specific
        # connection hints. libpq/psycopg reject them as invalid URI options.
        # Strip ONLY known non-libpq tuning hints, preserve security settings.
        parts = urllib.parse.urlsplit(database_url)
        qs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        prisma_hints = {"pgbouncer", "connection_limit", "pool_timeout", "schema"}
        if any(k in prisma_hints for k, _ in qs):
            qs = [(k, v) for k, v in qs if k not in prisma_hints]
            database_url = urllib.parse.urlunsplit((
                parts.scheme, parts.netloc, parts.path,
                urllib.parse.urlencode(qs), parts.fragment,
            ))
        loopback = urllib.parse.urlsplit(database_url).hostname in ("localhost", "127.0.0.1", "::1")
        local_test = os.getenv("SMETRA_LOCAL_POSTGRES") == "1" and loopback
        self.pool = _connection_pool(database_url, local_test)
        if self.pool is not None:
            self.raw = self.pool.getconn(timeout=5)
        else:
            self.raw = psycopg.connect(
                database_url,
                sslmode="disable" if local_test else "require",
                connect_timeout=5,
                prepare_threshold=None,
                autocommit=True,
                row_factory=row_factory,
            )
        self.lock_key = int.from_bytes(
            hashlib.sha256(self.schema.encode()).digest()[:8], "big", signed=True
        )
        self.lock_scopes = ()

    def set_transaction_lock_scopes(self, scopes):
        """Temporarily select the logical resources this transaction must serialize."""
        previous = self.lock_scopes
        if scopes is None:
            self.lock_scopes = ()
            return previous
        if isinstance(scopes, str):
            scopes = (scopes,)
        normalized = set()
        for scope in scopes:
            if scope is None:
                continue
            value = str(scope).strip()
            if value:
                normalized.add(value)
        self.lock_scopes = tuple(sorted(normalized))
        return previous

    def _transaction_lock_keys(self):
        if not self.lock_scopes:
            return (self.lock_key,)
        return tuple(sorted({
            int.from_bytes(
                hashlib.sha256(
                    f"smetra:transaction:{self.schema}:{scope}".encode()
                ).digest()[:8],
                "big",
                signed=True,
            )
            for scope in self.lock_scopes
        }))

    def scope(self, session_hash, workspace_id):
        """Keep untrusted request context transaction-local for the RLS policies."""
        if not self.runtime or self.scoped or not session_hash or not workspace_id:
            raise ValueError("Invalid runtime database scope")
        self.raw.execute("BEGIN")
        try:
            self.raw.execute(
                "SELECT set_config('smetra.session_hash',%s,true), "
                "set_config('smetra.workspace_id',%s,true)",
                (session_hash, workspace_id),
            )
            self.scoped = True
        except Exception:
            self.raw.execute("ROLLBACK")
            raise

    def _release(self):
        raw, self.raw = self.raw, None
        if raw is None:
            return
        if self.pool is not None:
            try:
                self.pool.putconn(raw)
                return
            except Exception:
                # A broken connection should not be handed back to application code.
                try:
                    raw.close()
                except Exception:
                    pass
                return
        raw.close()

    def finish(self, success):
        if self.scoped and self.nested:
            try:
                self.raw.execute("ROLLBACK")
            finally:
                self.scoped = self.nested = False
                self._release()
            raise RuntimeError("Unfinished runtime write transaction")
        try:
            if self.scoped:
                self.raw.execute("COMMIT" if success else "ROLLBACK")
        finally:
            self.scoped = False
            self.nested = False
            self._release()

    def execute(self, sql, parameters=None):
        command = sql.strip().upper()
        try:
            if self.runtime and not self.scoped:
                raise RuntimeError("Runtime query without verified session scope")
            if command == "BEGIN IMMEDIATE":
                if self.runtime:
                    if self.nested:
                        raise RuntimeError("Nested runtime write transaction")
                    self.raw.execute("SAVEPOINT smetra_write")
                    self.nested = True
                else:
                    self.raw.execute("BEGIN")
                # Preserve SQLite's atomic read/check/write semantics across instances.
                self.raw.execute("SET LOCAL lock_timeout='15s'")
                if not self.lock_scopes:
                    # Legacy callers hold the exclusive gate until they are migrated.
                    return self.raw.execute(
                        "SELECT pg_advisory_xact_lock(%s)", (self.lock_key,)
                    )
                # Scoped transactions share the gate with one another, but remain
                # mutually exclusive with legacy global transactions.
                self.raw.execute(
                    "SELECT pg_advisory_xact_lock_shared(%s)", (self.lock_key,)
                )
                result = None
                for lock_key in self._transaction_lock_keys():
                    result = self.raw.execute(
                        "SELECT pg_advisory_xact_lock(%s)", (lock_key,)
                    )
                return result
            if self.runtime and command in ("COMMIT", "ROLLBACK"):
                if not self.nested:
                    raise RuntimeError("Runtime transaction boundary is managed by the request")
                if command == "ROLLBACK":
                    self.raw.execute("ROLLBACK TO SAVEPOINT smetra_write")
                result = self.raw.execute("RELEASE SAVEPOINT smetra_write")
                self.nested = False
                return result
            pragma = re.fullmatch(r"PRAGMA table_info\((\w+)\)", sql.strip(), re.I)
            if pragma:
                return self.raw.execute(
                    "SELECT column_name AS name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s",
                    (self.schema, pragma[1]),
                )
            return self.raw.execute(
                translate(sql, self.schema, parameters is not None), parameters
            )
        except psycopg.IntegrityError as error:
            raise sqlite3.IntegrityError(type(error).__name__) from None

    def executemany(self, sql, rows):
        """Batch simple INSERTs to reduce network round-trips through Supavisor.

        Keep the conservative row-by-row path for other SQL forms, since their
        conflict handling, RETURNING semantics, or placeholders may differ.
        Bound each statement below PostgreSQL's extended-protocol parameter cap.
        """
        match = _SIMPLE_INSERT_VALUES.fullmatch(sql)
        if match and isinstance(rows, (list, tuple)) and rows:
            template = match.group("values")
            width = template.count("?")
            if width and all(
                hasattr(row, "__len__") and len(row) == width for row in rows
            ):
                batch_size = max(1, 60_000 // width)
                for offset in range(0, len(rows), batch_size):
                    batch = rows[offset : offset + batch_size]
                    statement = (
                        f"{match.group('prefix')} "
                        + ",".join(template for _ in batch)
                    )
                    parameters = tuple(value for row in batch for value in row)
                    self.execute(statement, parameters)
                return

        for row in rows:
            self.execute(sql, row)

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        if kind:
            self.raw.rollback()
        else:
            self.raw.commit()

    def close(self):
        if self.raw is None:
            return
        try:
            if self.scoped:
                self.raw.execute("ROLLBACK")
        finally:
            self.scoped = False
            self.nested = False
            self._release()


def throttle(key, limit, window, moment, *, connection=None):
    """Atomic distributed limit; reuse an existing unscoped request connection.

    A request already occupies an auth connection. Taking another from the
    same small pool can deadlock all concurrent requests during a Redis outage.
    The caller retains ownership of its transaction and connection.
    """
    owned = connection is None
    if owned:
        connection = Connection()
    try:
        with connection if owned else nullcontext():
            row = connection.execute(
                "INSERT INTO rate_limits(key,count,started) VALUES(?,1,?) "
                "ON CONFLICT(key) DO UPDATE SET "
                "count=CASE WHEN rate_limits.started<=? THEN 1 ELSE rate_limits.count+1 END, "
                "started=CASE WHEN rate_limits.started<=? THEN ? ELSE rate_limits.started END "
                "RETURNING count",
                (
                    hashlib.sha256(key.encode()).hexdigest(),
                    moment,
                    moment - window,
                    moment - window,
                    moment,
                ),
            ).fetchone()
            return row[0] <= limit
    finally:
        if owned:
            connection.close()
