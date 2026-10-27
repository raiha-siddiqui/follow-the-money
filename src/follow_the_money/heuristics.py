"""Conservative Bitcoin hypotheses and separate account-model signals.

All confidence/probability values here are uncalibrated estimates. A shared
input, guessed change output or freeze event never establishes ownership.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import math
from typing import Any, Iterable, Sequence

from follow_the_money.contracts import (
    BitcoinTx,
    FreezeEvent,
    FtmError,
    Transfer,
    USDT_TRON,
)


@dataclass(frozen=True)
class CoinJoinSignal:
    suspected: bool
    reason: str
    alternative: str = "An exchange batch payout can also have equal outputs."


def detect_coinjoin(tx: BitcoinTx) -> CoinJoinSignal:
    """Repeated equal-value outputs plus distinct inputs are a conservative stop."""
    if not isinstance(tx, BitcoinTx):
        raise FtmError("wrong_chain", "CoinJoin detection applies only to Bitcoin")
    addresses = {
        i.prevout.address for i in tx.inputs if i.prevout and i.prevout.address
    }
    counts = Counter(o.value for o in tx.outputs if o.value > 0)
    suspected = len(addresses) >= 3 and max(counts.values(), default=0) >= 3
    return CoinJoinSignal(
        suspected, "equal_output_multi_input" if suspected else "pattern_not_detected"
    )


@dataclass(frozen=True)
class ChangeEstimate:
    probabilities: tuple[float, ...]
    none_probability: float
    reason: str
    calibrated: bool = False

    @property
    def candidate(self) -> int | None:
        if not self.probabilities:
            return None
        index = max(range(len(self.probabilities)), key=lambda i: self.probabilities[i])
        return index if self.probabilities[index] > self.none_probability else None


def change_features(tx: BitcoinTx, index: int) -> tuple[float, ...]:
    """Live-recomputable output features; no later spending information is used."""
    output = tx.outputs[index]
    scripts = {i.prevout.script_type for i in tx.inputs if i.prevout}
    inputs = {i.prevout.address for i in tx.inputs if i.prevout and i.prevout.address}
    total = sum(o.value for o in tx.outputs)
    return (
        float(output.script_type in scripts),
        float(output.value % 1000 != 0),
        output.value / max(1, total),
        float(output.address in inputs),
    )


def detect_change(
    tx: BitcoinTx, *, seen_addresses: set[str] | None = None
) -> ChangeEstimate:
    """A distribution including 'no identifiable change', not a calibrated fact."""
    if not isinstance(tx, BitcoinTx):
        raise FtmError("wrong_chain", "Account-model transfers do not have change")
    if (
        len(tx.outputs) != 2
        or any(i.coinbase for i in tx.inputs)
        or detect_coinjoin(tx).suspected
    ):
        return ChangeEstimate(
            tuple(0.0 for _ in tx.outputs), 1.0, "abstain_ambiguous_structure"
        )
    reused = [i for i in range(2) if change_features(tx, i)[3]]
    if len(reused) == 1:
        # Deterministic candidate selection, not a calibrated ownership probability.
        return ChangeEstimate(
            tuple(0.8 if i == reused[0] else 0.0 for i in range(2)),
            0.2,
            "unique_input_address_reuse",
        )
    if len(reused) == 2:
        return ChangeEstimate((0.0, 0.0), 1.0, "ambiguous_input_address_reuse")
    weights = []
    for index, output in enumerate(tx.outputs):
        same_script, nonround, fraction, reused = change_features(tx, index)
        fresh = float(
            seen_addresses is not None
            and output.address is not None
            and output.address not in seen_addresses
        )
        logit = (
            -1.0 + 1.4 * same_script + 0.8 * nonround + 0.3 * fraction + fresh + reused
        )
        weights.append(math.exp(logit) if output.address else 0.0)
    null_weight = math.exp(1.0)
    total = null_weight + sum(weights)
    return ChangeEstimate(
        tuple(w / total for w in weights),
        null_weight / total,
        "script_roundness_fraction_freshness_heuristic",
    )


@dataclass(frozen=True)
class ClusterDecision:
    members: tuple[str, ...]
    txids: tuple[str, ...]
    stop: bool
    reason: str
    confidence: float = 0.6


@dataclass
class ClusterBook:
    """Capped common-input hypotheses; service membership propagates without merging.

    The cap limits wallet hypotheses, not evidence retention. Oversized joins
    mark every involved component as a service stop and never create a bridge.
    """

    cap: int = 500
    counterparty_cap: int = 500
    groups: dict[str, set[str]] = field(default_factory=dict)
    index: dict[str, str] = field(default_factory=dict)
    proofs: dict[str, set[str]] = field(default_factory=dict)
    service: set[str] = field(default_factory=set)
    counterparties: dict[str, set[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            type(self.cap) is not int
            or not 2 <= self.cap <= 10000
            or type(self.counterparty_cap) is not int
            or self.counterparty_cap < 1
        ):
            raise ValueError("invalid cluster limits")

    def members(self, address: str) -> set[str]:
        return set(self.groups.get(self.index.get(address, ""), {address}))

    def mark_service(self, address: str) -> None:
        self.service.update(self.members(address))

    def linkable(self, address: str) -> bool:
        return not bool(self.members(address) & self.service)

    def cluster_common_input(self, tx: BitcoinTx) -> ClusterDecision:
        if not isinstance(tx, BitcoinTx):
            raise FtmError(
                "wrong_chain", "Common-input clustering applies only to Bitcoin"
            )
        addresses = sorted(
            {i.prevout.address for i in tx.inputs if i.prevout and i.prevout.address}
        )
        if detect_coinjoin(tx).suspected:
            return ClusterDecision((), (tx.txid,), True, "coinjoin_stop", 0.0)
        outputs = {o.address for o in tx.outputs if o.address}
        for address in addresses:
            counterparties = self.counterparties.setdefault(address, set())
            counterparties.update(outputs - self.members(address))
            if len(counterparties) > self.counterparty_cap:
                self.mark_service(address)
        combined: set[str] = set()
        proofs = {tx.txid}
        for address in addresses:
            combined.update(self.members(address))
            proofs.update(self.proofs.get(self.index.get(address, ""), ()))
        if len(combined) > self.cap or combined & self.service:
            self.service.update(combined)
            return ClusterDecision(
                tuple(sorted(combined)),
                tuple(sorted(proofs)),
                True,
                "service_or_cluster_cap",
                0.0,
            )
        if len(addresses) < 2:
            return ClusterDecision(
                tuple(addresses), (tx.txid,), False, "insufficient_common_inputs", 0.0
            )
        root = min(combined)
        old_roots = {self.index[a] for a in combined if a in self.index}
        for old in old_roots:
            self.groups.pop(old, None)
            self.proofs.pop(old, None)
        self.groups[root], self.proofs[root] = combined, proofs
        self.index.update({a: root for a in combined})
        return ClusterDecision(
            tuple(sorted(combined)),
            tuple(sorted(proofs)),
            False,
            "common_input_hypothesis",
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "cap": self.cap,
            "counterparty_cap": self.counterparty_cap,
            "groups": [
                {"members": sorted(values), "txids": sorted(self.proofs[root])}
                for root, values in sorted(self.groups.items())
            ],
            "service": sorted(self.service),
            "counterparties": {
                a: sorted(v) for a, v in sorted(self.counterparties.items())
            },
        }

    @classmethod
    def restore(cls, value: dict[str, Any]) -> ClusterBook:
        book = cls(value["cap"], value["counterparty_cap"])
        for group in value["groups"]:
            members = set(group["members"])
            if not members or len(members) > book.cap or members & book.index.keys():
                raise FtmError("invalid_state", "Malformed cluster snapshot")
            root = min(members)
            book.groups[root] = members
            book.proofs[root] = set(group["txids"])
            book.index.update({a: root for a in members})
        book.service = set(value["service"])
        book.counterparties = {a: set(v) for a, v in value["counterparties"].items()}
        return book


@dataclass(frozen=True)
class PeelSignal:
    detected: bool
    txids: tuple[str, ...]
    reason: str


def detect_peel_chain(
    transactions: Sequence[BitcoinTx], *, min_length: int = 3
) -> PeelSignal:
    """Require real outpoint continuity, never just similarly sized amounts."""
    if type(min_length) is not int or min_length < 2:
        raise ValueError("peel chains require at least two transactions")
    if len(transactions) < min_length:
        return PeelSignal(False, (), "too_short")
    for tx in transactions:
        if len(tx.inputs) != 1 or len(tx.outputs) != 2 or tx.inputs[0].coinbase:
            return PeelSignal(False, (), "not_single_input_two_output")
    for earlier, later in zip(transactions, transactions[1:]):
        index = max(range(2), key=lambda i: earlier.outputs[i].value)
        carried = earlier.outputs[index]
        spend = later.inputs[0]
        if (
            carried.value < 0.6 * sum(o.value for o in earlier.outputs)
            or (spend.txid, spend.vout) != (earlier.txid, index)
            or spend.prevout != carried
            or earlier.timestamp is not None
            and later.timestamp is not None
            and later.timestamp < earlier.timestamp
        ):
            return PeelSignal(False, (), "outpoint_or_value_continuity_failed")
    return PeelSignal(
        True,
        tuple(t.txid for t in transactions),
        "peel_shape_not_laundering_attribution",
    )


@dataclass(frozen=True)
class WeakChangeExample:
    features: tuple[float, ...]
    label: int
    txid: str
    timestamp: int
    label_observed_at: int
    evidence_txid: str
    limitation: str = (
        "Weak co-spend label; the paired output negative is an assumption."
    )


def weak_change_labels(
    transactions: Sequence[BitcoinTx],
    *,
    observed_by: int | None = None,
) -> tuple[WeakChangeExample, ...]:
    """Later co-spend gives weak positives; label observation time prevents leakage."""
    transactions = [
        tx
        for tx in transactions
        if tx.confirmed
        and tx.timestamp is not None
        and (observed_by is None or tx.timestamp <= observed_by)
    ]
    spends: dict[tuple[str, int], list[BitcoinTx]] = {}
    for tx in transactions:
        if detect_coinjoin(tx).suspected:
            continue
        for item in tx.inputs:
            if item.txid is not None and item.vout is not None:
                spends.setdefault((item.txid, item.vout), []).append(tx)
    examples = []
    for tx in transactions:
        if (
            len(tx.outputs) != 2
            or tx.timestamp is None
            or detect_coinjoin(tx).suspected
        ):
            continue
        senders = {
            i.prevout.address for i in tx.inputs if i.prevout and i.prevout.address
        }
        positives = {}
        for index in range(2):
            for later in sorted(
                spends.get((tx.txid, index), []), key=lambda t: (t.timestamp, t.txid)
            ):
                other_inputs = {
                    i.prevout.address
                    for i in later.inputs
                    if i.prevout and (i.txid, i.vout) != (tx.txid, index)
                }
                if (
                    later.timestamp is not None
                    and later.timestamp > tx.timestamp
                    and other_inputs & senders
                    and any(
                        (i.txid, i.vout) == (tx.txid, index)
                        and i.prevout == tx.outputs[index]
                        for i in later.inputs
                    )
                ):
                    positives[index] = later
                    break
        if len(positives) != 1:
            continue
        positive, later = next(iter(positives.items()))
        for index in range(2):
            examples.append(
                WeakChangeExample(
                    change_features(tx, index),
                    int(index == positive),
                    tx.txid,
                    tx.timestamp,
                    later.timestamp,
                    later.txid,
                )
            )
    return tuple(examples)


def account_signals(
    address: str, transfers: Iterable[Transfer], events: Iterable[FreezeEvent] = ()
) -> dict[str, Any]:
    """USDT account signals explicitly omit Bitcoin change and common-input logic."""
    selected = [
        t
        for t in transfers
        if t.contract == USDT_TRON and address in {t.sender, t.recipient}
    ]
    freezes = sorted(
        (e for e in events if e.contract == USDT_TRON and e.address == address),
        key=lambda e: (e.timestamp, e.txid),
    )
    return {
        "chain": "tron",
        "address": address,
        "transfer_records": len(selected),
        "counterparties": sorted(
            {x for t in selected for x in (t.sender, t.recipient)} - {address}
        ),
        "change": None,
        "common_input_cluster": None,
        "freeze_signal": freezes[-1].action if freezes else None,
        "blacklisted_at_last_observation": _blacklist_state(freezes),
        "destroyed_funds_events": sum(
            e.action == "DestroyedBlackFunds" for e in freezes
        ),
        "freeze_txids": [e.txid for e in freezes],
        "notice": "A historical contract signal, not current freeze status, ownership or wrongdoing.",
    }


def _blacklist_state(events: Sequence[FreezeEvent]) -> bool | None:
    """Destruction does not remove an address from the blacklist; ties abstain."""
    changes = [e for e in events if e.action in {"AddedBlackList", "RemovedBlackList"}]
    if not changes:
        return None
    latest = max(e.timestamp for e in changes)
    actions = {e.action for e in changes if e.timestamp == latest}
    return actions == {"AddedBlackList"} if len(actions) == 1 else None


def seen_addresses_before(tx: BitcoinTx, evidence: dict) -> set[str]:
    """Addresses in confirmed evidence no later than tx time, excluding tx itself.

    This is freshness within the available recordings, not global chain novelty.
    """
    seen = set()
    if tx.timestamp is None:
        return seen
    for rows in evidence.values():
        for row in rows:
            if row["chain"] != "bitcoin":
                continue
            value = row["value"]
            if (
                value["txid"] == tx.txid
                or not value["confirmed"]
                or value["timestamp"] is None
                or value["timestamp"] > tx.timestamp
            ):
                continue
            seen.update(
                i["prevout"]["address"]
                for i in value["inputs"]
                if i["prevout"] and i["prevout"]["address"]
            )
            seen.update(o["address"] for o in value["outputs"] if o["address"])
    return seen
