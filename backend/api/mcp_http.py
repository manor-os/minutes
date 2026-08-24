"""
HTTP transport for the Minutes MCP server (cloud edition).

Exposes the FastMCP streamable-HTTP app under ``/api/mcp`` with
service-level authentication so the Manor AI platform (and user tokens)
can reach meeting tools over the network:

  * ``X-API-Key: <MEETING_NOTE_TAKER_API_KEY>`` + ``X-Entity-Id: <entity>``
    — service-to-service (Manor agents acting for an entity)
  * ``Authorization: Bearer <user JWT>`` — the token's own entity_id is used

The resolved entity is bound to a ContextVar for the duration of the
request, so every MCP tool query is tenant-scoped.
"""
import contextlib
import json

from mcp_server.server import mcp, reset_request_entity_id, set_request_entity_id


def _resolve_entity_id(headers: dict) -> str | None:
    """Return the entity for this request, or None when unauthenticated."""
    from api.services.api_key_service import api_key_service

    api_key = headers.get("x-api-key")
    if api_key and api_key_service.validate_api_key(api_key):
        entity_id = (headers.get("x-entity-id") or "").strip()
        return entity_id or None

    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        from api.services.local_auth_service import verify_token

        payload = verify_token(auth[7:].strip())
        if payload and payload.get("entity_id"):
            return str(payload["entity_id"])
    return None


# Built once per process — FastMCP's session manager can only be started
# once, so repeated wrapper constructions must share the same ASGI app.
_mcp_asgi_app = None


def _get_mcp_asgi_app():
    global _mcp_asgi_app
    if _mcp_asgi_app is None:
        # Serve at the mount root — the outer app mounts us at /api/mcp
        mcp.settings.streamable_http_path = "/"
        _mcp_asgi_app = mcp.streamable_http_app()
    return _mcp_asgi_app


class AuthenticatedMCPApp:
    """Pure-ASGI wrapper: authenticate, bind the entity, forward to MCP."""

    def __init__(self):
        self._app = _get_mcp_asgi_app()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers") or []
        }
        entity_id = _resolve_entity_id(headers)
        if not entity_id:
            body = json.dumps({
                "error": "unauthorized",
                "detail": "Authenticate with X-API-Key + X-Entity-Id, "
                          "or a Bearer user token.",
            }).encode()
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return

        token = set_request_entity_id(entity_id)
        try:
            await self._app(scope, receive, send)
        finally:
            reset_request_entity_id(token)


@contextlib.asynccontextmanager
async def mcp_lifespan(app):
    """Run the MCP session manager for the lifetime of the API process.
    Must wrap the FastAPI lifespan when the MCP mount is enabled."""
    async with mcp.session_manager.run():
        yield
