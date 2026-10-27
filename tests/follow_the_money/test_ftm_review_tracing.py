"""Point-in-time, independent-critic and explorer contract regressions."""

import json
from pathlib import Path
from urllib.request import Request, ProxyHandler
from uuid import uuid4

import pytest

for dependency in (
    "pydantic",
    "langgraph",
    "langgraph.checkpoint.sqlite",
    "portalocker",
    "fastapi",
    "httpx",
    "numpy",
):
    pytest.importorskip(dependency)

from follow_the_money.acquire import NoRedirects, acquire, source_opener
from follow_the_money.cases import TraceRequest, make_claim
from follow_the_money.clients import (
    EsploraClient,
    TronGridClient,
    parse_bitcoin,
    tron_address,
)
from follow_the_money.contracts import FtmError, USDT_TRON, digest
from follow_the_money.critic import challenge
from follow_the_money.features import LIVE_FEATURES
from follow_the_money.fixtures import build_fixtures, fictional_tx, raw_output
from follow_the_money.heuristics import (
    detect_change,
    seen_addresses_before,
    weak_change_labels,
)
from follow_the_money.labels import LabelStore
from follow_the_money.service import TraceService
from follow_the_money.transport import Budget, JsonTransport, ReplayCache, request_url

ROOT = Path(__file__).resolve().parents[2]


def evidence(*transactions):
    return {t.txid: [{"chain": "bitcoin", "value": t.to_dict()}] for t in transactions}


def put(cache, url, payload):
    cache.write(
        url,
        200,
        json.dumps(payload).encode(),
        evidence_kind="synthetic",
        license="CC0-1.0 authored fixture",
    )


def tx(provenance, name="change", outputs=None, timestamp=10):
    return parse_bitcoin(
        fictional_tx(
            name,
            [(digest(name + "-funding"), 0, raw_output("syn_a", 100000))],
            outputs or [("syn_a", 60000), ("syn_b", 39123)],
            timestamp,
        ),
        provenance,
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_unique_input_reuse_dominates_roundness(provenance, reverse):
    outputs = [("syn_a", 60000), ("syn_b", 39123)]
    if reverse:
        outputs.reverse()
    transaction = tx(provenance, outputs=outputs)
    assert detect_change(transaction).candidate == (1 if reverse else 0)
    assert detect_change(transaction).reason == "unique_input_address_reuse"
    assert not detect_change(transaction).calibrated


def test_two_reused_outputs_abstain(provenance):
    transaction = tx(provenance, outputs=[("syn_a", 60000), ("syn_a", 39123)])
    assert detect_change(transaction).candidate is None


def test_critic_catches_wrong_change_independently_of_producer(provenance, monkeypatch):
    import follow_the_money.heuristics as heuristics

    transaction = tx(provenance)
    monkeypatch.setattr(
        heuristics,
        "detect_change",
        lambda *a, **k: pytest.fail("critic reused producer heuristic"),
    )
    wrong = make_claim(
        "change_hypothesis", "bitcoin", (transaction.txid,), ("syn_b",), output_index=1
    )
    right = make_claim(
        "change_hypothesis", "bitcoin", (transaction.txid,), ("syn_a",), output_index=0
    )
    assert not challenge(wrong, evidence(transaction), [])["retained"]
    assert challenge(right, evidence(transaction), [])["retained"]


def test_freshness_uses_observed_history_not_future_or_current_outputs(provenance):
    past = tx(provenance, name="past", outputs=[("syn_old", 10000)], timestamp=5)
    current = tx(
        provenance, outputs=[("syn_old", 39123), ("syn_new", 60000)], timestamp=10
    )
    future = tx(provenance, name="future", outputs=[("syn_new", 10000)], timestamp=11)
    seen = seen_addresses_before(current, evidence(past, current, future))
    assert "syn_old" in seen and "syn_new" not in seen
    estimate = detect_change(current, seen_addresses=seen)
    without_history = detect_change(current, seen_addresses=set())
    assert estimate.probabilities[0] < without_history.probabilities[0]
    claim = make_claim(
        "change_hypothesis", "bitcoin", (current.txid,), ("syn_old",), output_index=0
    )
    assert not challenge(claim, evidence(past, current, future), [])["retained"]


def test_post_cutoff_second_cospend_cannot_drop_training_label(provenance):
    original = tx(provenance, outputs=[("syn_change", 60000), ("syn_payment", 39123)])
    spends = []
    for index, timestamp in ((0, 20), (1, 40)):
        output = original.outputs[index]
        raw = fictional_tx(
            f"later-{index}",
            [
                (original.txid, index, raw_output(output.address, output.value)),
                (digest(f"extra-{index}"), 0, raw_output("syn_a", 1000)),
            ],
            [(f"syn_later_{index}", output.value)],
            timestamp,
        )
        spends.append(parse_bitcoin(raw, provenance))
    before = weak_change_labels([original, spends[0]], observed_by=30)
    after = weak_change_labels([original, *spends], observed_by=30)
    assert len(before) == 2 and after == before
    assert [r.label for r in after] == [1, 0]
    assert weak_change_labels([original, *spends], observed_by=50) == ()


def event_url(name, cursor=None):
    return request_url(
        "https://api.trongrid.io",
        f"/v1/contracts/{USDT_TRON}/events",
        {
            "only_confirmed": "true",
            "event_name": name,
            "limit": 200,
            "fingerprint": cursor,
        },
    )


def event(name, address, timestamp, index=0):
    return {
        "transaction_id": digest([name, address, timestamp, index]),
        "contract_address": USDT_TRON,
        "event_name": name,
        "result": {"_user": address},
        "block_timestamp": timestamp,
    }


def test_freeze_pagination_all_actions_and_every_traced_address(tmp_path):
    fixture = build_fixtures(tmp_path / "fixture")
    cache = ReplayCache(Path(fixture["cache"]))
    rows = [event("AddedBlackList", f"syn_unrelated_{i}", 1, i) for i in range(199)] + [
        event("AddedBlackList", "syn_tron_route", 2)
    ]
    put(
        cache,
        event_url("AddedBlackList"),
        {"success": True, "data": rows, "meta": {"fingerprint": "next"}},
    )
    put(
        cache,
        event_url("AddedBlackList", "next"),
        {
            "success": True,
            "data": [event("AddedBlackList", "syn_tron_exchange", 3)],
            "meta": {},
        },
    )
    put(
        cache,
        event_url("RemovedBlackList"),
        {
            "success": True,
            "data": [event("RemovedBlackList", "syn_tron_route", 4)],
            "meta": {},
        },
    )
    put(
        cache,
        event_url("DestroyedBlackFunds"),
        {
            "success": True,
            "data": [event("DestroyedBlackFunds", "syn_tron_exchange", 5)],
            "meta": {},
        },
    )
    service = TraceService.initialize(
        tmp_path / "service", cache=cache.root, labels=Path(fixture["labels"])
    )
    view = service.start_case(
        TraceRequest(
            chain="tron",
            seed="syn_tron_seed",
            request_id=str(uuid4()),
            check_freeze_signals=True,
            max_calls=12,
        ),
        actor="model",
    )
    state = view["state"]
    assert state["budget"]["calls"] == 6  # Four event pages and two transfer pages.
    accounts = {a["address"]: a for a in state["signals"]["accounts"]}
    assert accounts["syn_tron_route"]["blacklisted_at_last_observation"] is False
    assert accounts["syn_tron_exchange"]["blacklisted_at_last_observation"] is True
    assert accounts["syn_tron_exchange"]["destroyed_funds_events"] == 1
    assert state["signals"]["freeze_history_complete"]
    freezes = [c for c in state["claims"] if c["kind"] == "freeze_signal"]
    assert len(freezes) == 4 and all(
        not c["addresses"][0].startswith("syn_unrelated") for c in freezes
    )
    assert all(
        challenge(c, state["evidence"], state["labels"])["retained"] for c in freezes
    )


def test_tron_hex_address_normalization():
    # Published USDT contract address is a protocol identifier, never a credential.
    hex_address = "a614f803b6fd780986a42c78ec9c7f77e6ded13c"  # pragma: allowlist secret -- public TRON contract address
    assert tron_address("0x" + hex_address) == USDT_TRON
    assert tron_address("41" + hex_address) == USDT_TRON
    assert tron_address("0x" + "0" * 24 + hex_address) == USDT_TRON
    assert tron_address(USDT_TRON) == USDT_TRON


def test_trc20_approval_rows_are_skipped_without_losing_cursor(tmp_path):
    cache = ReplayCache(tmp_path)
    url = request_url(
        "https://api.trongrid.io",
        "/v1/accounts/syn_a/transactions/trc20",
        {"contract_address": USDT_TRON, "only_confirmed": "true", "limit": 200},
    )
    transfer = {
        "transaction_id": digest("transfer"),
        "from": "syn_a",
        "to": "syn_b",
        "value": "123456",
        "block_timestamp": 10,
        "type": "Transfer",
        "token_info": {"address": USDT_TRON, "decimals": 6},
    }
    put(
        cache,
        url,
        {
            "success": True,
            "data": [{"type": "Approval"}, transfer],
            "meta": {"fingerprint": "next"},
        },
    )
    page = TronGridClient(JsonTransport(cache, Budget(1))).get_trc20_transfers("syn_a")
    assert len(page.transfers) == 1 and page.transfers[0].amount == 123456
    assert page.next_cursor == "next" and not page.complete


def test_esplora_continuation_accepts_fifty_recorded_rows(tmp_path, make_tx):
    cache = ReplayCache(tmp_path)
    cursor = digest("previous-page")
    rows = [make_tx(index=i) for i in range(50)]
    put(cache, f"https://mempool.space/api/address/syn_seed_a/txs/chain/{cursor}", rows)
    page = EsploraClient(JsonTransport(cache, Budget(1))).get_address_txs(
        "syn_seed_a", cursor
    )
    assert len(page.transactions) == 50 and page.next_cursor == rows[-1]["txid"]
    assert not page.complete


def test_peel_chain_and_live_features_reach_the_agent_and_scoring_tool(tmp_path):
    cache = ReplayCache(tmp_path / "cache")
    labels = LabelStore(tmp_path / "labels.sqlite")
    labels.initialize()
    raws = []
    for index in range(3):
        inputs = (
            [(digest("peel-funding"), 0, raw_output("syn_peel_0", 100000))]
            if not raws
            else [(raws[-1]["txid"], 1, raws[-1]["vout"][1])]
        )
        raws.append(
            fictional_tx(
                f"peel-{index}",
                inputs,
                [
                    (f"syn_payment_{index}", 1000),
                    (f"syn_peel_{index + 1}", 98000 - index * 2000),
                ],
                100 + index,
            )
        )
    addresses = {
        i["prevout"]["scriptpubkey_address"] for r in raws for i in r["vin"]
    } | {o["scriptpubkey_address"] for r in raws for o in r["vout"]}
    for address in addresses:
        put(
            cache,
            f"https://mempool.space/api/address/{address}/txs",
            [
                r
                for r in raws
                if address
                in {i["prevout"]["scriptpubkey_address"] for i in r["vin"]}
                | {o["scriptpubkey_address"] for o in r["vout"]}
            ],
        )
    service = TraceService.initialize(
        tmp_path / "service", cache=cache.root, labels=labels.path
    )
    case = service.start_case(
        TraceRequest(
            chain="bitcoin",
            seed="syn_peel_0",
            goal="bounded_exploration",
            request_id=str(uuid4()),
            max_calls=12,
        ),
        actor="model",
    )
    state = case["state"]
    peel = [c for c in state["claims"] if c["kind"] == "peel_hypothesis"]
    assert len(peel) == 1 and peel[0]["txids"] == [r["txid"] for r in raws]
    assert challenge(peel[0], state["evidence"], [])["retained"]
    score = service.score_address(case["case_id"], "syn_peel_1")
    assert score["ood"] and score["method"] == "heuristic_fallback"
    assert score["feature_names"] == LIVE_FEATURES and score["features"][1] > 0


def test_tron_priority_distinguishes_relative_branch_amounts(tmp_path):
    fixture = build_fixtures(tmp_path / "fixture")
    cache = ReplayCache(Path(fixture["cache"]))
    url = request_url(
        "https://api.trongrid.io",
        "/v1/accounts/syn_tron_seed/transactions/trc20",
        {"contract_address": USDT_TRON, "only_confirmed": "true", "limit": 200},
    )
    rows = [
        {
            "transaction_id": digest(["branch", i]),
            "from": "syn_tron_seed",
            "to": target,
            "value": amount,
            "block_timestamp": 1700000000000,
            "type": "Transfer",
            "token_info": {"address": USDT_TRON, "decimals": 6},
        }
        for i, (target, amount) in enumerate(
            (("syn_noise", "1"), ("syn_tron_exchange", "999"))
        )
    ]
    put(cache, url, {"success": True, "data": rows, "meta": {}})
    service = TraceService.initialize(
        tmp_path / "service", cache=cache.root, labels=Path(fixture["labels"])
    )
    state = service.start_case(
        TraceRequest(chain="tron", seed="syn_tron_seed", request_id=str(uuid4())),
        actor="model",
    )["state"]
    assert (
        state["budget"]["calls"] == 1
        and state["endpoints"][0]["address"] == "syn_tron_exchange"
    )
    assert state["frontier"][0]["heuristic"] < state["trace"][-1]["heuristic"]


def test_transport_network_counter_is_measured_not_constant(tmp_path, monkeypatch):
    fixture = build_fixtures(tmp_path / "fixture")
    original = EsploraClient.get_address_txs

    def counted(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        # Inject a counter observation, with no network request or budget bypass.
        self.transport.budget.network_calls = 7
        return result

    monkeypatch.setattr(EsploraClient, "get_address_txs", counted)
    service = TraceService.initialize(
        tmp_path / "service",
        cache=Path(fixture["cache"]),
        labels=Path(fixture["labels"]),
    )
    state = service.start_case(
        TraceRequest(chain="bitcoin", seed="syn_seed_a", request_id=str(uuid4())),
        actor="model",
    )["state"]
    assert state["budget"]["network_calls"] == 7


@pytest.mark.parametrize(
    "redirect", ["http://example.invalid/data", "https://other.invalid/data"]
)
def test_acquisition_redirects_are_refused(redirect):
    with pytest.raises(FtmError, match="redirects"):
        NoRedirects().redirect_request(
            Request("https://example.invalid/data"), None, 302, "Found", {}, redirect
        )


def test_acquisition_ignores_proxy_environment(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    assert not any(
        isinstance(h, ProxyHandler) and h.proxies for h in source_opener().handlers
    )


def test_all_registry_sources_have_receipt_bound_pins():
    registry = json.loads(
        (ROOT / "config/follow_the_money/sources.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (ROOT / "config/follow_the_money/manifest.json").read_text(encoding="utf-8")
    )
    receipts = {r["id"]: r for r in manifest["artifacts"]}
    for source in registry["sources"]:
        assert source["sha256"] == receipts[source["id"]]["sha256"]


def test_cached_acquisition_must_also_match_current_pin(tmp_path):
    from io import BytesIO

    class Response(BytesIO):
        headers = {}

    source = {
        "id": "authored",
        "url": "https://example.invalid/source",
        "approved": True,
        "license": "CC0",
        "max_bytes": 100,
    }
    acquire(source, tmp_path, opener=lambda *a, **k: Response(b"fixture"))
    with pytest.raises(FtmError, match="differs"):
        acquire(
            {**source, "sha256": "0" * 64},
            tmp_path,
            opener=lambda *a, **k: pytest.fail("cached path reached network"),
        )


def test_independent_critic_benchmark_and_optional_ml_error(monkeypatch):
    from follow_the_money.evaluation import critic_metrics, require_ml_extra

    metrics = critic_metrics({"claims": [], "evidence": {}, "labels": []})
    assert (
        metrics["supported_fixture_claims"] == 3
        and metrics["supported_claims_withdrawn"] == 0
    )
    assert metrics["planted_false_claims"] == metrics["false_claims_withdrawn"] == 5
    assert {
        c["kind"] for c in metrics["independent_cases"] if not c["expected_supported"]
    } == {
        "wrong_amount",
        "wrong_txid",
        "wrong_change_output",
        "cluster_through_service",
        "cluster_through_coinjoin",
    }
    monkeypatch.setattr(
        "importlib.util.find_spec",
        lambda name: None if name == "torch_geometric" else object(),
    )
    with pytest.raises(FtmError, match="ml extra"):
        require_ml_extra()


def test_actual_public_recording_fifty_confirmed_rows_on_continuation(tmp_path):
    """Local recorded-payload regression; CI's authored fifty-row test is above."""
    annotation = json.loads(
        (ROOT / "config/follow_the_money/gold-traces.json").read_text(encoding="utf-8")
    )["traces"][0]
    cache = ReplayCache(ROOT / "data/follow_the_money/replay-public")
    url = f"https://mempool.space/api/address/{annotation['seed']}/txs"
    response = cache.read(url)
    if response is None:
        pytest.skip(
            "Approved public recording is local evidence; never download it in tests"
        )
    rows = response.json()
    assert len(rows) == 50 and all(r["status"]["confirmed"] for r in rows)

    class RecordedTransport:
        def get(self, query):
            assert "/txs/chain/" in query
            return response

    page = EsploraClient(RecordedTransport()).get_address_txs(
        annotation["seed"], digest("previous-recorded-page")
    )
    assert len(page.transactions) == 50 and page.next_cursor == rows[-1]["txid"]
    assert all(t.provenance == response.provenance for t in page.transactions)


def test_agent_passes_point_in_time_seen_addresses(tmp_path, monkeypatch):
    import follow_the_money.agent as agent

    fixture = build_fixtures(tmp_path / "fixture")
    original, calls = agent.detect_change, []

    def captured(transaction, *, seen_addresses=None):
        calls.append((transaction.timestamp, seen_addresses))
        return original(transaction, seen_addresses=seen_addresses)

    monkeypatch.setattr(agent, "detect_change", captured)
    service = TraceService.initialize(
        tmp_path / "service",
        cache=Path(fixture["cache"]),
        labels=Path(fixture["labels"]),
    )
    service.start_case(
        TraceRequest(chain="bitcoin", seed="syn_seed_a", request_id=str(uuid4())),
        actor="model",
    )
    assert calls and all(isinstance(seen, set) for _, seen in calls)
    assert any("syn_route_1" in seen for _, seen in calls)


@pytest.mark.parametrize(
    "value",
    [
        None,
        {"score": float("nan"), "ood": False},
        {"score": 2, "ood": False},
        {"score": 0.0, "ood": True, "method": "priority_model"},
    ],
)
def test_agent_invalid_or_ood_scores_preserve_heuristic_search(tmp_path, value):
    fixture = build_fixtures(tmp_path / "fixture")
    service = TraceService.initialize(
        tmp_path / "service",
        cache=Path(fixture["cache"]),
        labels=Path(fixture["labels"]),
        score=lambda *_: value,
    )
    state = service.start_case(
        TraceRequest(chain="bitcoin", seed="syn_seed_a", request_id=str(uuid4())),
        actor="model",
    )["state"]
    assert (
        state["budget"]["calls"] == 3
        and state["endpoints"][0]["address"] == "syn_exchange"
    )
    assert all(
        row["ranking"]["method"] == "heuristic_fallback"
        for row in state["trace"]
        if "ranking" in row
    )


def test_newest_first_page_still_supplies_earlier_freshness_evidence(
    tmp_path, monkeypatch
):
    import follow_the_money.agent as agent

    cache = ReplayCache(tmp_path / "cache")
    labels = LabelStore(tmp_path / "labels.sqlite")
    labels.initialize()
    old = fictional_tx(
        "old",
        [(digest("old-funding"), 0, raw_output("syn_a", 100000))],
        [("syn_b", 90000)],
        5,
    )
    new = fictional_tx(
        "new",
        [(digest("new-funding"), 0, raw_output("syn_a", 100000))],
        [("syn_b", 39123), ("syn_c", 60000)],
        10,
    )
    put(cache, "https://mempool.space/api/address/syn_a/txs", [new, old])
    original, captured = agent.detect_change, {}

    def inspect(transaction, *, seen_addresses):
        captured[transaction.txid] = set(seen_addresses)
        return original(transaction, seen_addresses=seen_addresses)

    monkeypatch.setattr(agent, "detect_change", inspect)
    service = TraceService.initialize(
        tmp_path / "service", cache=cache.root, labels=labels.path
    )
    service.start_case(
        TraceRequest(
            chain="bitcoin", seed="syn_a", max_calls=1, request_id=str(uuid4())
        ),
        actor="model",
    )
    assert "syn_b" in captured[new["txid"]]
    assert "syn_c" not in captured[old["txid"]]
