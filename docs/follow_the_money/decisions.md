# Implementation decisions and deviations

- Use separate `follow_the_money` package. Reuse Project 1's public locking,
  auth and observability utilities; call its v2 service for published sanctioned
  names. Do not edit P1's source-fingerprinted v1 agent.
- Replay is mandatory for tracing services/tests. Explicit recording is a
  separate operator command with endpoint allowlist, caps, cache and receipts.
  TronGrid/TronScan stay fixture-only because there is no key/live validation.
- PyTorch Geometric installs for Linux/Windows CPython 3.14; use actual SAGEConv
  and GATConv. Windows wheel resolution is not a Windows execution test.
- Elliptic real-data training is blocked by access/licence/size constraints.
  Synthetic temporal graph/weak-change experiments verify mechanics. No real
  illicit/licit accuracy or calibration claim is made. Feature proxies are
  generated; their live definitions are separately implemented and tested.
- CrewAI 1.15.30 excludes Python 3.14. Use an actual independent LangGraph critic
  subgraph. It recomputes support and supplies an alternative explanation for
  every claim; deterministic behavior does not require an LLM key.
- A provider-specific LLM adapter/ablation is not run. Optional untrusted rank
  proposals are constrained and audited; model callbacks cannot widen budgets,
  forge evidence or approve. No model-generated claim prose is accepted.
- GraphSAGE/GAT predict on temporal graphs; no synthetic model is deployed on
  real wallets. The own-trace learned value policy is integrated into the
  fictional search evaluation and optional CLI demonstration. Services default
  to heuristics until a suitable policy is injected and independently validated.
  This is a deliberate deviation from blindly promoting a GNN into live search.
- Value training now requires completed reviewed cases. Its initial experiment
  used completed searches still awaiting approval; final hardening changed this
  to explicit **simulated** fixture approval and critic-retained targets before
  the final rerun. No real human review is fabricated.
- Colonial's published affidavit lacks usable full addresses/txids. Retain it
  as documentary fixture evidence but exclude it from endpoint metrics. Use a
  separate cited 2025 DOJ public pair for a one-hop replay benchmark. Both
  policies take one query there; no real efficiency improvement is asserted.
- SQLite checkpoints plus audited operation reservations support interrupted
  recovery. Audit hash + separate local anchor are tamper evidence, not signed
  authenticity. A crash between database commit and anchor write fails closed
  for operator inspection. No automatic repair fabricates a valid history.
- Human approval exists only in authenticated API/UI/service operations, never
  in MCP or generated model actions. Approval means reviewed research output,
  not sending a request. Drafts always retain `sent=false`.
- M365 SDK 1.9.0 works on 3.14 with an explicit disabled connection protocol and
  SDK anonymous buffered replies behind our agent-key authentication boundary.
  Anonymous HTTP access requires explicit opt-in and persistent quotas. Actual Playground 0.2.29 routes a local message;
  tenant/Azure/Teams publication is blocked. Generated v1.9/v2.4 manifests were
  checked against the fetched official schemas, not accepted by a tenant.
- Initial delivery was subsequently committed as `d440a0e` and merged with main
  at `d91e372`. The original sandbox Git limitation below is historical.
- Local Git 2.49 can read this repository; system 2.43 cannot. Windows Git
  interop failed. The sandbox exposes worktree metadata read-only, so even the
  required plan-first commit could not be written. The owner authorized leaving
  changes uncommitted for the coordinator. No push/merge occurred.
