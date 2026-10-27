"""Explicit bounded public acquisition. Importing this module never downloads."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener

from follow_the_money.contracts import FtmError, Provenance, canonical, strict_json

MAX_DOWNLOAD = 2_000_000_000


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise FtmError(
            "redirect_refused", "Source redirects require operator registry review"
        )


def source_opener():
    return build_opener(ProxyHandler({}), NoRedirects())


def acquire(
    source: dict[str, Any], root: Path, *, opener: Callable | None = None
) -> dict[str, Any]:
    """Stream approved bytes to an exclusive file; receipt only after completion.

    The source registry is operator-owned configuration. No model/tool output
    may provide this registry. This acquisition helper is not an agent tool.
    """
    if source.get("approved") is not True:
        raise FtmError("source_not_approved", "Source is not approved for download")
    bound = source["max_bytes"]
    if type(bound) is not int or not 0 < bound < MAX_DOWNLOAD:
        raise FtmError("invalid_input", "Download bound must be below 2 GB")
    name = source["id"]
    if (
        not isinstance(name, str)
        or not name.replace("-", "").replace("_", "").isalnum()
    ):
        raise FtmError("invalid_input", "Invalid source ID")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    receipt_path = root / (name + ".receipt.json")
    if target.exists():
        if not receipt_path.exists():
            raise FtmError(
                "incomplete_download", "Existing file has no completed receipt"
            )
        receipt = strict_json(receipt_path.read_bytes())
        if (
            receipt["source_url"] != source["url"]
            or receipt["license"] != source["license"]
            or receipt["size_bytes"] != target.stat().st_size
            or receipt["sha256"] != file_hash(target)
            or source.get("sha256") is not None
            and receipt["sha256"] != source["sha256"]
        ):
            raise FtmError("source_changed", "Existing source or receipt differs")
        return {**receipt, "download_operations_this_run": 0}
    temporary = root / (name + ".partial")
    request = Request(
        source["url"], headers={"User-Agent": "FollowTheMoneyResearch/0.1"}
    )
    if not source["url"].startswith("https://"):
        raise FtmError("invalid_input", "Acquisition requires HTTPS")
    sha, size = hashlib.sha256(), 0
    owned = False
    try:
        # Reserve the partial before any network work; never unlink another writer's file.
        handle = temporary.open("xb")
        owned = True
        with handle, (opener or source_opener().open)(request, timeout=30) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > bound:
                raise FtmError("source_too_large", "Source exceeds approved size")
            while chunk := response.read(min(65536, bound - size + 1)):
                size += len(chunk)
                if size > bound:
                    raise FtmError("source_too_large", "Source exceeds approved size")
                handle.write(chunk)
                sha.update(chunk)
        expected = source.get("sha256")
        if expected and expected != sha.hexdigest():
            raise FtmError(
                "source_changed", "Source checksum differs from pinned digest"
            )
        receipt = {
            "id": name,
            "source_url": source["url"],
            "license": source["license"],
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "size_bytes": size,
            "sha256": sha.hexdigest(),
            "download_operations_this_run": 1,
            "revision": source.get("revision"),
            "evidence_kind": source.get("evidence_kind", "public_dataset"),
        }
        temporary.replace(target)
        receipt_path.write_text(canonical(receipt) + "\n", encoding="utf-8")
        return receipt
    finally:
        if owned:
            temporary.unlink(missing_ok=True)


def file_hash(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def provenance(receipt: dict[str, Any]) -> Provenance:
    return Provenance(
        **{
            key: receipt[key]
            for key in (
                "source_url",
                "retrieved_at",
                "sha256",
                "license",
                "evidence_kind",
            )
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry", type=Path, default=Path("config/follow_the_money/sources.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/follow_the_money/sources")
    )
    parser.add_argument(
        "--manifest", type=Path, default=Path("config/follow_the_money/manifest.json")
    )
    parser.add_argument("--source", action="append", required=True)
    args = parser.parse_args()
    sources = {s["id"]: s for s in strict_json(args.registry.read_bytes())["sources"]}
    receipts = (
        strict_json(args.manifest.read_bytes())
        if args.manifest.exists()
        else {"schema": "ftm-source-manifest-v1", "artifacts": [], "blocked": []}
    )
    indexed = {r["id"]: r for r in receipts["artifacts"]}
    for name in args.source:
        if name not in sources:
            parser.error("unknown source")
        receipt = acquire(sources[name], args.output)
        indexed[name] = receipt
        receipts["artifacts"] = [indexed[k] for k in sorted(indexed)]
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps(receipts, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    main()
