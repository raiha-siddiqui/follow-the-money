"""Ransomwhere seed loading with explicit crowdsourced-source provenance."""

from __future__ import annotations

from follow_the_money.contracts import FtmError, Provenance, Seed, strict_json


def load_ransomwhere(raw: bytes, provenance: Provenance) -> tuple[Seed, ...]:
    """Load v1.1.0 address rows, preserving multiple reported family labels."""
    data = strict_json(raw)
    if isinstance(data, dict):
        data = data.get("result", data.get("data"))
    if not isinstance(data, list):
        raise FtmError("invalid_source", "Expected Ransomwhere address rows")
    seeds = {}
    for row in data:
        if not isinstance(row, dict):
            raise FtmError("invalid_source", "Malformed Ransomwhere row")
        if str(row.get("blockchain", "bitcoin")).lower() not in {"bitcoin", "btc"}:
            continue
        address = row.get("address")
        family = row.get("family") or "unattributed in source"
        seed = Seed(address=address, family=family, provenance=provenance)
        seeds[(seed.address, seed.family)] = seed
    return tuple(seeds[key] for key in sorted(seeds))
