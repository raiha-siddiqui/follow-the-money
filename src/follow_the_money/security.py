"""Shared local HTTP boundary; identities come from the hashed key store in infra/auth.py."""

from contextvars import ContextVar
from urllib.parse import urlsplit

from starlette.responses import JSONResponse

from follow_the_money.auth import KeyStore, Principal
from follow_the_money.contracts import FtmError, strict_json

principal_context: ContextVar[Principal | None] = ContextVar(
    "ftm_principal", default=None
)
MAX_BODY = 65536


def error_payload(code: str, message: str, *, retryable=False, details=None) -> dict:
    return {
        "error": code,
        "message": message,
        "retryable": retryable,
        "details": details or {},
    }


def local_url(value: str) -> str:
    """Credentials may only go to an explicit loopback server, without redirects."""
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Use a plain loopback HTTP origin")
    return value.rstrip("/")


class LocalBoundary:
    """Bound bodies and authenticate before application code; deny browser origins."""

    def __init__(self, app, keys: KeyStore, *, public_health=False):
        if not len(keys):
            raise ValueError("Configure at least one hashed API key")
        self.app, self.keys, self.public_health = app, keys, public_health

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {}
        for key, value in scope["headers"]:
            if key in headers and key in {
                b"authorization",
                b"host",
                b"origin",
                b"content-length",
            }:
                return await self.reject(scope, receive, send, 400, "invalid_input")
            headers[key] = value.decode("latin1")
        host = headers.get(b"host", "")
        try:
            local_url("http://" + host)
        except ValueError:
            return await self.reject(scope, receive, send, 421, "invalid_host")
        if headers.get(b"origin") not in (None, "http://" + host):
            return await self.reject(scope, receive, send, 403, "invalid_origin")
        auth = headers.get(b"authorization", "")
        scheme, separator, presented = auth.partition(" ")
        token = presented if separator and scheme.lower() == "bearer" else None
        principal = self.keys.authenticate(token)
        public = (
            self.public_health
            and scope["path"] == "/health"
            and scope["method"] == "GET"
        )
        if principal is None and not public:
            return await self.reject(scope, receive, send, 401, "unauthorized")
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > MAX_BODY:
                return await self.reject(scope, receive, send, 413, "body_too_large")
            if not message.get("more_body"):
                break
        if body and scope["method"] in {"POST", "PUT", "PATCH"}:
            try:
                strict_json(bytes(body))
            except (FtmError, ValueError):
                return await self.reject(scope, receive, send, 422, "invalid_input")
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        context = principal_context.set(principal)
        try:
            return await self.app(scope, bounded_receive, send)
        finally:
            principal_context.reset(context)

    @staticmethod
    async def reject(scope, receive, send, status, code):
        response = JSONResponse(
            error_payload(code, "Request rejected"), status_code=status
        )
        await response(scope, receive, send)
