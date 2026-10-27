"""One locked service boundary for all interfaces and human decisions.

Network acquisition is deliberately separate: this service constructs only
replay transports. Recovery rebuilds a graph from its original request and
audited tool journal, rather than trusting an interrupted checkpoint blindly.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import re
import sqlite3
from uuid import UUID, uuid4

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from follow_the_money.agent import Dependencies, build_graph, initial_state
from follow_the_money.cases import Approval, TraceRequest, proposal_payload
from follow_the_money.clients import EsploraClient, TronGridClient, TronScanClient
from follow_the_money.contracts import FtmError, canonical, digest, strict_json
from follow_the_money.labels import LabelStore
from follow_the_money.memory import CaseMemory
from follow_the_money.resolver import EntityResolver
from follow_the_money.storage import Ledger
from follow_the_money.transport import Budget, JsonTransport, ReplayCache
from follow_the_money.infra import ReviewError, create_lock_file, workspace_lock


def validate_actor(actor: str) -> str:
    if not isinstance(actor, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}", actor
    ):
        raise FtmError("invalid_input", "Invalid actor label")
    return actor


def case_identifier(value: str) -> str:
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise FtmError("invalid_input", "Invalid case ID") from None
    return value


class TraceService:
    def __init__(
        self,
        root: Path,
        *,
        resolver: EntityResolver | None = None,
        score=None,
        model_actors=(),
        rank_override=None,
        memory=None,
        failpoint=lambda stage: None,
    ):
        self.root = Path(root)
        self.model_actors = {"local-mcp", "local-playground", *model_actors}
        settings = strict_json((self.root / "settings.json").read_bytes())
        if settings.get("schema") != "ftm-workspace-v1":
            raise FtmError("incompatible", "Unsupported workspace schema")
        self.model_actors.update(settings.get("model_actors", []))
        self.cache = ReplayCache(Path(settings["cache_root"]))
        self.labels = LabelStore(Path(settings["labels_path"]))
        self.tron_provider = settings["tron_provider"]
        self.resolver = resolver or EntityResolver()
        self.score, self.rank_override, self.memory, self.failpoint = (
            score or self.score_frontier,
            rank_override,
            memory
            or (
                CaseMemory(
                    self.root / "memory", settings.get("memory_namespace", "research")
                )
                if (self.root / "memory").is_dir()
                else None
            ),
            failpoint,
        )

    @staticmethod
    def score_frontier(item: dict, chain: str) -> dict:
        from follow_the_money.scoring import score_address

        return score_address(
            item.get("live_features", ()),
            guard=None,
            chain=chain,
            feature_names=item.get("feature_names", ()),
            heuristic=item["heuristic"],
        )

    def score_address(self, case_id: str, address: str) -> dict:
        """Score an observed address using recorded features; never fetch live data."""
        from follow_the_money.features import (
            LIVE_FEATURES,
            live_features,
            evidence_records,
        )

        case = self.get_case(case_id)
        state = case["state"] or {}
        items = [i for i in state.get("frontier", []) if i["address"] == address]
        items += [
            i
            for i in state.get("trace", [])
            if i.get("address") == address and "heuristic" in i
        ]
        if not items:
            raise FtmError("not_found", "Address has no recorded scoring context")
        item = dict(items[0])
        chain = case["request"]["chain"]
        records = evidence_records(state["evidence"], chain)
        as_of = item.get("received_at", 0) // (1000 if chain == "tron" else 1)
        values = live_features(address, records, as_of=as_of)
        item.update(live_features=values, feature_names=LIVE_FEATURES)
        return {
            "address": address,
            "as_of": as_of,
            "chain": chain,
            "features": values,
            "feature_names": LIVE_FEATURES,
            **self.score(item, chain),
        }

    @classmethod
    def initialize(
        cls,
        root: Path,
        *,
        cache: Path,
        labels: Path,
        tron_provider: str = "trongrid",
        **kwargs,
    ):
        root = Path(root)
        if tron_provider not in {"trongrid", "tronscan"}:
            raise FtmError("invalid_input", "Unknown TRON fixture provider")
        if root.exists() and any(root.iterdir()):
            raise FtmError(
                "workspace_exists", "Initialize requires a new empty workspace"
            )
        if not Path(labels).is_file():
            raise FtmError("invalid_input", "Initialize a label store first")
        root.mkdir(parents=True, exist_ok=True)
        create_lock_file(root)
        (root / "checkpoints").mkdir()
        (root / "settings.json").write_text(
            canonical(
                {
                    "schema": "ftm-workspace-v1",
                    "cache_root": str(Path(cache).resolve()),
                    "labels_path": str(Path(labels).resolve()),
                    "tron_provider": tron_provider,
                    "model_actors": sorted(
                        validate_actor(a) for a in kwargs.get("model_actors", ())
                    ),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        ledger = Ledger(root)
        try:
            ledger.initialize()
        finally:
            ledger.close()
        CaseMemory.initialize(root / "memory")
        return cls(root, **kwargs)

    @contextmanager
    def _locked(self):
        try:
            with workspace_lock(self.root, timeout=5):
                ledger = Ledger(self.root)
                try:
                    ledger.verify()
                    yield ledger
                finally:
                    ledger.close()
        except ReviewError as exc:
            raise FtmError(
                "workspace_busy", "Workspace lock unavailable", retryable=True
            ) from exc

    @contextmanager
    def _graph(self, ledger: Ledger, case_id: str, request: TraceRequest):
        connection = sqlite3.connect(
            self.root / "checkpoints" / f"{case_id}.sqlite", check_same_thread=False
        )
        try:
            serde = JsonPlusSerializer(
                pickle_fallback=False,
                allowed_json_modules=[],
                allowed_msgpack_modules=[("langgraph.types", "Interrupt")],
            )
            saver = SqliteSaver(connection, serde=serde)
            transport = JsonTransport(self.cache, Budget(request.max_calls, 0))
            client = (
                EsploraClient(transport)
                if request.chain == "bitcoin"
                else (
                    TronGridClient(transport)
                    if self.tron_provider == "trongrid"
                    else TronScanClient(transport)
                )
            )
            deps = Dependencies(
                client,
                self.labels,
                ledger,
                self.resolver,
                self.score,
                self.rank_override,
                self.memory,
                self.failpoint,
            )
            yield build_graph(saver, deps)
        finally:
            connection.close()

    @staticmethod
    def _config(thread_id: str) -> dict:
        return {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 5000,
            "callbacks": [],
        }

    def _run(self, ledger: Ledger, case_id: str) -> dict:
        row = ledger.case(case_id)
        request = TraceRequest.model_validate(row["request"])
        thread_id = f"{case_id}:{uuid4()}"
        ledger.event(case_id, "graph_started", {"thread_id": thread_id})
        try:
            with self._graph(ledger, case_id, request) as graph:
                config = self._config(thread_id)
                graph.invoke(initial_state(case_id, thread_id, request), config)
                state = dict(graph.get_state(config).values)
                if (
                    state.get("status") != "awaiting_approval"
                    or digest(proposal_payload(state)) != state["evidence_sha256"]
                ):
                    raise FtmError(
                        "inconsistent",
                        "Graph did not reach a valid human-review boundary",
                    )
                # A previously recorded decision is recoverable only for identical evidence.
                if row["approval"]:
                    if row["approval"]["evidence_sha256"] != state["evidence_sha256"]:
                        raise FtmError(
                            "inconsistent",
                            "Recovered evidence differs from the recorded decision",
                        )
                    graph.invoke(Command(resume=row["approval"]), config)
                    state = dict(graph.get_state(config).values)
                ledger.save_state(case_id, state)
        except FtmError:
            raise
        except Exception as exc:
            raise FtmError(
                "interrupted",
                "Case execution stopped; recover this case",
                details={"case_id": case_id, "next_action": "recover"},
            ) from exc
        return self._view(ledger.case(case_id))

    def start_case(self, request: TraceRequest, *, actor: str) -> dict:
        actor = validate_actor(actor)
        with self._locked() as ledger:
            existing = ledger.by_request(request.request_id)
            if existing:
                row = ledger.case(existing)
                if row["request"] != request.to_dict() or row["actor"] != actor:
                    raise FtmError(
                        "conflict", "Request ID is already bound to different content"
                    )
                return (
                    self._run(ledger, existing)
                    if row["state"] is None
                    else self._view(row)
                )
            case_id = str(uuid4())
            ledger.create_case(case_id, request.to_dict(), actor)
            return self._run(ledger, case_id)

    @staticmethod
    def _view(row: dict) -> dict:
        return {
            "case_id": row["id"],
            "status": row["status"],
            "request": row["request"],
            "created_by": row["actor"],
            "state": row["state"],
            "approval": row["approval"],
            "next_action": "recover"
            if row["state"] is None
            or row["approval"]
            and row["status"] == "awaiting_approval"
            else "approve"
            if row["status"] == "awaiting_approval"
            else "none",
        }

    def get_case(self, case_id: str) -> dict:
        case_identifier(case_id)
        with self._locked() as ledger:
            return self._view(ledger.case(case_id))

    def list_cases(self) -> list[dict]:
        with self._locked() as ledger:
            return [
                {
                    "case_id": row["id"],
                    "status": row["status"],
                    "created_by": row["actor"],
                }
                for row in (
                    ledger.case(r["id"])
                    for r in ledger.db.execute(
                        "SELECT id FROM cases ORDER BY rowid DESC LIMIT 100"
                    ).fetchall()
                )
            ]

    def recover(self, case_id: str) -> dict:
        case_identifier(case_id)
        with self._locked() as ledger:
            row = ledger.case(case_id)
            if row["state"] is not None and not (
                row["approval"] and row["status"] == "awaiting_approval"
            ):
                return self._view(row)
            return self._run(ledger, case_id)

    def submit_approval(self, case_id: str, approval: Approval, *, actor: str) -> dict:
        case_identifier(case_id)
        actor = validate_actor(actor)
        submitted = {**approval.to_dict(), "actor": actor}
        with self._locked() as ledger:
            row = ledger.case(case_id)
            if actor == row["actor"] or actor in self.model_actors:
                raise FtmError("forbidden", "An independent human approver is required")
            if row["approval"]:
                if row["approval"] != submitted:
                    raise FtmError(
                        "conflict", "A different decision is already recorded"
                    )
                return (
                    self._run(ledger, case_id)
                    if row["status"] == "awaiting_approval"
                    else self._view(row)
                )
            state = row["state"]
            if row["status"] != "awaiting_approval" or state is None:
                raise FtmError("invalid_state", "Case is not awaiting approval")
            if (
                approval.evidence_sha256 != state["evidence_sha256"]
                or digest(proposal_payload(state)) != approval.evidence_sha256
            ):
                raise FtmError(
                    "stale_approval",
                    "Approval digest differs from the reviewed evidence",
                )
            with self._graph(
                ledger, case_id, TraceRequest.model_validate(row["request"])
            ) as graph:
                config = self._config(state["thread_id"])
                snapshot = graph.get_state(config)
                if (
                    dict(snapshot.values) != state
                    or snapshot.next != ("human_approval",)
                    or not any(t.interrupts for t in snapshot.tasks)
                ):
                    raise FtmError(
                        "checkpoint_changed",
                        "Checkpoint differs from the audited human-review boundary",
                    )
                ledger.approve(case_id, submitted)
                self.failpoint("after_approval")
                graph.invoke(Command(resume=submitted), config)
                finished = dict(graph.get_state(config).values)
                ledger.save_state(case_id, finished)
            return self._view(ledger.case(case_id))

    def audit(self, case_id: str) -> dict:
        case_identifier(case_id)
        with self._locked() as ledger:
            ledger.case(case_id)
            return {"verification": ledger.verify(), "events": ledger.events(case_id)}
