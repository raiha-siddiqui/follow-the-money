import json

import pytest

pytest.importorskip("pydantic")
pytest.importorskip("httpx")

import httpx

from follow_the_money.contracts import FtmError
from follow_the_money.transport import (
    Budget,
    JsonTransport,
    ReplayCache,
    checked_url,
    request_url,
    retry_delay,
)

URL = "https://mempool.space/api/tx/" + "a" * 64


def test_replay_never_falls_through_and_charges_query(tmp_path):
    calls = []
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: calls.append(request))
    )
    transport = JsonTransport(ReplayCache(tmp_path), Budget(1), client=client)
    with pytest.raises(FtmError, match="absent"):
        transport.get(URL)
    assert transport.budget.snapshot() == {
        "max_calls": 1,
        "max_network_calls": 0,
        "calls": 1,
        "network_calls": 0,
    }
    assert not calls


def test_warm_cache_counts_logical_work_but_no_network(tmp_path):
    cache = ReplayCache(tmp_path)
    cache.write(
        URL, 200, b'{"a":1}', evidence_kind="synthetic", license="Authored fiction"
    )
    transport = JsonTransport(cache, Budget(2))
    assert transport.get(URL).json() == {"a": 1}
    assert transport.get(URL).json() == {"a": 1}
    assert transport.budget.calls == 2
    assert transport.budget.network_calls == 0
    with pytest.raises(FtmError) as exc:
        transport.get(URL)
    assert exc.value.code == "budget_exhausted"


def test_retries_rate_limit_and_every_response_recorded(tmp_path):
    ticks = [0.0]
    waits = []
    requests = []

    def sleep(seconds):
        waits.append(seconds)
        ticks[0] += seconds

    def send(request):
        requests.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "3"}, json={"busy": True})
            if len(requests) == 1
            else httpx.Response(200, json={"ok": True})
        )

    transport = JsonTransport(
        ReplayCache(tmp_path),
        Budget(2, 3),
        mode="record",
        allow_live=True,
        client=httpx.Client(transport=httpx.MockTransport(send)),
        clock=lambda: ticks[0],
        sleep=sleep,
    )
    assert transport.get(URL).json() == {"ok": True}
    assert transport.budget.network_calls == 2
    assert transport.budget.calls == 1
    assert sum(waits) >= 3
    assert len(list((tmp_path / "attempts").glob("*.json"))) == 2
    assert all(
        "body_base64" in json.loads(p.read_text(encoding="utf-8"))
        for p in (tmp_path / "attempts").glob("*.json")
    )
    transport.get(URL)
    assert len(requests) == 2


def test_retry_budget_cannot_overrun(tmp_path):
    seen = []

    def send(request):
        seen.append(request)
        return httpx.Response(503)

    transport = JsonTransport(
        ReplayCache(tmp_path),
        Budget(1, 1),
        mode="record",
        allow_live=True,
        client=httpx.Client(transport=httpx.MockTransport(send)),
        sleep=lambda _: None,
    )
    with pytest.raises(FtmError) as exc:
        transport.get(URL)
    assert exc.value.code == "budget_exhausted"
    assert len(seen) == 1


def test_long_retry_after_stops_instead_of_violating_server_delay(tmp_path):
    transport = JsonTransport(
        ReplayCache(tmp_path),
        Budget(1, 3),
        mode="record",
        allow_live=True,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(429, headers={"Retry-After": "3600"})
            )
        ),
        sleep=lambda _: None,
    )
    with pytest.raises(FtmError) as exc:
        transport.get(URL)
    assert exc.value.code == "rate_limited"
    assert transport.budget.network_calls == 1


def test_redirects_are_not_followed(tmp_path):
    transport = JsonTransport(
        ReplayCache(tmp_path),
        Budget(1, 1),
        mode="record",
        allow_live=True,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    302, headers={"Location": "https://evil.invalid"}
                )
            )
        ),
    )
    with pytest.raises(FtmError, match="302"):
        transport.get(URL)


@pytest.mark.parametrize(
    "url",
    [
        "http://mempool.space/api/tx/a",
        "https://user:secret@mempool.space/api",  # pragma: allowlist secret -- fictional credentials exercise URL rejection
        "https://mempool.space/api?api_key=secret",
        "https://mempool.space/api#hidden",
        "https://mempool.space:443/api",
    ],
)
def test_unsafe_cache_keys_rejected(url):
    with pytest.raises((ValueError, FtmError)):
        checked_url(url)


def test_tron_live_and_unapproved_recording_refused(tmp_path):
    with pytest.raises(FtmError):
        JsonTransport(ReplayCache(tmp_path), Budget(1, 1), mode="record")
    transport = JsonTransport(
        ReplayCache(tmp_path), Budget(1, 1), mode="record", allow_live=True
    )
    with pytest.raises(FtmError):
        transport.get("https://api.trongrid.io/v1/accounts/a")
    assert transport.budget.network_calls == 0


def test_tampered_cache_fails_closed(tmp_path):
    cache = ReplayCache(tmp_path)
    cache.write(URL, 200, b"{}", evidence_kind="synthetic", license="Authored fiction")
    path = cache.path(URL)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["body_base64"] = "eyJ4IjoxfQ=="
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(FtmError) as exc:
        cache.read(URL)
    assert exc.value.code == "cache_corrupt"


@pytest.mark.parametrize("args", [(True,), (-1,), (1, -1), (1, 1, 2), (1.0,)])
def test_budget_validation(args):
    with pytest.raises(ValueError):
        Budget(*args)


def test_request_keys_stable_and_retry_delay():
    assert (
        request_url("https://x.invalid/", "/a", {"b": 2, "a": "x y"})
        == "https://x.invalid/a?a=x+y&b=2"
    )
    assert retry_delay("invalid", 2) == 4
    assert retry_delay("nan", 0) > 60
