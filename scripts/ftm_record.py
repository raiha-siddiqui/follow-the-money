"""Owner-invoked bounded Bitcoin fixture recording; never used by tests or CI."""

import argparse
import json
from pathlib import Path

from follow_the_money.clients import EsploraClient
from follow_the_money.contracts import FtmError, utc_now
from follow_the_money.transport import Budget, JsonTransport, ReplayCache, request_url

GENESIS_TXID = "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"  # pragma: allowlist secret -- public Bitcoin genesis transaction ID


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--txid", action="append")
    parser.add_argument("--address", action="append", default=[])
    parser.add_argument("--max-network-calls", type=int, default=4)
    parser.add_argument(
        "--cache", type=Path, default=Path("data/follow_the_money/replay-public")
    )
    parser.add_argument(
        "--manifest", type=Path, default=Path("config/follow_the_money/manifest.json")
    )
    args = parser.parse_args()
    if not 1 <= args.max_network_calls <= 30:
        parser.error("network limit must be from 1 to 30")
    cache = ReplayCache(args.cache)
    budget = Budget(30, args.max_network_calls)
    transport = JsonTransport(cache, budget, mode="record", allow_live=True)
    client = EsploraClient(transport)
    errors = []
    urls = []
    try:
        for txid in args.txid or [GENESIS_TXID]:
            for tool, suffix in (
                (client.get_tx, ""),
                (client.get_outspends, "/outspends"),
            ):
                url = request_url(client.base, f"/tx/{txid}{suffix}")
                urls.append(url)
                try:
                    tool(txid)
                except FtmError as exc:
                    errors.append({"url": url, **exc.to_dict()})
        for address in args.address:
            urls.append(request_url(client.base, f"/address/{address}/txs"))
            try:
                client.get_address_txs(address)
            except FtmError as exc:
                errors.append({"url": urls[-1], **exc.to_dict()})
    finally:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        artifacts = {a["id"]: a for a in manifest["artifacts"]}
        for url in urls:
            response = cache.read(url)
            if response is not None:
                key = "esplora-" + cache.path(url).stem
                artifacts[key] = {
                    "id": key,
                    **response.provenance.to_dict(),
                    "size_bytes": len(response.body),
                    "status": response.status,
                    "local_cache": str(cache.path(url)),
                }
        manifest["artifacts"] = [artifacts[k] for k in sorted(artifacts)]
        run = {
            "at": utc_now(),
            **budget.snapshot(),
            "errors": errors,
            "events": transport.events,
        }
        manifest.setdefault("recording_runs", []).append(run)
        args.manifest.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(run, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
