import json

import pytest


pytest.importorskip("pydantic")
pytest.importorskip("httpx")

from follow_the_money.clients import (
    EsploraClient,
    TronGridClient,
    TronScanClient,
    parse_bitcoin,
)
from follow_the_money.contracts import FtmError, USDT_TRON
from follow_the_money.transport import Budget, JsonTransport, ReplayCache, request_url


def recorded(tmp_path, url, value):
    cache = ReplayCache(tmp_path)
    cache.write(
        url,
        200,
        json.dumps(value).encode(),
        evidence_kind="synthetic",
        license="Authored fictional fixture",
    )
    return JsonTransport(cache, Budget(10))


@pytest.mark.parametrize("provider", ["grid", "scan", "freeze"])
def test_non_object_tron_responses_are_typed_errors(tmp_path, provider):
    class InvalidResponse:
        def json(self):
            return []

    class ReplayStub:
        def get(self, url):
            return InvalidResponse()

    client = (
        TronScanClient(ReplayStub())
        if provider == "scan"
        else TronGridClient(ReplayStub())
    )
    with pytest.raises(FtmError) as exc:
        if provider == "freeze":
            client.get_freeze_events()
        else:
            client.get_trc20_transfers("syn_tron_seed")
    assert exc.value.code == "invalid_response"


def test_bitcoin_replay_roundtrip(tmp_path, make_tx):
    raw = make_tx()
    url = "https://mempool.space/api/tx/" + raw["txid"]
    client = EsploraClient(recorded(tmp_path, url, raw))
    tx = client.get_tx(raw["txid"])
    assert tx.outputs[0].value == 10000
    assert tx.inputs[0].prevout.address == "syn_seed_a"
    assert tx.provenance.evidence_kind == "synthetic"


def test_bitcoin_pagination_is_explicit(tmp_path, make_tx):
    rows = [make_tx(i) for i in range(25)]
    url = "https://mempool.space/api/address/syn_seed_a/txs"
    client = EsploraClient(recorded(tmp_path, url, rows))
    page = client.get_address_txs("syn_seed_a")
    assert page.next_cursor == rows[-1]["txid"] and not page.complete
    with pytest.raises(FtmError) as exc:
        client.get_address_txs("syn_seed_a", page.next_cursor)
    assert exc.value.code == "replay_miss"


def test_duplicate_page_rejected(tmp_path, make_tx):
    url = "https://mempool.space/api/address/syn_seed_a/txs"
    client = EsploraClient(recorded(tmp_path, url, [make_tx(), make_tx()]))
    with pytest.raises(FtmError):
        client.get_address_txs("syn_seed_a")


def test_wrong_txid_and_malformed_satoshis_rejected(tmp_path, make_tx, provenance):
    raw = make_tx()
    client = EsploraClient(
        recorded(tmp_path, "https://mempool.space/api/tx/" + "f" * 64, raw)
    )
    with pytest.raises(FtmError):
        client.get_tx("f" * 64)
    raw["vout"][0]["value"] = 1.1
    with pytest.raises(FtmError):
        parse_bitcoin(raw, provenance)


@pytest.mark.parametrize(
    "item",
    [
        {"spent": True},
        {"spent": False, "txid": "a" * 64},
        {"spent": "false"},
        {"spent": True, "txid": "a" * 64, "vin": True},
    ],
)
def test_invalid_outspends_rejected(tmp_path, item):
    url = "https://mempool.space/api/tx/" + "a" * 64 + "/outspends"
    with pytest.raises(FtmError):
        EsploraClient(recorded(tmp_path, url, [item])).get_outspends("a" * 64)


def test_trongrid_exact_amount_contract_and_cursor(tmp_path):
    row = {
        "transaction_id": "a" * 64,
        "from": "syn_tron_seed",
        "to": "syn_tron_exchange",
        "token_info": {"address": USDT_TRON, "decimals": 6},
        "type": "Transfer",
        "value": "9007199254740993",
        "block_timestamp": 1700000000000,
    }
    url = request_url(
        "https://api.trongrid.io",
        "/v1/accounts/syn_tron_seed/transactions/trc20",
        {"contract_address": USDT_TRON, "only_confirmed": "true", "limit": 200},
    )
    transport = recorded(
        tmp_path,
        url,
        {"success": True, "data": [row], "meta": {"fingerprint": "opaque-next"}},
    )
    client = TronGridClient(transport)
    page = client.get_trc20_transfers("syn_tron_seed")
    assert page.transfers[0].amount == 9007199254740993
    assert page.next_cursor == "opaque-next" and not page.complete
    row["token_info"]["address"] = "fake_token"
    transport.cache.write(
        url,
        200,
        json.dumps({"success": True, "data": [row]}).encode(),
        evidence_kind="synthetic",
        license="Authored",
    )
    with pytest.raises(FtmError):
        client.get_trc20_transfers("syn_tron_seed")


def test_tronscan_schema_and_failed_transfer(tmp_path):
    row = {
        "transaction_id": "b" * 64,
        "from_address": "syn_t",
        "to_address": "syn_u",
        "contract_address": USDT_TRON,
        "quant": "1000001",
        "tokenInfo": {"tokenDecimal": 6},
        "block_ts": 1700000000000,
        "confirmed": True,
        "contractRet": "SUCCESS",
        "finalResult": "SUCCESS",
    }
    url = request_url(
        "https://apilist.tronscanapi.com/api",
        "/token_trc20/transfers",
        {
            "relatedAddress": "syn_t",
            "contract_address": USDT_TRON,
            "start": 0,
            "limit": 50,
            "confirm": "true",
        },
    )
    transport = recorded(tmp_path, url, {"token_transfers": [row], "total": 1})
    assert (
        TronScanClient(transport).get_trc20_transfers("syn_t").transfers[0].amount
        == 1000001
    )
    row["finalResult"] = "REVERT"
    transport.cache.write(
        url,
        200,
        json.dumps({"token_transfers": [row], "total": 1}).encode(),
        evidence_kind="synthetic",
        license="Authored",
    )
    with pytest.raises(FtmError):
        TronScanClient(transport).get_trc20_transfers("syn_t")


def test_freeze_events_are_contract_specific(tmp_path):
    url = request_url(
        "https://api.trongrid.io",
        f"/v1/contracts/{USDT_TRON}/events",
        {"only_confirmed": "true", "event_name": "AddedBlackList", "limit": 200},
    )
    transport = recorded(
        tmp_path,
        url,
        {
            "success": True,
            "data": [
                {
                    "transaction_id": "c" * 64,
                    "event_name": "AddedBlackList",
                    "result": {"_user": "syn_t"},
                    "block_timestamp": 1700000000000,
                }
            ],
        },
    )
    events = TronGridClient(transport).get_freeze_events().events
    assert events[0].address == "syn_t" and events[0].contract == USDT_TRON


@pytest.mark.parametrize("value", ["../x", "x?api_key=z", "x/y", "x\n", "", "ü"])
def test_address_path_injection_rejected(tmp_path, value):
    with pytest.raises(FtmError) as exc:
        EsploraClient(JsonTransport(ReplayCache(tmp_path), Budget(1))).get_address_txs(
            value
        )
    assert exc.value.code == "invalid_input"


@pytest.mark.parametrize(
    "mutation",
    ["inflation", "duplicate_input", "self_reference", "no_input", "no_output"],
)
def test_impossible_bitcoin_transaction_rejected(make_tx, provenance, mutation):
    raw = make_tx()
    if mutation == "inflation":
        raw["vout"][0]["value"] = 100000000
    elif mutation == "duplicate_input":
        raw["vin"].append(raw["vin"][0])
    elif mutation == "self_reference":
        raw["vin"][0]["txid"] = raw["txid"]
    elif mutation == "no_input":
        raw["vin"] = []
    else:
        raw["vout"] = []
    with pytest.raises(FtmError) as exc:
        parse_bitcoin(raw, provenance)
    assert exc.value.code == "invalid_response"
