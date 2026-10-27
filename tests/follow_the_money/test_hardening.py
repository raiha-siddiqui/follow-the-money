import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest

pytest.importorskip("pydantic")
pytest.importorskip("yaml")
pytest.importorskip("langgraph")
pytest.importorskip("langgraph.checkpoint.sqlite")
pytest.importorskip("portalocker")
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("numpy")

import numpy as np

from follow_the_money.cases import TraceRequest, make_claim
from follow_the_money.clients import EsploraClient, TronGridClient, parse_bitcoin
from follow_the_money.contracts import FtmError, USDT_TRON, digest
from follow_the_money.critic import challenge
from follow_the_money.evaluation import trace_value_rows
from follow_the_money.fixtures import build_fixtures
from follow_the_money.scoring import DistributionGuard, score_address
from follow_the_money.service import TraceService
from follow_the_money.transport import Budget, JsonTransport, ReplayCache, request_url


def test_critic_malformed_transfer_is_withdrawn_without_crashing(make_tx, provenance):
    tx = parse_bitcoin(make_tx(), provenance)
    claim = make_claim(
        "transfer",
        "bitcoin",
        (tx.txid,),
        ("syn_seed_a", "syn_next"),
        amount=10000,
        output_index=0,
    )
    claim["addresses"] = ["syn_seed_a"]
    claim["claim_id"] = digest({k: v for k, v in claim.items() if k != "claim_id"})
    outcome = challenge(
        claim, {tx.txid: [{"chain": "bitcoin", "value": tx.to_dict()}]}, []
    )
    assert (
        not outcome["retained"] and outcome["reason"] == "malformed_claim_or_evidence"
    )


def test_model_exception_falls_back_without_leaking_details():
    guard = DistributionGuard.fit(
        np.array([[0.0], [1.0]]), chain="bitcoin", feature_names=["x"]
    )

    def broken(x):
        raise RuntimeError("sensitive model internals")

    result = score_address(
        [0.5],
        guard=guard,
        predict=broken,
        chain="bitcoin",
        feature_names=["x"],
        heuristic=0.4,
    )
    assert (
        result["ood"] and result["score"] == 0.4 and result["reason"] == "model_error"
    )


def test_address_page_cannot_inject_unrelated_transaction(tmp_path, make_tx):
    cache = ReplayCache(tmp_path)
    cache.write(
        "https://mempool.space/api/address/syn_other/txs",
        200,
        json.dumps([make_tx()]).encode(),
        evidence_kind="synthetic",
        license="fictional",
    )
    with pytest.raises(FtmError, match="unrelated"):
        EsploraClient(JsonTransport(cache, Budget(1))).get_address_txs("syn_other")


@pytest.mark.parametrize("mutation", ["full_page", "wrong_contract"])
def test_freeze_incomplete_or_wrong_contract_fails_closed(tmp_path, mutation):
    event = {
        "transaction_id": "a" * 64,
        "result": {"_user": "syn_tron_seed"},
        "event_name": "AddedBlackList",
        "block_timestamp": 1700000000000,
    }
    rows = (
        [event] * 200
        if mutation == "full_page"
        else [{**event, "contract_address": "wrong"}]
    )
    cache = ReplayCache(tmp_path)
    url = request_url(
        "https://api.trongrid.io",
        f"/v1/contracts/{USDT_TRON}/events",
        {"only_confirmed": "true", "event_name": "AddedBlackList", "limit": 200},
    )
    cache.write(
        url,
        200,
        json.dumps({"success": True, "data": rows}).encode(),
        evidence_kind="synthetic",
        license="fictional",
    )
    with pytest.raises(FtmError):
        TronGridClient(JsonTransport(cache, Budget(1))).get_freeze_events()


def test_case_catalogue_checks_headers_and_value_labels_need_review(tmp_path):
    f = build_fixtures(tmp_path / "fixtures")
    service = TraceService.initialize(
        tmp_path / "service", cache=Path(f["cache"]), labels=Path(f["labels"])
    )
    view = service.start_case(
        TraceRequest(chain="bitcoin", seed="syn_seed_a", request_id=str(uuid4())),
        actor="test",
    )
    with pytest.raises(ValueError, match="reviewed"):
        trace_value_rows(view["state"], "syn_exchange", split="train")
    with sqlite3.connect(service.root / "ledger.sqlite") as connection:
        connection.execute("UPDATE cases SET actor='forged'")
    with pytest.raises(FtmError, match="header"):
        service.list_cases()
