"""Verified logical backups for the private PostgreSQL application schema."""
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict


class BackupError(RuntimeError):
    pass


def _schema(value):
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value or ""):
        raise BackupError("Use one explicit PostgreSQL schema name")
    return value


def _environment(database_url):
    try:
        parameters = conninfo_to_dict(database_url)
    except Exception:
        raise BackupError("Invalid PostgreSQL connection configuration") from None
    if not parameters.get("host") or not parameters.get("dbname"):
        raise BackupError("The database URL must include an explicit host and database")
    environment = dict(os.environ)
    # libpq exposes the mapping, so SSL and other security settings are preserved.
    # Credentials stay in the child environment, never in argv or diagnostics.
    for item in psycopg.pq.Conninfo.get_defaults():
        name, variable = item.keyword.decode(), item.envvar
        if name in parameters and variable:
            environment[variable.decode()] = parameters[name]
    environment["PGAPPNAME"] = "smetra-backup"
    environment.setdefault("PGCONNECT_TIMEOUT", "10")
    return environment


def _run(command, database_url):
    if not shutil.which(command[0]):
        raise BackupError(command[0] + " is required; install matching PostgreSQL client tools")
    try:
        result = subprocess.run(command, env=_environment(database_url),
                                capture_output=True, timeout=1800, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise BackupError(command[0] + " could not finish; no database credentials were logged") from None
    if result.returncode:
        # Provider/client stderr can contain a DSN or credentials.
        raise BackupError(command[0] + " failed (exit " + str(result.returncode) + ")")
    return result


def _sha256(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def _inventory(con, schema):
    tables = con.execute(
        "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=%s AND c.relkind='r' ORDER BY c.relname", (schema,),
    ).fetchall()
    if not tables:
        raise BackupError("The selected application schema has no tables")
    rows = {}
    for name, enabled, forced in tables:
        count, total = 0, 0
        # Order-independent row fingerprints include every column and duplicate.
        # They detect content changes without putting private records in the manifest.
        with con.cursor(name="smetra_backup_rows") as cursor:
            cursor.execute(sql.SQL("SELECT row_to_json(t)::text FROM {}.{} t").format(
                sql.Identifier(schema), sql.Identifier(name)))
            for (value,) in cursor:
                count += 1
                total = (total + int.from_bytes(hashlib.sha256(value.encode()).digest(), "big")) % (1 << 256)
        rows[name] = {"count": count, "content": hashlib.sha256(
            (str(count) + ":" + str(total)).encode()).hexdigest(),
            "rls": enabled, "force_rls": forced}
    constraints = con.execute(
        "SELECT c.relname,k.conname,pg_get_constraintdef(k.oid) FROM pg_constraint k "
        "JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=%s ORDER BY c.relname,k.conname", (schema,),
    ).fetchall()
    policies = con.execute(
        "SELECT tablename,policyname,permissive,roles::text,cmd,qual,with_check "
        "FROM pg_policies WHERE schemaname=%s ORDER BY tablename,policyname", (schema,),
    ).fetchall()
    indexes = con.execute(
        "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname=%s "
        "ORDER BY tablename,indexname", (schema,),
    ).fetchall()
    grants = con.execute(
        "SELECT table_name,grantee,privilege_type FROM information_schema.role_table_grants "
        "WHERE table_schema=%s AND grantee<>current_user "
        "ORDER BY table_name,grantee,privilege_type", (schema,),
    ).fetchall()
    column_grants = con.execute(
        "SELECT table_name,column_name,grantee,privilege_type FROM information_schema.role_column_grants "
        "WHERE table_schema=%s AND grantee<>current_user "
        "ORDER BY table_name,column_name,grantee,privilege_type", (schema,),
    ).fetchall()
    columns = con.execute(
        "SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,"
        "pg_get_expr(d.adbin,d.adrelid) FROM pg_attribute a "
        "JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        "LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
        "WHERE n.nspname=%s AND a.attnum>0 AND NOT a.attisdropped AND c.relkind='r' "
        "ORDER BY c.relname,a.attnum", (schema,),
    ).fetchall()
    routines = con.execute(
        "SELECT p.proname,pg_get_functiondef(p.oid) FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=%s AND p.prokind='f' "
        "ORDER BY p.proname,p.oid::regprocedure::text", (schema,),
    ).fetchall()
    structure = [columns, constraints, policies, indexes, grants, column_grants, routines]
    return {"tables": rows, "structure_sha256": hashlib.sha256(
        json.dumps(structure, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()}


def _connect(database_url):
    try:
        return psycopg.connect(database_url, autocommit=True, connect_timeout=10)
    except Exception:
        raise BackupError("PostgreSQL connection failed; verify the private connection configuration") from None


def check(database_url, schema="smetra"):
    schema = _schema(schema)
    with _connect(database_url) as con:
        con.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        result = _inventory(con, schema)
        con.execute("ROLLBACK")
    return {"ok": True, "schema": schema, "tables": len(result["tables"]),
            "rows": sum(table["count"] for table in result["tables"].values())}


def backup(database_url, destination, schema="smetra"):
    schema, destination = _schema(schema), Path(destination).resolve()
    manifest_path = Path(str(destination) + ".json")
    if destination.exists() or manifest_path.exists():
        raise BackupError("Backup destination already exists")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".smetra-backup-", dir=destination.parent)
    os.close(handle)
    temporary = Path(temporary)
    started = time.monotonic()
    try:
        with _connect(database_url) as con:
            con.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            snapshot = con.execute("SELECT pg_export_snapshot()").fetchone()[0]
            inventory = _inventory(con, schema)
            _run(["pg_dump", "--format=custom", "--no-password", "--strict-names",
                  "--schema=" + schema, "--snapshot=" + snapshot, "--file=" + str(temporary)],
                 database_url)
            con.execute("ROLLBACK")
        manifest = {"format": "smetra-postgres-backup-v1", "schema": schema,
                    "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "dump_sha256": _sha256(temporary), "bytes": temporary.stat().st_size,
                    "inventory": inventory, "seconds": round(time.monotonic() - started, 3)}
        # Hard-link publication is atomic and fails if another writer owns the name.
        os.link(temporary, destination)
        with manifest_path.open("x", encoding="utf-8") as stream:
            os.chmod(manifest_path, 0o600)
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
        return {"ok": True, "backup": str(destination), "manifest": str(manifest_path),
                "tables": len(inventory["tables"]), "seconds": manifest["seconds"],
                "sha256": manifest["dump_sha256"]}
    finally:
        temporary.unlink(missing_ok=True)


def restore_check(archive, target_url):
    """Restore only to an explicitly named local drill database, never production."""
    archive = Path(archive).resolve()
    parsed = urllib.parse.urlsplit(target_url)
    try:
        effective = conninfo_to_dict(target_url)
    except Exception:
        raise BackupError("Invalid restore connection configuration") from None
    loopback = ("localhost", "127.0.0.1", "::1")
    if (parsed.scheme not in ("postgresql", "postgres")
            or effective.get("host") not in loopback
            or effective.get("hostaddr", "127.0.0.1") not in loopback):
        raise BackupError("Restore checks require an isolated loopback PostgreSQL database")
    database = effective.get("dbname", "")
    if not re.fullmatch(r"smetra_restore_[a-z0-9_]{1,40}", database):
        raise BackupError("The target database name must start with smetra_restore_")
    try:
        manifest = json.loads(Path(str(archive) + ".json").read_text())
        if manifest["format"] != "smetra-postgres-backup-v1" or manifest["dump_sha256"] != _sha256(archive):
            raise BackupError("Backup checksum does not match its manifest")
        schema = _schema(manifest["schema"])
        inventory = manifest["inventory"]
        if (not isinstance(inventory, dict) or not isinstance(inventory.get("tables"), dict)
                or not inventory["tables"] or not re.fullmatch(r"[a-f0-9]{64}", inventory.get("structure_sha256", ""))):
            raise BackupError("The backup inventory is invalid")
        for table, record in inventory["tables"].items():
            if (not isinstance(table, str) or not isinstance(record, dict)
                    or type(record.get("count")) is not int or record["count"] < 0
                    or not isinstance(record.get("content"), str)
                    or not re.fullmatch(r"[a-f0-9]{64}", record["content"])
                    or type(record.get("rls")) is not bool or type(record.get("force_rls")) is not bool):
                raise BackupError("The backup inventory is invalid")
    except (OSError, ValueError, KeyError, TypeError):
        raise BackupError("A valid backup and its checksum manifest are required") from None
    started = time.monotonic()
    with _connect(target_url) as con:
        if con.info.dbname != database or con.info.hostaddr not in ("127.0.0.1", "::1"):
            raise BackupError("The effective restore connection is not the isolated local target")
        if con.execute("SELECT 1 FROM pg_namespace WHERE nspname=%s", (schema,)).fetchone():
            raise BackupError("The target application schema already exists; nothing was changed")
        _run(["pg_restore", "--no-password", "--exit-on-error", "--single-transaction",
              "--no-owner", "--dbname=" + database, str(archive)], target_url)
        con.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        restored = _inventory(con, schema)
        con.execute("ROLLBACK")
    if restored != manifest["inventory"]:
        raise BackupError("Restore inventory differs; keep the isolated copy for inspection")
    return {"ok": True, "tables": len(restored["tables"]),
            "rows": sum(table["count"] for table in restored["tables"].values()),
            "seconds": round(time.monotonic() - started, 3),
            "verified": ["row_contents", "constraints", "indexes", "rls", "policies", "grants"]}
