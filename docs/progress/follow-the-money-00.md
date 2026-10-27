# Follow the Money — Phase 00: design and environment

Goal: define an end-to-end research implementation before application code.
The owner explicitly authorized the full phased task, dependencies, small
public downloads, bounded read-only Bitcoin calls and local commits.

## Files and design

- `docs/follow_the_money/plan.md`: scope and safety boundaries; execution DAG;
  phase-by-phase file/dependency/test matrix; separate synthetic, recorded and
  court-derived evidence; evaluation and blocker policy.
- `.gitignore`: excludes `data/follow_the_money/`, including downloaded
  toolchain sources, dataset bytes, caches and local results. Existing `data/`
  rules were selective, so this additional exclusion is necessary.
- This report records the preflight. No application functions exist yet.

## Actions actually run

Read `AGENTS.md`, the supplied reference extraction (including Project 2 in
full and M365), shared P1 environment notes, and inspected P1 contracts,
portable lock, service/workflow/nodes, audit chain, memory lookup/provider/store,
API auth/error/schema/settings, MCP policies/server/tools, observability and
stack. Earlier P1 completion reports describe limitations, not P2 results.

- `git status --short --branch`: failed, system Git rejects the
  `relativeworktrees` extension.
- `git.exe status --short --branch`: failed with WSL
  `UtilBindVsockAnyPort: socket failed 1`; Windows interop unavailable here.
- `git -c extensions.relativeWorktrees=false status --short --branch`: also
  failed; no repository config was changed.
- Downloaded Git 2.49.0 source from kernel.org (7,771,796 bytes, GPL-2.0-only,
  SHA-256 `618190cf590b7e9f6c11f91f23b1d267cd98c3ab33b850416d8758f8b5a85628`).
  Initial `make ... NO_CURL=YesPlease git` failed because OpenSSL headers are
  absent. Retried with `NO_OPENSSL=YesPlease` and locally extracted zlib dev
  package; final result recorded below. No system packages were installed.
- `UV_CACHE_DIR=~/pw-tools/uv-cache UV_PROJECT_ENVIRONMENT=~/pw-tools/qa-p2 ~/pw-tools/uvbin/bin/uv sync --locked --only-group qa --no-install-project --python 3.14`:
  succeeded, CPython 3.14.9, resolved 151 packages, installed 18 packages;
  includes Ruff 0.14.10. A first `uv python find` without the cache override
  failed on read-only home cache; explicit cache override succeeded.
- Queried PyPI JSON for wheel and Python metadata. Torch 2.14.1 and
  scikit-learn 1.9.1 publish CPython 3.14 Linux x86_64 and Windows amd64 wheels;
  torch-geometric 2.8.1 and Microsoft Agents hosting 1.9.0 publish universal
  wheels. CrewAI 1.15.30 declares `>=3.10,<3.14`: use a LangGraph critic.
  These checks do not yet prove all transitive dependencies install.
- Inspected publisher pages for Ransomwhere 1.1.0, GraphSense TagPacks, OFAC
  address extraction and Elliptic++; no dataset performance is claimed.

Tests: **0 application tests run** (design phase). No metrics computed.
Example: a case starts with a chain/address/budget; it ends in a critic-reviewed
packet awaiting human approval, with txids and an explicit evidence class.
This is the intended contract, not a demonstrated implementation yet.

## Why these boundaries matter (5W1H)

What: an auditable tracing prototype. Why: finite explorer budgets and noisy
ownership heuristics demand explicit uncertainty. When: replay-first during
development; live reads only in bounded recording commands. Where: separate
`follow_the_money` package and Linux test mirror. Who: software proposes leads;
a human approves drafts. How: typed evidence, budgeted tools, temporal learning,
critic, persisted interrupt and namespaced memory.

Next: Phase 01 implements the data contracts, replay transport and source
adapters, with wheel resolution, provenance receipts and offline tests.
Open risks: dataset licences/access, sparse court evidence, TRON key absent,
no tenant/subscription, and compatibility of transitive optional dependencies.

## Environment gate result

The Git 2.49.0 build succeeded (exit 0):

```bash
apt download zlib1g-dev
dpkg-deb -x zlib1g-dev_*.deb ~/pw-tools/git-p2-deps
make -C ~/pw-tools/git-p2-src -j4 NO_OPENSSL=YesPlease NO_GETTEXT=YesPlease NO_TCLTK=YesPlease NO_CURL=YesPlease ZLIB_PATH=~/pw-tools/git-p2-deps/usr BASIC_LDFLAGS=-L~/pw-tools/git-p2-deps/usr/lib/x86_64-linux-gnu git
```

Local Git is `~/pw-tools/git-p2-src/git`; this is an environment
deviation from git.exe, required because Windows interop fails. It is used
only for local repository work. A Python assertion check passed for all ten
phase entries, LF text and the data ignore rule.

Wheel-only resolution with `uv pip compile ~/pw-tools/p2-requirements.in
--python-version 3.14 --python-platform <platform> --only-binary :all:` succeeded
for `x86_64-pc-windows-msvc` (111 packages) and
`x86_64-unknown-linux-gnu` (128 packages). These are preflight dependency sets,
not the project's authoritative lock. The extra declarations and pinned lock
are Phase 01 work.

## Commit blocker

Git 2.49.0 read the branch and confirmed base `fb32c9f`, but
`git add .gitignore docs/follow_the_money/plan.md docs/progress/follow-the-money-00.md`
failed (exit 128): `Unable to create .../worktrees/Polyglot_watchlist-p2/index.lock:
Read-only file system`. No commit was created. The sandbox protects Git metadata
and this session cannot request escalation. Owner: environment/workspace owner.
Next action: grant write access to the existing worktree Git metadata, then
review and commit the phase changes locally. No attempt to bypass that protection
is made. The initial-commit ordering cannot be satisfied here; the checked plan
precedes all application code, and authorized source implementation continues.
