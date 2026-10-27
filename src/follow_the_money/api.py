"""Authenticated local FastAPI interface over the single durable trace service."""

from typing import Literal

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPBearer
from pydantic import Field

from follow_the_money.cases import Approval, TraceRequest
from follow_the_money.contracts import Address, Chain, FtmError, Record
from follow_the_money.security import LocalBoundary, error_payload, principal_context
from follow_the_money.service import TraceService
from follow_the_money.views import case_summary, memory_summary
from follow_the_money.auth import KeyStore, Principal, can_start, is_human
from follow_the_money.infra import Observability, ObservabilityMiddleware


class MemoryQuery(Record):
    chain: Chain
    addresses: list[Address] = Field(min_length=1, max_length=100)


class RuleRequest(Record):
    chain: Chain
    address: Address
    action: Literal["stop", "annotate"]
    text: str = Field(min_length=1, max_length=1000)


class MemoryRevision(Record):
    expected_revision: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=1000)
    action: Literal["correct", "delete"]


def create_app(
    service: TraceService, keys: KeyStore, *, obs: Observability | None = None
) -> FastAPI:
    obs = obs or Observability()
    if service is not None:
        service.model_actors.update(getattr(keys, "model_actors", ()))
    app = FastAPI(
        title="Follow the Money — research review",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        telemetry={
            "tracing": False,
            "metrics": False,
            "logs": False,
            "operation_spans": False,
            "auto_configure": False,
        },
    )
    app.state.service, app.state.observability = service, obs
    bearer = HTTPBearer(auto_error=False)

    def viewer(_=Depends(bearer)) -> Principal:
        principal = principal_context.get()
        if principal is None:
            raise FtmError("unauthorized", "Authentication required")
        return principal

    def reviewer(principal=Depends(viewer)) -> Principal:
        if not is_human(principal, service.model_actors):
            raise FtmError("forbidden", "Independent human approver role required")
        return principal

    def agent(principal=Depends(viewer)) -> Principal:
        if not can_start(principal):
            raise FtmError("forbidden", "Agent role required")
        return principal

    def human_reader(principal=Depends(viewer)) -> Principal:
        if principal.role == "agent" or principal.actor in service.model_actors:
            raise FtmError("forbidden", "Use the bounded model case operation")
        return principal

    @app.exception_handler(FtmError)
    async def service_error(_: Request, exc: FtmError):
        status = {
            "unauthorized": 401,
            "forbidden": 403,
            "not_found": 404,
            "invalid_input": 422,
            "workspace_busy": 503,
            "replay_miss": 409,
        }.get(exc.code, 409)
        return JSONResponse(
            error_payload(
                exc.code, exc.message, retryable=exc.retryable, details=exc.details
            ),
            status_code=status,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid(_: Request, exc: RequestValidationError):
        fields = [
            {"field": ".".join(map(str, e["loc"])), "problem": e["type"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            error_payload(
                "invalid_input",
                "Input does not match schema",
                details={"fields": fields},
            ),
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        return JSONResponse(
            error_payload(
                "internal_error",
                "Operation failed; inspect the local audit and recover if needed",
            ),
            status_code=500,
        )

    @app.get("/health", operation_id="health")
    def health():
        return {"status": "ok", "mode": "replay", "research_only": True}

    @app.get("/v1/cases", operation_id="list_cases")
    def list_cases(_=Depends(viewer)) -> dict:
        return {"cases": service.list_cases()}

    @app.post("/v1/cases", operation_id="start_trace")
    def start_trace(request: TraceRequest, actor=Depends(agent)) -> dict:
        with obs.span("ftm.start_trace"):
            case = service.start_case(request, actor=actor.actor)
            return (
                case_summary(case)
                if actor.role == "agent" or actor.actor in service.model_actors
                else case
            )

    @app.get("/v1/cases/{case_id}", operation_id="get_case")
    def get_case(case_id: str, _=Depends(human_reader)) -> dict:
        return service.get_case(case_id)

    @app.get("/v1/cases/{case_id}/summary", operation_id="get_case_summary")
    def get_case_summary(case_id: str, _=Depends(viewer)) -> dict:
        return case_summary(service.get_case(case_id))

    @app.get("/v1/cases/{case_id}/audit", operation_id="get_audit")
    def get_audit(case_id: str, _=Depends(human_reader)) -> dict:
        return service.audit(case_id)

    @app.post("/v1/cases/{case_id}/approval", operation_id="human_approval")
    def human_approval(
        case_id: str, approval: Approval, actor=Depends(reviewer)
    ) -> dict:
        with obs.span("ftm.human_approval"):
            return service.submit_approval(case_id, approval, actor=actor.actor)

    @app.post("/v1/cases/{case_id}/recover", operation_id="recover_case")
    def recover_case(case_id: str, _=Depends(reviewer)) -> dict:
        return service.recover(case_id)

    @app.post("/v1/memory/query", operation_id="query_case_memory")
    def query_memory(query: MemoryQuery, actor=Depends(viewer)) -> dict:
        value = service.memory.query_case_memory(query.chain, list(query.addresses))
        return (
            memory_summary(value)
            if actor.role == "agent" or actor.actor in service.model_actors
            else value
        )

    @app.get("/v1/memory", operation_id="list_memory")
    def list_memory(_=Depends(human_reader)) -> dict:
        return {"entries": service.memory.entries()}

    @app.post("/v1/memory/rules", operation_id="add_rule")
    def add_rule(rule: RuleRequest, actor=Depends(reviewer)) -> dict:
        return service.memory.add_rule(**rule.to_dict(), actor=actor.actor)

    @app.post("/v1/memory/{entry_id}/revision", operation_id="revise_memory")
    def revise_memory(
        entry_id: str, revision: MemoryRevision, actor=Depends(reviewer)
    ) -> dict:
        args = {"expected_revision": revision.expected_revision, "actor": actor.actor}
        if revision.action == "correct":
            return service.memory.correct(entry_id, note=revision.note, **args)
        return service.memory.delete(entry_id, reason=revision.note, **args)

    @app.get("/metrics", include_in_schema=False)
    def metrics(_=Depends(viewer)):
        return Response(obs.metrics.render(), media_type="text/plain")

    app.add_middleware(LocalBoundary, keys=keys, public_health=True)
    app.add_middleware(
        ObservabilityMiddleware,
        observability=obs,
    )
    return app
