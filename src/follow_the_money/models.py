"""Temporal GNNs, training-distribution checks and optional trace value model."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import torch
from torch import nn
from torch_geometric.nn import GATConv, SAGEConv

from follow_the_money.contracts import FtmError
from follow_the_money.scoring import DistributionGuard, score_address  # noqa: F401 -- compatibility imports


class PriorityGNN(nn.Module):
    """Two causal message-passing layers; never symmetrize temporal edges."""

    def __init__(self, width: int, kind: str = "sage", hidden: int = 16):
        super().__init__()
        if kind not in {"sage", "gat"}:
            raise ValueError("kind must be sage or gat")
        layer = SAGEConv if kind == "sage" else GATConv
        self.first = layer(width, hidden)
        self.second = layer(hidden, 1)

    def forward(self, features: torch.Tensor, edges: torch.Tensor) -> torch.Tensor:
        return self.second(torch.relu(self.first(features, edges)), edges).squeeze(-1)


def fit_trace_value(rows: Sequence[dict[str, Any]], *, train_end: int):
    """Fit graph hop distance (or a censoring penalty) using observed labels.

    The cutoff is evidence time. Distinct case IDs alone do not imply independent
    examples; the caller reports duplicate features and validation limitations.
    """
    from sklearn.ensemble import HistGradientBoostingRegressor

    selected = [
        r for r in rows if r["label_observed_at"] <= train_end and r["split"] == "train"
    ]
    if len({r["case_id"] for r in selected}) < 3:
        raise FtmError(
            "insufficient_traces", "At least three completed training cases required"
        )
    x = np.asarray([r["features"] for r in selected], dtype=float)
    y = np.asarray([r["remaining_hops_or_penalty"] for r in selected], dtype=float)
    if not np.isfinite(x).all() or not np.isfinite(y).all() or (y < 0).any():
        raise FtmError("invalid_training", "Invalid trace value examples")
    return HistGradientBoostingRegressor(
        max_iter=30, max_leaf_nodes=7, min_samples_leaf=2, random_state=47
    ).fit(x, y)
