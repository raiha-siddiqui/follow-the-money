"""Published attribution adapters and a provenance-preserving SQLite label store."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Iterable

import yaml

from follow_the_money.contracts import (
    FtmError,
    Label,
    Provenance,
    canonical,
    strict_json,
)


def parse_tagpack(raw: bytes, provenance: Provenance) -> tuple[Label, ...]:
    """Inherit pack-level fields; never infer private identities from addresses."""
    data = yaml.safe_load(raw)
    if not isinstance(data, dict) or not isinstance(data.get("tags"), list):
        raise FtmError("invalid_source", "Expected a GraphSense tag pack")
    result = []
    for tag in data["tags"]:
        merged = {**data, **tag}
        chain = {"BTC": "bitcoin", "TRX": "tron", "TRON": "tron"}.get(
            merged.get("currency")
        )
        if chain is None:
            continue
        category = merged.get("category", "other")
        if category not in {"exchange", "mixer", "sanctioned", "service"}:
            category = "other"
        result.append(
            Label(
                chain=chain,
                address=merged["address"],
                label=merged["label"],
                category=category,
                source_ref=merged["source"],
                provenance=provenance,
            )
        )
    return tuple(result)


def parse_ofac(raw: bytes, provenance: Provenance, *, chain: str) -> tuple[Label, ...]:
    """A snapshot assertion from the published list, never current legal advice."""
    addresses = (
        strict_json(raw) if raw.lstrip().startswith(b"[") else raw.decode().splitlines()
    )
    if not isinstance(addresses, list):
        raise FtmError("invalid_source", "Expected an OFAC address list")
    return tuple(
        Label(
            chain=chain,
            address=a.strip(),
            label="Listed in published OFAC address snapshot",
            category="sanctioned",
            source_ref=provenance.source_url,
            provenance=provenance,
        )
        for a in addresses
        if isinstance(a, str) and a.strip()
    )


def parse_opensanctions(raw: bytes, provenance: Provenance) -> tuple[Label, ...]:
    """Wallet records only. No bulk acquisition or owner inference occurs here."""
    result = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        record = strict_json(line)
        if record.get("schema") != "CryptoWallet":
            continue
        props = record["properties"]
        currencies = props.get("currency", [])
        chain = {"BTC": "bitcoin", "XBT": "bitcoin", "TRX": "tron", "TRON": "tron"}.get(
            currencies[0] if len(currencies) == 1 else None
        )
        if chain is None:
            continue
        for address in props.get("publicKey", []):
            # A crypto wallet in OpenSanctions is not necessarily sanctioned.
            result.append(
                Label(
                    chain=chain,
                    address=address,
                    label=record.get("caption", "Published wallet record"),
                    category="other",
                    source_ref=props.get("sourceUrl", [provenance.source_url])[0],
                    provenance=provenance,
                )
            )
    return tuple(result)


class LabelStore:
    """Conflicting published labels remain separate, with their snapshot dates."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS labels (chain TEXT, address TEXT, source_sha TEXT, payload TEXT, PRIMARY KEY(chain,address,source_sha,payload))"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS lookup_labels ON labels(chain,address)"
            )

    def add(self, labels: Iterable[Label]) -> int:
        # Validate everything before the transaction; partial imports roll back.
        values = [
            (x.chain, x.address, x.provenance.sha256, canonical(x.to_dict()))
            for x in labels
        ]
        with (
            closing(
                sqlite3.connect(self.path.absolute().as_uri() + "?mode=rw", uri=True)
            ) as db,
            db,
        ):
            before = db.total_changes
            db.executemany("INSERT OR IGNORE INTO labels VALUES (?,?,?,?)", values)
            return db.total_changes - before

    def lookup_labels(self, chain: str, address: str) -> tuple[Label, ...]:
        with closing(
            sqlite3.connect(self.path.absolute().as_uri() + "?mode=ro", uri=True)
        ) as db:
            rows = db.execute(
                "SELECT payload FROM labels WHERE chain=? AND address=? ORDER BY source_sha,payload",
                (chain, address),
            )
            return tuple(Label.model_validate_json(row[0]) for row in rows)
