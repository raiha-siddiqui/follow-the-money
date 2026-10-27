**Project 2 — Follow the Money: delivery and review fixes**

The original local research implementation was committed as `d440a0e` and merged
with current main at `d91e372`. The earlier statement that no Project 2 commit
existed is obsolete. This review repairs the merged interfaces, authorization,
model-visible evidence, tracing correctness and reported evaluation claims.

The delivered system includes replay-first Bitcoin/TRC-20 clients, bounded
LangGraph tracing, independently checked claims, durable human review, audited
case memory, REST/MCP/Streamlit and a local Microsoft Agents SDK wrapper. Public
output remains research leads; nothing is sent to an exchange or authority.
Ordinary search uses heuristics with an explicit OOD fallback. The optional
learned value demonstration is synthetic only. GNNs and the trained change
classifier are library/experiment components, not deployed search policies.

The reference architecture, file/function explanations and historical runs remain
in phase reports 00–09. Their old metrics are historical where superseded below.
Current sources are fingerprinted in `config/follow_the_money/source-verification.json`.

## Review fixes

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

Corrected measured results:

- Adequate-budget branching search: BFS **16 queries**, heuristic **3**, toy value
  policy **3**. The original 12-query budget censors BFS; only this task separates
  the strategies. Deterministic replay makes pass^k equal pass^1.
- Value fit: **0.358491** MAE versus **8.456747** constant-mean baseline, in graph
  hops-or-penalty units. **51 training rows**, **17 duplicate probe rows**, **zero
  novel probe rows**. This is in-sample, not temporal/held-out generalization.
- Varied synthetic change signals: AP **0.828147**, ROC AUC **0.786848**, accuracy
  **0.761905**, with 118 training and 42 test output rows. Weak-label assumptions remain.
- Independent critic cases: **3/3 supported retained**, **5/5 planted errors
  withdrawn**. The separate in-loop check retains 12 of 13 claims and is circular.
- Six public one-hop replay runs: both strategies use **one query**; each run
  retains three of four claims. Transport counters report **zero live calls**.
- Synthetic GNN results remain unchanged: GraphSAGE AP **0.946293 → 0.699059**;
  GAT **0.572325 → 0.562924**; XGBoost **0.930949 → 0.711873**. GAT is near the
  **0.516667** base rate; its small drop proves no robustness. Single seed, no CIs.

## Review verification

Full review validation is in progress. The final exact counts, wall times,
commands, earlier failures and handoff status will be recorded in
[the review-fixes report](follow-the-money-review-fixes.md). The intermediate
Project 2 run passed 169 tests; the core-only environment passed 158 with four
explicit optional skips. These are not the final full-repository totals.

## Remaining external work

Real Elliptic training/licensing, live TRON verification, broader independently
adjudicated gold traces, provider-backed LLM evaluation, real-world calibration,
and tenant/Azure/Teams deployment remain outside this repair. No new download,
API key use, paid compute, external message, push or merge was performed.
Hosted CI and Windows runtime were not run; local validation uses Linux Python
3.14.9 while hosted CI is configured for Python 3.14.0.
