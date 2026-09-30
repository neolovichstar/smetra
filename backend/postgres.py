"""PostgreSQL bridge for the existing parameterized repository queries.

SQLite remains the local default. All cloud tables live in a private schema;
Supavisor transaction pooling needs neither session state nor prepared queries.
"""

import hashlib
import os
import re
import sqlite3
import urllib.parse
from decimal import Decimal

import psycopg

TABLES = frozenset(
    "users sessions email_tokens quotes payments refunds events support audit workspaces workspace_members clients catalog_items quote_items quote_versions activity projects project_stages tasks leads project_payments expenses comments notifications notification_reads custom_field_definitions estimate_templates documents files ai_usage schema_migrations file_payloads rate_limits".split()
)
TABLES = TABLES | frozenset(
    "external_identities oauth_states oauth_tickets assistant_messages assistant_actions".split()
)
TABLES = TABLES | frozenset("intake_forms client_requests".split())
TABLES = TABLES | frozenset("assistant_conversations workspace_knowledge file_text_chunks".split())
TABLES = TABLES | frozenset(
    "construction_objects construction_zones construction_measurements construction_quantities construction_facts construction_defects construction_daily_logs construction_log_photos construction_suppliers construction_purchases construction_changes".split()
)
TOKENS = re.compile(r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\")")


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
                if match[1] in TABLES
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
        database_url = os.environ["RUNTIME_DATABASE_URL" if runtime else "DATABASE_URL"]
        loopback = urllib.parse.urlsplit(database_url).hostname in ("localhost", "127.0.0.1", "::1")
        local_test = os.getenv("SMETRA_LOCAL_POSTGRES") == "1" and loopback
        self.raw = psycopg.connect(
            database_url,
            sslmode="disable" if local_test else "require",
            connect_timeout=15,
            prepare_threshold=None,
            autocommit=True,
            row_factory=row_factory,
        )
        self.lock_key = int.from_bytes(
            hashlib.sha256(self.schema.encode()).digest()[:8], "big", signed=True
        )

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

    def finish(self, success):
        if self.scoped:
            if self.nested:
                self.raw.execute("ROLLBACK")
                self.scoped = self.nested = False
                self.raw.close()
                raise RuntimeError("Unfinished runtime write transaction")
            self.raw.execute("COMMIT" if success else "ROLLBACK")
            self.scoped = False
            self.nested = False
        self.raw.close()

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
                return self.raw.execute(
                    "SELECT pg_advisory_xact_lock(%s)", (self.lock_key,)
                )
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
        # Do not use pipeline mode with the transaction pooler.
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
        if self.scoped:
            self.raw.execute("ROLLBACK")
            self.scoped = False
        self.raw.close()


def throttle(key, limit, window, moment):
    """Atomic rate limiting shared by all Vercel instances."""
    connection = Connection()
    try:
        with connection:
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
        connection.close()
