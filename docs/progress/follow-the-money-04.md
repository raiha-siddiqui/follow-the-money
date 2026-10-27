# Phase 04 — durable agent, critic and human approval

Implemented under the owner's end-to-end authorization. The WSL restart was
handled by checking Git and old process handles: both prior training/test handles
were absent. A single-process offline rerun passed **83 tests, 110 upstream
warnings in 82.42s**. Numerical-library threads are now limited to one; no model
training runs alongside full-suite verification.

## Files and behavior

- `cases.py`: strict trace/approval contracts, canonical claim templates and
  approval digest contents. Arbitrary source/LLM prose cannot become report prose.
- `planner.py`: records goal, calls/hops and mandatory stops.
- `agent.py`: real LangGraph planner → frontier → replay tools → reflection loop,
  critic subgraph → evidence-bound `interrupt()` → report → memory hook. Bitcoin
  continuation checks the received outpoint. TRON uses account transfers and an
  optional budgeted historical blacklist lookup. Every override attempt is logged;
  an override can select only an existing frontier entry.
- `critic.py`: independently checks cited structured evidence, exact amounts and
  output indices, hypotheses and published-label receipts. Every claim gets a
  challenge and alternative; unsupported claims remain visible as withdrawals.
- `storage.py`: atomic SQLite budget reservations/results, idempotency and a hash
  ledger with separate retained anchor. Verification detects altered/missing
  reservations, results, state and approval records, including tail truncation.
- `service.py`: portable Project 1 workspace locks; replay-only transports;
  request idempotency; durable SQLite checkpoints; stale/duplicate decisions;
  recovery rebuilds from audited tool results. Checkpoint state and interrupt
  position must match the audited proposal before a decision resumes it.
- `resolver.py`: sanctioned-wallet names supplied by published labels call the
  public Project 1 v2 `start_case`; candidates remain pending human review.
- `fixtures.py`: reproducible fictional BTC branches/CoinJoin and USDT transfers,
  with synthetic byte-hashed replay receipts. `test_agent_service.py` exercises
  the service, restarts, injected crashes, tampering and the actual P1 service.
- `contracts.py`: stable errors now carry a case ID/next action after interruption.

## Verification and example

The first integration run found differing page provenance being mistaken for
conflicting transaction bodies: **8 failed, 4 passed**. The comparison now checks
transaction fields separately and retains every page receipt. After that fix and
additional audit deletion tests: **14 passed in 17.04s**. The subsequent complete
phase run, including freeze integration, is recorded below.

Final full phase run (same environment flags, target `tests/follow_the_money`):
**98 passed, 110 upstream warnings in 84.51s (0:01:24)**. Exit 0; log
`~/pw-tools/p2-phase04-tests.log`.

Commands actually run: pinned Ruff format/check over the package/tests; mirror
with the Phase 01 rsync command; then
`OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ~/pw-tools/venv-p2/bin/python -m pytest -q tests/follow_the_money/test_agent_service.py -p no:cacheprovider`.
Ruff: **All checks passed**; final formatting scope including recording script:
**31 files already formatted**. Logs live under `~/pw-tools/p2-*.log`.

Synthetic input `seed=syn_seed_a`, budget 12/hops 5 reaches the fictional exchange
after **3 logical calls, 0 network calls**, then pauses with no final report.
After a matching human decision, it produces cited claims and, if requested,
`DRAFT_ONLY`, `sent=false`. Rejection withholds retained claims. TRON reaches its
fictional endpoint in **2 logical calls** without Bitcoin clusters/change.

## Limitations, deviations and blockers

The critic is deterministic LangGraph because CrewAI excludes Python 3.14.
It checks encoded evidence and alternatives; it does not replace an investigator.
No key/provider was used. The agent runs recorded snapshots; live recording is a
separate explicitly bounded command. Ledger reservations count logical queries,
including failures; repeated recovery of the same reserved replay operation does
not pretend to be a new network request. Address flows do not prove coin-level
attribution across multiple inputs. Missing pages remain visible limitations.

Hash chains are not signatures. An attacker who can rewrite the database and its
anchor can forge both. A crash between ledger commit and anchor replacement fails
closed and requires operator inspection; this is not a fully hardened production
transaction coordinator. Recovery from a stored human decision requires exactly
the same proposal digest. Optional callbacks that change on replay can stop
recovery with a conflict instead of silently changing approved evidence.

After restart, Git staging was retried with the compatible local Git binary:
`git add -- docs/follow_the_money/plan.md docs/progress/follow-the-money-00.md`.
It again failed creating `index.lock`: **Read-only file system**. No P2 commits
exist; the owner explicitly assigned committing the retained changes to the
coordinator. No push or merge was attempted.

What: an auditable bounded loop. Why: preserve evidence and human control across
failures. When: every case and decision. Where: the local locked service and replay
cache. Who: software proposes; an authenticated analyst reviews. How: durable
reservations, independent claim checks and an evidence-bound interrupt.

Next: namespaced long-term cases, clusters, links and analyst rules, including
service suppression, correction and deletion from active recall.


Review correction (2026-10-27): see the [per-finding review report](follow-the-money-review-fixes.md).
Tracing now calls peel/account/live-feature scoring, with explicit heuristic/OOD
fallback; the trained change classifier and GNNs remain library/experiment only.
Models use agent-role keys and bounded human-approved summaries. Human approvers
are separate from case creators and configured model actors. Playground requires
an agent key or explicit anonymous opt-in and persists conversation quotas.
