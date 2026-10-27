"""Structured errors shared by the tracing service and its workspace lock.

Adapted from the Polyglot Watchlist review service so this project runs on its
own. Every error has a stable ``code`` and a ``retryable`` flag.
"""

from __future__ import annotations

import json
from typing import Any, Mapping


def canonical(value: object) -> str:
    """One finite JSON text for hashing and storage (sorted keys, UTF-8 safe)."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


class ReviewError(Exception):
    """Base class for expected review-service failures."""

    code = "review_error"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        retryable: bool | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.details = dict(details or {})
        if retryable is not None:
            # Per-instance override, e.g. a retryable cause after a case already exists.
            self.retryable = bool(retryable)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": json.loads(canonical(self.details)),
        }


class ValidationError(ReviewError):
    """Caller input has the wrong shape, type, bounds or value."""

    code = "invalid_input"


class WorkspaceError(ReviewError):
    """A workspace is missing, incomplete, not empty or not an owned v2 store."""

    code = "workspace_invalid"


class WorkspaceBusyError(ReviewError):
    """The cooperative workspace lock was not acquired before its deadline."""

    code = "workspace_busy"
    retryable = True


class ReentrantCallError(ReviewError):
    """This thread already holds the workspace lock (e.g. a provider called back)."""

    code = "reentrant_call"
