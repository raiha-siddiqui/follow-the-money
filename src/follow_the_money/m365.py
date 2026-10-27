"""Microsoft 365 Agents SDK local wrapper; authenticated local Playground, no send path."""

import asyncio
import sqlite3
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from aiohttp import web
from microsoft_agents.activity import Activity, Attachment
from microsoft_agents.hosting.aiohttp import CloudAdapter, start_agent_process
from microsoft_agents.hosting.core import AgentApplication, MemoryStorage
from microsoft_agents.hosting.core.rest_channel_service_client_factory import (
    RestChannelServiceClientFactory,
)

from follow_the_money.cases import TraceRequest
from follow_the_money.auth import KeyStore, Principal
from follow_the_money.contracts import FtmError, digest
from follow_the_money.views import case_summary
from follow_the_money.security import local_url, principal_context
from follow_the_money.service import TraceService

HELP = "Local research demo. Commands: trace bitcoin syn_seed_a; trace tron syn_tron_seed; case <case-id>. Traces use replay only and pause for human review in the local UI. No command approves, sends a request, or establishes ownership."


def review_card(case: dict, reviewer_url="http://127.0.0.1:8501") -> dict:
    local_url(reviewer_url)
    state = case.get("state") or {}
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": "Research case awaiting human review",
                "weight": "Bolder",
                "wrap": True,
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Case", "value": case["case_id"]},
                    {"title": "Status", "value": case["status"]},
                    {
                        "title": "Evidence SHA-256",
                        "value": state.get("evidence_sha256", "pending"),
                    },
                ],
            },
            {
                "type": "TextBlock",
                "text": "Inspect transaction citations and critic outcomes. Approval is recorded only in the authenticated local reviewer UI. Nothing is sent.",
                "wrap": True,
            },
        ],
        "actions": [
            {
                "type": "Action.OpenUrl",
                "title": "Open local human review",
                "url": reviewer_url,
            }
        ],
    }


class LocalReplyFactory(RestChannelServiceClientFactory):
    """Use the SDK's anonymous reply buffer; prohibit connector/OAuth operations."""

    def __init__(self):
        super().__init__(None, token_service_endpoint="http://127.0.0.1:9/disabled")

    async def create_connector_client(self, *args, **kwargs):
        raise PermissionError("Outbound connectors are disabled in the local demo")

    async def create_user_token_client(
        self, context, claims_identity, use_anonymous=False
    ):
        if not use_anonymous or context.activity.is_agentic_request():
            raise PermissionError("Only anonymous buffered local replies are supported")
        return await super().create_user_token_client(context, claims_identity, True)


class DisabledConnections:
    """SDK connection protocol for the local demo; every token request fails closed."""

    def get_connection(self, *args, **kwargs):
        raise PermissionError("OAuth and external connections are disabled")

    get_default_connection = get_connection
    get_token_provider = get_connection
    get_token_provider_from_activity = get_connection
    get_default_connection_configuration = get_connection


class ConversationQuota:
    """Persist reservations so retries and restarts cannot reset the local quota."""

    def __init__(self, service, max_cases=5, max_conversations=100):
        if not 1 <= max_cases <= 100 or not 1 <= max_conversations <= 1000:
            raise ValueError("Invalid Playground quota")
        self.path = service.root / "playground-quota.sqlite"
        self.max_cases, self.max_conversations = max_cases, max_conversations
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS reservations (actor TEXT, conversation TEXT, request_id TEXT UNIQUE)"
            )

    def reserve(self, actor, conversation, request_id):
        conversation = digest(conversation)
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT actor, conversation FROM reservations WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if existing:
                if existing != (actor, conversation):
                    raise ValueError("Request belongs to another conversation")
                return
            count = db.execute(
                "SELECT count(*) FROM reservations WHERE actor=? AND conversation=?",
                (actor, conversation),
            ).fetchone()[0]
            total = db.execute(
                "SELECT count(*) FROM (SELECT DISTINCT actor, conversation FROM reservations)"
            ).fetchone()[0]
            if (
                count >= self.max_cases
                or count == 0
                and total >= self.max_conversations
            ):
                raise ValueError("Conversation quota reached")
            db.execute(
                "INSERT INTO reservations VALUES (?,?,?)",
                (actor, conversation, request_id),
            )

    def owns(self, actor, conversation, request_id):
        with sqlite3.connect(self.path) as db:
            return (
                db.execute(
                    "SELECT 1 FROM reservations WHERE actor=? AND conversation=? AND request_id=?",
                    (actor, digest(conversation), request_id),
                ).fetchone()
                is not None
            )


def create_agent(service: TraceService, *, max_cases_per_conversation=5):
    adapter = CloudAdapter(channel_service_client_factory=LocalReplyFactory())
    agent = AgentApplication(
        storage=MemoryStorage(),
        adapter=adapter,
        start_typing_timer=False,
        connection_manager=DisabledConnections(),
    )
    lock = asyncio.Lock()
    quota = ConversationQuota(service, max_cases=max_cases_per_conversation)

    @agent.activity("message")
    async def message(context, _):
        # A card submission or source document cannot become an approval command.
        activity = context.activity
        if activity.value or activity.attachments:
            await context.send_activity(
                "Submissions and attachments are not accepted here. Use the authenticated human review UI."
            )
            return
        principal = principal_context.get()
        if principal is None or principal.role != "agent":
            raise PermissionError("Agent authentication required")
        text = activity.text or ""
        parts = text.split()
        try:
            if len(text) > 500:
                raise ValueError
            async with lock:
                if len(parts) == 3 and parts[0] == "trace":
                    if not activity.id or len(activity.id) > 200:
                        raise ValueError
                    request = TraceRequest(
                        chain=parts[1],
                        seed=parts[2],
                        request_id=str(
                            uuid5(
                                NAMESPACE_URL,
                                f"ftm-playground:{principal.actor}:{activity.conversation.id}:{activity.id}",
                            )
                        ),
                    )
                    quota.reserve(
                        principal.actor, activity.conversation.id, request.request_id
                    )
                    case = await asyncio.to_thread(
                        service.start_case, request, actor=principal.actor
                    )
                elif len(parts) == 2 and parts[0] == "case":
                    case = await asyncio.to_thread(service.get_case, parts[1])
                    if not quota.owns(
                        principal.actor,
                        activity.conversation.id,
                        case["request"]["request_id"],
                    ):
                        raise ValueError("Case belongs to another conversation")
                else:
                    await context.send_activity(HELP)
                    return
            summary = case_summary(case)
            await context.send_activity(
                f"Case {summary['case_id']}: {summary['status']}. Retained claims shown: {len(summary['claims'])}; withdrawn: {summary['withdrawn_claims']}. Research leads only."
            )
            await context.send_activity(
                Activity(
                    type="message",
                    attachments=[
                        Attachment(
                            content_type="application/vnd.microsoft.card.adaptive",
                            content=review_card(case),
                        )
                    ],
                )
            )
        except (ValueError, FtmError):
            await context.send_activity(
                "Request rejected or replay unavailable. Use the documented commands and inspect the local audit."
            )

    @agent.error
    async def error(context, _):
        await context.send_activity(
            "Local operation failed. Inspect the workspace and recover through the reviewer UI."
        )

    return agent


def create_local_app(
    service: TraceService,
    keys: KeyStore | None = None,
    *,
    allow_anonymous=False,
    max_cases_per_conversation=5,
) -> web.Application:
    """Only synchronous local replies: no callback to an activity's service URL."""
    if not keys and not allow_anonymous:
        raise ValueError(
            "Configure agent keys or explicitly opt in to anonymous local access"
        )
    service.model_actors.update(getattr(keys, "model_actors", ()))
    agent = create_agent(service, max_cases_per_conversation=max_cases_per_conversation)

    @web.middleware
    async def boundary(request, handler):
        try:
            local_url("http://" + request.host)
            if request.remote not in {"127.0.0.1", "::1"}:
                raise ValueError
            if request.headers.get("Origin") not in (None, "http://" + request.host):
                raise ValueError
            if request.method == "POST":
                body = await request.json()
                if (
                    body.get("deliveryMode") != "expectReplies"
                    or body.get("channelId") != "emulator"
                ):
                    raise ValueError
                if not isinstance(body.get("serviceUrl"), str):
                    raise ValueError
                url = urlsplit(body["serviceUrl"])
                local_url(f"{url.scheme}://{url.netloc}")
                conversation = body.get("conversation", {}).get("id")
                if (
                    not isinstance(conversation, str)
                    or not 1 <= len(conversation) <= 200
                ):
                    raise ValueError
        except (ValueError, TypeError, AttributeError):
            return web.json_response({"error": "local_playground_only"}, status=403)
        principal = None
        if request.path != "/health":
            # Separate local bearer header: the SDK Authorization header is reserved for channel JWTs.
            token = request.headers.get("X-FTM-Key")
            principal = keys.authenticate(token) if keys else None
            if principal is None and allow_anonymous and token is None:
                principal = Principal("local-playground", "agent")
            if principal is None:
                return web.json_response({"error": "unauthorized"}, status=401)
            if principal.role != "agent":
                return web.json_response({"error": "forbidden"}, status=403)
        context = principal_context.set(principal)
        try:
            return await handler(request)
        finally:
            principal_context.reset(context)

    app = web.Application(middlewares=[boundary], client_max_size=65536)

    async def messages(request):
        return await start_agent_process(request, agent, agent.adapter)

    async def health(_):
        return web.json_response(
            {
                "mode": "anonymous_local_playground"
                if allow_anonymous
                else "authenticated_local_playground",
                "sends_external_messages": False,
            }
        )

    app.router.add_post("/api/messages", messages)
    app.router.add_get("/health", health)
    return app


def run_local(service: TraceService, *, port=3978, **kwargs):
    web.run_app(
        create_local_app(service, **kwargs),
        host="127.0.0.1",
        port=port,
        access_log=None,
    )
