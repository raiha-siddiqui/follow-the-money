"""Reproducible offline experiments; metrics always identify their data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any, Sequence

import numpy as np
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)
from xgboost import XGBClassifier

from follow_the_money.contracts import FtmError
from follow_the_money.datasets import (
    TemporalGraph,
    synthetic_change_examples,
    synthetic_graph,
)
from follow_the_money.heuristics import WeakChangeExample
from follow_the_money.models import DistributionGuard, PriorityGNN


def metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float | None]:
    both = len(np.unique(y)) == 2
    return {
        "average_precision": float(average_precision_score(y, p)) if both else None,
        "roc_auc": float(roc_auc_score(y, p)) if both else None,
        "brier": float(brier_score_loss(y, p)),
        "accuracy": float(accuracy_score(y, p >= 0.5)),
    }


def train_one(
    graph: TemporalGraph,
    *,
    kind: str,
    live: bool,
    train_end: int = 18,
    validation_end: int = 24,
    epochs: int = 40,
    seed: int = 47,
    output: Path | None = None,
) -> dict[str, Any]:
    """Fit scaler/model only on the training era; validation selects GNN epoch.

    Later nodes cannot send messages to earlier nodes. Test labels are touched
    only after model/epoch selection. Unknown labels remain unlabelled context.
    """
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.use_deterministic_algorithms(True)
    train, valid, test = graph.masks(train_end, validation_end)
    columns = graph.live_columns if live else tuple(range(graph.features.shape[1]))
    x = graph.features[:, columns]
    guard = DistributionGuard.fit(
        x[train],
        chain=graph.provenance.get("chain", "bitcoin"),
        feature_names=[graph.feature_names[i] for i in columns],
    )
    standardized = ((x - guard.mean) / guard.scale).astype(np.float32)
    start = time.perf_counter()
    best_epoch = None
    if kind == "xgboost":
        model = XGBClassifier(
            n_estimators=60,
            max_depth=3,
            learning_rate=0.08,
            subsample=1,
            colsample_bytree=1,
            random_state=seed,
            n_jobs=1,
            tree_method="hist",
        )
        model.fit(standardized[train], graph.labels[train])
        probability = model.predict_proba(standardized)[:, 1]
        if output:
            output.mkdir(parents=True, exist_ok=True)
            model.save_model(output / f"{kind}-{'live' if live else 'full'}.json")
    else:
        model = PriorityGNN(len(columns), kind)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.02, weight_decay=1e-4)
        inputs = torch.from_numpy(standardized)
        labels = torch.tensor(graph.labels, dtype=torch.float32)
        train_edges = torch.from_numpy(graph.visible_edges(train_end))
        validation_edges = torch.from_numpy(graph.visible_edges(validation_end))
        best_loss, best_state = float("inf"), None
        for epoch in range(epochs):
            model.train()
            optimizer.zero_grad()
            logits = model(inputs, train_edges)
            loss = torch.nn.functional.binary_cross_entropy_with_logits(
                logits[train], labels[train]
            )
            loss.backward()
            optimizer.step()
            model.eval()
            with torch.no_grad():
                val = float(
                    torch.nn.functional.binary_cross_entropy_with_logits(
                        model(inputs, validation_edges)[valid], labels[valid]
                    )
                )
            if val < best_loss:
                best_loss, best_epoch = val, epoch + 1
                best_state = {
                    k: v.detach().clone() for k, v in model.state_dict().items()
                }
        if best_state is None:
            raise FtmError("invalid_training", "Positive epoch count required")
        model.load_state_dict(best_state)
        model.eval()
        with torch.no_grad():
            probability = torch.sigmoid(
                model(inputs, torch.from_numpy(graph.edges))
            ).numpy()
        if output:
            output.mkdir(parents=True, exist_ok=True)
            torch.save(
                model.state_dict(), output / f"{kind}-{'live' if live else 'full'}.pt"
            )
    report = {
        "model": kind,
        "features": "live" if live else "full",
        "columns": [graph.feature_names[i] for i in columns],
        "seed": seed,
        "best_epoch": best_epoch,
        "train_end": train_end,
        "validation_end": validation_end,
        "counts": {
            k: int(m.sum())
            for k, m in zip(("train", "validation", "test"), (train, valid, test))
        },
        "validation": metrics(graph.labels[valid], probability[valid]),
        "test": metrics(graph.labels[test], probability[test]),
        "fit_seconds": time.perf_counter() - start,
        "provenance": graph.provenance,
        "scaler": {"mean": guard.mean.tolist(), "scale": guard.scale.tolist()},
        "ood_threshold": guard.threshold,
        "calibrated": False,
    }
    if output:
        (output / f"{kind}-{'live' if live else 'full'}.metadata.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
    return report


def train_change(
    examples: Sequence[WeakChangeExample], *, train_end: int, test_start: int
) -> dict[str, Any]:
    """Train only on labels observed by train_end; group all outputs by tx time."""
    if train_end >= test_start:
        raise FtmError("invalid_split", "Change split must have increasing cutoffs")
    train = [
        r
        for r in examples
        if r.timestamp <= train_end and r.label_observed_at <= train_end
    ]
    test = [r for r in examples if r.timestamp >= test_start]
    if (
        len({r.label for r in train}) != 2
        or not test
        or {r.txid for r in train} & {r.txid for r in test}
    ):
        raise FtmError(
            "insufficient_labels",
            "Need disjoint temporal weak-label training and test sets",
        )
    model = LogisticRegression(random_state=47).fit(
        [r.features for r in train], [r.label for r in train]
    )
    p = model.predict_proba([r.features for r in test])[:, 1]
    return {
        "model": model,
        "train_count": len(train),
        "test_count": len(test),
        "test": metrics(np.array([r.label for r in test]), p),
        "label_kind": "weak_cospend",
        "calibrated": False,
        "limitation": "Paired negatives and common-input ownership are assumptions.",
    }


def experiment(
    *, output: Path, seed: int = 47, nodes: int = 600, epochs: int = 40
) -> dict[str, Any]:
    graph = synthetic_graph(seed, nodes)
    runs = [
        train_one(graph, kind=kind, live=live, epochs=epochs, output=output)
        for kind in ("sage", "gat", "xgboost")
        for live in (False, True)
    ]
    differences = {
        kind: runs[i]["test"]["average_precision"]
        - runs[i + 1]["test"]["average_precision"]
        for i, kind in zip((0, 2, 4), ("sage", "gat", "xgboost"))
    }
    examples = list(synthetic_change_examples(observed_by=6000)) + [
        r for r in synthetic_change_examples() if r.timestamp >= 7000
    ]
    change = train_change(examples, train_end=6000, test_start=7000)
    change_model = change.pop("model")
    change["coefficients"] = change_model.coef_.tolist()
    change["intercept"] = change_model.intercept_.tolist()
    report = {
        "schema": "ftm-training-v1",
        "evidence_kind": "synthetic",
        "runs": runs,
        "full_minus_live_test_ap": differences,
        "change_classifier": {"evidence_kind": "synthetic", **change},
        "notice": "Single seed (47), no confidence intervals. GAT is near the test positive base rate (0.5167); its full-to-live drop is not meaningful evidence of robustness. Change signals vary and weak paired negatives remain assumptions. Pipeline verification only. Synthetic metrics do not estimate real-world tracing or illicit-address performance.",
        "elliptic_plus_plus": "BLOCKED: dataset licence not verified",
        "elliptic2": "BLOCKED: 25,805,701,153 bytes exceeds limit",
    }
    (output / "results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("data/follow_the_money/models")
    )
    parser.add_argument("--epochs", type=int, default=40)
    args = parser.parse_args()
    report = experiment(output=args.output, epochs=args.epochs)
    print(
        json.dumps(
            {
                "runs": len(report["runs"]),
                "evidence_kind": report["evidence_kind"],
                "full_minus_live_test_ap": report["full_minus_live_test_ap"],
            }
        )
    )


if __name__ == "__main__":
    main()
