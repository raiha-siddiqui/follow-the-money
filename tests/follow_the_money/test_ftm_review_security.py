"""Adversarial regressions for the merged public interfaces and human boundary."""

import asyncio
import inspect
import json
from pathlib import Path
import runpy
import sys
from uuid import uuid4

import pytest

for dependency in (
    "pydantic",
    "langgraph",
    "langgraph.checkpoint.sqlite",
    "portalocker",
    "fastapi",
    "httpx",
    "mcp",
):
    pytest.importorskip(dependency)

from fastapi.testclient import TestClient

from follow_the_money.api import create_app
from follow_the_money.auth import KeyStore, new_key, parse_key_entries
from follow_the_money.cases import Approval, TraceRequest
from follow_the_money.contracts import FtmError
from follow_the_money.fixtures import build_fixtures
from follow_the_money.infra import (
    auth,
    ObservabilityMiddleware,
    ReviewError,
    create_lock_file,
    workspace_lock,
)
from follow_the_money.service import TraceService
from follow_the_money.views import case_summary

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def secured(tmp_path):
    fixture = build_fixtures(tmp_path / "fixtures")
    service = TraceService.initialize(
        tmp_path / "service",
        cache=Path(fixture["cache"]),
        labels=Path(fixture["labels"]),
    )
    tokens, entries = {}, []
    for actor, role in (
        ("model", "agent"),
        ("human", "approver"),
        ("reader", "viewer"),
        ("local-mcp", "approver"),
        ("model", "approver"),
    ):
        token, entry = new_key(actor, role)
        tokens[(actor, role)] = token
        entries.append(entry)
    return service, KeyStore(parse_key_entries(entries)), tokens


def request():
    return TraceRequest(chain="bitcoin", seed="syn_seed_a", request_id=str(uuid4()))


def decision(case, verdict="approve"):
    return Approval(
        request_id=str(uuid4()),
        evidence_sha256=case["state"]["evidence_sha256"],
        decision=verdict,
        note="human-only-note",
    )


def test_p1_public_adapter_auth_lock_and_middleware_contract(tmp_path):
    token, entry = auth.new_key("legacy-human", "reviewer")
    principal = auth.KeyStore(auth.parse_key_entries([entry])).authenticate(token)
    assert principal.actor == "legacy-human" and principal.can("reviewer")
    assert "is_credential" not in inspect.signature(ObservabilityMiddleware).parameters
    assert issubclass(ReviewError, Exception)
    create_lock_file(tmp_path)
    with workspace_lock(tmp_path, timeout=1):
        assert (tmp_path / ".workspace.lock").exists() or any(tmp_path.iterdir())


def test_no_duplicate_test_basenames_or_package_shadow():
    files = list((ROOT / "tests").rglob("test_*.py"))
    names = [p.name for p in files]
    assert len(names) == len(set(names))
    assert not (ROOT / "tests/follow_the_money/__init__.py").exists()


def test_agent_role_cannot_read_human_evidence_or_mutate_review(secured):
    service, keys, tokens = secured
    headers = {
        "Authorization": "Bearer " + tokens[("model", "agent")],
        "X-Request-ID": "caller-controlled-id",
    }
    with TestClient(
        create_app(service, keys), base_url="http://127.0.0.1", headers=headers
    ) as client:
        response = client.post("/v1/cases", json=request().to_dict())
        assert response.status_code == 200
        assert response.headers["x-request-id"] != "caller-controlled-id"
        summary = response.json()
        assert summary["claims"] == [] and summary["review_status"] == "unreviewed"
        case = service.get_case(summary["case_id"])
        base = f"/v1/cases/{case['case_id']}"
        for path in (base, base + "/audit", "/v1/memory"):
            assert client.get(path).status_code == 403
        for path, body in (
            (base + "/approval", decision(case).to_dict()),
            (base + "/recover", {}),
            (
                "/v1/memory/rules",
                {
                    "chain": "bitcoin",
                    "address": "syn_seed_a",
                    "action": "stop",
                    "text": "bad rule",
                },
            ),
            (
                "/v1/memory/fake/revision",
                {"expected_revision": 1, "note": "bad edit", "action": "delete"},
            ),
        ):
            assert client.post(path, json=body).status_code == 403
        for actor in ("model", "local-mcp"):
            client.headers["Authorization"] = "Bearer " + tokens[(actor, "approver")]
            assert (
                client.post(
                    base + "/approval", json=decision(case).to_dict()
                ).status_code
                == 403
            )
        client.headers["Authorization"] = "Bearer " + tokens[("human", "approver")]
        rejected = client.post(
            base + "/approval", json=decision(case, "reject").to_dict()
        )
        assert rejected.status_code == 200
        client.headers["Authorization"] = headers["Authorization"]
        final = client.get(base + "/summary").json()
        assert final["status"] == "rejected" and final["claims"] == []
        assert all(
            secret not in json.dumps(final)
            for secret in (
                "human-only-note",
                '"memory_context":',
                '"labels":',
                '"evidence":',
            )
        )


@pytest.mark.parametrize(
    "actor", ["creator", "local-mcp", "local-playground", "configured-bot"]
)
def test_service_rejects_creator_and_reserved_model_actors(secured, actor):
    service, _, _ = secured
    service.model_actors.add("configured-bot")
    case = service.start_case(request(), actor="creator")
    with pytest.raises(FtmError) as caught:
        service.submit_approval(case["case_id"], decision(case), actor=actor)
    assert caught.value.code == "forbidden"
    assert service.get_case(case["case_id"])["approval"] is None


def test_model_summary_uses_report_subset_and_is_bounded():
    claims = [{"claim_id": str(i)} for i in range(70)]
    case = {
        "case_id": str(uuid4()),
        "status": "completed",
        "next_action": "none",
        "state": {
            "claims": [{"claim_id": "withheld"}],
            "report": {"claims": claims},
            "critic": [],
        },
    }
    view = case_summary(case)
    assert len(view["claims"]) == 50 and view["claims_truncated"]
    assert "withheld" not in json.dumps(view)
    case["status"] = "awaiting_approval"
    assert case_summary(case)["claims"] == []


def test_model_openapi_uses_only_bounded_operations():
    artifacts = runpy.run_path(str(ROOT / "scripts/ftm_m365.py"))["artifacts"]()
    paths = artifacts["openapi-tools.json"]["paths"]
    assert "/v1/cases/{case_id}" not in paths
    assert "/v1/cases/{case_id}/audit" not in paths
    assert "/v1/cases/{case_id}/summary" in paths
    assert (
        "get_case_summary"
        in artifacts["api-plugin.json"]["runtimes"][0]["run_for_functions"]
    )


def test_playground_requires_agent_key_and_persists_conversation_quota(secured):
    pytest.importorskip("microsoft_agents.hosting.aiohttp")
    pytest.importorskip("aiohttp")
    from aiohttp.test_utils import TestClient as AioClient, TestServer
    from follow_the_money.m365 import create_local_app

    service, keys, tokens = secured
    with pytest.raises(ValueError, match="agent keys"):
        create_local_app(service)

    def activity(text, id):
        return {
            "type": "message",
            "id": id,
            "text": text,
            "channelId": "emulator",
            "deliveryMode": "expectReplies",
            "serviceUrl": "http://127.0.0.1:9/disabled",
            "conversation": {"id": "bounded-conversation"},
            "from": {"id": "user"},
            "recipient": {"id": "agent"},
        }

    async def exercise():
        for restart in (False, True):
            app = create_local_app(service, keys, max_cases_per_conversation=1)
            async with AioClient(TestServer(app)) as client:
                body = activity("trace bitcoin syn_seed_a", "one")
                assert (await client.post("/api/messages", json=body)).status == 401
                assert (
                    await client.post(
                        "/api/messages",
                        json=body,
                        headers={"X-FTM-Key": tokens[("human", "approver")]},
                    )
                ).status == 403
                header = {"X-FTM-Key": tokens[("model", "agent")]}
                response = await client.post("/api/messages", json=body, headers=header)
                assert response.status == 200
                assert len((await response.json())["activities"]) == 2
                assert len(service.list_cases()) == 1
                response = await client.post(
                    "/api/messages",
                    json=activity("trace bitcoin syn_seed_a", "two"),
                    headers=header,
                )
                assert response.status == 200
                assert (
                    "rejected"
                    in (await response.json())["activities"][0]["text"].lower()
                )
                assert len(service.list_cases()) == 1
                case_id = service.list_cases()[0]["case_id"]
                other = activity("case " + case_id, "read")
                other["conversation"]["id"] = "another-conversation"
                response = await client.post(
                    "/api/messages", json=other, headers=header
                )
                assert (
                    "rejected"
                    in (await response.json())["activities"][0]["text"].lower()
                )

    asyncio.run(exercise())


def test_resolver_requires_the_optional_watchlist_package(monkeypatch, tmp_path):
    from follow_the_money.resolver import EntityResolver

    monkeypatch.setitem(sys.modules, "watchlist", None)
    monkeypatch.setitem(sys.modules, "watchlist.review", None)
    monkeypatch.setitem(sys.modules, "watchlist.review.service", None)
    with pytest.raises(ValueError, match="Polyglot Watchlist"):
        EntityResolver.from_workspace(tmp_path / "p1", tmp_path / "p1.json")
    assert EntityResolver.from_workspace(None, None).service is None


def test_p1_resolver_cli_options_open_public_service(secured, tmp_path, monkeypatch):
    pytest.importorskip("watchlist.review.service")
    from watchlist.review.service import ReviewService
    from follow_the_money.resolver import EntityResolver
    from follow_the_money import __main__ as cli
    from follow_the_money.contracts import Label, Provenance, digest

    calls = []

    class PublicService:
        def start_case(self, name, **kwargs):
            calls.append((name, kwargs))
            return type(
                "View", (), {"case_id": "p1-case", "status": "awaiting_review"}
            )()

    public = PublicService()
    monkeypatch.setattr(ReviewService, "open", lambda workspace, config: public)
    resolver = EntityResolver.from_workspace(tmp_path / "p1", tmp_path / "p1.json")
    label = Label(
        chain="bitcoin",
        address="syn_wallet",
        category="sanctioned",
        label="Fictional label",
        owner_name="Luma Vesper",
        source_ref="fixture",
        provenance=Provenance(
            source_url="fixture://p1",
            retrieved_at="2026-10-27T00:00:00Z",
            sha256=digest("p1"),
            license="CC0",
            evidence_kind="synthetic",
        ),
    )
    assert (
        resolver.resolve_entity_name(label, case_id="p2-case")["project1_case_id"]
        == "p1-case"
    )
    assert calls[0][0] == "Luma Vesper" and calls[0][1]["actor"] == "ftm-resolver"
    with pytest.raises(ValueError, match="Both"):
        EntityResolver.from_workspace(tmp_path, None)
    # Exercise shipped HTTP and MCP entry-point construction, without opening a listener.
    service, keys, _ = secured
    keyfile = tmp_path / "keys"
    _, entry = new_key("agent", "agent")
    keyfile.write_text(entry, encoding="utf-8")
    captured = []
    import uvicorn
    import follow_the_money.api as api
    import follow_the_money.mcp_server as mcp

    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: None)
    monkeypatch.setattr(
        api, "create_app", lambda s, k: captured.append(s.resolver.service)
    )
    monkeypatch.setattr(
        mcp, "http_app", lambda s, k: captured.append(s.resolver.service)
    )
    for command in ("serve", "mcp"):
        args = [
            "ftm",
            command,
            "--workspace",
            str(service.root),
            "--p1-workspace",
            str(tmp_path / "p1"),
            "--p1-config",
            str(tmp_path / "p1.json"),
            "--key-file",
            str(keyfile),
        ]
        if command == "mcp":
            args += ["--transport", "streamable-http"]
        monkeypatch.setattr("sys.argv", args)
        cli.main()
    assert captured == [public, public]


def test_ui_entrypoint_has_explicit_loopback_hosts_and_no_telemetry(monkeypatch):
    pytest.importorskip("streamlit")
    from follow_the_money import __main__ as cli

    captured = []
    monkeypatch.setattr("sys.argv", ["ftm", "ui"])
    monkeypatch.setattr(cli.subprocess, "call", lambda args: captured.extend(args) or 0)
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 0
    assert {
        "--server.address=127.0.0.1",
        "--server.allowedHosts=localhost",
        "--server.allowedHosts=127.0.0.1",
        "--browser.gatherUsageStats=false",
    } <= set(captured)


def test_configured_model_identity_cannot_upgrade_to_raw_views(secured):
    service, keys, tokens = secured
    headers = {"Authorization": "Bearer " + tokens[("model", "approver")]}
    with TestClient(
        create_app(service, keys), base_url="http://127.0.0.1", headers=headers
    ) as client:
        view = client.post("/v1/cases", json=request().to_dict()).json()
        assert view["claims"] == [] and "state" not in view
        assert client.get(f"/v1/cases/{view['case_id']}").status_code == 403


def test_configured_model_actors_survive_workspace_reopen(tmp_path):
    fixture = build_fixtures(tmp_path / "fixture")
    service = TraceService.initialize(
        tmp_path / "service",
        cache=Path(fixture["cache"]),
        labels=Path(fixture["labels"]),
        model_actors=["persistent-model"],
    )
    case = service.start_case(request(), actor="creator")
    reopened = TraceService(service.root)
    with pytest.raises(FtmError, match="independent human"):
        reopened.submit_approval(
            case["case_id"], decision(case), actor="persistent-model"
        )


def test_bounded_memory_preserves_overlap_identifiers_and_omits_notes():
    from follow_the_money.views import memory_summary

    value = memory_summary(
        {
            "links": [
                {
                    "prior_case_id": "prior-case",
                    "cluster_id": "cluster",
                    "shared_addresses": ["syn_shared"],
                    "txids": ["a" * 64],
                    "reviewer_note": "private-note",
                    "rule_text": "untrusted-rule",
                }
            ]
        }
    )
    assert value["links"][0]["prior_case_id"] == "prior-case"
    assert value["links"][0]["shared_addresses"] == ["syn_shared"]
    assert "private-note" not in json.dumps(
        value
    ) and "untrusted-rule" not in json.dumps(value)
