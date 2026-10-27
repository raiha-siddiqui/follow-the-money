# Phase 06 — measured evaluation, 2026-10-27

Goal: compare bounded search against breadth-first search, challenge claims, and
measure consistency on fixed fixtures and a cited public transaction pair.
Dependencies: phases 01–05; no LLM provider, keys or real Elliptic training.

## Files and functions

- `evaluation.py`: `evaluate` runs the three frozen tasks with fresh workspaces;
  failures have null calls-to-endpoint, not deceptively cheap successes.
  `train_value_policy` trains a value regressor on three completed simulated
  review traces; a renamed fourth case is probed (all its feature rows duplicate training rows). Its target is shortest remaining
  graph distance, with a penalty for unreachable nodes, not measured API cost.
- `gold.py`: `validate_gold_pair` checks exact funding/spending outpoints and
  integer units. `evaluate_gold` requires public recordings and replays them.
- `fixtures.py`: distinct identifiers/times for four isomorphic toy worlds.
- `agent.py`, `cases.py`: optional seed outpoint, address reuse handling, and
  stop scanning history once that exact outpoint's confirmed spend is found.
  Tool reservations distinguish frontier entries while remaining retry-safe.
- `test_evaluation.py` and the address-reuse service regression cover censoring,
  temporal/case isolation, malformed gold facts, missing cache and redaction.
- `gold-traces.json`, `evaluation-results.json`, `public-gold-results.json`,
  source registry and manifest preserve annotations, results and byte receipts.

## Commands actually run and results

All test/evaluation processes used one numerical thread and ran sequentially.
Linux mirror `~/pw-p2-build`; interpreter
`~/pw-tools/venv-p2/bin/python`; environment
`OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`.

- `python -m pytest -q tests/follow_the_money/test_agent_service.py tests/follow_the_money/test_memory.py tests/follow_the_money/test_evaluation.py -p no:cacheprovider`:
  **28 passed, 1 warning in 107.38s**. Log `p2-phase06-tests.log` under pw-tools.
- `python -m follow_the_money.evaluation --output data/follow_the_money/evaluation-v1 --repeats 3`:
  **27 runs**, no physical network calls. Three tasks × three strategies × three
  repeats. BFS succeeds on 2/3 tasks; heuristic and trace-value policies 3/3.
  Branching task: BFS exhausts 12 calls; both priorities reach the endpoint in
  3. CoinJoin stop: 1 call; TRON endpoint: 2. All strategies have identical
  behavior hashes across three repeats per task. Pass^3: 2/3, 3/3, 3/3.
  Mean queries 5, 2, 2; median latency 0.662473139, 0.556957156,
  0.550549665 seconds. Tool schema validity 1.0. External service cost $0;
  local electricity/hardware cost not measured.
- Value model: 51 training rows / 17 duplicate probe rows; in-sample fit distance MAE
  **0.3584913178917404**. Three training case IDs, one duplicate-probe case ID.
  These are renamed isomorphic toy graphs, not evidence of generalization.
- Critic: 12 supported fixture claims retained; 10/10 planted amount errors
  withdrawn. Memory: TP=1, FP=0, FN=0, TN=3 on four exact-overlap queries.
- Public replay v2: six successful runs, BFS **1 query** and priority **1
  query**, pass^3 true for each. Three separate replay queries validate the
  gold transaction pair before the benchmark. Zero live calls during replay.
  The first public run unnecessarily scanned an older page after finding the
  anchored spend; that was fixed and the benchmark rerun. No real search gain
  is claimed. Final phase will rerun after remaining hardening changes.
- Ruff check and format of new evaluation files passed.

## Public evidence and example

[DOJ filing, 2025-02-19](https://www.justice.gov/usao-ma/media/1390101/dl?inline=),
PDF page 16 (affidavit page 13), paragraphs 35–38 and figures 1–2. Document
SHA-256 `53ae96300ca66650efac81fb629d080f17d73300e8c77a26629d757ef917bf5f`.
Funding `48388dd0482ae39ef56d8cd39374f7aa1a33fc347ce4ddbc66564379a6a628ea:29`
contains 133272285 satoshis; spending transaction
`c903bb557e868f2a484e7a49b3ce40978ab7eb9ea326ce165f98ade70e01c3bb`
consumes it and output 0 transfers 124016260 satoshis to a historically
published exchange deposit address. This is a cited possible flow, not proof
of ownership, wrongdoing, or current exchange control. The filing has a short
address suffix discrepancy and prose suggesting an intermediary; only the
full addresses and chain-verified outpoints are used.

`scripts/ftm_record.py` recorded two transactions plus outspends (4 physical
GETs), then one address page (1 physical GET; the other two requests hit cache).
With the earlier genesis recording, **7 public Bitcoin API requests total**.
Raw data remains gitignored. Source URL, licence, retrieval date, bytes and
SHA-256 are in the manifest. Court PDFs were inspected with local PyMuPDF 2.0,
including rendered image pages; this tool is not a runtime dependency.

[Colonial affidavit](https://www.justice.gov/archives/opa/press-release/file/1402056/dl?inline)
is image-based, with full addresses redacted and no transaction IDs. Its
amounts/paragraphs are encoded as documentary observations, excluded from
endpoint evaluation. Filling the gaps would invent evidence.

## Limits, blockers and recap

The engineer implemented search evaluation for an analyst, at phase 06, in the
local Linux mirror, using frozen synthetic worlds and one replayed public hop.
This measures software behavior and prevents fabricated benchmark claims.
Real Elliptic/generalization, unredacted Colonial gold, live TRON and LLM
ablations remain blocked; dataset/provider owners must supply permitted data
or access. Only simulated fixture reviews trained memory/value experiments.
No real case was approved and nothing was sent. Git staging remains blocked
by the read-only worktree Git metadata; the coordinator will commit changes.
Next: authenticated API, MCP transports, reviewer UI and offline CI.

Final audit correction (phase 09): the initial value experiment used completed
searches that were still awaiting approval. The final implementation requires
completed, explicitly simulated fixture reviews and derives targets only from
critic-retained edges; final measurements supersede the initial receipt.


Review correction (2026-10-27): historical metrics above are superseded by the
[review-fixes report](follow-the-money-review-fixes.md) and regenerated result
JSON. The old value MAE is in-sample because probe features duplicate training;
build-time timestamps did not provide temporal validation. The original perfect
change-classifier scores were tautological. GAT is near chance, with one seed and
no CIs. pass^k equals pass^1 in deterministic replay; schema self-consistency is
not independent tool accuracy. Rechecking critic-kept claims is circular; the
review adds independent planted error types and an adequate-budget BFS run.
The trained change classifier and GNNs remain library/experiment only.


Review rerun (2026-10-27): fixed-budget success remains BFS **2/3**, heuristic
**3/3**, toy value **3/3**, across 27 deterministic runs. Only the branching task
separates the strategies; pass^k equals pass^1. At a common adequate budget of
32 queries, endpoint costs are **16 / 3 / 3**, respectively. Schema
self-consistency remains 100%; it is not independently judged tool accuracy.
The value fit uses 51 training rows and 17 duplicate probe rows (zero novel
rows): in-sample hops-or-penalty MAE **0.3584913178917404**, versus constant-mean
**8.456747404844291**. Evidence timestamps replace build-time timestamps, but
renamed isomorphic graphs still provide no temporal-generalization evidence.
Independent critic cases retain **3/3** supported claims and withdraw **5/5**
errors (amount, transaction ID, change output, CoinJoin cluster, service
cluster). The separate circular in-loop recheck retains **12/13**. Memory
counts remain TP=1, FP=0, FN=0, TN=3.
