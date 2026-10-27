"""Tracing roles over constant-time hashed-key authentication (see infra/auth.py).

Agent keys can start traces and read bounded summaries. Approvers are humans;
the legacy reviewer role remains a human-role alias. Neither role can approve
its own case. The underlying key hashing and comparison are shared with Polyglot Watchlist.
"""

from dataclasses import dataclass
from typing import Iterable

from follow_the_money.infra import auth

ROLES = ("viewer", "agent", "approver", "reviewer")


@dataclass(frozen=True)
class Principal:
    actor: str
    role: str

    def can(self, required: str) -> bool:
        if required == "viewer":
            return self.role in ROLES
        if required == "agent":
            return self.role in {"agent", "approver", "reviewer"}
        return required in {"approver", "reviewer"} and self.role in {
            "approver",
            "reviewer",
        }


@dataclass(frozen=True)
class KeyEntry:
    role: str
    key: auth.ApiKey


def parse_key_entries(lines: Iterable[str]) -> tuple[KeyEntry, ...]:
    entries, seen = [], set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) != 3 or parts[1] not in ROLES:
            raise auth.AuthConfigError("Use actor:role:sha256 with a Project 2 role")
        actor, role, hashed = parts
        key = auth.parse_key_entry(f"{actor}:viewer:{hashed}")
        if hashed in seen:
            raise auth.AuthConfigError("duplicate API key hash")
        seen.add(hashed)
        entries.append(KeyEntry(role, key))
    return tuple(entries)


def new_key(actor: str, role: str) -> tuple[str, str]:
    if role not in ROLES:
        raise auth.AuthConfigError("Unknown Project 2 role")
    token, entry = auth.new_key(actor, "viewer")
    return token, entry.replace(":viewer:", f":{role}:", 1)


class KeyStore:
    def __init__(self, entries: Iterable[KeyEntry]):
        entries = tuple(entries)
        if len({entry.key.sha256 for entry in entries}) != len(entries):
            raise auth.AuthConfigError("duplicate API key hash")
        self._count = len(entries)
        self.model_actors = frozenset(e.key.actor for e in entries if e.role == "agent")
        self._stores = {
            role: auth.KeyStore(e.key for e in entries if e.role == role)
            for role in ROLES
        }

    def __len__(self) -> int:
        return self._count

    def authenticate(self, token: str | None) -> Principal | None:
        found = None
        # Always check every role and hash, including after a successful match.
        for role, store in self._stores.items():
            principal = store.authenticate(token)
            if principal is not None:
                found = Principal(principal.actor, role)
        return found


def can_start(principal) -> bool:
    return principal.role in {"agent", "approver", "reviewer"}


def is_human(principal, model_actors=()) -> bool:
    return (
        principal.role in {"approver", "reviewer"}
        and principal.actor not in model_actors
    )
