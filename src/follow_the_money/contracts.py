"""Strict evidence contracts: integer asset units and explicit provenance."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Chain = Literal["bitcoin", "tron"]
EvidenceKind = Literal[
    "synthetic", "public_recording", "public_dataset", "court_document"
]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Address = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")]
NOTICE = (
    "Research leads for human review only. Addresses, labels, clusters and scores "
    "do not establish identity, ownership or wrongdoing. Requests remain drafts; "
    "nothing is sent to an exchange or authority."
)
USDT_TRON = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"  # pragma: allowlist secret -- public USDT TRON contract identifier


def canonical(value: object) -> str:
    """Stable finite JSON for evidence digests; hashes are not authentication."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def strict_json(raw: bytes | str) -> Any:
    """Reject duplicate keys and non-finite numbers from untrusted sources."""

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("non-finite JSON value")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


class FtmError(Exception):
    """Stable domain failure, never an empty successful trace."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


class Record(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, allow_inf_nan=False
    )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class Provenance(Record):
    source_url: str = Field(min_length=1, max_length=2000)
    retrieved_at: str
    sha256: Hash
    license: str = Field(min_length=1, max_length=500)
    evidence_kind: EvidenceKind

    @field_validator("retrieved_at")
    @classmethod
    def aware_time(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("retrieval time must include a timezone")
        return value


class TxOutput(Record):
    address: Address | None
    value: int = Field(ge=0, le=2_100_000_000_000_000)
    script_type: str = Field(min_length=1, max_length=100)


class TxInput(Record):
    txid: Hash | None
    vout: int | None = Field(ge=0)
    prevout: TxOutput | None
    coinbase: bool = False


class BitcoinTx(Record):
    txid: Hash
    inputs: tuple[TxInput, ...]
    outputs: tuple[TxOutput, ...]
    confirmed: bool
    timestamp: int | None = Field(default=None, ge=0)
    provenance: Provenance


class Outspend(Record):
    provenance: Provenance
    spent: bool
    txid: Hash | None = None
    vin: int | None = Field(default=None, ge=0)


class Transfer(Record):
    txid: Hash
    sender: Address
    recipient: Address
    contract: Address
    amount: int = Field(ge=0, le=10**78)
    decimals: int = Field(ge=0, le=36)
    timestamp: int = Field(ge=0, description="Unix milliseconds")
    event_index: int | None = Field(default=None, ge=0)
    provenance: Provenance


class FreezeEvent(Record):
    txid: Hash
    address: Address
    contract: Address
    action: Literal["AddedBlackList", "RemovedBlackList", "DestroyedBlackFunds"]
    timestamp: int = Field(ge=0)
    provenance: Provenance


class Label(Record):
    chain: Chain
    address: Address
    label: str = Field(min_length=1, max_length=500)
    category: Literal["exchange", "mixer", "sanctioned", "service", "other"]
    source_ref: str = Field(min_length=1, max_length=2000)
    owner_name: str | None = Field(default=None, min_length=1, max_length=200)
    provenance: Provenance


class Seed(Record):
    chain: Chain = "bitcoin"
    address: Address
    family: str = Field(min_length=1, max_length=200)
    provenance: Provenance


class Page(Record):
    """An explicitly partial page; no empty page implies a whole-chain search."""

    transactions: tuple[BitcoinTx, ...] = ()
    transfers: tuple[Transfer, ...] = ()
    next_cursor: str | None = None
    complete: bool
    provenance: Provenance


class FreezePage(Record):
    events: tuple[FreezeEvent, ...] = ()
    next_cursor: str | None = None
    complete: bool
    provenance: Provenance
