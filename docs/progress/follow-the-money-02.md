# Phase 02 — conservative tracing heuristics

Completed under the owner's end-to-end authorization. No commit: Git worktree
metadata remains read-only (Phase 00). No network calls in this phase.

## Goal and files/functions

`src/follow_the_money/heuristics.py` adds `ClusterBook`: common-input hypotheses
with a hard size cap, counterparty stop, and snapshot restoration. Service
membership propagates without joining wallet groups. `detect_coinjoin` stops
multi-input/equal-output structures before clustering. `detect_change` assigns
output probabilities plus a null hypothesis; these are explicitly uncalibrated.
`detect_peel_chain` checks exact outpoints, values and time, not just shape.
`weak_change_labels` requires later co-spend evidence, matching prevouts and an
observation timestamp; the paired negative is an assumption. `account_signals`
exposes USDT transfers and historical blacklist events without Bitcoin rules.

`clients.py` now rejects empty inputs/outputs, duplicate or self-referencing
inputs, and non-coinbase output inflation. This is structural validation, not
independent consensus verification. `test_heuristics.py` covers stops, probability
mass, evidence continuity and chain separation; `test_clients.py` adds malformed
transaction cases. No dependencies changed.

## Commands actually run and results

- Ruff format/check over `src/follow_the_money`, `tests/follow_the_money`,
  `scripts/ftm_record.py`: **All checks passed; 17 files already formatted**.
- Mirrored with the Phase 01 `rsync` command (excluding protected metadata/data).
- From `~/pw-p2-build`:
  `PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ~/pw-tools/venv-p2/bin/python -m pytest -q tests/follow_the_money -p no:cacheprovider`:
  **73 passed in 2.18s**. Log: `~/pw-tools/p2-phase02-tests.log`.
- A standalone synthetic `detect_change` example with a 10,000-satoshi round
  payment and 89,137-satoshi fresh, matching-script output returned probabilities
  **0.0254197581680301**, **0.7923509756691753**, and null probability
  **0.1822292661627946**; `calibrated=False`. These are computed heuristic weights,
  not measured accuracy or ownership probabilities.

## Limitations and acceptance

All phase tests passed. Common inputs can reflect collaborative transactions;
CoinJoin detection can miss patterns or flag batch payouts. No wallet identity
or laundering finding follows from a cluster or peel shape. Freshness is relative
to observed data. Blacklist events are historical signals, not current status.
No learned classifier or real-data accuracy is claimed in this phase.

What: bounded tracing hypotheses. Why: prevent unsafe graph expansion. When:
before ranking or claims. Where: typed Bitcoin/USDT evidence. Who: analyst reviews
the uncertainty. How: explicit stop conditions, outpoint checks and abstention.

Next: temporal ML pipelines, full/live-feature comparisons, OOD fallback and
weak-label learning. Elliptic++ licence verification and Git commits remain
blocked; owners/next actions are recorded in the manifest and Phase 00.


Review correction (2026-10-27): see the [per-finding review report](follow-the-money-review-fixes.md).
Tracing now calls peel/account/live-feature scoring, with explicit heuristic/OOD
fallback; the trained change classifier and GNNs remain library/experiment only.
Models use agent-role keys and bounded human-approved summaries. Human approvers
are separate from case creators and configured model actors. Playground requires
an agent key or explicit anonymous opt-in and persists conversation quotas.
