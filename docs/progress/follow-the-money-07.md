# Phase 07 — local interfaces, 2026-10-27

Goal: give analysts and tool clients the same durable service, with authenticated
human decisions and offline transports. Dependencies: installed FastAPI,
Streamlit, official MCP SDK 2.3.0, and Project 1 auth/observability utilities.

Files/functions:
- `security.py`: `LocalBoundary` authenticates hashed bearer keys, limits bodies
  to 64 KiB, rejects duplicate JSON keys, foreign Host/Origin and oversized input.
  `local_url` prevents the UI sending credentials to arbitrary destinations.
- `api.py`: `create_app` exposes replay tracing, cases, audit, digest-bound human
  approval, recovery, memory queries/rules/corrections/tombstones and metrics.
  Identity comes from the key, never request data. Viewer cannot mutate state.
  Errors omit rejected values and unexpected exception contents.
- `mcp_server.py`: official SDK stdio and streamable HTTP; `build_server` exposes
  start/read/list/audit verification/memory tools. No approval or rule-write
  tools. HTTP authenticates each request; stdio inherits the local operator's
  configured role. `case_summary` bounds and critic-filters model context.
- `ui.py`: real Streamlit tabs for trace, critic withdrawals, transaction
  evidence and memory; explicit reviewer acknowledgement and digest-bound
  approve/reject. It calls the HTTP API and does not edit workspace files.
- `__main__.py`: offline init/demo, keygen, API/MCP/UI/evaluation entry points.
  Servers bind loopback only. Demo stops at the real LangGraph interrupt.
- `test_interfaces.py`: auth, tamper/stale decision, retry, origin/body bounds,
  memory revisions, actual MCP transports, actual Streamlit AppTest review.
- `.github/workflows/follow-the-money.yml`: locked install, serial offline test
  job and lint/format. Prepared, not run on hosted GitHub. No push performed.

Commands/results in Linux mirror, one pytest process, numerical threads=1,
`PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`:
`~/pw-tools/venv-p2/bin/python -m pytest -q tests/follow_the_money/test_interfaces.py -p no:cacheprovider`
first **9 passed, 1 failed in 34.38s** (test used an old SDK list result shape),
then **10 passed in 44.89s** after using `ListToolsResult.tools`.
Ruff check and format passed for new files. The HTTP MCP smoke uses a real
loopback Uvicorn socket; stdio launches and closes a real SDK subprocess.
Streamlit AppTest connects to a real API, displays withdrawals and records a
human-test rejection. Every test server/thread is closed in cleanup.

Example: POST `/v1/cases` with `chain=bitcoin`, `seed=syn_seed_a` and a canonical
client UUID returns `status=awaiting_approval`, transaction-cited claims, critic
outcomes and an evidence digest. A stale digest returns `stale_approval`; a
viewer decision returns HTTP 403. An approved draft still has `sent=false`.

Limits: local single-workspace research service; bearer possession is attributed
identity, not proof of a person at a keyboard. Keep reviewer credentials away
from model clients. Model tool surfaces cannot approve. No public deployment,
production SSO, external monitoring collector or Windows runtime test is claimed.
MCP defaults follow the [official SDK transport guidance](https://py.sdk.modelcontextprotocol.io/run/deploy/).

Who/what/why/when/where/how: the engineer supplied analyst and model interfaces
at phase 07, in the local mirror, using one shared service and real transport
smokes to prevent inconsistent approval behavior. Git writes remain blocked;
coordinator owns staging/commits. Next is M365 artifact generation and the local
Agents SDK/Playground wrapper, with tenant deployment explicitly blocked.


Review correction (2026-10-27): see the [per-finding review report](follow-the-money-review-fixes.md).
Tracing now calls peel/account/live-feature scoring, with explicit heuristic/OOD
fallback; the trained change classifier and GNNs remain library/experiment only.
Models use agent-role keys and bounded human-approved summaries. Human approvers
are separate from case creators and configured model actors. Playground requires
an agent key or explicit anonymous opt-in and persists conversation quotas.


Review interface checks now exercise actual REST and streamable-HTTP MCP
requests against the merged Project 1 observability/auth interfaces. Model
clients receive agent keys and bounded case summaries; human mutations and raw
review evidence require an approver. A creator or configured model actor cannot
approve even with a human-role key. The opt-in paired P1 workspace/config flags
open the public ReviewService. Streamlit explicitly allows localhost and
127.0.0.1 while retaining loopback binding and disabled usage telemetry.
