"""Temporal graph data with explicit provenance and causal edge direction."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from follow_the_money.acquire import file_hash
from follow_the_money.contracts import FtmError, digest
from follow_the_money.features import LIVE_FEATURES


@dataclass(frozen=True)
class TemporalGraph:
    ids: tuple[str, ...]
    features: np.ndarray
    labels: np.ndarray
    times: np.ndarray
    edges: np.ndarray
    feature_names: tuple[str, ...]
    live_columns: tuple[int, ...]
    provenance: dict[str, Any]

    def validate(self) -> None:
        n = len(self.ids)
        if (
            n < 3
            or len(set(self.ids)) != n
            or self.features.shape != (n, len(self.feature_names))
            or self.labels.shape != (n,)
            or self.times.shape != (n,)
            or self.edges.ndim != 2
            or self.edges.shape[0] != 2
            or not np.isfinite(self.features).all()
            or not np.isfinite(self.times).all()
            or not set(np.unique(self.labels)) <= {-1, 0, 1}
            or not self.live_columns
            or len(set(self.live_columns)) != len(self.live_columns)
            or min(self.live_columns) < 0
            or max(self.live_columns) >= self.features.shape[1]
        ):
            raise FtmError(
                "invalid_dataset", "Invalid temporal graph dimensions or values"
            )
        if self.edges.size and (
            self.edges.min() < 0
            or self.edges.max() >= n
            or np.any(self.times[self.edges[0]] > self.times[self.edges[1]])
        ):
            raise FtmError("future_edge", "Graph edges must point from past to present")

    def masks(self, train_end: int, validation_end: int) -> tuple[np.ndarray, ...]:
        self.validate()
        if train_end >= validation_end:
            raise FtmError("invalid_split", "Temporal boundaries must increase")
        known = self.labels >= 0
        masks = (
            known & (self.times <= train_end),
            known & (self.times > train_end) & (self.times <= validation_end),
            known & (self.times > validation_end),
        )
        if any(m.sum() == 0 for m in masks):
            raise FtmError("invalid_split", "Each temporal split needs labelled nodes")
        return masks

    def visible_edges(self, cutoff: int) -> np.ndarray:
        return self.edges[
            :,
            (self.times[self.edges[0]] <= cutoff)
            & (self.times[self.edges[1]] <= cutoff),
        ]


def synthetic_graph(seed: int = 47, nodes: int = 600) -> TemporalGraph:
    """Fictional endpoint-priority labels, never illicit/licit address claims.

    The sixth feature is a synthetic privileged signal deliberately unavailable
    during live tracing. It measures the danger of deploying offline features.
    """
    if nodes < 60:
        raise ValueError("at least 60 nodes required")
    rng = np.random.default_rng(seed)
    times = np.arange(nodes) * 30 // nodes + 1
    x = rng.normal(0, 1, (nodes, 6)).astype(np.float32)
    edges = [(int(rng.integers(0, i)), i) for i in range(1, nodes) for _ in range(2)]
    edge_array = np.array(edges, dtype=np.int64).T
    neighbour = np.zeros(nodes)
    for a, b in edges:
        neighbour[b] += x[a, 0] / 2
    logit = (
        0.8 * x[:, 0]
        - 0.6 * x[:, 1]
        + 1.6 * x[:, 5]
        + 0.5 * neighbour
        + rng.normal(0, 0.6, nodes)
    )
    y = (logit > 0).astype(np.int64)
    graph = TemporalGraph(
        tuple(f"synthetic-node-{i}" for i in range(nodes)),
        x,
        y,
        times,
        edge_array,
        LIVE_FEATURES + ("synthetic_privileged_signal",),
        tuple(range(5)),
        {
            "evidence_kind": "synthetic",
            "generator": "ftm-temporal-v1",
            "seed": seed,
            "license": "CC0-1.0",
            "chain": "synthetic",
            "target": "constructed_endpoint_priority",
            "sha256": digest(
                {
                    "seed": seed,
                    "nodes": nodes,
                    "features": x.tolist(),
                    "labels": y.tolist(),
                    "edges": edges,
                }
            ),
        },
    )
    graph.validate()
    return graph


def synthetic_change_examples(count: int = 90, *, observed_by: int | None = None):
    """Generate fictional UTXOs and derive weak labels from later co-spends."""
    from follow_the_money.contracts import BitcoinTx, Provenance, TxInput, TxOutput
    from follow_the_money.heuristics import weak_change_labels

    provenance = Provenance(
        source_url="https://example.invalid/ftm/synthetic-change-v1",
        retrieved_at="2026-10-26T00:00:00+00:00",
        sha256=digest({"generator": "synthetic-change-v1", "count": count}),
        license="CC0-1.0",
        evidence_kind="synthetic",
    )
    rng = np.random.default_rng(47)
    transactions = []
    for i in range(count):
        positive = int(rng.integers(2))
        sender = f"syn_sender_{i}"
        change = TxOutput(
            address=sender if rng.random() < 0.25 else f"syn_change_{i}",
            value=int(rng.integers(5, 45)) * 1000
            + (int(rng.integers(1, 1000)) if rng.random() < 0.6 else 0),
            script_type="v0_p2wpkh" if rng.random() < 0.7 else "p2pkh",
        )
        payment = TxOutput(
            address=f"syn_pay_{i}",
            value=int(rng.integers(5, 45)) * 1000
            + (int(rng.integers(1, 1000)) if rng.random() < 0.4 else 0),
            script_type="v0_p2wpkh" if rng.random() < 0.5 else "p2pkh",
        )
        outputs = (change, payment) if positive == 0 else (payment, change)
        original = BitcoinTx(
            txid=digest({"original": i}),
            inputs=(
                TxInput(
                    txid=digest({"funding": i}),
                    vout=0,
                    prevout=TxOutput(
                        address=sender, value=100000, script_type="v0_p2wpkh"
                    ),
                ),
            ),
            outputs=outputs,
            confirmed=True,
            timestamp=(i + 1) * 100,
            provenance=provenance,
        )
        later = BitcoinTx(
            txid=digest({"later": i}),
            inputs=(
                TxInput(txid=original.txid, vout=positive, prevout=change),
                TxInput(
                    txid=digest({"independent_funding": i}),
                    vout=0,
                    prevout=TxOutput(
                        address=sender, value=10000, script_type="v0_p2wpkh"
                    ),
                ),
            ),
            outputs=(
                TxOutput(
                    address=f"syn_later_{i}",
                    value=change.value + 9000,
                    script_type="v0_p2wpkh",
                ),
            ),
            confirmed=True,
            timestamp=original.timestamp + 10,
            provenance=provenance,
        )
        transactions.extend((original, later))
    return weak_change_labels(transactions, observed_by=observed_by)


def load_csv_graph(
    features_path: Path,
    edges_path: Path,
    *,
    schema: dict[str, Any],
    receipts: dict[str, dict[str, Any]],
) -> TemporalGraph:
    """Import explicitly mapped Elliptic++-style CSVs after operator licence review.

    No guessed columns or network downloads. Receipt keys are 'features'/'edges';
    schema supplies id/time/label/features/live_features/source/target/label_map.
    Unknown labels map to -1, never to a negative training example.
    """
    for name, path in (("features", features_path), ("edges", edges_path)):
        receipt = receipts[name]
        if (
            not receipt.get("license_approved")
            or not receipt.get("license")
            or file_hash(path) != receipt["sha256"]
        ):
            raise FtmError(
                "unapproved_dataset",
                "Verified licence and matching source hash required",
            )
    with features_path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    ids = tuple(r[schema["id"]] for r in rows)
    index = {node: i for i, node in enumerate(ids)}
    names = tuple(schema["features"])
    with edges_path.open(newline="", encoding="utf-8-sig") as stream:
        pairs = [
            (index[r[schema["source"]]], index[r[schema["target"]]])
            for r in csv.DictReader(stream)
        ]
    graph = TemporalGraph(
        ids,
        np.array([[float(r[f]) for f in names] for r in rows], dtype=np.float32),
        np.array(
            [schema["label_map"].get(r[schema["label"]], -1) for r in rows],
            dtype=np.int64,
        ),
        np.array([int(r[schema["time"]]) for r in rows]),
        np.array(pairs, dtype=np.int64).reshape(-1, 2).T,
        names,
        tuple(names.index(f) for f in schema["live_features"]),
        {"evidence_kind": "public_dataset", "receipts": receipts, "schema": schema},
    )
    graph.validate()
    return graph
