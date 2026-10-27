# Phase 09 — hardening, reproduction and final verification, 2026-10-27

Goal: finish the research prototype's local scope, verify reproducible evidence,
and leave a precise handoff for inaccessible external work. Dependencies are the
previous phases; no additional model/data/tenant permission is assumed.

## Files and functions

- `acquire.acquire`: reserve a partial download before opening the network and
  delete only the file this invocation owns. Another writer's partial survives.
- `critic.challenge`: malformed claim/evidence resets support to false; a
  one-address transfer cannot crash the critic or retain an earlier true result.
- `clients`: Bitcoin address pages reject unrelated transactions; freeze events
  reject full/incomplete and wrong-contract pages. Non-object TRON responses
  produce typed errors. `security.LocalBoundary` accepts case-insensitive Bearer.
- `models.score_address`: failed prediction falls back without exposing model
  exception details. `TraceService.list_cases` verifies header/state integrity.
- `evaluation.trace_value_rows/train_value_policy`: require completed reviewed
  cases, explicitly simulate fictional reviews, use critic-retained target
  edges and keep training/probe case IDs separate (feature rows duplicate). The prior experiment used
  completed searches still pending review; this correction is documented.
- `__main__`: optional `demo --learned-synthetic` trains on separate fictional
  traces and uses the learned value ranker; the demonstration pauses for review.
- `test_hardening.py`, client/interface/acquisition tests: adversarial regressions.
- `tests/test_packaging.py`: expected package bytes now cover **both** packages;
  canonicalize dependency names for standard metadata comparisons. No P1
  application code was changed.
- `Makefile`: fresh timestamped Project 2 demo/evaluation output paths.
- top-level README and `docs/follow_the_money/{README,data-card,model-card,decisions}.md`:
  both projects, commands, evidence semantics, architecture, model limits, M365
  comparison, actual local integration and remaining owners/actions.
- `source-verification.json`: SHA-256 receipts for 47 source/test/script files;
  result/provenance JSON and final report preserve measured outcomes.

## Commands and exact results

Source: `/mnt/d/Projects/raiha/Polyglot_watchlist-p2`. Linux mirror:
`~/pw-p2-build`. Interpreter: `~/pw-tools/venv-p2/bin/python`.
Every pytest/evaluation command used:

```bash
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
```

One pytest process at a time; no torch-heavy job overlapped a suite. Playground
and SDK servers were stopped; connection checks on ports 3978 and 56150 both
returned `connect_ex=111` (closed).

`python -m pytest -q tests/follow_the_money -p no:cacheprovider`:
**130 passed, 114 warnings in 120.00s**, then after the final malformed-response
and Bearer hardening, **133 passed, 114 warnings in 85.91s**. Warnings are
upstream TorchScript/PyG typing and SDK adapter deprecations, not skipped tests.
Final log: `~/pw-tools/p2-final-tests-v2.log`.

The initial P1 regression run returned **316 passed, 14 failed, 28 errors in
136.11s**. Investigation found the mirror command's unanchored `--exclude data`
had omitted the packaged `src/watchlist/data/synthetic_entities.json`; it was
not missing from the worktree. Packaging assertions also assumed one package
and case-sensitive dependency names. The corrected mirror command is:

```bash
rsync -a --delete --exclude .git --exclude .agents --exclude .aws --exclude .codex --exclude .venv --exclude .tools --exclude /data/ --exclude __pycache__ /mnt/d/Projects/raiha/Polyglot_watchlist-p2/ ~/pw-p2-build/
```

The same regression selection then passed **358 tests in 176.01s**, with
`WATCHLIST_WHEELHOUSE=~/pw-tools/wheelhouse`,
`QA_PYTHON=~/pw-tools/qa-p2/bin/python`,
`UV=~/pw-tools/uvbin/bin/uv`,
`UV_CACHE_DIR=~/pw-tools/uv-cache`:

```bash
python -m pytest -q tests/test_api_auth.py tests/test_observability.py tests/test_review_v2_contracts.py tests/test_review_v2_service.py tests/test_review_v2_recovery.py tests/test_review_v2_portability.py tests/test_review_v2_concurrency.py tests/test_packaging.py tests/test_project_checks.py -p no:cacheprovider
```

This is **491 passing tests in the final selections**, not a claim to have rerun
the entire approximately 3,500-test Project 1 repository suite. Packaging checks
include exact bytes/resources, RECORD hashes, offline clean installation and
identical wheel rebuild from sdist. A separate installed-package smoke outside
the repo imported `follow_the_money` 0.1.0 and ran its `--help`, both exit 0.

`UV_CACHE_DIR=~/pw-tools/uv-cache ~/pw-tools/uvbin/bin/uv lock`:
**resolved 170 packages in 89ms**. `uv lock --check --offline` also passed.
`~/pw-tools/qa-p2/bin/ruff check --config pyproject.toml`:
**All checks passed**. `ruff format --check --config pyproject.toml`:
**183 files already formatted**. JSON configuration parsed and LF-only checks
passed; final receipt includes the final documentation inventory.

```bash
UV_CACHE_DIR=~/pw-tools/uv-cache ~/pw-tools/uvbin/bin/uv build --offline --no-build-isolation --python ~/pw-tools/venv-p2/bin/python --out-dir data/follow_the_money/dist-final
```

Built wheel and sdist successfully. Wheel 719366 bytes,
SHA-256 `b5b1438fb4bd6a52f5b92c393b7accc9647a2bc49e9e7a86c42f56ca5b69ed6f`;
sdist 771603 bytes,
SHA-256 `19fe0ea29c782023ca13e351dbebde7a65f3e95d02711936d1f9da4a0c070d4e`.
The build contains the implementation and README at that build point; subsequent
progress-report/result receipts do not change packaged application source.

## Git and handoff

Compatible Git 2.49 reports branch `project-2`, HEAD
`fb32c9f93fa0f76becd4017eb44cd741d2aaf583`. `git add --
docs/follow_the_money/plan.md` still exits 128: cannot create the worktree
`index.lock`, **Read-only file system**. No P2 commit, push or merge was made.
The owner explicitly authorized this uncommitted handoff. Modified tracked
files: `.gitignore`, `Makefile`, `README.md`, `pyproject.toml`, `uv.lock`,
`tests/test_packaging.py`. New files: the P2 package/tests/config/docs/progress
folders, `.github/workflows/follow-the-money.yml`, `scripts/ftm_record.py` and
`scripts/ftm_m365.py`. The coordinator must review/stage/commit them, including
the plan. Use the requested `Co-Authored-By: GPT 6 Astra <noreply@openai.com>`
trailer. Raw `data/` and tool environments remain excluded.

The engineer completed this local research scope at phase 09 using serial
verification and explicit provenance, for an analyst who retains the decision.
The final report records final evaluation reruns and external blockers with
owners and next actions. No subsequent implementation phase is pending locally.

## Final evaluation and example receipts

`python -m follow_the_money.evaluation --output data/follow_the_money/evaluation-final --repeats 3`
completed **27 synthetic runs**. BFS / heuristic / learned-value success and
pass^3 are 2/3, 3/3, 3/3; all three have identical behavior over repeats on each
task. Mean queries 5, 2, 2; median latency **0.352978343000359,
0.35482132300057856, 0.34618376700018416 seconds**. All tool queries satisfy
schemas; no physical API calls and external service cost $0. The branching
fixture is censored at BFS's 12-query budget versus 3 for both priorities.
Critic: 12/12 supported retained, 10/10 planted amount errors withdrawn. Memory:
TP=1, FP=0, FN=0, TN=3. Value graph-distance MAE **0.3584913178917404** on 17
duplicate probe rows after training on 51 rows from three explicitly simulated reviewed
cases. Renamed isomorphic graphs are not independent real-world generalization.

The final public replay was run with this exact inline Python body (same
interpreter/environment, from the Linux mirror):

```python
import json
from pathlib import Path
from follow_the_money.gold import evaluate_gold
annotation = json.loads(Path('config/follow_the_money/gold-traces.json').read_text())['traces'][0]
report = evaluate_gold(output=Path('data/follow_the_money/public-gold-final'), cache=Path('data/follow_the_money/replay-public'), annotation=annotation, repeats=3)
print(json.dumps({'runs': report['runs'], 'pass_k': report['pass_k'], 'validation': report['validation']}, indent=2))
```

**Six successful runs**, BFS and priority **1 query** each, pass^3 true, 0
physical API calls, 4 retained/0 withdrawn claims per run, all awaiting approval.
Exact funding/spend/outpoint/124016260-satoshi output validation passed. Three
replay validation queries are accounted separately. Public labels are historical
court assertions, not current ownership. No real case was approved.

`python -m follow_the_money demo --learned-synthetic --workspace data/follow_the_money/learned-demo-final`:
exit 0; `status=awaiting_approval`, calls=3/max=12, network_calls=0. All three
visited frontier entries used `method=learned_trace_value`, OOD false; no real
wallet model or approval was inferred.

Final result files are `config/follow_the_money/evaluation-results.json`
(SHA-256 `253b378bf85e14a09085dd3e0a3f9380d8d6f770676ec645bf94594cdb2a1add`)
and `public-gold-results.json`
(`b4e29c4424364040ddd985bff22640d2bda7a29eed861c1688028cab59edb6f3`).
Final wheel bytes match **154 package files** in the source worktree. All **47**
source/test/script receipts match the worktree and Linux mirror; source-set hash
`8a7af2a7fc82d4e800f312da9050d32da3dcb29c4bd4c44ef3b2e4c1db8baa8b`.

Final text inventory: **86 files LF-only**, **17 configuration JSON files parsed**;
11 phase/final reports exist. Final report and verification receipts were written.


Review correction (2026-10-27): historical metrics above are superseded by the
[review-fixes report](follow-the-money-review-fixes.md) and regenerated result
JSON. The old value MAE is in-sample because probe features duplicate training;
build-time timestamps did not provide temporal validation. The original perfect
change-classifier scores were tautological. GAT is near chance, with one seed and
no CIs. pass^k equals pass^1 in deterministic replay; schema self-consistency is
not independent tool accuracy. Rechecking critic-kept claims is circular; the
review adds independent planted error types and an adequate-budget BFS run.
The trained change classifier and GNNs remain library/experiment only.
