"""A local append-only hash ledger and durable idempotent tool reservations.

Hashes detect corruption relative to a separately retained anchor. They do not
authenticate a database against an attacker who can rewrite both DB and anchor.
All access is serialized by the portable workspace lock in infra/locking.py, taken by service.py.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, Callable

from follow_the_money.contracts import FtmError, canonical, digest, strict_json, utc_now


class Ledger:
    def __init__(self, root: Path):
        self.root = root
        self.db = sqlite3.connect(root / "ledger.sqlite", timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")

    def close(self) -> None:
        self.db.close()

    def initialize(self) -> None:
        self.db.executescript("""
          CREATE TABLE events(seq INTEGER PRIMARY KEY, event_key TEXT UNIQUE NOT NULL,
            body TEXT NOT NULL, previous TEXT NOT NULL, sha256 TEXT NOT NULL);
          CREATE TABLE cases(id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
            request TEXT NOT NULL, actor TEXT NOT NULL, state TEXT, state_hash TEXT,
            status TEXT NOT NULL, approval TEXT);
          CREATE TABLE operations(case_id TEXT NOT NULL REFERENCES cases(id), op_id TEXT NOT NULL,
            query TEXT NOT NULL, result TEXT, result_hash TEXT, PRIMARY KEY(case_id,op_id));
        """)
        self._anchor(0, "0" * 64)

    def _anchor(self, sequence: int, sha: str) -> None:
        temporary = self.root / "anchor.pending"
        temporary.write_text(
            canonical({"sequence": sequence, "sha256": sha}) + "\n", encoding="utf-8"
        )
        temporary.replace(self.root / "anchor.json")

    def event(
        self,
        case_id: str,
        kind: str,
        payload: dict,
        *,
        key: str | None = None,
        mutation: Callable[[], Any] | None = None,
    ) -> str:
        key = key or digest({"case_id": case_id, "kind": kind, "payload": payload})
        old = self.db.execute(
            "SELECT body,sha256 FROM events WHERE event_key=?", (key,)
        ).fetchone()
        if old:
            saved = strict_json(old["body"])
            if (saved["case_id"], saved["kind"], saved["payload"]) != (
                case_id,
                kind,
                payload,
            ):
                raise FtmError(
                    "conflict", "Audit idempotency key already has different content"
                )
            return old["sha256"]
        last = self.db.execute(
            "SELECT seq,sha256 FROM events ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        seq, previous = (last["seq"] + 1, last["sha256"]) if last else (1, "0" * 64)
        body = {"case_id": case_id, "kind": kind, "payload": payload, "at": utc_now()}
        sha = digest({"sequence": seq, "previous": previous, "body": body})
        with self.db:
            if mutation:
                mutation()
            self.db.execute(
                "INSERT INTO events VALUES(?,?,?,?,?)",
                (seq, key, canonical(body), previous, sha),
            )
        self._anchor(seq, sha)
        return sha

    def verify(self) -> dict[str, Any]:
        previous, count = "0" * 64, 0
        reservations, results, created = {}, {}, set()
        for row in self.db.execute("SELECT * FROM events ORDER BY seq"):
            count += 1
            body = strict_json(row["body"])
            payload = body["payload"]
            if body["kind"] == "case_created":
                created.add(body["case_id"])
            if body["kind"] == "tool_reserved":
                reservations[(body["case_id"], payload["op_id"])] = payload["query"]
            if body["kind"] == "tool_result":
                results[(body["case_id"], payload["op_id"])] = payload["hash"]
            expected = digest(
                {
                    "sequence": count,
                    "previous": previous,
                    "body": strict_json(row["body"]),
                }
            )
            if (
                row["seq"] != count
                or row["previous"] != previous
                or row["sha256"] != expected
            ):
                raise FtmError("audit_corrupt", "Audit hash chain failed verification")
            previous = expected
        try:
            anchor = strict_json((self.root / "anchor.json").read_bytes())
        except (OSError, ValueError):
            raise FtmError("audit_corrupt", "Audit anchor unavailable") from None
        if anchor != {"sequence": count, "sha256": previous}:
            raise FtmError(
                "audit_corrupt",
                "Audit tail differs from retained anchor; operator recovery required",
            )
        cases = {row[0] for row in self.db.execute("SELECT id FROM cases")}
        if cases != created:
            raise FtmError("audit_corrupt", "Case rows differ from creation events")
        operations = list(self.db.execute("SELECT * FROM operations"))
        if {(r["case_id"], r["op_id"]) for r in operations} != set(reservations):
            raise FtmError("audit_corrupt", "Budget reservations differ from audit")
        for row in operations:
            key = (row["case_id"], row["op_id"])
            query = strict_json(row["query"])
            if query != reservations[key] or digest(query) != row["op_id"]:
                raise FtmError("audit_corrupt", "Tool query differs from reservation")
            if row["result"] is None:
                if key in results or row["result_hash"] is not None:
                    raise FtmError("audit_corrupt", "Completed evidence is missing")
            elif (
                digest(strict_json(row["result"])) != row["result_hash"]
                or results.get(key) != row["result_hash"]
            ):
                raise FtmError("audit_corrupt", "Tool evidence differs from audit")
        return {
            "valid": True,
            "events": count,
            "sha256": previous,
            "limitation": "Not a signature; retain independent anchors.",
        }

    def events(self, case_id: str) -> list[dict]:
        return [
            {"sequence": r["seq"], "sha256": r["sha256"], **strict_json(r["body"])}
            for r in self.db.execute("SELECT * FROM events ORDER BY seq")
            if strict_json(r["body"])["case_id"] == case_id
        ]

    def create_case(self, case_id: str, request: dict, actor: str) -> None:
        self.event(
            case_id,
            "case_created",
            {"request": request, "actor": actor},
            key=f"create:{case_id}",
            mutation=lambda: self.db.execute(
                "INSERT INTO cases VALUES(?,?,?,?,NULL,NULL,'preparing',NULL)",
                (case_id, request["request_id"], canonical(request), actor),
            ),
        )

    def by_request(self, request_id: str) -> str | None:
        row = self.db.execute(
            "SELECT id FROM cases WHERE request_id=?", (request_id,)
        ).fetchone()
        return row[0] if row else None

    def case(self, case_id: str) -> dict:
        row = self.db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        if row is None:
            raise FtmError("not_found", "Case does not exist")
        result = dict(row)
        for name in ("request", "state", "approval"):
            result[name] = (
                strict_json(result[name]) if result[name] is not None else None
            )
        events = self.events(case_id)
        creates = [e for e in events if e["kind"] == "case_created"]
        if len(creates) != 1 or creates[0]["payload"] != {
            "request": result["request"],
            "actor": result["actor"],
        }:
            raise FtmError("audit_corrupt", "Case header differs from audit")
        saved = [e for e in events if e["kind"] == "state_saved"]
        if (result["state"] is None) != (not saved):
            raise FtmError("audit_corrupt", "Case state presence differs from audit")
        if result["state"] is not None and (
            digest(result["state"]) != result["state_hash"]
            or not saved
            or saved[-1]["payload"]
            != {"hash": result["state_hash"], "status": result["status"]}
        ):
            raise FtmError("audit_corrupt", "Case state differs from audit")
        decisions = [e for e in events if e["kind"] == "approval_recorded"]
        if (result["approval"] is None) != (not decisions):
            raise FtmError("audit_corrupt", "Approval presence differs from audit")
        if result["approval"] is not None and (
            not decisions or decisions[-1]["payload"] != result["approval"]
        ):
            raise FtmError("audit_corrupt", "Approval differs from audit")
        return result

    def save_state(self, case_id: str, state: dict) -> None:
        sha, status = digest(state), state["status"]
        self.event(
            case_id,
            "state_saved",
            {"hash": sha, "status": status},
            mutation=lambda: self.db.execute(
                "UPDATE cases SET state=?,state_hash=?,status=? WHERE id=?",
                (canonical(state), sha, status, case_id),
            ),
        )

    def approve(self, case_id: str, approval: dict) -> None:
        self.event(
            case_id,
            "approval_recorded",
            approval,
            key=f"approval:{case_id}",
            mutation=lambda: self.db.execute(
                "UPDATE cases SET approval=? WHERE id=?", (canonical(approval), case_id)
            ),
        )

    def calls(self, case_id: str) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM operations WHERE case_id=?", (case_id,)
        ).fetchone()[0]

    def tool(
        self,
        case_id: str,
        query: dict,
        function: Callable[[], dict],
        *,
        max_calls: int,
        failpoint: Callable[[str], None] = lambda stage: None,
    ) -> dict:
        """Reserve before execution. Replay retries reuse one logical operation.

        This service only admits replay transports; all live HTTP recording is a
        separate explicit operator command. A reserved failed call still counts.
        """
        op_id = digest(query)
        row = self.db.execute(
            "SELECT * FROM operations WHERE case_id=? AND op_id=?", (case_id, op_id)
        ).fetchone()
        if row and row["result"] is not None:
            result = strict_json(row["result"])
            completed = [
                e
                for e in self.events(case_id)
                if e["kind"] == "tool_result" and e["payload"]["op_id"] == op_id
            ]
            if (
                digest(result) != row["result_hash"]
                or not completed
                or completed[-1]["payload"]["hash"] != row["result_hash"]
            ):
                raise FtmError("audit_corrupt", "Tool evidence differs from audit")
            return result
        if row is None:
            if self.calls(case_id) >= max_calls:
                raise FtmError("budget_exhausted", "Logical call budget exhausted")
            self.event(
                case_id,
                "tool_reserved",
                {"op_id": op_id, "query": query},
                key=f"reserve:{case_id}:{op_id}",
                mutation=lambda: self.db.execute(
                    "INSERT INTO operations VALUES(?,?,?,NULL,NULL)",
                    (case_id, op_id, canonical(query)),
                ),
            )
        failpoint("after_reservation")
        try:
            result = {"ok": True, "value": function()}
        except FtmError as exc:
            result = {"ok": False, "error": exc.to_dict()}
        sha = digest(result)
        self.event(
            case_id,
            "tool_result",
            {"op_id": op_id, "hash": sha},
            key=f"tool:{case_id}:{op_id}",
            mutation=lambda: self.db.execute(
                "UPDATE operations SET result=?,result_hash=? WHERE case_id=? AND op_id=?",
                (canonical(result), sha, case_id, op_id),
            ),
        )
        failpoint("after_tool_result")
        return result


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
