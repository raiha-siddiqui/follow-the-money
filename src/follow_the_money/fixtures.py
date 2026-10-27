"""Authored fictional transaction worlds for offline demos and evaluations."""

from pathlib import Path
from follow_the_money.contracts import Label, Provenance, USDT_TRON, canonical, digest
from follow_the_money.labels import LabelStore
from follow_the_money.transport import ReplayCache, request_url

FIXTURE_DATE = "2026-10-26T00:00:00+00:00"


def raw_output(address: str, value: int) -> dict:
    return {
        "scriptpubkey_address": address,
        "value": value,
        "scriptpubkey_type": "v0_p2wpkh",
    }


def fictional_tx(
    name: str,
    inputs: list[tuple[str, int, dict]],
    outputs: list[tuple[str, int]],
    timestamp: int,
) -> dict:
    return {
        "txid": digest({"fictional_transaction": name}),
        "vin": [
            {"txid": txid, "vout": index, "prevout": prevout, "is_coinbase": False}
            for txid, index, prevout in inputs
        ],
        "vout": [raw_output(address, value) for address, value in outputs],
        "status": {"confirmed": True, "block_time": timestamp},
    }


def build_fixtures(root: Path, *, variant: int = 0) -> dict:
    """Materialize a frozen fictional graph; no real wallets or allegations."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    cache = ReplayCache(root / "replay")
    labels = LabelStore(root / "labels.sqlite")
    labels.initialize()

    def address_name(address: str) -> str:
        return f"syn_v{variant}_{address[4:]}" if variant else address

    transactions = []
    seed = fictional_tx(
        "branch-root",
        [
            (digest("funding-a"), 0, raw_output("syn_seed_a", 900000)),
            (digest("funding-partner"), 0, raw_output("syn_partner", 100000)),
        ],
        [(f"syn_noise_{i}", 1000) for i in range(6)] + [("syn_route_1", 993000)],
        1700000000,
    )
    transactions.append(seed)
    route1 = fictional_tx(
        "route-1",
        [(seed["txid"], 6, seed["vout"][6])],
        [("syn_route_noise", 1000), ("syn_route_2", 991000)],
        1700000100,
    )
    transactions.append(route1)
    transactions.append(
        fictional_tx(
            "route-2",
            [(route1["txid"], 1, route1["vout"][1])],
            [("syn_exchange", 990000)],
            1700000200,
        )
    )
    for i in range(6):
        transactions.append(
            fictional_tx(
                f"noise-{i}",
                [(seed["txid"], i, seed["vout"][i])],
                [(f"syn_sink_{i}", 900)],
                1700000100,
            )
        )
    coinjoin = fictional_tx(
        "coinjoin",
        [
            (
                digest(f"cj-funding-{i}"),
                0,
                raw_output("syn_coinjoin" if i == 0 else f"syn_cj_input_{i}", 40000),
            )
            for i in range(3)
        ],
        [(f"syn_cj_output_{i}", 39000) for i in range(3)],
        1700000000,
    )
    transactions.append(coinjoin)
    if variant:
        txids = {
            tx["txid"]: digest({"variant": variant, "txid": tx["txid"]})
            for tx in transactions
        }
        for tx in transactions:
            tx["txid"] = txids[tx["txid"]]
            tx["status"]["block_time"] += variant * 10000
            for item in tx["vin"]:
                item["txid"] = txids.get(
                    item["txid"], digest({"variant": variant, "funding": item["txid"]})
                )
                item["prevout"]["scriptpubkey_address"] = address_name(
                    item["prevout"]["scriptpubkey_address"]
                )
            for item in tx["vout"]:
                item["scriptpubkey_address"] = address_name(
                    item["scriptpubkey_address"]
                )
    address_txs: dict[str, list] = {}
    for tx in transactions:
        addresses = {i["prevout"]["scriptpubkey_address"] for i in tx["vin"]} | {
            o["scriptpubkey_address"] for o in tx["vout"]
        }
        for address in addresses:
            address_txs.setdefault(address, []).append(tx)
    responses = []

    def put(url: str, value: object):
        response = cache.write(
            url,
            200,
            canonical(value).encode(),
            evidence_kind="synthetic",
            license="CC0-1.0 authored fictional fixture",
            retrieved_at=FIXTURE_DATE,
        )
        responses.append({"url": url, "sha256": response.provenance.sha256})

    base = "https://mempool.space/api"
    for address, txs in sorted(address_txs.items()):
        put(
            request_url(base, f"/address/{address}/txs"),
            sorted(txs, key=lambda tx: (-tx["status"]["block_time"], tx["txid"])),
        )
    for tx in transactions:
        put(request_url(base, f"/tx/{tx['txid']}"), tx)
        spends = []
        for index, _ in enumerate(tx["vout"]):
            spend = next(
                (
                    (later, vin)
                    for later in transactions
                    for vin, item in enumerate(later["vin"])
                    if (item["txid"], item["vout"]) == (tx["txid"], index)
                ),
                None,
            )
            spends.append(
                {"spent": False}
                if spend is None
                else {"spent": True, "txid": spend[0]["txid"], "vin": spend[1]}
            )
        put(request_url(base, f"/tx/{tx['txid']}/outspends"), spends)
    transfers = [
        {
            "transaction_id": digest("tron-seed"),
            "from": "syn_tron_seed",
            "to": "syn_tron_route",
            "value": "1000000000",
            "block_timestamp": 1700000000000,
            "type": "Transfer",
            "token_info": {"address": USDT_TRON, "decimals": 6},
            "event_index": 0,
        },
        {
            "transaction_id": digest("tron-route"),
            "from": "syn_tron_route",
            "to": "syn_tron_exchange",
            "value": "900000000",
            "block_timestamp": 1700000100000,
            "type": "Transfer",
            "token_info": {"address": USDT_TRON, "decimals": 6},
            "event_index": 0,
        },
    ]
    for address in ("syn_tron_seed", "syn_tron_route", "syn_tron_exchange"):
        put(
            request_url(
                "https://api.trongrid.io",
                f"/v1/accounts/{address}/transactions/trc20",
                {"contract_address": USDT_TRON, "only_confirmed": "true", "limit": 200},
            ),
            {
                "success": True,
                "data": [t for t in transfers if address in {t["from"], t["to"]}],
                "meta": {},
            },
        )
    for event_name in ("RemovedBlackList", "DestroyedBlackFunds"):
        put(
            request_url(
                "https://api.trongrid.io",
                f"/v1/contracts/{USDT_TRON}/events",
                {"only_confirmed": "true", "event_name": event_name, "limit": 200},
            ),
            {"success": True, "data": [], "meta": {}},
        )
    put(
        request_url(
            "https://api.trongrid.io",
            f"/v1/contracts/{USDT_TRON}/events",
            {"only_confirmed": "true", "event_name": "AddedBlackList", "limit": 200},
        ),
        {
            "success": True,
            "data": [
                {
                    "transaction_id": digest("fictional-freeze"),
                    "event_name": "AddedBlackList",
                    "result": {"_user": "syn_tron_seed"},
                    "block_timestamp": 1699999999000,
                }
            ],
            "meta": {},
        },
    )
    source = Provenance(
        source_url="https://example.invalid/ftm/fictional-labels-v1",
        retrieved_at=FIXTURE_DATE,
        sha256=digest(["syn_exchange", "syn_tron_exchange"]),
        license="CC0-1.0 authored fictional labels",
        evidence_kind="synthetic",
    )
    labels.add(
        [
            Label(
                chain=chain,
                address=address_name(address) if chain == "bitcoin" else address,
                label="Fictional Example Exchange",
                category="exchange",
                source_ref="Authored demo fixture; not a real service",
                provenance=source,
            )
            for chain, address in (
                ("bitcoin", "syn_exchange"),
                ("tron", "syn_tron_exchange"),
            )
        ]
    )
    manifest = {
        "schema": "ftm-fictional-world-v1",
        "evidence_kind": "synthetic",
        "transactions": len(transactions),
        "transfers": len(transfers),
        "responses": responses,
        "graph_sha256": digest({"transactions": transactions, "transfers": transfers}),
        "cache": str(cache.root),
        "labels": str(labels.path),
        "variant": variant,
        "seed": address_name("syn_seed_a"),
        "endpoint": address_name("syn_exchange"),
    }
    (root / "fixture-manifest.json").write_text(
        canonical(manifest) + "\n", encoding="utf-8"
    )
    return manifest
