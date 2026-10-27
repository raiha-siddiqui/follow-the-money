# Phase 05 — scoped long-term case memory

Implemented under the owner's end-to-end authorization. No new dependency.

## Files/functions and acceptance

`memory.py:CaseMemory` stores reviewed cases, capped cluster hypotheses, links
and analyst rules in a separate locked SQLite workspace. It reuses the P2 audit
ledger and P1 portable lock. Every materialized entry is verified against its
revision history. Namespaces isolate recall. `query_case_memory` finds exact
address overlap with a prior reviewed cluster and supplies source txids, case ID,
revision and evidence digest; it does not infer ownership.

`publish` excludes services/endpoints and unsupported cluster proofs.
`correct` records a disputed revision; disputed clusters/cases leave active
recall. `delete` creates a tombstone. Deleting a case suppresses its clusters.
`add_rule` allows only exact-address stop/annotation rules. Rules cannot enlarge
budgets, skip mandatory stops, approve claims or send anything.

`service.py` initializes/opens persistent memory. `agent.py` reads rules before
expansion, recalls prior clusters before review, and publishes only after
approval. `cases.py` includes memory context in the approval digest; publication
receipts remain separate so the reviewed digest stays stable. The report shows
reviewed memory context. `test_memory.py` covers the complete lifecycle.

## Commands and actual results

Pinned Ruff format/check: **All checks passed**. Mirrored with the Phase 01
rsync command. Then, from the Linux mirror:

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ~/pw-tools/venv-p2/bin/python -m pytest -q tests/follow_the_money/test_agent_service.py tests/follow_the_money/test_memory.py -p no:cacheprovider
```

**21 passed in 61.76s (0:01:01)**. Log:
`~/pw-tools/p2-phase05-tests.log`. One pytest process; no training job.

Example: approve a fictional `syn_seed_a` case, reopen the service, and start
`syn_partner`. The second proposal recalls the first case's common-input
hypothesis with txid evidence. Querying `syn_exchange` produces no cluster link.
Another namespace returns no links. A stop rule on the seed reduces calls to
zero; deleting that rule restores the synthetic three-call trace.

## Limits and next phase

Recall uses exact address overlap, not a learned claim of wallet identity.
Tombstones remove active recall; audit history remains and is not secure erasure.
Corrections do not rewrite transaction facts. A new review is required to replace
a disputed hypothesis. Large histories are scanned locally; production indexing,
retention policy and cryptographically authenticated anchors remain future work.
Git commits remain blocked by read-only metadata; coordinator owns committing.

What: persistent reviewed context. Why: notice recurring evidence without
joining unrelated service users. When: recall before review, publish after it.
Where: a named local memory scope. Who: analysts control edits. How: exact
identifiers, cited hypotheses, hard exclusions and revisioned audit records.

Next: fixed synthetic and court-evidence evaluation, fair BFS comparisons,
repeatability/critic/memory measures, and trace-derived value training.



Review correction (2026-10-27): stored case memory remains unchanged in shape;
the model-facing view now exposes bounded overlap identifiers and evidence
commitments without reviewer notes or rule text. Raw memory inspection and
revisions require the human approver boundary. Agent/model actors cannot use
those mutation routes. The 175-test Project 2 review run covers the bounded view
and role restrictions; final repository results are in the review-fixes report.
