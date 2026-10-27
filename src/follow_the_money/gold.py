"""Court-cited trace validation and replay-only public benchmark."""

from __future__ import annotations

import json
from pathlib import Path
import time
from uuid import uuid4

from follow_the_money.cases import TraceRequest
from follow_the_money.clients import EsploraClient
from follow_the_money.contracts import BitcoinTx, FtmError, Label, Outspend, Provenance
from follow_the_money.labels import LabelStore
from follow_the_money.service import TraceService
from follow_the_money.transport import Budget, JsonTransport, ReplayCache


def validate_gold_pair(
    parent: BitcoinTx, spend: BitcoinTx, outspend: Outspend, expected: dict
) -> dict:
    """Verify exact UTXO continuity/units without accepting attribution assertions."""
    try:
        output = parent.outputs[expected["seed_vout"]]
        item = spend.inputs[expected["spend_vin"]]
        endpoint = spend.outputs[expected["endpoint_vout"]]
        valid = (
            parent.confirmed
            and spend.confirmed
            and parent.txid == expected["seed_txid"]
            and spend.txid == expected["spend_txid"]
            and output.address == expected["seed"]
            and output.value == expected["seed_units"]
            and (item.txid, item.vout) == (parent.txid, expected["seed_vout"])
            and item.prevout == output
            and endpoint.address == expected["endpoint"]
            and endpoint.value == expected["endpoint_units"]
            and outspend.spent
            and (outspend.txid, outspend.vin) == (spend.txid, expected["spend_vin"])
        )
    except (IndexError, KeyError, TypeError):
        valid = False
    if not valid:
        raise FtmError(
            "gold_mismatch",
            "Recorded transaction facts differ from the cited gold annotation",
        )
    return {
        "verified": True,
        "funding_txid": parent.txid,
        "funding_vout": expected["seed_vout"],
        "spend_txid": spend.txid,
        "endpoint_units": endpoint.value,
        "ownership_verified": False,
        "source_response_hashes": [
            parent.provenance.sha256,
            spend.provenance.sha256,
            outspend.provenance.sha256,
        ],
    }


def evaluate_gold(
    *, output: Path, cache: Path, annotation: dict, repeats: int = 3
) -> dict:
    if not annotation.get("benchmark_eligible"):
        return {"status": "blocked", "reason": annotation["reason"]}
    if not 1 <= repeats <= 5:
        raise ValueError("repeats must be 1..5")
    output.mkdir(parents=True, exist_ok=True)
    budget = Budget(3)
    client = EsploraClient(JsonTransport(ReplayCache(cache), budget))
    parent = client.get_tx(annotation["seed_txid"])
    spend = client.get_tx(annotation["spend_txid"])
    spent = client.get_outspends(parent.txid)[annotation["seed_vout"]]
    if any(
        p.evidence_kind != "public_recording"
        for p in (parent.provenance, spend.provenance, spent.provenance)
    ):
        raise FtmError(
            "wrong_evidence_class",
            "Public benchmark requires recorded public responses",
        )
    verified = validate_gold_pair(parent, spend, spent, annotation)
    labels = LabelStore(output / "labels.sqlite")
    labels.initialize()
    source = Provenance(
        source_url=annotation["source_url"],
        retrieved_at=annotation["source_retrieved_at"],
        sha256=annotation["source_sha256"],
        license=annotation["source_license"],
        evidence_kind="court_document",
    )
    labels.add(
        [
            Label(
                chain="bitcoin",
                address=annotation["endpoint"],
                label=annotation["endpoint_label"],
                category="exchange",
                source_ref=annotation["citation"],
                provenance=source,
            )
        ]
    )
    runs = []
    for strategy in ("bfs", "priority"):
        for repeat in range(repeats):
            service = TraceService.initialize(
                output / f"{strategy}-{repeat}", cache=cache, labels=labels.path
            )
            request = TraceRequest(
                chain="bitcoin",
                seed=annotation["seed"],
                seed_txid=annotation["seed_txid"],
                seed_vout=annotation["seed_vout"],
                max_calls=annotation["max_calls"],
                max_hops=annotation["max_hops"],
                strategy=strategy,
                request_id=str(uuid4()),
            )
            start = time.perf_counter()
            state = service.start_case(request, actor="public-fixture-evaluator")[
                "state"
            ]
            elapsed = time.perf_counter() - start
            reached = any(
                e["address"] == annotation["endpoint"]
                and e["txid"] == annotation["spend_txid"]
                for e in state["endpoints"]
            )
            retained = {c["claim_id"] for c in state["critic"] if c["retained"]}
            supported = any(
                c["kind"] == "transfer"
                and c["claim_id"] in retained
                and c["txids"] == [annotation["spend_txid"]]
                and c["addresses"][1] == annotation["endpoint"]
                and c["amount"] == annotation["endpoint_units"]
                for c in state["claims"]
            )
            runs.append(
                {
                    "strategy": strategy,
                    "repeat": repeat,
                    "success": reached and supported,
                    "calls_to_endpoint": state["budget"]["calls"]
                    if reached and supported
                    else None,
                    "calls": state["budget"]["calls"],
                    "network_calls": state["budget"]["network_calls"],
                    "latency_seconds": elapsed,
                    "case_status": state["status"],
                    "critic_claims": len(state["critic"]),
                    "withdrawn_claims": sum(not c["retained"] for c in state["critic"]),
                }
            )
    report = {
        "schema": "ftm-public-gold-v1",
        "evidence_kind": "public_recording",
        "annotation_id": annotation["id"],
        "citation": annotation["citation"],
        "source_url": annotation["source_url"],
        "source_sha256": annotation["source_sha256"],
        "validation": verified,
        "validation_calls_separate_from_tracing": budget.snapshot(),
        "runs": runs,
        "k": repeats,
        "pass_k": {
            s: all(r["success"] for r in runs if r["strategy"] == s)
            for s in ("bfs", "priority")
        },
        "notice": "Deterministic replay makes pass^k equal pass^1. One publicly documented hop with a supplied historical service label. Priority uses its heuristic/OOD fallback; no synthetic model is applied to real addresses. No human approval or account ownership is claimed.",
    }
    (output / "results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report
