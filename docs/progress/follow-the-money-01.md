# Follow the Money — Phase 01: replay data and tools

## Goal and outcome

Build auditable, bounded data access before tracing or training. Typed Bitcoin
and USDT/TRC-20 adapters, a checked replay cache, source loaders and manifests
are implemented. The first complete Linux run passed **59 tests in 63.14s**.
A final rerun after tightening DNS blocking and response provenance is recorded
below. No model-quality metric has been computed.

## Files and functions

| File | Explanation |
|---|---|
| `src/follow_the_money/__init__.py` | Lightweight package identity. |
| `contracts.py` | `Record` rejects extra fields/coercion; `Provenance` binds source, retrieval date, hash, licence and evidence class; `TxOutput`, `TxInput`, `BitcoinTx`, `Outspend`, `Transfer`, `FreezeEvent`, `Label`, `Seed`, `Page` distinguish asset models. `strict_json` rejects duplicate/nonfinite JSON; `canonical`/`digest` define stable hashes; `FtmError` is the stable failure contract. Amounts are integer base units. |
| `transport.py` | `Budget.charge` counts logical queries and physical attempts separately under a thread lock. `ReplayCache.read/write` verifies URL identity and body hash, bounds bytes and atomically replaces files. `JsonTransport.get` fails closed on replay misses; recording only allows no-key Bitcoin hosts, GET, bounded retries and delays. Every received response is preserved; failed transport attempts are counted. `retry_delay` respects numeric/date Retry-After. |
| `clients.py` | `parse_bitcoin` preserves outpoints and scripts; `EsploraClient` exposes tx/address-page/outspends; TronGrid and TronScan normalize their distinct schemas, exact token amounts, success fields and cursors. Only the configured USDT contract is accepted. `get_freeze_events` reads a confirmed event fixture; an incomplete page fails explicitly. |
| `labels.py` | GraphSense inheritance, OFAC snapshot assertions, OpenSanctions wallet-only parsing; `LabelStore` keeps conflicting source assertions separately in SQLite. An OpenSanctions wallet is not automatically marked sanctioned. No owner is inferred. |
| `seeds.py` | `load_ransomwhere` reads v1.1.0, filters Bitcoin rows, preserves family conflicts, deduplicates exact address/family pairs. |
| `acquire.py` | Operator-only bounded streaming downloads, exclusive partial files, checksum receipts and reuse verification. Not an agent tool. |
| `scripts/ftm_record.py` | Operator-only no-key recording with a physical-request cap, explicit counts and manifest updates. Defaults to the published genesis transaction, not a personal wallet investigation. |
| `config/follow_the_money/{sources,manifest,dependencies,tasks}.json` | Pinned source locations, byte receipts/blockers, cross-platform wheel evidence, and fixed fictional task criteria before learning. |
| `tests/follow_the_money/` | Contract, replay, retry/budget, tampering, pagination, token, source, label and seed tests. Autouse guards block external DNS/sockets; loopback remains available for later transport tests. |
| `pyproject.toml`, `uv.lock` | Added optional `ftm`, `ftm-ml`, `ftm-m365` extras; wheel/sdist include the new package; Ruff scope covers its files. Pinned uv relocked successfully. |
| `Makefile` | Added Project 2 quality scope and test/evaluation/demo targets. Evaluation/demo commands are implemented in later phases. |

## Commands actually run and evidence

- `UV_CACHE_DIR=~/pw-tools/uv-cache ~/pw-tools/uvbin/bin/uv lock`: **170 packages resolved**; existing P1 pins retained, new optional dependencies added.
- `UV_CACHE_DIR=~/pw-tools/uv-cache UV_PROJECT_ENVIRONMENT=~/pw-tools/venv-p2 ~/pw-tools/uvbin/bin/uv sync --project ~/pw-p2-build --locked --dev --extra ftm --extra ftm-ml --extra ftm-m365 --python 3.14`: exit 0, authoritative lock installed into the separate environment.
- Wheel-only preflight: Linux **128 packages**, Windows **111 packages**. Windows runtime was **not run**. Linux runtime smoke: PyG `SAGEConv` and `GATConv` each returned shape `(3, 2)`; `MCPServer`, `AgentApplication`, `CloudAdapter` imports passed. Torch 2.14.1, PyG 2.8.1, sklearn 1.9.1, XGBoost 3.4.1, MCP 2.3.0, Agents hosting 1.9.0. Torch emitted a Python 3.14 TorchScript warning; this project does not use TorchScript.
- Mirror command: `rsync -a --delete --exclude .git --exclude .agents --exclude .aws --exclude .codex --exclude .venv --exclude .tools --exclude data --exclude __pycache__ /mnt/d/Projects/raiha/Polyglot_watchlist-p2/ ~/pw-p2-build/`.
- From that mirror: `PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ~/pw-tools/venv-p2/bin/python -m pytest -q tests/follow_the_money -p no:cacheprovider`: initial collection failed because a test-package `__init__.py` shadowed the application; removed the test package marker. Next full run: **59 passed in 63.14s**.
- `~/pw-tools/qa-p2/bin/python -m ruff check --config pyproject.toml src/follow_the_money tests/follow_the_money scripts/ftm_record.py`: **All checks passed**. `ruff format --check` with the same scope: **15 files already formatted**.
- From mirror, pinned `uv lock --check --offline`: exit 0, **170 packages**. `uv build --offline --no-build-isolation --python ~/pw-tools/venv-p2/bin/python --out-dir data/follow_the_money/phase01-dist`: built both `.tar.gz` and `.whl` successfully.
- `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 ~/pw-tools/venv-p2/bin/python -m follow_the_money.acquire --source ransomwhere-1_1_0 --source graphsense-binance --source graphsense-license --source ofac-btc --source ofac-tron`: five downloads succeeded, sizes/hashes in the manifest. Source download operations are counted separately from physical redirects, which urllib did not instrument.
- Real-source parser smoke loaded **11,178 Bitcoin seeds**, **2 GraphSense labels**, **532 Bitcoin OFAC labels**, **261 TRON OFAC labels**. These are row counts, not validated attribution/quality measures.
- `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 ~/pw-tools/venv-p2/bin/python scripts/ftm_record.py`: **2 logical calls, 2 physical HTTP requests, 0 errors**, under a cap of 4. Saved genesis transaction and outspends responses, each HTTP 200. A separate replay smoke used **2 logical calls, 0 network calls**.

## Example and provenance

Input: `EsploraClient(replay_transport).get_tx("4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b")`. <!-- pragma: allowlist secret -- public Bitcoin genesis transaction ID -->
Observed output: one genesis output of **5,000,000,000 satoshis**,
`evidence_kind=public_recording`; outspends returns one record. This tests
transport/parser behavior, not tracing performance.

Ransomwhere by Jack Cable, [Zenodo v1.1.0](https://zenodo.org/records/13999026),
CC BY 4.0: 5,572,091 bytes, SHA-256
`5c939f3f0d390813f78e649cdd5cd50dcac6ac286e8c9ba52206b273f761082d`.
The [GraphSense pack](https://github.com/graphsense/graphsense-tagpacks) and
[OFAC extractor/list](https://github.com/0xB10C/ofac-sanctioned-digital-currency-addresses)
retain published-source provenance; an old label is not proof of present control.
Raw downloads and replay responses stay under gitignored `data/follow_the_money/`.
Package-manager cache/environments use the owner's designated `pw-tools` paths.

## Limitations and blockers

- Address validation enforces safe path shape, not blockchain checksums; fiction
  is explicitly supported. No balance conservation or taint model exists yet.
- Pagination is explicit. Full mempool pages, unavailable next pages and capped
  event pages are incomplete evidence, not an empty or exhaustive graph.
- Token event indices may be absent in upstream indexed APIs. Preserve that
  absence; do not claim a raw log index or sum repeated events as unique funds.
- Source import functions consume the operator-supplied provenance receipt;
  acquisition verifies bytes before receipt reuse. They do not establish label truth.
- Only two public Bitcoin responses were recorded; no ransomware crawl or gold
  trace result is claimed. TRON is fixture-only; no keys were used.
- Elliptic2 public metadata: **25,805,701,153 bytes**, above the 2 GB limit.
  Elliptic++ Drive is readable but dataset licence is unverified. OpenSanctions
  live-data permission is also unestablished. Owners and next actions are in
  the manifest. Real ML results remain blocked; synthetic verification follows.
- CrewAI 1.15.30 requires Python `<3.14`; the authorized LangGraph critic
  alternative will be used. No Microsoft tenant/Azure deployment is available.
- Local commits remain blocked by the sandbox's read-only Git metadata (Phase
  00). No push or merge was attempted; source changes are reviewable in place.

## 5W1H and next phase

What: typed replay tools. Why: evidence must be repeatable before evaluating an
agent. When: tests/demos replay; an operator explicitly records public data.
Where: the new package, configs and Linux test mirror. Who: analysts inspect
published assertions; software does not identify people. How: exact units,
source hashes, explicit pages, separate budgets and offline tests.

Next: capped common-input hypotheses, conservative CoinJoin/service stops,
probabilistic change estimates, peel continuity and account-model signals.

Final Phase 01 rerun: **59 passed in 96.66s (0:01:36)**; exit 0.


Review reproduction note (2026-10-27): the historical mirror command above used
an overly broad `--exclude data`. Do not reuse it: the corrected command uses
`--exclude /data`, retaining `src/watchlist/data`. This repair verified that the
packaged synthetic data is present and byte-checked it in packaging tests. The
seven registered source hashes were checked against existing local receipts and
bytes; acquisition now refuses redirects/proxies and verifies cached-byte pins.
