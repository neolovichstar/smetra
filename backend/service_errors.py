"""Dependency-neutral errors shared by storage and the HTTP boundary."""


class DatabaseBusyError(RuntimeError):
    """No database slot is available within the bounded acquisition budget."""
