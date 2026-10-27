"""Typed Esplora and TRC-20 adapters; pagination is explicit and budgeted."""

from __future__ import annotations

import re
import hashlib
from typing import Any

from pydantic import ValidationError

from follow_the_money.contracts import (
    BitcoinTx,
    FtmError,
    FreezeEvent,
    FreezePage,
    Outspend,
    Page,
    Provenance,
    Transfer,
    TxInput,
    TxOutput,
    USDT_TRON,
)
from follow_the_money.transport import JsonTransport, request_url


def identifier(value: str, *, txid: bool = False) -> str:
    """Path safety and shape only; authored fixture addresses have no checksum."""
    pattern = r"[0-9a-f]{64}" if txid else r"[A-Za-z0-9_-]{1,128}"
    if type(value) is not str or not re.fullmatch(pattern, value):
        raise FtmError("invalid_input", "Invalid address or transaction identifier")
    return value


def integer_string(value: Any) -> int:
    """Token amounts are often strings; never round through a binary float."""
    if type(value) is int and value >= 0:
        return value
    if type(value) is str and re.fullmatch(r"[0-9]{1,79}", value):
        return int(value)
    raise ValueError("expected a nonnegative integer amount")


def output(data: dict[str, Any]) -> TxOutput:
    return TxOutput(
        address=data.get("scriptpubkey_address"),
        value=data["value"],
        script_type=data["scriptpubkey_type"],
    )


def parse_bitcoin(data: dict[str, Any], provenance: Provenance) -> BitcoinTx:
    """Keep input outpoints, so downstream paths can check actual spend continuity."""
    try:
        inputs = []
        for item in data["vin"]:
            coinbase = item.get("is_coinbase", False)
            if type(coinbase) is not bool:
                raise ValueError("coinbase flag")
            prev = item.get("prevout")
            if not coinbase and (
                prev is None or "txid" not in item or "vout" not in item
            ):
                raise ValueError("missing input outpoint")
            inputs.append(
                TxInput(
                    txid=None if coinbase else item["txid"],
                    vout=None if coinbase else item["vout"],
                    prevout=None if prev is None else output(prev),
                    coinbase=coinbase,
                )
            )
        result = BitcoinTx(
            txid=data["txid"],
            inputs=tuple(inputs),
            outputs=tuple(output(x) for x in data["vout"]),
            confirmed=data["status"]["confirmed"],
            timestamp=data["status"].get("block_time"),
            provenance=provenance,
        )
        if not result.inputs or not result.outputs:
            raise ValueError("empty transaction")
        coinbase_count = sum(i.coinbase for i in result.inputs)
        if coinbase_count and (coinbase_count != 1 or len(result.inputs) != 1):
            raise ValueError("mixed coinbase inputs")
        if not coinbase_count:
            outpoints = [(i.txid, i.vout) for i in result.inputs]
            if len(set(outpoints)) != len(outpoints) or any(
                i.txid == result.txid for i in result.inputs
            ):
                raise ValueError("duplicate or self-referencing outpoint")
            if sum(o.value for o in result.outputs) > sum(
                i.prevout.value for i in result.inputs
            ):
                raise ValueError("outputs exceed inputs")
        return result
    except (KeyError, TypeError, ValueError, ValidationError):
        raise FtmError("invalid_response", "Malformed Bitcoin transaction") from None


class EsploraClient:
    """Compatible with mempool.space and Blockstream Esplora JSON APIs."""

    def __init__(
        self, transport: JsonTransport, base: str = "https://mempool.space/api"
    ):
        self.transport, self.base = transport, base

    def get_tx(self, txid: str) -> BitcoinTx:
        txid = identifier(txid, txid=True)
        response = self.transport.get(request_url(self.base, f"/tx/{txid}"))
        result = parse_bitcoin(response.json(), response.provenance)
        if result.txid != txid:
            raise FtmError(
                "invalid_response", "Explorer returned a different transaction"
            )
        return result

    def get_address_txs(self, address: str, cursor: str | None = None) -> Page:
        address = identifier(address)
        suffix = (
            "/txs" if cursor is None else "/txs/chain/" + identifier(cursor, txid=True)
        )
        response = self.transport.get(
            request_url(self.base, f"/address/{address}{suffix}")
        )
        raw = response.json()
        if not isinstance(raw, list) or len(raw) > (100 if cursor is None else 50):
            raise FtmError("invalid_response", "Malformed Bitcoin transaction page")
        txs = tuple(parse_bitcoin(item, response.provenance) for item in raw)
        if any(
            address
            not in {i.prevout.address for i in tx.inputs if i.prevout}
            | {o.address for o in tx.outputs}
            for tx in txs
        ):
            raise FtmError(
                "invalid_response", "Explorer returned an unrelated transaction"
            )
        confirmed = [t for t in txs if t.confirmed]
        next_cursor = confirmed[-1].txid if len(confirmed) >= 25 else None
        # A full mempool page also means completeness cannot be established.
        complete = next_cursor is None and sum(not t.confirmed for t in txs) < 50
        if next_cursor == cursor and cursor is not None:
            raise FtmError("invalid_response", "Explorer pagination did not advance")
        if len({t.txid for t in txs}) != len(txs):
            raise FtmError("invalid_response", "Duplicate transaction in page")
        return Page(
            transactions=txs,
            next_cursor=next_cursor,
            complete=complete,
            provenance=response.provenance,
        )

    def get_outspends(self, txid: str) -> tuple[Outspend, ...]:
        response = self.transport.get(
            request_url(self.base, f"/tx/{identifier(txid, txid=True)}/outspends")
        )
        try:
            raw = response.json()
            if not isinstance(raw, list):
                raise ValueError("expected list")
            result = tuple(
                Outspend(
                    spent=x["spent"],
                    txid=x.get("txid"),
                    vin=x.get("vin"),
                    provenance=response.provenance,
                )
                for x in raw
            )
            if any(
                x.spent != (x.txid is not None and x.vin is not None)
                or not x.spent
                and (x.txid is not None or x.vin is not None)
                for x in result
            ):
                raise ValueError("inconsistent outspend")
            return result
        except (TypeError, KeyError, ValueError, AttributeError):
            raise FtmError("invalid_response", "Malformed outspend list") from None


class TronGridClient:
    """USDT only; no live key is available, so the transport forbids live TRON."""

    def __init__(self, transport: JsonTransport, base: str = "https://api.trongrid.io"):
        self.transport, self.base = transport, base

    def get_trc20_transfers(
        self, address: str, cursor: str | None = None, *, limit: int = 200
    ) -> Page:
        if (
            type(limit) is not int
            or not 1 <= limit <= 200
            or cursor is not None
            and (type(cursor) is not str or len(cursor) > 2000)
        ):
            raise FtmError("invalid_input", "Invalid TRC-20 page options")
        address = identifier(address)
        url = request_url(
            self.base,
            f"/v1/accounts/{address}/transactions/trc20",
            {
                "contract_address": USDT_TRON,
                "only_confirmed": "true",
                "limit": limit,
                "fingerprint": cursor,
            },
        )
        response = self.transport.get(url)
        try:
            raw = response.json()
            if (
                raw.get("success") is not True
                or not isinstance(raw["data"], list)
                or len(raw["data"]) > limit
            ):
                raise ValueError("unsuccessful page")
            transfers = []
            for item in raw["data"]:
                if item.get("type") == "Approval":
                    continue
                token = item["token_info"]
                if (
                    item["type"] != "Transfer"
                    or token["address"] != USDT_TRON
                    or integer_string(token["decimals"]) != 6
                ):
                    raise ValueError("wrong contract, decimals or event")
                if address not in {item["from"], item["to"]}:
                    raise ValueError("unrelated account")
                transfers.append(
                    Transfer(
                        txid=item["transaction_id"],
                        sender=item["from"],
                        recipient=item["to"],
                        contract=token["address"],
                        amount=integer_string(item["value"]),
                        decimals=6,
                        timestamp=item["block_timestamp"],
                        event_index=item.get("event_index"),
                        provenance=response.provenance,
                    )
                )
            cursor_next = raw.get("meta", {}).get("fingerprint") or None
            if cursor_next is not None and (
                type(cursor_next) is not str
                or len(cursor_next) > 2000
                or cursor_next == cursor
            ):
                raise ValueError("invalid pagination token")
            return Page(
                transfers=tuple(transfers),
                next_cursor=cursor_next,
                complete=cursor_next is None and len(raw["data"]) < limit,
                provenance=response.provenance,
            )
        except (TypeError, KeyError, ValueError, AttributeError):
            raise FtmError(
                "invalid_response", "Malformed TronGrid transfer page"
            ) from None

    def get_freeze_events(
        self, cursor: str | None = None, *, event_name: str = "AddedBlackList"
    ) -> FreezePage:
        """One bounded page; callers explicitly budget all three event types."""
        if (
            event_name
            not in {"AddedBlackList", "RemovedBlackList", "DestroyedBlackFunds"}
            or cursor is not None
            and (not isinstance(cursor, str) or not 1 <= len(cursor) <= 2000)
        ):
            raise FtmError("invalid_input", "Invalid freeze event query")
        response = self.transport.get(
            request_url(
                self.base,
                f"/v1/contracts/{USDT_TRON}/events",
                {
                    "only_confirmed": "true",
                    "event_name": event_name,
                    "limit": 200,
                    "fingerprint": cursor,
                },
            )
        )
        try:
            raw = response.json()
            rows = raw["data"]
            next_cursor = raw.get("meta", {}).get("fingerprint") or None
            if (
                raw.get("success") is not True
                or not isinstance(rows, list)
                or len(rows) > 200
                or next_cursor is not None
                and (
                    not isinstance(next_cursor, str)
                    or len(next_cursor) > 2000
                    or next_cursor == cursor
                )
                or len(rows) == 200
                and next_cursor is None
            ):
                raise ValueError("failed or incomplete event page")
            events = []
            for row in rows:
                if (
                    row.get("contract_address", USDT_TRON) != USDT_TRON
                    or row["event_name"] != event_name
                ):
                    raise ValueError("wrong contract or event")
                events.append(
                    FreezeEvent(
                        txid=row["transaction_id"],
                        address=tron_address(row["result"]["_user"]),
                        contract=USDT_TRON,
                        action=event_name,
                        timestamp=row["block_timestamp"],
                        provenance=response.provenance,
                    )
                )
            if len({(e.txid, e.address, e.action) for e in events}) != len(events):
                raise ValueError("duplicate event")
            return FreezePage(
                events=tuple(events),
                next_cursor=next_cursor,
                complete=next_cursor is None,
                provenance=response.provenance,
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            raise FtmError(
                "invalid_response", "Malformed or incomplete Tether event page"
            ) from None


class TronScanClient:
    """TronScan's distinct schema is normalized to the same transfer contract."""

    def __init__(
        self,
        transport: JsonTransport,
        base: str = "https://apilist.tronscanapi.com/api",
    ):
        self.transport, self.base = transport, base

    def get_trc20_transfers(
        self, address: str, cursor: str | None = None, *, limit: int = 50
    ) -> Page:
        address = identifier(address)
        try:
            start = integer_string(cursor or "0")
            if type(limit) is not int or not 1 <= limit <= 50 or start > 10000:
                raise ValueError("page bounds")
        except ValueError:
            raise FtmError("invalid_input", "Invalid TronScan page options") from None
        url = request_url(
            self.base,
            "/token_trc20/transfers",
            {
                "relatedAddress": address,
                "contract_address": USDT_TRON,
                "start": start,
                "limit": limit,
                "confirm": "true",
            },
        )
        response = self.transport.get(url)
        try:
            raw = response.json()
            items = raw["token_transfers"]
            if not isinstance(items, list) or len(items) > limit:
                raise ValueError("wrong page")
            transfers = []
            for item in items:
                if (
                    item["contract_address"] != USDT_TRON
                    or item.get("confirmed") is not True
                    or item.get("contractRet") != "SUCCESS"
                    or item.get("finalResult") != "SUCCESS"
                    or integer_string(item["tokenInfo"]["tokenDecimal"]) != 6
                ):
                    raise ValueError("wrong or unsuccessful token transfer")
                if address not in {item["from_address"], item["to_address"]}:
                    raise ValueError("unrelated account")
                transfers.append(
                    Transfer(
                        txid=item["transaction_id"],
                        sender=item["from_address"],
                        recipient=item["to_address"],
                        contract=USDT_TRON,
                        amount=integer_string(item["quant"]),
                        decimals=6,
                        timestamp=item["block_ts"],
                        event_index=item.get("event_index"),
                        provenance=response.provenance,
                    )
                )
            total = integer_string(raw["total"])
            more = start + len(items) < total
            if more and not items:
                raise ValueError("pagination stalled")
            return Page(
                transfers=tuple(transfers),
                next_cursor=str(start + len(items)) if more else None,
                complete=not more,
                provenance=response.provenance,
            )
        except (TypeError, KeyError, ValueError, AttributeError):
            raise FtmError(
                "invalid_response", "Malformed TronScan transfer page"
            ) from None


def tron_address(value: str) -> str:
    """Normalize ABI hex _user addresses to TRON base58check; preserve fixture IDs."""
    if not isinstance(value, str):
        raise ValueError("invalid TRON address")
    raw = value[2:] if value.startswith("0x") else value
    if re.fullmatch(r"[0-9a-fA-F]{40}|41[0-9a-fA-F]{40}|0{24}[0-9a-fA-F]{40}", raw):
        payload = bytes.fromhex(raw[-40:])
        payload = b"\x41" + payload
        check = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        number, encoded = int.from_bytes(payload + check, "big"), ""
        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        while number:
            number, index = divmod(number, 58)
            encoded = alphabet[index] + encoded
        return encoded
    return identifier(value)
