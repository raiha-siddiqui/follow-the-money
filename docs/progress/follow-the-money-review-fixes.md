# Project 2 adversarial review fixes

This repair covers B1–B3, S1–S4, C1–C6, H1–H7 and E1–E6 on `project-2`, based on merge `d91e372` (original Project 2 commit `d440a0e`). It repairs the merged servers, separates model and human permissions, bounds model-visible evidence, corrects tracing, and replaces overstated evaluation claims. `src/watchlist/agent/*` is unchanged.

## Per-finding outcomes

| Finding | Verified outcome |
|---|---|
| B1 | Confirmed. Removed the obsolete middleware keyword from both HTTP servers; p1_interfaces.py makes auth, telemetry, locks and ReviewError explicit. REST and actual streamable-HTTP MCP contract tests exercise the merged interfaces. |
| B2 | Confirmed. Renamed test_evaluation.py to test_ftm_evaluation.py; a repository-wide basename regression finds no duplicates. No test-package __init__.py was added. |
| B3 | Confirmed. Inspected the detector findings: public transaction/contract identifiers, integrity hashes, receipts and fictional test literals, with no real secret found. Python/Markdown exceptions use inline pragmas; JSON exceptions bind file hash, line and detector type with a reason. Rebound two stale merged Project 1 exceptions without editing their source files. Kept the complete scan scope and 600-second timeout. |
| S1 | Confirmed. Project 2 agent keys can start traces and read bounded summaries. Human approver keys authorize approval, recovery, rules and memory revisions; reviewer remains a human alias. Creators and configured model/service actors cannot approve. Project 1 roles remain unchanged. |
| S2 | Confirmed. Pending cases expose no model-visible claims; reviewed cases use report.claims, capped at 50. Rejected cases expose none. Raw evidence, notes, labels and rules are human-only. Copilot uses get_case_summary; MCP and bounded memory views preserve only permitted fields. |
| S3 | Confirmed. Playground requires an agent key in X-FTM-Key, or explicit --allow-anonymous. Persistent limits default to five distinct traces per actor/conversation and 100 conversations per workspace. Retries/restarts preserve limits; case reads stay within the same actor/conversation. |
| S4 | Confirmed. Acquisition refuses redirects, disables environment proxies and checks pins on cached reuse. All seven registered sources are pinned to hashes checked against existing local bytes and receipts. No download was needed. |
| C1 | Confirmed. Exactly one output reusing an input address wins change selection; ambiguous reuse abstains. The critic uses independent structural vetoes, not detect_change, and rejects the planted wrong output. |
| C2 | Confirmed. Producer and critic use confirmed evidence at or before transaction time. Newest-first pages supply their older observations before scoring; future/current-output observations cannot manufacture freshness. |
| C3 | Confirmed in part: the optional toy value policy already had a caller, but ordinary service scoring and the listed utilities did not. Tracing now calls peel detection, account signals, live features and score_address with OOD fallback; MCP exposes score_address. TRON uses relative outgoing-page amounts. GNNs and the trained change classifier remain explicitly library/experiment only. |
| C4 | Confirmed. Freeze pages have explicit cursors and per-page budgets; all three event types are fetched and matched to every traced address. Historical net blacklist state distinguishes removal from fund destruction. Hex/ABI addresses normalize to base58; Approval rows are skipped. Incomplete histories remain explicit. |
| C5 | Confirmed. Continuation pages accept up to 50 transactions. Regression coverage includes an authored recording and the existing 50-confirmed-transaction public recording; no fresh request was made. |
| C6 | Confirmed. Weak-label construction filters spends by the observation cutoff before choosing labels. A later second co-spend cannot retroactively remove a training example. |
| H1 | Confirmed. Chose the permitted honesty fix: the value result is an in-sample fit diagnostic, with duplicate-probe counts and a constant-mean baseline. All 17 probe rows duplicate training features; no held-out performance is claimed. |
| H2 | Confirmed. Synthetic change examples now vary script match, roundness, relative amount and reuse. Reran training; the old perfect scores are superseded. |
| H3 | Confirmed. Documented deterministic pass^k = pass^1 and that only one task separates strategies. Added an adequate-budget BFS endpoint run. Renamed tool accuracy to schema self-consistency; tracing/gold metrics read the transport counter. |
| H4 | Confirmed. Independent authored critic cases cover wrong amount, wrong txid, wrong change, CoinJoin clustering and service clustering. In-loop rechecks are separately identified as circular self-consistency. |
| H5 | Confirmed. Documents and receipts say GAT is near chance relative to the 0.516667 positive base rate; the small full-to-live drop is not meaningful robustness evidence. One seed, no confidence intervals. |
| H6 | Confirmed. Targets and metrics now name graph hops or penalty, not API calls. Label observation time comes from recorded evidence rather than build wall-clock time. Renamed graph copies remain explicitly non-validating, even with ordered evidence timestamps. |
| H7 | Partly stale: the README title already covered both projects. Removed its contradictory exclusion sentence, corrected commit history to d440a0e merged at d91e372, and replaced machine-specific plan paths. |
| E1 | Confirmed. Optional test imports are guarded, the conftest contract import is lazy/guarded, and NumPy-only scoring is separate from torch/PyG. CI imports ML and Microsoft packages explicitly so missing extras cannot silently skip their tests. |
| E2 | Confirmed. Project 2 text reads/writes now specify UTF-8, including tests and recording scripts. An AST audit found no remaining read_text/write_text omissions. |
| E3 | Confirmed. Project 2 CI pins Python 3.14.0, disables check-latest/Python downloads, pins the uv checksum and includes the requested shared-source/tooling trigger paths. |
| E4 | Confirmed. Evaluation and learned-synthetic demo document ftm-ml and fail with an actionable missing-extra message. make help lists the Project 2 targets. |
| E5 | Partly confirmed: loopback binding and disabled usage telemetry already existed. Added explicit localhost and 127.0.0.1 allowed-host flags; the CLI regression covers all flags. |
| E6 | Confirmed. CLI/API/MCP entry points accept paired --p1-workspace/--p1-config options and open the existing public ReviewService. Public-service resolution and entry-point wiring are tested; absent configuration remains explicit unavailable. |

## Files and behavior

All source paths below are under `src/follow_the_money/` unless stated otherwise. Functions identify the meaningful new code; unchanged helper plumbing is omitted.

| Files | What changed and why |
|---|---|
| `auth.py` (new), `p1_interfaces.py` (new) | `Principal.can`, `KeyStore.authenticate`, `can_start` and `is_human` define Project 2 agent/human roles while delegating hashed-key authentication to Project 1. The adapter names the four shared public interfaces explicitly. |
| `views.py` (new), `api.py`, `mcp_server.py` | `case_summary` reads human-approved report claims and caps output; `memory_summary` strips free text. REST adds the bounded summary operation; MCP uses it and exposes `score_address`. Both middleware constructors match merged main. Human evidence and mutations require human permissions. |
| `service.py`, `cases.py` | `submit_approval` rejects creators and configured model actors. Actor settings survive reopen. `score_frontier` and `score_address` supply live-feature/OOD behavior. Signals enter the approval digest so a review binds the evidence shown. |
| `m365.py` | `ConversationQuota` persists actor/conversation limits; `create_local_app` requires an agent key or explicit anonymous opt-in. Reads are conversation-scoped; outbound connectors remain disabled. |
| `__main__.py`, `resolver.py` | CLI adds role, model-actor, Playground quota/auth and paired P1 workspace/config options. `EntityResolver.from_workspace` opens the public ReviewService. UI arguments explicitly restrict allowed hosts. |
| `acquire.py`, `clients.py`, `contracts.py` | Acquisition rejects redirects/proxies and enforces cached-byte pins. `FreezePage` and `get_freeze_events` support cursors/all three actions. `tron_address` normalizes hex/ABI forms. Transfer pages skip Approval rows; Esplora continuations accept 50 transactions. |
| `heuristics.py`, `critic.py` | Unique input-address reuse wins change selection; ambiguous reuse abstains. `seen_addresses_before` enforces evidence time. Weak labels filter spends before the cutoff. The critic's `structurally_supported_change` independently vetoes wrong change; CoinJoin/service clustering is rejected. Historical freeze state distinguishes removal and destruction. |
| `agent.py`, `features.py`, `scoring.py` (new), `models.py` | The loop calls peel/account signals, `live_features` and NumPy-only `score_address`, with checked OOD/error fallback. Newest-first pages still provide older evidence before scoring. TRON priority compares outgoing amounts. Actual transport counters replace constant network metrics. GNN/change-classifier components remain library experiments. |
| `datasets.py`, `training.py`, `fixtures.py` | Synthetic change signals vary; weak-label cutoffs apply before selection. Authored freeze fixtures represent all three actions. Training receipts state single-seed limits. |
| `evaluation.py`, `gold.py` | `train_value_policy` reports an in-sample hops-or-penalty fit, duplicate rows and a constant baseline. `critic_metrics` covers five error types. Evaluation adds adequate-budget BFS, honest schema-consistency naming, and real transport counters. |
| `memory.py`, `security.py` | Shared locking/error/auth imports go through the explicit adapter and Project 2 role boundary. |
| `scripts/ftm_m365.py`, `scripts/ftm_record.py` | Regenerated model operations target bounded summaries and document agent keys; text I/O is UTF-8. Public identifier literals have narrow scanner pragmas. |
| `scripts/project_checks.py` | Added individually reviewed hash-bound exceptions for public IDs, hashes and receipts, including main's validation JSON. Rebound two stale Project 1 exceptions without changing their source. Detector scope and 600-second timeout are unchanged. |
| `config/follow_the_money/` | Seven source pins, regenerated M365 OpenAPI/plugin/instructions, rerun training/evaluation/gold receipts, source fingerprints and final verification receipt. The older Playground demonstration is explicitly historical. |
| `.github/workflows/{ci,follow-the-money}.yml`, `Makefile` | CI checks optional ML/Microsoft imports, pins Python/uv behavior, includes shared-source triggers, and lists Project 2 commands and ML prerequisites. |
| Root `README.md`; `docs/follow_the_money/{README,plan,model-card,decisions}.md`; progress reports 01–04 and 06–09 plus final | Corrected scope, role setup, generic commands, feature deployment status, measured results and limits; retained old runs only as labeled history. |

Tests: renamed `test_evaluation.py` to `test_ftm_evaluation.py`; added `test_ftm_review_security.py` and `test_ftm_review_tracing.py`. They cover merged HTTP contracts, role separation, report-only views, quotas/restarts, resolver wiring, redirects/proxies/pins, change/freshness/cutoffs, pagination/address normalization, production scoring/signals and independent critic errors. Existing interface/model/M365/agent/memory/transport tests were updated for the intentional behavior changes. Every Project 2 test module now guards optional imports as needed and uses explicit UTF-8; the conftest contract import is lazy. No assertion was relaxed to hide a failure, and no test-package `__init__.py` was added.

## Validation

The fixer's own sandboxed run was interrupted before its final receipts. The coordinator then verified the committed tree outside the sandbox on Linux (WSL Ubuntu 24.04, Python 3.14.9, all extras, two parallel shards):

- Full offline suite (`-m "not integration"`): **4,589 passed, 154 skipped, 4 failed** in 61 minutes. The skips are private Step 08 evidence and absent optional runtimes.
- The 4 failures are v1 `tests/test_agent.py` lock-worker timing tests (writer body exception, killed writer, service re-entry, concurrent review). They fail identically on `main`'s code under the same host load (load average about 8 on 8 cores from unrelated jobs); the worker's status call took 9.7–11.4 s against the test's 10 s deadline. They passed on the same v1 code in the merged-main run (4,419 passed, 0 failed). The frozen v1 tests were not loosened.
- Repository secret scan: initially **67 unresolved** findings because two receipts were regenerated after their exceptions were recorded. After rebinding `source-verification.json` and `training-results.json` and adding a hash-bound entry for the public base58 alphabet in `clients.py`: **passed, 0 unresolved, 462 files, 212 s** (limit 600 s).
- `tests/test_project_checks.py` and `tests/test_packaging.py`: **57 passed**. Ruff check and format: clean (192 files). `uv lock --check --offline`: consistent (170 packages).
- The 52 hashes in `config/follow_the_money/source-verification.json` match the committed files.

## Corrected measurements

- Fixed synthetic search: 27 deterministic runs; BFS succeeds on 2/3 tasks, heuristic and toy value on 3/3. Only one task separates them; pass^k equals pass^1. At budget 32, branching endpoint costs are **16 / 3 / 3 queries**.
- Value fit: **51 training rows**, **17 duplicate probe rows**, **zero novel probe rows**. In-sample hops-or-penalty MAE **0.3584913178917404**, constant-mean baseline **8.456747404844291**. No held-out or temporal-generalization claim remains.
- Varied synthetic change classifier: **118 training / 42 test rows**; AP **0.8281470203125101**, ROC AUC **0.7868480725623582**, accuracy **0.7619047619047619**. Weak labels still encode assumptions.
- Independent critic: **3/3 supported retained, 5/5 planted errors withdrawn**. The separate circular in-loop recheck retains **12/13**. Memory: TP=1, FP=0, FN=0, TN=3.
- Public one-hop replay: **6/6 successful runs**, one query per strategy/run, **3 retained / 1 withdrawn** claims per run, and **zero measured physical calls**. No real-world search-efficiency gain is claimed.
- Graph AP full → live: GraphSAGE **0.946293 → 0.699059**; GAT **0.572325 → 0.562924**; XGBoost **0.930949 → 0.711873**. GAT is near the **0.516667** base rate; its small drop is not meaningful robustness evidence. One seed, no confidence intervals. GNNs and the trained change classifier do not drive ordinary tracing.

Example behavior: an agent key starts a fictional trace and receives `status=awaiting_approval` with `claims=[]` from the model summary. Its approval request is denied. A distinct human approver may approve a selected claim subset; only that subset then appears to model clients. Rejection leaves `claims=[]`. For input A=100000 and outputs A=60000/B=39123, change detection selects A; an independently planted claim naming B is withdrawn.

## Limits and handoff

This remains an offline research prototype producing leads for human review. No new data/model download, live explorer call, API-key use, paid compute, external message, push or merge occurred. Existing public bytes were reused and hash-checked. Hosted CI, Windows runtime, tenant/Azure deployment, live TRON validation, real Elliptic training/licensing, provider-backed LLM evaluation and independently adjudicated real-world effectiveness remain unclaimed.

The repair's what/why is safer interfaces and honest tracing evidence; who is a model starting a bounded trace and a distinct human reviewing it; when is before merged Project 2 is accepted; where is this branch and its approved Linux mirror; how is offline replay, explicit contracts, independent counterexamples and full regression checks. No later feature phase is started. The coordinator owns the Git handoff and any future deployment/data approval.
