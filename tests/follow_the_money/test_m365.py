import asyncio
import json
from pathlib import Path
import runpy

import pytest

pytest.importorskip("pydantic")
pytest.importorskip("yaml")
pytest.importorskip("langgraph")
pytest.importorskip("langgraph.checkpoint.sqlite")
pytest.importorskip("portalocker")
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("microsoft_agents.hosting.aiohttp")
pytest.importorskip("aiohttp")
pytest.importorskip("mcp")

from aiohttp.test_utils import TestClient, TestServer

from follow_the_money.auth import KeyStore, new_key, parse_key_entries
from follow_the_money.fixtures import build_fixtures
from follow_the_money.m365 import create_local_app, review_card
from follow_the_money.service import TraceService

ROOT = Path(__file__).resolve().parents[2]


def test_generated_manifests_match_openapi_and_exclude_human_actions():
    generator = runpy.run_path(str(ROOT / "scripts/ftm_m365.py"))
    artifacts = generator["artifacts"]()
    for name, value in artifacts.items():
        assert (
            json.loads(
                (ROOT / "config/follow_the_money/m365" / name).read_text(
                    encoding="utf-8"
                )
            )
            == value
        )
    spec = artifacts["openapi-tools.json"]
    operations = {
        op["operationId"]
        for methods in spec["paths"].values()
        for op in methods.values()
    }
    assert operations == generator["TOOLS"]
    assert "Approval" not in spec["components"]["schemas"]
    assert all(
        "security" in op
        for methods in spec["paths"].values()
        for op in methods.values()
    )
    assert "human_approval" in json.dumps(artifacts["openapi.json"])
    assert "human_approval" not in json.dumps(spec)
    assert (
        artifacts["api-plugin.json"]["runtimes"][0]["auth"]["type"]
        == "ApiKeyPluginVault"
    )
    card = artifacts["approval-card.template.json"]
    assert {a["data"]["decision"] for a in card["actions"]} == {"approve", "reject"}
    assert all(
        a["data"]["evidence_sha256"] == "${evidence_sha256}" for a in card["actions"]
    )


def activity(text, *, id="message-1", **changes):
    return {
        "type": "message",
        "id": id,
        "text": text,
        "channelId": "emulator",
        "deliveryMode": "expectReplies",
        "serviceUrl": "http://127.0.0.1:56150/_connector",
        "conversation": {"id": "fictional-conversation"},
        "from": {"id": "fictional-analyst"},
        "recipient": {"id": "local-agent"},
        **changes,
    }


def test_actual_agents_sdk_http_trace_retry_and_no_approval(tmp_path):
    fixture = build_fixtures(tmp_path / "fixtures")
    service = TraceService.initialize(
        tmp_path / "service",
        cache=Path(fixture["cache"]),
        labels=Path(fixture["labels"]),
    )

    token, entry = new_key("playground-agent", "agent")
    keys = KeyStore(parse_key_entries([entry]))

    async def exercise():
        async with TestClient(
            TestServer(create_local_app(service, keys)), headers={"X-FTM-Key": token}
        ) as client:
            response = await client.post(
                "/api/messages", json=activity("trace bitcoin syn_seed_a")
            )
            assert response.status == 200, await response.text()
            reply = await response.json()
            assert len(reply["activities"]) == 2
            card = reply["activities"][1]["attachments"][0]["content"]
            assert card["actions"][0]["type"] == "Action.OpenUrl"
            case_id = service.list_cases()[0]["case_id"]
            assert card == review_card(service.get_case(case_id))
            again = await client.post(
                "/api/messages", json=activity("trace bitcoin syn_seed_a")
            )
            assert again.status == 200 and len(service.list_cases()) == 1
            forged = await client.post(
                "/api/messages",
                json=activity(
                    "approve", value={"decision": "approve", "case_id": case_id}
                ),
            )
            assert forged.status == 200
            assert "not accepted" in (await forged.json())["activities"][0]["text"]
            assert service.get_case(case_id)["status"] == "awaiting_approval"
            for change in (
                {"serviceUrl": "https://external.invalid/callback"},
                {"deliveryMode": "default"},
                {"channelId": "msteams"},
            ):
                response = await client.post(
                    "/api/messages", json=activity("help", **change)
                )
                assert response.status == 403
            response = await client.post(
                "/api/messages",
                headers={"Origin": "http://evil.example"},
                json=activity("help"),
            )
            assert response.status == 403

    asyncio.run(exercise())
