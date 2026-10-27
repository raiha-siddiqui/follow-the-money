"""Point-in-time features: no future spends, source labels or identities."""

from __future__ import annotations

import math
from typing import Iterable

from follow_the_money.contracts import BitcoinTx, Transfer

LIVE_FEATURES = (
    "log_out_count",
    "log_in_count",
    "log_out_units",
    "log_counterparties",
    "log_age_days",
)


def live_features(
    address: str, records: Iterable[BitcoinTx | Transfer], *, as_of: int
) -> tuple[float, ...]:
    """Compute chain-local features from confirmed observations through a cutoff.

    Bitcoin timestamps are seconds; indexed TRC-20 timestamps are milliseconds.
    Raw token units differ by chain, so models must declare their training chain.
    """
    outgoing = incoming = units = 0
    others: set[str] = set()
    earliest = as_of
    for record in records:
        timestamp = record.timestamp
        if isinstance(record, Transfer):
            timestamp //= 1000
            if timestamp > as_of or address not in {record.sender, record.recipient}:
                continue
            outgoing += record.sender == address
            incoming += record.recipient == address
            units += record.amount if record.sender == address else 0
            others.update({record.sender, record.recipient} - {address})
        else:
            if not record.confirmed or timestamp is None or timestamp > as_of:
                continue
            senders = {
                i.prevout.address
                for i in record.inputs
                if i.prevout and i.prevout.address
            }
            recipients = {o.address for o in record.outputs if o.address}
            if address not in senders | recipients:
                continue
            outgoing += address in senders
            incoming += address in recipients
            units += (
                sum(o.value for o in record.outputs if o.address != address)
                if address in senders
                else 0
            )
            others.update((senders | recipients) - {address})
        earliest = min(earliest, timestamp)
    return tuple(
        math.log1p(x)
        for x in (outgoing, incoming, units, len(others), (as_of - earliest) / 86400)
    )


def evidence_records(evidence: dict, chain: str) -> list[BitcoinTx | Transfer]:
    """Decode unique structured transactions, omitting separate contract events."""
    import json

    records = {}
    for rows in evidence.values():
        for row in rows:
            if row["chain"] != chain or "action" in row["value"]:
                continue
            cls = BitcoinTx if chain == "bitcoin" else Transfer
            record = cls.model_validate_json(json.dumps(row["value"]))
            key = (
                (record.txid,)
                if chain == "bitcoin"
                else (
                    record.txid,
                    record.sender,
                    record.recipient,
                    record.amount,
                    record.event_index,
                )
            )
            records[key] = record
    return list(records.values())
