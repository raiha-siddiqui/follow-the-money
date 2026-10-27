"""Shared infrastructure: key authentication, request telemetry and workspace locks.

These modules were adapted from the Polyglot Watchlist project so that this
repository installs and runs on its own. The tracing service owns its own
authorization policy on top of them.
"""

from follow_the_money.infra import auth
from follow_the_money.infra.errors import ReviewError
from follow_the_money.infra.locking import create_lock_file, workspace_lock
from follow_the_money.infra.observability import Observability, ObservabilityMiddleware

__all__ = [
    "auth",
    "Observability",
    "ObservabilityMiddleware",
    "ReviewError",
    "create_lock_file",
    "workspace_lock",
]
