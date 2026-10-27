# Follow the Money — Project 2

A research agent for bounded Bitcoin and USDT TRC-20 tracing. It produces
transaction-cited leads for a human analyst, not findings of identity,
ownership, guilt or current sanctions status. Everything runs in replay mode
by default. No transaction signing, exchange contact or authority contact exists.

The working system has typed explorer clients, cache/request accounting,
heuristics, temporal learning experiments, an actual LangGraph planner/loop,
an independent critic subgraph, durable human-review interrupts, case memory,
FastAPI, official MCP transports, Streamlit and a Microsoft Agents SDK wrapper.
See the [plan](plan.md), [final receipt](../progress/follow-the-money-final.md),
[data card](data-card.md), [model card](model-card.md) and [decisions](decisions.md).

## Run locally

Use Python 3.14 and pinned uv 0.13.5. Work in the repository with a Linux/WSL
shell; this task's tested interpreter was Python 3.14.9. Install dependencies
before offline runs. The ML extra is optional for tracing, required for training
and the complete test/evaluation suite. The Microsoft extra is optional too.

```bash
uv sync --locked --dev --extra ml --extra m365 --group qa
export PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export LANGSMITH_TRACING=false OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
uv run --no-sync python -m follow_the_money demo --workspace data/follow_the_money/my-demo
```

Use a fresh workspace path. The output is a **synthetic** case awaiting human
approval, with three explorer queries, transaction evidence and critic outcomes.
It does not silently approve itself. A request ID makes retries idempotent.

For the learned value policy demonstration, use a different fresh workspace:

```bash
uv run --no-sync python -m follow_the_money demo --learned-synthetic --workspace data/follow_the_money/learned-demo
```

This requires the `ml` extra (as does `make eval`). It fits three fictional
traces and probes a renamed fourth with identical feature rows: an in-sample
fit diagnostic, with a constant-predictor baseline, not held-out validation.
Those training reviews are explicitly simulated by a separate fixture actor. The resulting demonstration still pauses for real human review.
The synthetic-only policy rejects real addresses and TRON. Ordinary tracing
uses its conservative heuristic/OOD fallback. GraphSAGE/GAT are temporal graph
experiments; they are not passed off as validated real-address risk models.

Issue local API keys, keep each token private, and put only the hash entries in
an operator-owned file under `data/`:

```bash
uv run --no-sync python -m follow_the_money keygen --actor analyst --role approver
uv run --no-sync python -m follow_the_money keygen --actor trace-model --role agent
uv run --no-sync python -m follow_the_money keygen --actor observer --role viewer
# Save each key_file_entry as a line in data/follow_the_money/keys.txt.
uv run --no-sync python -m follow_the_money serve --workspace data/follow_the_money/my-demo/service --key-file data/follow_the_money/keys.txt
# In another local terminal:
uv run --no-sync python -m follow_the_money ui
```

The API is `http://127.0.0.1:8765`; Streamlit is `http://127.0.0.1:8501`.
Enter a token in the UI's password field. Inspect trace, every claim's txids,
critic objections/withdrawals and memory context, then approve or reject the
shown digest. Approval can produce a **DRAFT_ONLY**, `sent=false` request.
The UI never calls an exchange. A stale digest is rejected. Viewer keys cannot
start, approve or mutate a case. Bearer possession is attributed identity, not
proof of a human at the keyboard. Give model/Copilot clients **agent** keys:
start traces and read bounded summaries only. Human **approver** keys authorize
approval, recovery, rules and memory revisions; `reviewer` is a legacy human
alias. Creators cannot approve their own cases. `local-mcp`, `local-playground`,
configured agent-key actors and actors supplied through `--model-actor` cannot
approve. Keep human keys out of model clients and plugin vaults.

Agent keys cannot read the raw human case, audit or memory inspector. Use
`GET /v1/cases/{case_id}/summary`: pending cases expose no claims, and reviewed
cases expose at most 50 claims from the human-approved report. Rejected cases
expose no claims. Raw labels, notes, rules and evidence stay in the human UI.

MCP uses the official Python SDK, with no approval tool:

```bash
uv run --no-sync python -m follow_the_money mcp --workspace data/follow_the_money/my-demo/service --transport stdio --read-only
uv run --no-sync python -m follow_the_money mcp --workspace data/follow_the_money/my-demo/service --transport streamable-http --key-file data/follow_the_money/keys.txt --port 8766
```

Configure stdio as a client-spawned command; stdout is reserved for protocol.
HTTP endpoint: `http://127.0.0.1:8766/mcp`, with `Authorization: Bearer <token>`.
Tools: `start_trace`, `get_case`, `list_cases`, `verify_audit`,
`query_case_memory`, `score_address`. Stdio without `--read-only` uses the
agent role and permits starting traces under its configured actor. HTTP enforces
agent/human/viewer permissions per request.
Host/Origin checks and 64 KiB request bounds apply. Responses are untrusted data.

## Architecture and evidence

The [plan's diagram](plan.md#architecture-and-dependency-graph) shows the loop.
The planner freezes chain, goal, API query/hop budgets and stops. Each frontier
entry is an address plus incoming outpoint/time, so address reuse does not
silently drop a later spend. A priority callback can rank it; exceptions, schema
mismatch and OOD cause heuristic fallback. An optional untrusted ranking
proposal may choose only an existing candidate; every attempt and override is
audited. No provider/key is required or used.

Bitcoin uses capped common-input hypotheses, probabilistic change estimates,
peel continuity and conservative CoinJoin detection. Service/mixer/oversized
clusters are stop points. TRON uses account transfers and historical USDT
blacklist events, with no Bitcoin clustering or change inference. A freeze
signal is not present-day status or evidence of wrongdoing. Missing or partial
pages are explicit. Each physical HTTP retry is charged separately; logical
tool queries remain charged when a cache hit makes network cost zero.

The critic checks typed evidence, with independent structural vetoes for change
claims and service/CoinJoin vetoes for common-input claims. It challenges **every**
claim, including retained ones. Contradictions are withdrawn and counted.
Approval binds claims, objections, evidence, labels, trace, budget and memory
context. The hash chain and separate anchor detect local corruption; they are
not signatures and cannot defeat an administrator rewriting all local files.
After approval, non-service cluster hypotheses can link exact addresses across
cases. Corrections suppress disputed recall; tombstones preserve historical
audit payload and are not secure erasure. Rules can stop or annotate, not widen
budgets or bypass critic/approval.

`EntityResolver` calls Project 1's public v2 `start_case` only for a published
sanctioned-wallet label with an owner name. Opt in on `demo`, `init`, `serve`, `mcp` or `m365` with both
`--p1-workspace <existing-p1-workspace> --p1-config config/review-v2.json`.
The entry point opens Project 1’s public `ReviewService`; it never silently
initializes a workspace. Python callers can still inject `EntityResolver(service=...)`.
The real public-service integration is tested with P1's fictional retriever.
Unconfigured resolution is explicit `unavailable`; no name or ownership is
inferred. P1's own human review remains required.

## Evaluation and learning

```bash
uv run --no-sync python -m follow_the_money.training --output data/follow_the_money/training-new
uv run --no-sync python -m follow_the_money evaluate --output data/follow_the_money/evaluation-new --repeats 3
uv run --no-sync pytest -q tests/follow_the_money -p no:cacheprovider
uv run --no-sync ruff check src/follow_the_money tests/follow_the_money scripts/ftm_*.py
```

The fixed tasks and result JSONs are in `config/follow_the_money/`. Three toy
tasks × three policies × three repeats measure success, censored endpoint
queries, tool schema validity, actual latency, external cost and pass^3.
The branching fixture reaches its endpoint in 3 queries with either priority
policy; BFS exhausts 12 in the fixed-budget comparison. A separate adequate
budget (32 queries) measures BFS’s actual endpoint cost. This is deliberately constructed test evidence.
A cited 2025 DOJ funding/spending pair is replay-verified separately: BFS and
priority each use **one query**, with no claimed real-world efficiency gain.
The Colonial affidavit's redacted addresses/no txids prevent an honest endpoint
benchmark; documentary observations remain outside the success denominator.

GraphSAGE/GAT and XGBoost use the same features and temporal split, with only
past-to-present messages and training-only scaling. The live-feature subset
experiment retrains instead of dropping columns only at inference. Synthetic
feature proxies and weak co-spend labels are explicitly labeled; no Elliptic
performance is claimed. The value model learns observed graph distance from
completed simulated traces, not real investigator effort. Its target is hop
distance or penalty 25, with names stating those units. Evidence timestamps
replace build wall-clock timestamps; the renamed-graph fit is explicitly not
temporal validation. All 17 probe feature rows duplicate training rows.
Tool schema self-consistency checks bounded queries against our own schema;
it is not independently judged tool-call accuracy. Deterministic replay makes
pass^k equal pass^1. Only one of the three tasks separates strategies.
The critic benchmark has independent wrong-amount, wrong-txid, wrong-change,
CoinJoin-cluster and service-cluster cases; rechecking in-loop claims is
reported separately as circular self-consistency.

The full public gold replay needs the raw ignored cache matching the manifest.
CI uses authored fixtures, cited gold annotation/unit checks and fail-closed
cache-miss tests; it never downloads public transaction pages. Run explicit
`scripts/ftm_record.py --help` for approved bounded acquisition. Recordings need
source licences, approved scope and request caps; never enable hidden network
fallback. Data acquisition is separate from serving/tracing.

## Microsoft 365: three types of agent

| Type | Orchestration and use | Delivered here | Still blocked |
|---|---|---|---|
| Copilot Studio | Microsoft-hosted low-code topics, connectors and MCP tools | Routing/safety instructions for both projects; human approval template | Tenant configuration, publication to Teams and actual invocation |
| Declarative agent | Instructions/actions specialize Copilot's model and orchestration | v1.9 manifest and v2.4 API plugin generated from actual OpenAPI; official schema validation passed | Tenant/vault/HTTPS endpoint, Teams app package and platform validation |
| Custom engine agent | Our LangGraph engine behind Microsoft Agents SDK | Python 3.14 SDK wrapper; actual local Agents Playground message routed to a paused case | Entra/tenant/Azure deployment and real-user validation |

Generate artifacts with `python scripts/ftm_m365.py`. Approval and rule mutations
are excluded from the model OpenAPI. The server/vault placeholders deliberately
cannot deploy. A future trusted Adaptive Card handler must authenticate the
human and re-fetch the digest; the local wrapper accepts no approvals. The
plugin vault must hold an agent-role key, and the generated model OpenAPI uses
the bounded case summary operation.

```bash
uv run --no-sync python -m follow_the_money m365 --workspace data/follow_the_money/my-demo/service --port 3978 --key-file data/follow_the_money/keys.txt
# Local development tool, installed separately at the pinned tested version:
npm install --prefix data/follow_the_money/playground --ignore-scripts --no-audit --no-fund @microsoft/m365agentsplayground@0.2.29
data/follow_the_money/playground/node_modules/.bin/agentsplayground -e http://127.0.0.1:3978/api/messages -c emulator --delivery-mode expectReplies --disable-telemetry --host 127.0.0.1 --port 56150
```

The local wrapper requires an agent key in the `X-FTM-Key` request header,
emulator + `expectReplies` and a loopback service URL. If the Playground client
cannot supply that header, start the server with the explicit `--allow-anonymous`
flag for a local demo; this is never the default. The default persistent quota
is five distinct trace requests per actor/conversation and 100 conversations
per workspace; retries do not consume additional slots, and restarts do not
reset quotas. `--max-cases-per-conversation` adjusts the first bound. Case reads
are limited to the same actor/conversation. The wrapper returns replies in the
HTTP response, and disables external connectors/OAuth. Playground commands:
`trace bitcoin syn_seed_a`, `trace tron syn_tron_seed`, `case <UUID>`.
[Phase 08](../progress/follow-the-money-08.md) records exactly what ran: actual
web/backend and SDK request, no browser visual inspection, tenant or Azure.
[Microsoft's SDK](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/agent-application)
and [Playground](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/test-with-toolkit-project)
document the local integration; the installed 1.9.0 SDK additionally requires
an explicit connection protocol, implemented here to deny OAuth.

## Operating limits

One local research workspace and portable lock serialize state changes. API
work has bounded input and per-case budgets; this is not a public multi-tenant
service. Stop servers after demonstrations. Use fresh paths for experiments;
never delete evidence just to make a rerun pass. Keep independent audit anchors
and back up the workspace as a unit while stopped. A database/anchor mismatch
fails closed and needs operator inspection, not automatic hash repair.

Blocked work and owners are in the [final report](../progress/follow-the-money-final.md).
No live TRON key, LLM provider, verified Elliptic licence, Windows runtime,
tenant/Azure deployment, production calibration or genuine analyst study is
claimed. The source branch was not pushed or merged. The review report records the
local Git handoff status and exact validation results.


Review implementation status: `live_features`, `score_address` with OOD fallback,
peel-chain claims, account signals and all three paginated freeze event types now
have tracing callers. Ordinary tracing uses amount-based heuristic priority;
TRON compares amounts across the outgoing page instead of assigning every branch
0.75. GNNs and the trained change classifier remain **library/experiment only**;
they do not drive ordinary search. Only `--learned-synthetic` injects the toy value
ranker. GAT AP 0.572325 versus base rate 0.516667 is near chance; its small
full-to-live drop is not meaningful robustness evidence (one seed, no CIs).

Acquisition refuses redirects and environment proxies. Every registered source
is pinned to its already-verified SHA-256, including checks when reusing cached
bytes. This review downloaded no data and made no live explorer calls.

Review rerun: the varied-signal change classifier has AP **0.828147**, ROC AUC
**0.786848**, accuracy **0.761905** (118 training / 42 test output rows). The
branching search reaches its endpoint in **16 queries with BFS**, **3 with
heuristic priority**, and **3 with the optional toy value policy**, at a common
budget of 32. The value model’s **0.358491** in-sample MAE compares with a
constant-mean baseline of **8.456747**, in hops-or-penalty units; all **17** probe
rows duplicate training features. The independent critic set retains **3/3**
supported cases and withdraws **5/5** planted errors. These are constructed
software checks, not real-world effectiveness estimates.
