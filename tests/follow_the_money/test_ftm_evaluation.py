import json
from pathlib import Path

import pytest


pytest.importorskip("pydantic")
pytest.importorskip("yaml")
pytest.importorskip("langgraph")
pytest.importorskip("langgraph.checkpoint.sqlite")
pytest.importorskip("portalocker")
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from follow_the_money.contracts import FtmError, Outspend, TxInput, TxOutput
from follow_the_money.clients import parse_bitcoin
from follow_the_money.evaluation import TASKS, evaluate, train_value_policy
from follow_the_money.fixtures import build_fixtures
from follow_the_money.gold import evaluate_gold, validate_gold_pair

CONFIG = Path(__file__).resolve().parents[2] / "config/follow_the_money"


def test_task_contract_is_frozen_and_documented():
    config = json.loads((CONFIG / "tasks.json").read_text(encoding="utf-8"))
    assert config["evidence_kind"] == "synthetic"
    assert [
        {k: row[k] for k in task} for row, task in zip(config["tasks"], TASKS)
    ] == list(TASKS)
    gold = json.loads((CONFIG / "gold-traces.json").read_text(encoding="utf-8"))[
        "traces"
    ]
    assert gold[0]["benchmark_eligible"] and len(gold[0]["source_sha256"]) == 64
    assert not gold[1]["benchmark_eligible"]
    assert all(row["txid"] is None for row in gold[1]["observations"])


def test_fixed_evaluation_censors_failures_and_preserves_human_boundary(tmp_path):
    report = evaluate(output=tmp_path / "evaluation", repeats=1, include_value=False)
    assert len(report["runs"]) == 6
    bfs = next(
        r
        for r in report["runs"]
        if r["task"] == "branching-service" and r["strategy"] == "bfs"
    )
    heuristic = next(
        r
        for r in report["runs"]
        if r["task"] == "branching-service" and r["strategy"] == "heuristic"
    )
    assert (
        not bfs["success"] and bfs["calls"] == 12 and bfs["calls_to_endpoint"] is None
    )
    assert heuristic["success"] and heuristic["calls_to_endpoint"] == 3
    assert all(
        r["network_calls"] == 0 and r["case_status"] == "awaiting_approval"
        for r in report["runs"]
    )
    assert (
        report["critic"]["false_claims_withdrawn"]
        == report["critic"]["planted_false_claims"]
    )
    assert report["memory"]["fp"] == report["memory"]["fn"] == 0


def test_value_policy_uses_disjoint_cases_and_rejects_real_addresses(tmp_path):
    pytest.importorskip("torch_geometric")
    pytest.importorskip("sklearn")
    score, result = train_value_policy(tmp_path / "value")
    assert not set(result["train_cases"]) & set(result["probe_cases"])
    assert len(set(result["graph_hashes"])) == 4
    assert result["train_rows"] == 51 and result["probe_rows"] == 17
    assert 0 <= result["in_sample_mae_hops_or_penalty"] < 3
    assert result["duplicate_probe_rows"] == 17 and result["novel_probe_rows"] == 0
    assert result["duplicate_probe_mae_hops_or_penalty"] == pytest.approx(
        result["in_sample_mae_hops_or_penalty"]
    )
    assert "not_temporal_validation" in result["split_kind"]
    assert "heldout_mae_calls" not in result
    item = {
        "address": "bc1example",
        "heuristic": 0.5,
        "hops": 1,
        "incoming_units": 1000000,
    }
    assert score(item, "bitcoin")["ood"]
    item["address"] = "syn_example"
    assert score(item, "tron")["ood"]
    assert 0 <= score(item, "bitcoin")["score"] <= 1


def test_variant_fixtures_keep_distinct_bitcoin_identifiers(tmp_path):
    a = build_fixtures(tmp_path / "a", variant=1)
    b = build_fixtures(tmp_path / "b", variant=2)
    assert a["seed"] != b["seed"] and a["graph_sha256"] != b["graph_sha256"]


def test_gold_validation_requires_exact_outpoint_and_units(make_tx, provenance):
    parent = parse_bitcoin(make_tx(), provenance)
    spend = parse_bitcoin(make_tx(2), provenance).model_copy(
        update={
            "inputs": (TxInput(txid=parent.txid, vout=0, prevout=parent.outputs[0]),),
            "outputs": (
                TxOutput(address="syn_exchange", value=9000, script_type="v0_p2wpkh"),
            ),
        }
    )
    outspend = Outspend(provenance=provenance, spent=True, txid=spend.txid, vin=0)
    expected = {
        "seed_txid": parent.txid,
        "seed_vout": 0,
        "spend_txid": spend.txid,
        "spend_vin": 0,
        "seed": parent.outputs[0].address,
        "seed_units": parent.outputs[0].value,
        "endpoint": "syn_exchange",
        "endpoint_vout": 0,
        "endpoint_units": 9000,
    }
    assert validate_gold_pair(parent, spend, outspend, expected)["verified"]
    for mutation in (
        {"seed_vout": 1},
        {"endpoint_units": 9001},
        {"spend_txid": "0" * 64},
    ):
        with pytest.raises(FtmError, match="differ"):
            validate_gold_pair(parent, spend, outspend, {**expected, **mutation})
    with pytest.raises(FtmError):
        validate_gold_pair(
            parent, spend, outspend.model_copy(update={"spent": False}), expected
        )


def test_redacted_gold_is_excluded_and_missing_public_cache_never_downloads(tmp_path):
    annotations = json.loads((CONFIG / "gold-traces.json").read_text(encoding="utf-8"))[
        "traces"
    ]
    assert (
        evaluate_gold(
            output=tmp_path / "blocked", cache=tmp_path, annotation=annotations[1]
        )["status"]
        == "blocked"
    )
    with pytest.raises(FtmError) as exc:
        evaluate_gold(
            output=tmp_path / "missing",
            cache=tmp_path / "empty-cache",
            annotation=annotations[0],
        )
    assert exc.value.code == "replay_miss"
