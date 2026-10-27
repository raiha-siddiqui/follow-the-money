"""Public case/approval contracts shared by CLI, API and reviewer interfaces."""

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from follow_the_money.contracts import Address, Chain, Hash, Record, digest


class TraceRequest(Record):
    chain: Chain
    seed: Address
    seed_txid: Hash | None = None
    seed_vout: int | None = Field(default=None, ge=0)
    goal: Literal["find_service_endpoint", "bounded_exploration"] = (
        "find_service_endpoint"
    )
    max_calls: int = Field(default=12, ge=1, le=100)
    max_hops: int = Field(default=5, ge=0, le=12)
    cluster_cap: int = Field(default=100, ge=2, le=500)
    strategy: Literal["priority", "bfs"] = "priority"
    draft_request: bool = False
    check_freeze_signals: bool = False
    request_id: str

    @field_validator("request_id")
    @classmethod
    def uuid_text(cls, value: str) -> str:
        if str(UUID(value)) != value:
            raise ValueError("request ID must be canonical UUID")
        return value

    @model_validator(mode="after")
    def seed_outpoint(self):
        if (
            (self.seed_txid is None) != (self.seed_vout is None)
            or self.chain != "bitcoin"
            and self.seed_txid is not None
        ):
            raise ValueError("A Bitcoin seed outpoint requires both txid and vout")
        return self


class Approval(Record):
    request_id: str
    evidence_sha256: Hash
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=1000)

    @field_validator("request_id")
    @classmethod
    def uuid_text(cls, value: str) -> str:
        return TraceRequest.uuid_text(value)


class Claim(Record):
    claim_id: Hash
    kind: str = Field(max_length=50)
    chain: Chain
    txids: tuple[Hash, ...] = Field(min_length=1, max_length=100)
    addresses: tuple[Address, ...] = Field(min_length=1, max_length=500)
    amount: int | None = Field(default=None, ge=0)
    output_index: int | None = Field(default=None, ge=0)
    confidence: float = Field(default=0.5, ge=0, le=1)
    label_sha256: Hash | None = None
    text: str = Field(max_length=2000)


def proposal_payload(state: dict) -> dict:
    """Every reviewed component is bound into the approval digest."""
    keys = (
        "request",
        "claims",
        "critic",
        "evidence",
        "labels",
        "trace",
        "clusters",
        "endpoints",
        "budget",
        "stop_reason",
        "resolutions",
        "memory_context",
        "signals",
    )
    return {key: state[key] for key in keys}


def claim_text(
    kind: str, chain: str, addresses: tuple[str, ...], amount: int | None = None
) -> str:
    """Render only bounded structured fields; source/LLM prose cannot become a claim."""
    if kind == "transfer":
        return f"Possible {chain} flow from {addresses[0]} to {addresses[1]}: {amount} base units. Input-to-output attribution is uncertain."
    if kind == "common_input_hypothesis":
        return (
            "Common-input hypothesis for "
            + ", ".join(addresses)
            + "; collaborative spending can invalidate it."
        )
    if kind == "change_hypothesis":
        return (
            "Possible change output to "
            + addresses[0]
            + "; the estimate is uncalibrated."
        )
    if kind == "published_label":
        return (
            "A published source labels "
            + addresses[0]
            + "; this is not proof of current control or ownership."
        )
    if kind == "peel_hypothesis":
        return "Connected transactions have a peel-like shape; this does not establish laundering."
    if kind == "freeze_signal":
        return (
            "A recorded USDT blacklist event concerns "
            + addresses[0]
            + "; this is a historical signal, not current status or wrongdoing."
        )
    return "Unsupported claim type."


def make_claim(
    kind: str, chain: str, txids: tuple[str, ...], addresses: tuple[str, ...], **kwargs
) -> dict:
    fields = dict(
        kind=kind,
        chain=chain,
        txids=txids,
        addresses=addresses,
        text=claim_text(kind, chain, addresses, kwargs.get("amount")),
        **kwargs,
    )
    claim = Claim(claim_id="0" * 64, **fields).to_dict()
    claim["claim_id"] = digest({k: v for k, v in claim.items() if k != "claim_id"})
    return claim
