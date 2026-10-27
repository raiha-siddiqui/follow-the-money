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

from follow_the_money.cases import Approval, TraceRequest
from follow_the_money.contracts import FtmError, digest
from follow_the_money.fixtures import build_fixtures
from follow_the_money.memory import CaseMemory
from follow_the_money.service import TraceService


@pytest.fixture
def service(tmp_path):
    fixture = build_fixtures(tmp_path / "fixtures")
    return TraceService.initialize(
        tmp_path / "workspace",
        cache=Path(fixture["cache"]),
        labels=Path(fixture["labels"]),
    )


def start(service, seed="syn_seed_a"):
    return service.start_case(
        TraceRequest(chain="bitcoin", seed=seed, request_id=str(uuid4())),
        actor="analyst",
    )


def approve(service, view):
    return service.submit_approval(
        view["case_id"],
        Approval(
            request_id=str(uuid4()),
            evidence_sha256=view["state"]["evidence_sha256"],
            decision="approve",
        ),
        actor="reviewer",
    )


def test_restarted_case_flags_reviewed_cluster_not_service(service):
    first = start(service)
    assert service.memory.entries() == []
    finished = approve(service, first)
    assert finished["state"]["memory"]["clusters"] == 1
    second = start(TraceService(service.root), "syn_partner")
    links = second["state"]["memory_context"]["links"]
    assert links and links[0]["prior_case_id"] == first["case_id"]
    assert links[0]["txids"]
    assert service.memory.query_case_memory("bitcoin", ["syn_exchange"])["links"] == []
    approved = approve(service, second)
    assert approved["state"]["memory"]["links"] == 1
    assert any(e["kind"] == "link" for e in service.memory.entries())
    from follow_the_money.cases import proposal_payload

    assert (
        digest(proposal_payload(approved["state"]))
        == approved["state"]["evidence_sha256"]
    )


def test_rejected_and_foreign_namespaces_never_enter_recall(service):
    view = start(service)
    service.submit_approval(
        view["case_id"],
        Approval(
            request_id=str(uuid4()),
            evidence_sha256=view["state"]["evidence_sha256"],
            decision="reject",
        ),
        actor="reviewer",
    )
    assert not service.memory.entries()
    approve(service, start(service))
    foreign = CaseMemory(service.root / "memory", "other-team")
    assert foreign.query_case_memory("bitcoin", ["syn_partner"])["links"] == []
    assert service.memory.query_case_memory("tron", ["syn_partner"])["links"] == []
    assert (
        service.memory.query_case_memory(
            "bitcoin", ["syn_partner"], blocked_members=["syn_seed_a"]
        )["links"]
        == []
    )


def test_correction_removes_disputed_cluster_from_active_recall(service):
    approve(service, start(service))
    cluster = next(e for e in service.memory.entries() if e["kind"] == "cluster")
    updated = service.memory.correct(
        cluster["id"],
        expected_revision=1,
        note="Collaborative spend explanation requires re-review",
        actor="reviewer",
    )
    assert updated["revision"] == 2
    assert service.memory.query_case_memory("bitcoin", ["syn_partner"])["links"] == []
    with pytest.raises(FtmError, match="Stale"):
        service.memory.correct(
            cluster["id"], expected_revision=1, note="stale", actor="reviewer"
        )
    service.memory.delete(
        cluster["id"],
        expected_revision=2,
        reason="Withdrawn hypothesis",
        actor="reviewer",
    )
    assert all(e["id"] != cluster["id"] for e in service.memory.entries())
    assert any(
        e["id"] == cluster["id"] and e["deleted"]
        for e in service.memory.entries(include_deleted=True)
    )


def test_case_tombstone_suppresses_its_clusters(service):
    view = approve(service, start(service))
    service.memory.delete(
        "case:" + view["case_id"],
        expected_revision=1,
        reason="Remove from active recall",
        actor="reviewer",
    )
    assert service.memory.query_case_memory("bitcoin", ["syn_partner"])["links"] == []


def test_analyst_rule_can_only_restrict_and_is_bound_to_approval(service):
    for action in ("send", "increase_budget", "ignore_coinjoin"):
        with pytest.raises(FtmError):
            service.memory.add_rule(
                chain="bitcoin",
                address="syn_seed_a",
                action=action,
                text="untrusted instruction",
                actor="reviewer",
            )
    rule = service.memory.add_rule(
        chain="bitcoin",
        address="syn_seed_a",
        action="stop",
        text="Pause this branch for manual review",
        actor="reviewer",
    )
    result = start(service)["state"]
    assert result["budget"]["calls"] == 0
    assert result["memory_context"]["rules"][0]["id"] == rule["id"]
    assert any(t["reason"] == "analyst_stop_rule" for t in result["trace"])
    service.memory.delete(
        rule["id"],
        expected_revision=1,
        reason="Manual review complete",
        actor="reviewer",
    )
    assert start(service)["state"]["budget"]["calls"] == 3


def test_memory_tampering_fails_closed(service):
    approve(service, start(service))
    with sqlite3.connect(service.root / "memory/ledger.sqlite") as db:
        db.execute("DELETE FROM memory_entries WHERE kind='cluster'")
    with pytest.raises(FtmError, match="differ"):
        service.memory.query_case_memory("bitcoin", ["syn_partner"])
