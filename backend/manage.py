"""Backup and verification commands. Never deletes the live database."""

import argparse
import datetime as dt
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["backup", "check", "restore-check"])
    parser.add_argument("--output", help="New backup file; existing files are never overwritten")
    parser.add_argument("--archive", help="PostgreSQL archive for an isolated restore check")
    parser.add_argument("--schema", default=os.getenv("SMETRA_DB_SCHEMA", "smetra"))
    parser.add_argument(
        "--db", default=None
    )
    args = parser.parse_args()
    if args.command == "restore-check" or (os.getenv("DATABASE_URL") and not args.db):
        from backend import postgres_backup

        try:
            if args.command == "restore-check":
                if not args.archive or not os.getenv("RESTORE_DATABASE_URL"):
                    raise postgres_backup.BackupError("--archive and RESTORE_DATABASE_URL are required")
                result = postgres_backup.restore_check(args.archive, os.environ["RESTORE_DATABASE_URL"])
            elif args.command == "check":
                result = postgres_backup.check(os.environ["DATABASE_URL"], args.schema)
            else:
                destination = args.output or str(ROOT / "data/backups" / (
                    "smetra-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S-%f") + ".dump"))
                result = postgres_backup.backup(os.environ["DATABASE_URL"], destination, args.schema)
        except postgres_backup.BackupError as error:
            raise SystemExit(str(error)) from None
        except Exception as error:
            raise SystemExit("PostgreSQL operation failed (" + type(error).__name__ + ")") from None
        print(json.dumps(result, ensure_ascii=False))
        return
    source = Path(args.db or os.getenv("DB_PATH", str(ROOT / "data/smetra.sqlite3"))).resolve()
    if not source.is_file():
        raise SystemExit("Database does not exist: " + str(source))
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as con:
        if args.command == "check":
            integrity = con.execute("PRAGMA integrity_check").fetchall()
            foreign = con.execute("PRAGMA foreign_key_check").fetchall()
            print(
                json.dumps({"integrity": integrity, "foreign_key_violations": foreign})
            )
            if integrity != [("ok",)] or foreign:
                raise SystemExit(1)
        else:
            dest = Path(args.output).resolve() if args.output else (
                ROOT
                / "data/backups"
                / (
                    "smetra-"
                    + dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                    + ".sqlite3"
                )
            )
            if dest.exists():
                raise SystemExit("Backup destination already exists")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(dest) as backup:
                con.backup(backup)
                if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise SystemExit("Backup integrity check failed")
            print(str(dest))


if __name__ == "__main__":
    main()
