"""Custom exceptions for the ORCHESTRA database layer.

These wrap the lower-level SQLAlchemy / driver errors in a small, stable
hierarchy so that callers (repositories, services, API handlers) can react to
failures without importing SQLAlchemy internals. Every exception raised by the
database package derives from :class:`DatabaseError`.
"""

from __future__ import annotations

from typing import Optional


class DatabaseError(Exception):
    """Base class for every error raised by the database layer.

    Args:
        message: Human-readable description of what went wrong.
        original: The underlying exception that triggered this error, if any.
    """

    def __init__(self, message: str, *, original: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.message = message
        self.original = original

    def __str__(self) -> str:  # pragma: no cover - trivial
        if self.original is not None:
            return f"{self.message} (caused by {type(self.original).__name__}: {self.original})"
        return self.message


class NotFoundError(DatabaseError):
    """Raised when a requested row does not exist.

    Args:
        entity: The model / table name that was queried.
        identifier: The identifier that was searched for.
    """

    def __init__(
        self,
        entity: str,
        identifier: object = None,
        *,
        original: Optional[BaseException] = None,
    ) -> None:
        message = f"{entity} not found"
        if identifier is not None:
            message = f"{entity} with identifier {identifier!r} not found"
        super().__init__(message, original=original)
        self.entity = entity
        self.identifier = identifier


class DuplicateError(DatabaseError):
    """Raised when an insert/update violates a unique constraint."""


class ConstraintViolationError(DatabaseError):
    """Raised when a check / foreign-key / not-null constraint is violated."""


class ConnectionError(DatabaseError):
    """Raised when the database cannot be reached or a session cannot open.

    Note:
        This intentionally shadows the built-in :class:`ConnectionError` within
        this package's namespace; import it explicitly (``from
        orchestra.database.exceptions import ConnectionError``) when the
        database-specific semantics are required.
    """


class TransactionError(DatabaseError):
    """Raised when a transaction cannot be committed or rolled back."""


__all__ = [
    "DatabaseError",
    "NotFoundError",
    "DuplicateError",
    "ConstraintViolationError",
    "ConnectionError",
    "TransactionError",
]
