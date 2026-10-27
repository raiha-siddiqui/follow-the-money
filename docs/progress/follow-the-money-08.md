# Phase 08 — Microsoft 365 artifacts and local Playground, 2026-10-27

Goal: connect the custom LangGraph engine to Microsoft tooling without claiming
a tenant deployment. Files: `m365.py`, `scripts/ftm_m365.py`,
`config/follow_the_money/m365/*`, `test_m365.py` and this report. Dependencies:
Microsoft Agents SDK 1.9.0 (installed on Python 3.14), Agents Playground 0.2.29,
existing API/agent, current published schemas. No Azure subscription or tenant.

## What runs

`create_agent` uses real `AgentApplication`, `MemoryStorage` and `CloudAdapter`.
The LangGraph trace/checkpoint remains durable in TraceService; the SDK stores
only local conversational state. `LocalReplyFactory` permits buffered
`expectReplies` responses and rejects outbound connectors; `DisabledConnections`
rejects OAuth. `create_local_app` requires loopback, emulator and synchronous
reply mode. No key, login, callback to an external URL or paid service is used.
`trace bitcoin syn_seed_a` starts a bounded replay and emits a case summary and
Adaptive Card with case ID/digest and a link to the authenticated human UI.
Activity retries reuse a deterministic request UUID. Submitted cards cannot
approve. Source text/attachments cannot change commands or budget.

`ftm_m365.artifacts` generates full OpenAPI, a pruned model-tools OpenAPI, API
plugin, declarative-agent manifest and approval template. Human approval,
recovery and rule mutations are absent from the model tool surface. Copilot
Studio routing instructions connect name screening to Project 1 and wallet
tracing to Project 2. The standalone approval template is for a future trusted
host; it is **not wired** to the anonymous wrapper. It binds case/digest/decision
UUID and requires the host to authenticate the reviewer and re-fetch evidence.

## Commands and actual results

- `npm view @microsoft/m365agentsplayground version engines dist --json` initially
  failed EROFS on default npm cache; rerun with
  `npm_config_cache=~/pw-tools/npm-cache-p2` returned version **0.2.29**.
- `npm_config_cache=~/pw-tools/npm-cache-p2 npm install --prefix ~/pw-tools/playground-p2 --ignore-scripts --no-audit --no-fund @microsoft/m365agentsplayground@0.2.29`:
  **added 1 package in 3s**. Its Microsoft pre-release evaluation licence was
  inspected. No package bytes are redistributed. Tarball 5,039,076 bytes,
  SHA-256 `eda2faf616b407c72a9650b7b2d5d1de3f3ce0f976001157fd4e550d4178f427`.
- `~/pw-tools/venv-p2/bin/python scripts/ftm_m365.py`: generated six
  JSON artifacts and Studio instructions, deployment explicitly blocked.
- `jsonschema.validate` against downloaded official schemas: **declarative
  agent v1.9 valid; API plugin v2.4 valid**. Schema URLs, sizes and hashes are
  in the source manifest. This does not establish tenant acceptance.
- Serial offline `python -m pytest -q tests/follow_the_money/test_m365.py -p no:cacheprovider`:
  first 1 passed/1 failed in 5.72s (installed SDK needs a connection factory),
  second 1 passed/1 failed in 6.20s (explicit Authorization connection required),
  then **2 passed, 4 deprecation warnings in 6.69s** after implementing the
  deny-all local connection protocol. Tests use a real aiohttp SDK endpoint,
  test replay/idempotency, malicious callback and forged approval rejection.
- `python -m follow_the_money demo --workspace data/follow_the_money/demo-final-v1`:
  created a synthetic case paused at approval; no approval was submitted.
- `python -m follow_the_money m365 --workspace data/follow_the_money/demo-final-v1/service --port 3978`.
- `~/pw-tools/playground-p2/node_modules/.bin/agentsplayground -e http://127.0.0.1:3978/api/messages -c emulator --delivery-mode expectReplies --disable-telemetry --host 127.0.0.1 --port 56150`:
  **Listening on 56150**. Playground root and SDK health returned HTTP 200.
  A local HTTP client submitted `trace bitcoin syn_seed_a` through Playground's
  actual conversation endpoint: HTTP 200, new SDK-created case
  `d69cc3a6-4278-4c55-b1f8-4232918a3adc`, `awaiting_approval`, 12 critic outcomes,
  0 blockchain network calls, approval null. Receipt saved in
  `config/follow_the_money/m365/playground-receipt.json`.

The real Playground web app/backend ran and routed a message to the SDK. No
browser visual inspection, Teams chat, Copilot tenant invocation, publication,
Azure deployment or video recording was performed. The local servers were
stopped after the smoke test. The SDK adapter API warns of future deprecation;
this is pinned and covered by the real request test.

## Limits, ownership and recap

Generated server URL `https://deployment-required.invalid` and vault reference
are intentional placeholders. A tenant administrator must provide an approved
HTTPS deployment, identity/vault configuration, Teams app packaging and tenant
validation. The owner has no subscription, so this work is BLOCKED, not a
successful deployment. Current Studio instructions are committed artifacts,
not a published Studio agent. Git staging is blocked; coordinator commits.

The engineer built the custom-engine demonstration locally at phase 08 using
the installed SDK, tested actual requests, and generated reviewable manifests
so the analyst can assess the integration before any tenant work.
[SDK guidance](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/agent-application),
[Playground guide](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/test-with-toolkit-project),
[plugin schema](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/plugin-manifest-2.4),
[declarative schema](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/declarative-agent-manifest-1.9).
Next: final hardening, reproduction docs, serial full Project 2 tests, targeted
Project 1 regressions and the honest completion/BLOCKED report.


Review correction (2026-10-27): see the [per-finding review report](follow-the-money-review-fixes.md).
Tracing now calls peel/account/live-feature scoring, with explicit heuristic/OOD
fallback; the trained change classifier and GNNs remain library/experiment only.
Models use agent-role keys and bounded human-approved summaries. Human approvers
are separate from case creators and configured model actors. Playground requires
an agent key or explicit anonymous opt-in and persists conversation quotas.


Review regression coverage uses real local SDK HTTP requests with an agent key,
checks missing/wrong-role keys, and checks the explicit anonymous opt-in. A
persistent SQLite quota limits distinct traces to five per actor/conversation
by default and 100 conversations per workspace. Retry and restart checks prove
that those actions cannot reset limits. Case reads are conversation-scoped.
The regenerated Copilot tool OpenAPI calls the bounded summary operation;
approval, recovery, rules, memory revision and raw evidence are human-only.
The old Playground receipt remains explicitly historical; no tenant, Azure or
new browser-based Playground session was run in this repair.
