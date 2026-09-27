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
    parser.add_argument("command", choices=["backup", "check"])
    parser.add_argument(
        "--db", default=os.getenv("DB_PATH", str(ROOT / "data/smetra.sqlite3"))
    )
    args = parser.parse_args()
    source = Path(args.db).resolve()
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
            dest = (
                ROOT
                / "data/backups"
                / (
                    "smetra-"
                    + dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                    + ".sqlite3"
                )
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(dest) as backup:
                con.backup(backup)
                if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise SystemExit("Backup integrity check failed")
            print(str(dest))


if __name__ == "__main__":
    main()
