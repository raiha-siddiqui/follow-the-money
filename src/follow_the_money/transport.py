"""Replay-first HTTP GET transport with checked cache and separate call budgets."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import math
from pathlib import Path
import threading
import time
from typing import Any, Callable, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import httpx

from follow_the_money.contracts import (
    FtmError,
    Provenance,
    canonical,
    strict_json,
    utc_now,
)

LIVE_BASES = ("https://mempool.space/api/", "https://blockstream.info/api/")
MAX_BODY = 4 * 1024 * 1024


def request_url(base: str, path: str, params: dict[str, Any] | None = None) -> str:
    """Canonical GET key; clients supply paths, never URLs returned by a server."""
    if not path.startswith("/") or ".." in path or "?" in path or "#" in path:
        raise FtmError("invalid_input", "Invalid API path")
    pairs = sorted((k, str(v)) for k, v in (params or {}).items() if v is not None)
    return base.rstrip("/") + path + ("?" + urlencode(pairs) if pairs else "")


def checked_url(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.port
    ):
        raise FtmError(
            "invalid_input",
            "Only HTTPS URLs without credentials or fragments are accepted",
        )
    if any(
        k.lower() in {"key", "api_key", "token", "apikey"}
        for k, _ in parse_qsl(parsed.query)
    ):
        raise FtmError("invalid_input", "Credentials must not appear in cache keys")
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(sorted(parse_qsl(parsed.query))),
            "",
        )
    )


@dataclass
class Budget:
    """Logical queries count cache hits; each actual attempt consumes network budget."""

    max_calls: int
    max_network_calls: int = 0
    calls: int = 0
    network_calls: int = 0
    _lock: Any = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        for value in (
            self.max_calls,
            self.max_network_calls,
            self.calls,
            self.network_calls,
        ):
            if type(value) is not int or value < 0:
                raise ValueError("budgets must be nonnegative integers")
        if self.calls > self.max_calls or self.network_calls > self.max_network_calls:
            raise ValueError("consumption exceeds budget")

    def charge(self, *, network: bool = False) -> None:
        with self._lock:
            name, maximum = (
                ("network_calls", self.max_network_calls)
                if network
                else ("calls", self.max_calls)
            )
            if getattr(self, name) >= maximum:
                raise FtmError("budget_exhausted", f"{name} budget exhausted")
            setattr(self, name, getattr(self, name) + 1)

    def snapshot(self) -> dict[str, int]:
        return {
            k: getattr(self, k)
            for k in ("max_calls", "max_network_calls", "calls", "network_calls")
        }


@dataclass(frozen=True)
class CachedResponse:
    url: str
    status: int
    body: bytes
    provenance: Provenance

    def json(self) -> Any:
        try:
            return strict_json(self.body)
        except (ValueError, UnicodeError):
            raise FtmError("invalid_response", "Response is not strict JSON") from None


class ReplayCache:
    """One immutable-in-use snapshot directory, with a digest per response body."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def path(self, url: str) -> Path:
        return self.root / (
            hashlib.sha256(checked_url(url).encode()).hexdigest() + ".json"
        )

    def read(self, url: str) -> CachedResponse | None:
        path = self.path(url)
        if not path.exists():
            return None
        try:
            if path.stat().st_size > MAX_BODY * 2:
                raise ValueError("oversized cache")
            record = strict_json(path.read_bytes())
            body = base64.b64decode(record["body_base64"], validate=True)
            if record["schema"] != "ftm-response-v1" or record["url"] != checked_url(
                url
            ):
                raise ValueError("cache identity mismatch")
            provenance = Provenance.model_validate(record["provenance"])
            if (
                len(body) > MAX_BODY
                or hashlib.sha256(body).hexdigest() != provenance.sha256
                or provenance.source_url != checked_url(url)
            ):
                raise ValueError("cache content mismatch")
            status = record["status"]
            if type(status) is not int or not 100 <= status <= 599:
                raise ValueError("cache status invalid")
            return CachedResponse(checked_url(url), status, body, provenance)
        except (ValueError, KeyError, TypeError, OSError):
            raise FtmError(
                "cache_corrupt", "Recorded response failed integrity checks"
            ) from None

    def write(
        self,
        url: str,
        status: int,
        body: bytes,
        *,
        evidence_kind: str,
        license: str,
        retrieved_at: str | None = None,
    ) -> CachedResponse:
        if len(body) > MAX_BODY:
            raise FtmError("response_too_large", "Response exceeds cache limit")
        url = checked_url(url)
        provenance = Provenance(
            source_url=url,
            retrieved_at=retrieved_at or utc_now(),
            sha256=hashlib.sha256(body).hexdigest(),
            license=license,
            evidence_kind=evidence_kind,
        )
        record = {
            "schema": "ftm-response-v1",
            "url": url,
            "status": status,
            "body_base64": base64.b64encode(body).decode(),
            "provenance": provenance.to_dict(),
        }
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.path(url)
        temporary = target.with_suffix(f".{uuid4().hex}.tmp")
        try:
            temporary.write_text(
                canonical(record) + "\n", encoding="utf-8", newline="\n"
            )
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return CachedResponse(url, status, body, provenance)


class JsonTransport:
    """GET only. Replay is the default and a cache miss cannot open a socket.

    Recording is restricted to the owner-approved no-key Bitcoin APIs. TRON
    clients are replay-only. An injected httpx client is for offline tests.
    Rate limiting is per transport instance; live recording uses one instance.
    """

    def __init__(
        self,
        cache: ReplayCache,
        budget: Budget,
        *,
        mode: Literal["replay", "record"] = "replay",
        allow_live: bool = False,
        client: httpx.Client | None = None,
        interval: float = 2.0,
        retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        if (
            mode not in {"replay", "record"}
            or type(retries) is not int
            or not 0 <= retries <= 3
            or not math.isfinite(interval)
            or interval < 0
        ):
            raise ValueError("invalid transport settings")
        if mode == "record" and not allow_live:
            raise FtmError(
                "live_not_authorized", "Recording requires explicit live authorization"
            )
        self.cache, self.budget, self.mode = cache, budget, mode
        self.client, self.interval, self.retries = client, interval, retries
        self.sleep, self.clock = sleep, clock
        self.last_request: float | None = None
        self.events: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def get(self, url: str) -> CachedResponse:
        with self._lock:
            return self._get(checked_url(url))

    @staticmethod
    def _successful(response: CachedResponse) -> CachedResponse:
        if response.status != 200:
            raise FtmError(
                "upstream_error",
                f"Recorded upstream status {response.status}",
                retryable=response.status == 429 or response.status >= 500,
            )
        return response

    def _get(self, url: str) -> CachedResponse:
        self.budget.charge()
        cached = self.cache.read(url)
        if cached is not None:
            self.events.append({"url": url, "cache_hit": True, "status": cached.status})
            return self._successful(cached)
        if self.mode == "replay":
            self.events.append({"url": url, "cache_hit": False, "error": "replay_miss"})
            raise FtmError("replay_miss", "Response absent from this replay snapshot")
        if not url.startswith(LIVE_BASES):
            raise FtmError(
                "live_not_authorized",
                "Only approved public Bitcoin API hosts may be recorded",
            )
        for attempt in range(self.retries + 1):
            if self.last_request is not None:
                self.sleep(max(0.0, self.interval - (self.clock() - self.last_request)))
            self.budget.charge(network=True)
            self.last_request = self.clock()
            client = self.client or httpx.Client(
                timeout=15.0, follow_redirects=False, trust_env=False
            )
            try:
                with client.stream(
                    "GET",
                    url,
                    headers={"User-Agent": "FollowTheMoneyResearch/0.1"},
                    follow_redirects=False,
                ) as raw:
                    body = bytearray()
                    for chunk in raw.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BODY:
                            raise FtmError(
                                "response_too_large", "Upstream response exceeds limit"
                            )
                    response = self.cache.write(
                        url,
                        raw.status_code,
                        bytes(body),
                        evidence_kind="public_recording",
                        license="Public blockchain facts; explorer terms apply",
                    )
                    self.events.append(
                        {
                            "url": url,
                            "cache_hit": False,
                            "status": raw.status_code,
                            "attempt": attempt + 1,
                            "sha256": response.provenance.sha256,
                        }
                    )
                    # Preserve every attempt separately, including transient failures.
                    attempts = self.cache.root / "attempts"
                    attempts.mkdir(exist_ok=True)
                    (attempts / f"{uuid4().hex}.json").write_bytes(
                        self.cache.path(url).read_bytes()
                    )
                    if (
                        raw.status_code not in {429, 500, 502, 503, 504}
                        or attempt == self.retries
                    ):
                        return self._successful(response)
                    delay = retry_delay(raw.headers.get("Retry-After"), attempt)
                    if delay > 60:
                        raise FtmError(
                            "rate_limited",
                            "Retry-After exceeds this bounded recording window",
                            retryable=True,
                        )
                    self.sleep(delay)
            except httpx.TransportError:
                self.events.append(
                    {
                        "url": url,
                        "cache_hit": False,
                        "error": "transport_error",
                        "attempt": attempt + 1,
                    }
                )
                if attempt == self.retries:
                    raise FtmError(
                        "upstream_unavailable",
                        "Explorer request failed",
                        retryable=True,
                    ) from None
                self.sleep(2.0**attempt)
            finally:
                if self.client is None:
                    client.close()
        raise AssertionError("unreachable")


def retry_delay(value: str | None, attempt: int) -> float:
    """Respect numeric or HTTP-date Retry-After; never shorten a server delay."""
    if value is None:
        return 2.0**attempt
    try:
        delay = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            delay = (date - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return 2.0**attempt
    return max(0.0, delay) if math.isfinite(delay) else 61.0
