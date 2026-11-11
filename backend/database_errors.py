"""Classify temporary database failures without retrying business mutations."""

import sqlite3


def unavailable(error):
    if isinstance(error, sqlite3.OperationalError):
        return str(error).lower() in ("database is locked", "database table is locked", "database is busy")
    try:
        from psycopg import OperationalError
    except ImportError:
        return False
    if isinstance(error, OperationalError):
        return True
    try:
        from psycopg_pool import PoolTimeout
    except ImportError:
        return False
    return isinstance(error, PoolTimeout)
