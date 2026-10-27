# Phase 03 — temporal learning and OOD fallback

## Goal and implementation

Implemented under the owner's phase authorization. `features.py:live_features`
filters future/unconfirmed observations before computing counts, units,
counterparties and age. `datasets.py:TemporalGraph` checks dimensions, labels and
causal edges; `masks` makes chronological splits. `load_csv_graph` requires an
explicit column mapping and matching operator-approved source receipts; no real
Elliptic file was imported. `synthetic_graph` and `synthetic_change_examples`
provide named fictional evidence, with weak labels derived from actual generated
outpoints rather than asserted ownership.

`models.py:PriorityGNN` implements PyG GraphSAGE/GAT. `DistributionGuard` and
`score_address` prevent applying a synthetic/foreign-chain model silently.
`fit_trace_value` requires completed independent training cases.
`training.py:train_one` fits train-only scaling and uses validation for GNN epoch
selection; `train_change` uses the label observation cutoff. `experiment` runs
all full/live comparisons. `test_models.py` tests causality, future perturbation,
receipt checks, OOD fallback, weak labels and independent-case requirements.

New review artifacts: `config/follow_the_money/training-results.json` and
`docs/follow_the_money/model-card.md`. Trained artifacts stay in `data/`.

## Commands and exact results

- Ruff format/check over package/tests: **All checks passed**.
- Phase 01 mirror command, then offline pytest with the same flags:
  **83 passed, 110 warnings in 75.13s (0:01:15)**. Log:
  `~/pw-tools/p2-phase03-tests.log`. Warnings are Torch's unsupported
  Python 3.14 TorchScript notice and PyG's deprecated annotation evaluation.
- From mirror: `PYTHONDONTWRITEBYTECODE=1 ~/pw-tools/venv-p2/bin/python -m follow_the_money.training --output data/follow_the_money/models`:
  exit 0, **six model fits**, 600 synthetic nodes, split **360/120/120**.
- Full-minus-live test average precision: GraphSAGE **0.24723379642100918**,
  GAT **0.009400911952016311**, XGBoost **0.21907599541424527**. Complete metrics
  and provenance are in the result JSON; no real-data performance is implied.
- Change experiment: 180 weak output examples from 90 fictional transactions;
  **118 training**, **42 test** examples after the observation-time cutoff/gap.
  Its measured scores and coefficients are in the same JSON.

Example: a feature vector with `chain=bitcoin` against the synthetic guard
returns `ood=true`, `reason=schema_or_chain_mismatch`, and the supplied heuristic
score. A later test feature perturbation leaves the saved trained GNN weights
identical; the XGBoost JSON also stays identical.

## Limits, blockers and next phase

Synthetic feature proxies cannot validate real live-feature transfer. The CSV
adapter deliberately requires a reviewed schema; large-file production memory
optimization has not been exercised. No licensed Elliptic++ training, Elliptic2
download, Windows runtime, calibrated deployment or trace-value evaluation is
claimed. Owners/next actions remain in the source manifest. Git commits are
blocked by the read-only metadata mount.

What: executable temporal comparisons. Why: detect leakage and offline-feature
dependence. When: before adopting a ranking model. Where: CPU Linux mirror.
Who: a researcher reviews data rights and errors. How: fixed seed/splits,
future-edge isolation, measured comparisons and conservative fallback.

Next: durable LangGraph tracing, adversarial claim review, human interrupt,
idempotent approval and the Project 1 public-service resolver.


Review correction (2026-10-27): historical metrics above are superseded by the
[review-fixes report](follow-the-money-review-fixes.md) and regenerated result
JSON. The old value MAE is in-sample because probe features duplicate training;
build-time timestamps did not provide temporal validation. The original perfect
change-classifier scores were tautological. GAT is near chance, with one seed and
no CIs. pass^k equals pass^1 in deterministic replay; schema self-consistency is
not independent tool accuracy. Rechecking critic-kept claims is circular; the
review adds independent planted error types and an adequate-budget BFS run.
The trained change classifier and GNNs remain library/experiment only.


Review rerun (2026-10-27): the change generator varies amount, roundness, script
match and input-address reuse. With 118 training and 42 test output rows, AP is
**0.8281470203125101**, ROC AUC **0.7868480725623582**, accuracy
**0.7619047619047619** and Brier score **0.18110125727325666**. These replace the
old tautological perfect scores. The six graph-model runs were reproduced in
54.42 seconds total with the change experiment. GAT AP **0.572325** versus
**0.516667** positive base rate is near chance; its **0.009401** full-to-live drop
is not evidence of robustness. All graph results use one seed and no confidence
intervals. GNNs and the trained change classifier remain library experiments.
