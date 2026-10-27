import asyncio
from contextlib import contextmanager
from pathlib import Path
import socket
import sys
import threading
import time
from uuid import uuid4

import pytest

pytest.importorskip("pydantic")
pytest.importorskip("yaml")
pytest.importorskip("langgraph")
pytest.importorskip("langgraph.checkpoint.sqlite")
pytest.importorskip("portalocker")
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("mcp")
pytest.importorskip("streamlit")
pytest.importorskip("uvicorn")

import httpx
from fastapi.testclient import TestClient

from follow_the_money.api import create_app
from follow_the_money.fixtures import build_fixtures
from follow_the_money.security import local_url
from follow_the_money.service import TraceService
from follow_the_money.auth import KeyStore, new_key, parse_key_entries
from follow_the_money.infra.observability import Observability


@pytest.fixture
def runtime(tmp_path):
    fixtures = build_fixtures(tmp_path / "fixtures")
    service = TraceService.initialize(
        tmp_path / "service",
        cache=Path(fixtures["cache"]),
        labels=Path(fixtures["labels"]),
    )
    reviewer, entry = new_key("analyst", "reviewer")
    viewer, read_entry = new_key("observer", "viewer")
    agent, agent_entry = new_key("trace-model", "agent")
    keys = KeyStore(parse_key_entries([entry, read_entry, agent_entry]))
    keys.test_agent = agent
    return service, keys, reviewer, viewer


def trace_request():
    return {
        "chain": "bitcoin",
        "seed": "syn_seed_a",
        "request_id": str(uuid4()),
        "draft_request": True,
    }


def test_api_auth_review_idempotency_and_observability(runtime, tmp_path):
    service, keys, reviewer, viewer = runtime
    obs = Observability(trace_path=tmp_path / "spans.jsonl")
    with TestClient(
        create_app(service, keys, obs=obs), base_url="http://127.0.0.1"
    ) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/v1/cases").status_code == 401
        assert (
            client.get(
                "/v1/cases", headers={"Authorization": "bEaReR " + viewer}
            ).status_code
            == 200
        )
        client.headers["Authorization"] = "Bearer " + viewer
        assert client.post("/v1/cases", json=trace_request()).status_code == 403
        client.headers["Authorization"] = "Bearer " + keys.test_agent
        request = trace_request()
        case = client.post("/v1/cases", json=request).json()
        assert case["status"] == "awaiting_approval" and not case["claims"]
        assert "state" not in case
        assert client.post("/v1/cases", json=request).json() == case
        client.headers["Authorization"] = "Bearer " + reviewer
        case = client.get(f"/v1/cases/{case['case_id']}").json()
        assert case["created_by"] == "trace-model"
        url = f"/v1/cases/{case['case_id']}/approval"
        decision = {
            "request_id": str(uuid4()),
            "evidence_sha256": "0" * 64,
            "decision": "approve",
            "note": "private reviewer note",
        }
        assert client.post(url, json=decision).json()["error"] == "stale_approval"
        decision["evidence_sha256"] = case["state"]["evidence_sha256"]
        approved = client.post(url, json=decision)
        assert approved.status_code == 200 and approved.json()["status"] == "completed"
        assert approved.json()["state"]["report"]["draft_request"]["sent"] is False
        assert client.post(url, json=decision).json() == approved.json()
        assert client.get(f"/v1/cases/{case['case_id']}/audit").status_code == 200
        assert client.get("/metrics").status_code == 200
        assert "x-request-id" in approved.headers
        assert client.get("/openapi.json").json()["paths"]["/v1/cases"]["post"][
            "security"
        ]
    spans = (tmp_path / "spans.jsonl").read_text(encoding="utf-8")
    assert (
        reviewer not in spans
        and viewer not in spans
        and "private reviewer note" not in spans
    )


@pytest.mark.parametrize(
    "change,status,code",
    [
        ({"headers": {"Origin": "http://evil.example"}}, 403, "invalid_origin"),
        ({"headers": {"Host": "evil.example"}}, 421, "invalid_host"),
        ({"content": '{"chain":"bitcoin","chain":"tron"}'}, 422, "invalid_input"),
        ({"content": '"' + "a" * 65536 + '"'}, 413, "body_too_large"),
        ({"json": {**trace_request(), "actor": "forged-secret"}}, 422, "invalid_input"),
    ],
)
def test_api_rejects_untrusted_boundaries(runtime, change, status, code):
    service, keys, reviewer, _ = runtime
    with TestClient(
        create_app(service, keys),
        base_url="http://127.0.0.1",
        headers={"Authorization": "Bearer " + reviewer},
    ) as client:
        response = client.post("/v1/cases", **change)
        assert response.status_code == status and response.json()["error"] == code
        assert "forged-secret" not in response.text
        assert service.list_cases() == []


def test_api_memory_roles_and_optimistic_revision(runtime):
    service, keys, reviewer, viewer = runtime
    with TestClient(
        create_app(service, keys),
        base_url="http://127.0.0.1",
        headers={"Authorization": "Bearer " + reviewer},
    ) as client:
        row = client.post(
            "/v1/memory/rules",
            json={
                "chain": "bitcoin",
                "address": "syn_seed_a",
                "action": "stop",
                "text": "Scoped review hold",
            },
        ).json()
        assert row["revision"] == 1
        url = f"/v1/memory/{row['id']}/revision"
        mutation = {"action": "delete", "note": "Withdraw rule", "expected_revision": 1}
        client.headers["Authorization"] = "Bearer " + viewer
        assert client.post(url, json=mutation).status_code == 403
        client.headers["Authorization"] = "Bearer " + reviewer
        assert client.post(url, json=mutation).status_code == 200
        assert client.post(url, json=mutation).status_code == 409
        assert (
            client.post(
                "/v1/memory/query",
                json={"chain": "bitcoin", "addresses": ["syn_seed_a"]},
            ).json()["links"]
            == []
        )


@contextmanager
def local_server(app):
    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [sock]}, daemon=True
    )
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.02)
        assert server.started
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()


def test_mcp_http_actual_transport_auth_and_no_approval(runtime):
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    import httpx2
    from follow_the_money.mcp_server import http_app

    service, keys, reviewer, viewer = runtime

    async def exchange(url, token, write):
        async with httpx2.AsyncClient(
            headers={"Authorization": "Bearer " + token}, trust_env=False
        ) as http:
            async with Client(
                streamable_http_client(url + "/mcp", http_client=http)
            ) as client:
                names = {t.name for t in (await client.list_tools()).tools}
                assert names == {
                    "start_trace",
                    "get_case",
                    "list_cases",
                    "verify_audit",
                    "query_case_memory",
                    "score_address",
                }
                reply = await client.call_tool(
                    "start_trace", {"request": trace_request()}
                )
                if write:
                    assert (
                        not reply.is_error
                        and reply.structured_content["status"] == "awaiting_approval"
                    )
                    scored = await client.call_tool(
                        "score_address",
                        {
                            "case_id": reply.structured_content["case_id"],
                            "address": "syn_seed_a",
                        },
                    )
                    assert not scored.is_error and scored.structured_content["ood"]
                    assert scored.structured_content["method"] == "heuristic_fallback"
                else:
                    assert (
                        reply.is_error
                        and reply.structured_content["error"] == "forbidden"
                    )
                bad = await client.call_tool("get_case", {"case_id": "invalid"})
                assert bad.is_error

    with local_server(http_app(service, keys)) as url:
        assert httpx.post(url + "/mcp", trust_env=False).status_code == 401
        asyncio.run(exchange(url, keys.test_agent, True))
        asyncio.run(exchange(url, viewer, False))


def test_mcp_stdio_actual_subprocess(runtime):
    from mcp import Client, StdioServerParameters

    service, _, _, _ = runtime

    async def exchange():
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "follow_the_money",
                "mcp",
                "--workspace",
                str(service.root),
                "--read-only",
            ],
            env={
                "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
                "PYTHONDONTWRITEBYTECODE": "1",
                "LANGSMITH_TRACING": "false",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
            },
        )
        async with Client(params) as client:
            reply = await client.call_tool("list_cases", {})
            assert not reply.is_error and reply.structured_content == {"cases": []}
            reply = await client.call_tool("start_trace", {"request": trace_request()})
            assert reply.is_error

    asyncio.run(exchange())


def test_streamlit_real_review_and_credential_destination(runtime, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from follow_the_money import ui

    service, keys, reviewer, _ = runtime
    case = service.start_case(
        __import__("follow_the_money.cases", fromlist=["TraceRequest"]).TraceRequest(
            **trace_request()
        ),
        actor="test",
    )
    with local_server(create_app(service, keys)) as url:
        monkeypatch.setenv("FTM_API_URL", url)
        app = AppTest.from_file(ui.__file__, default_timeout=30).run()
        assert not app.exception
        app.sidebar.text_input[1].set_value(reviewer).run()
        assert not app.exception
        assert app.metric[0].label == "Withdrawn claims"
        check = next(c for c in app.checkbox if c.label.startswith("I reviewed"))
        check.check()
        next(b for b in app.button if b.label == "Record human decision").click().run()
        assert not app.exception
        assert service.get_case(case["case_id"])["status"] == "rejected"
    for url in (
        "https://example.com",
        "http://127.0.0.1@evil.example",
        "http://127.0.0.1/path",
        "http://localhost?token=secret",
    ):
        with pytest.raises(ValueError):
            local_url(url)
