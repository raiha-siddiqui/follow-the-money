"""Namespaced case memory with auditable revisioned recall, never identity facts.

Corrections create revisions. Deletion is a tombstone that removes active recall;
the audit history remains for research reproducibility, not secure erasure.
"""

from contextlib import contextmanager
from pathlib import Path
import re
from uuid import uuid4

from follow_the_money.contracts import FtmError, canonical, digest, strict_json
from follow_the_money.storage import Ledger
from follow_the_money.infra import create_lock_file, workspace_lock


class CaseMemory:
    def __init__(self, root: Path, namespace: str = "research"):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", namespace):
            raise FtmError("invalid_input", "Invalid memory namespace")
        self.root, self.namespace = Path(root), namespace

    @classmethod
    def initialize(cls, root: Path, namespace: str = "research"):
        memory = cls(root, namespace)
        if memory.root.exists() and any(memory.root.iterdir()):
            raise FtmError(
                "workspace_exists", "Memory initialization needs an empty directory"
            )
        memory.root.mkdir(parents=True, exist_ok=True)
        create_lock_file(memory.root)
        ledger = Ledger(memory.root)
        try:
            ledger.initialize()
            ledger.db.execute("""CREATE TABLE memory_entries(
              namespace TEXT NOT NULL, id TEXT NOT NULL, kind TEXT NOT NULL,
              payload TEXT NOT NULL, revision INTEGER NOT NULL, deleted INTEGER NOT NULL,
              PRIMARY KEY(namespace,id))""")
            ledger.db.commit()
        finally:
            ledger.close()
        return memory

    @contextmanager
    def _locked(self):
        with workspace_lock(self.root, timeout=5):
            ledger = Ledger(self.root)
            try:
                ledger.verify()
                # Validate the materialized recall table against immutable revisions.
                expected = {}
                for row in ledger.db.execute("SELECT body FROM events ORDER BY seq"):
                    event = strict_json(row[0])
                    if event["kind"] == "memory_revision":
                        value = event["payload"]
                        expected[(value["namespace"], value["id"])] = value
                actual = list(ledger.db.execute("SELECT * FROM memory_entries"))
                if {(r["namespace"], r["id"]) for r in actual} != set(expected):
                    raise FtmError("audit_corrupt", "Memory rows differ from audit")
                for row in actual:
                    value = expected[(row["namespace"], row["id"])]
                    if (
                        any(row[k] != value[k] for k in ("kind", "revision", "deleted"))
                        or strict_json(row["payload"]) != value["payload"]
                    ):
                        raise FtmError(
                            "audit_corrupt", "Memory content differs from audit"
                        )
                yield ledger
            finally:
                ledger.close()

    def _put(
        self,
        ledger: Ledger,
        entry_id: str,
        kind: str,
        payload: dict,
        *,
        actor: str,
        reason: str,
        expected_revision: int | None = None,
        deleted: bool = False,
    ) -> dict:
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}", actor)
            or not reason
            or len(reason) > 1000
        ):
            raise FtmError(
                "invalid_input", "Memory edits require an actor and bounded reason"
            )
        if len(canonical(payload)) > 100000:
            raise FtmError("invalid_input", "Memory entry exceeds size limit")
        row = ledger.db.execute(
            "SELECT * FROM memory_entries WHERE namespace=? AND id=?",
            (self.namespace, entry_id),
        ).fetchone()
        if row and expected_revision is None:
            if (
                row["kind"] == kind
                and strict_json(row["payload"]) == payload
                and row["deleted"] == int(deleted)
            ):
                return {"id": entry_id, "revision": row["revision"]}
            raise FtmError("conflict", "Existing memory needs an explicit revision")
        if expected_revision is not None and (
            row is None or row["revision"] != expected_revision
        ):
            raise FtmError("conflict", "Stale memory revision")
        revision = 1 if row is None else row["revision"] + 1
        value = {
            "namespace": self.namespace,
            "id": entry_id,
            "kind": kind,
            "payload": payload,
            "revision": revision,
            "deleted": int(deleted),
            "actor": actor,
            "reason": reason,
        }
        ledger.event(
            payload.get("case_id", "memory"),
            "memory_revision",
            value,
            mutation=lambda: ledger.db.execute(
                "INSERT OR REPLACE INTO memory_entries VALUES(?,?,?,?,?,?)",
                (
                    self.namespace,
                    entry_id,
                    kind,
                    canonical(payload),
                    revision,
                    int(deleted),
                ),
            ),
        )
        return {"id": entry_id, "revision": revision}

    def entries(self, *, include_deleted: bool = False) -> list[dict]:
        with self._locked() as ledger:
            rows = ledger.db.execute(
                "SELECT * FROM memory_entries WHERE namespace=? ORDER BY id",
                (self.namespace,),
            )
            return [
                {**dict(r), "payload": strict_json(r["payload"])}
                for r in rows
                if include_deleted or not r["deleted"]
            ]

    def query_case_memory(
        self,
        chain: str,
        addresses: list[str],
        *,
        exclude_case: str | None = None,
        blocked_members: list[str] = (),
    ) -> dict:
        if chain not in {"bitcoin", "tron"} or len(addresses) > 3000:
            raise FtmError("invalid_input", "Invalid memory query")
        requested, blocked = set(addresses), set(blocked_members)
        links = []
        entries = self.entries()
        active_cases = {
            e["payload"]["case_id"]
            for e in entries
            if e["kind"] == "case" and "correction" not in e["payload"]
        }
        for entry in entries:
            p = entry["payload"]
            if (
                entry["kind"] != "cluster"
                or p["chain"] != chain
                or p["case_id"] == exclude_case
                or p["case_id"] not in active_cases
                or "correction" in p
                or set(p["members"]) & blocked
            ):
                continue
            shared = sorted(requested & set(p["members"]) - blocked)
            if shared:
                links.append(
                    {
                        "prior_case_id": p["case_id"],
                        "cluster_id": entry["id"],
                        "shared_addresses": shared,
                        "txids": p["txids"],
                        "revision": entry["revision"],
                        "evidence_sha256": p["evidence_sha256"],
                        "notice": "An exact address overlaps a prior research hypothesis; this does not establish common ownership.",
                    }
                )
        return {
            "namespace": self.namespace,
            "links": links,
            "match_method": "exact_address_in_reviewed_cluster",
        }

    def rules(self, chain: str, address: str) -> list[dict]:
        return [
            {"id": e["id"], "revision": e["revision"], **e["payload"]}
            for e in self.entries()
            if e["kind"] == "analyst_rule"
            and e["payload"]["chain"] == chain
            and e["payload"]["address"] == address
        ]

    def add_rule(
        self, *, chain: str, address: str, action: str, text: str, actor: str
    ) -> dict:
        from follow_the_money.clients import identifier

        identifier(address)
        if (
            chain not in {"bitcoin", "tron"}
            or action not in {"stop", "annotate"}
            or not text
            or len(text) > 1000
        ):
            raise FtmError(
                "invalid_input", "Rules may only stop or annotate an exact address"
            )
        with self._locked() as ledger:
            return self._put(
                ledger,
                str(uuid4()),
                "analyst_rule",
                {
                    "chain": chain,
                    "address": address,
                    "action": action,
                    "text": text,
                    "source": "analyst_opinion",
                    "actor": actor,
                },
                actor=actor,
                reason="Analyst-created scoped rule",
            )

    def correct(
        self, entry_id: str, *, expected_revision: int, note: str, actor: str
    ) -> dict:
        """Annotate a correction; do not rewrite recorded transaction facts."""
        if not note or len(note) > 1000:
            raise FtmError("invalid_input", "Correction needs a bounded note")
        with self._locked() as ledger:
            row = ledger.db.execute(
                "SELECT * FROM memory_entries WHERE namespace=? AND id=?",
                (self.namespace, entry_id),
            ).fetchone()
            if row is None:
                raise FtmError("not_found", "Memory entry not found")
            payload = strict_json(row["payload"])
            payload["correction"] = {"note": note, "actor": actor}
            return self._put(
                ledger,
                entry_id,
                row["kind"],
                payload,
                actor=actor,
                reason=note,
                expected_revision=expected_revision,
                deleted=bool(row["deleted"]),
            )

    def delete(
        self, entry_id: str, *, expected_revision: int, reason: str, actor: str
    ) -> dict:
        with self._locked() as ledger:
            row = ledger.db.execute(
                "SELECT * FROM memory_entries WHERE namespace=? AND id=?",
                (self.namespace, entry_id),
            ).fetchone()
            if row is None:
                raise FtmError("not_found", "Memory entry not found")
            return self._put(
                ledger,
                entry_id,
                row["kind"],
                strict_json(row["payload"]),
                actor=actor,
                reason=reason,
                expected_revision=expected_revision,
                deleted=True,
            )

    def publish(self, state: dict) -> dict:
        if (
            state["status"] != "completed"
            or state["approval"].get("decision") != "approve"
        ):
            raise FtmError(
                "invalid_state", "Only reviewed completed cases enter memory"
            )
        case_id, chain = state["case_id"], state["request"]["chain"]
        blocked = set(state["clusters"]["service"]) | {
            e["address"] for e in state["endpoints"]
        }
        retained_txids = {t for c in state["report"]["claims"] for t in c["txids"]}
        clusters = [
            g
            for g in state["clusters"]["groups"]
            if not set(g["members"]) & blocked and set(g["txids"]) <= retained_txids
        ]
        with self._locked() as ledger:
            common = {
                "case_id": case_id,
                "chain": chain,
                "evidence_sha256": state["evidence_sha256"],
            }
            self._put(
                ledger,
                "case:" + case_id,
                "case",
                {
                    **common,
                    "txids": sorted(retained_txids),
                    "report_sha256": digest(state["report"]),
                },
                actor=state["approval"]["actor"],
                reason="Human-reviewed case publication",
            )
            for group in clusters:
                entry_id = digest(
                    {
                        "namespace": self.namespace,
                        "case_id": case_id,
                        "chain": chain,
                        "members": group["members"],
                    }
                )
                self._put(
                    ledger,
                    entry_id,
                    "cluster",
                    {
                        **common,
                        **group,
                        "limitation": "Capped common-input hypothesis, not wallet ownership",
                    },
                    actor=state["approval"]["actor"],
                    reason="Human-reviewed cluster hypothesis",
                )
            for link in state.get("memory_context", {}).get("links", []):
                entry_id = digest(
                    {
                        "namespace": self.namespace,
                        "case_id": case_id,
                        "prior_case_id": link["prior_case_id"],
                        "cluster_id": link["cluster_id"],
                    }
                )
                self._put(
                    ledger,
                    entry_id,
                    "link",
                    {**common, **link},
                    actor=state["approval"]["actor"],
                    reason="Reviewed overlap with prior case",
                )
        return {
            "status": "published",
            "namespace": self.namespace,
            "clusters": len(clusters),
            "links": len(state.get("memory_context", {}).get("links", [])),
        }
