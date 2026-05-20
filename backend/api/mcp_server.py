"""MCP server exposing meeting CRUD as tools.

Mounts as a Streamable HTTP transport at `/mcp` on the FastAPI app. The
`mcp_tools` module holds the pure DB-touching functions; this file wraps
them with auth (JWT -> entity_id) so each tool is multi-tenant safe.

Auth model: every tool takes an `auth_token` string parameter. The token
is the minutes JWT a user gets from local login or Manor SSO. The MCP
client (Claude Desktop, an agent SDK, etc.) is expected to plumb it
through on each call. Validation happens via the existing
`local_auth_service.verify_token` so any token also accepted by the REST
API works here unchanged.
"""
from typing import Any, Dict, List, Optional

from loguru import logger

from api.services.local_auth_service import verify_token, _stable_entity_id
from api import mcp_tools


def _resolve_entity_id(auth_token: str) -> int:
    """Decode the caller's JWT and return their entity_id.

    Raises ValueError on bad/expired tokens — FastMCP surfaces this as a
    tool-call error the client can display.
    """
    if not auth_token:
        raise ValueError("auth_token is required")
    payload = verify_token(auth_token)
    if not payload:
        raise ValueError("Invalid or expired auth_token")
    eid = payload.get("entity_id")
    if eid is None:
        # Fall back to deriving from email — keeps parity with the REST middleware.
        email = payload.get("email") or ""
        if not email:
            raise ValueError("Token is missing both entity_id and email")
        eid = _stable_entity_id(email)
    return int(eid)


# Lazily build the FastMCP instance: the import of `mcp.server.fastmcp`
# triggers anyio module load, which is fine at startup but we want
# `import api.mcp_server` to work even when `mcp` isn't installed (the
# server simply won't be mounted).
def build_server():
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(
        name="minutes",
        instructions=(
            "Tools for managing meeting recordings, transcripts, summaries, "
            "and action items on the minutes platform. Every tool requires "
            "an `auth_token` argument — pass the JWT issued by /api/auth/login "
            "or the Manor SSO callback. Data is scoped to the token's owner."
        ),
    )

    @server.tool(description="List the caller's meetings with filtering and pagination.")
    def list_meetings(
        auth_token: str,
        limit: int = 20,
        offset: int = 0,
        status: Optional[str] = None,
        search: Optional[str] = None,
        sort: str = "newest",
        favorite: Optional[bool] = None,
        tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        eid = _resolve_entity_id(auth_token)
        return mcp_tools.list_meetings(
            entity_id=eid, limit=limit, offset=offset, status=status,
            search=search, sort=sort, favorite=favorite, tag=tag,
        )

    @server.tool(description="Fetch one meeting in full (including transcript).")
    def get_meeting(auth_token: str, meeting_id: str) -> Optional[Dict[str, Any]]:
        eid = _resolve_entity_id(auth_token)
        return mcp_tools.get_meeting(entity_id=eid, meeting_id=meeting_id)

    @server.tool(description="Get just the transcript and speaker segments for a meeting.")
    def get_meeting_transcript(auth_token: str, meeting_id: str) -> Optional[Dict[str, Any]]:
        eid = _resolve_entity_id(auth_token)
        return mcp_tools.get_meeting_transcript(entity_id=eid, meeting_id=meeting_id)

    @server.tool(description="Get the AI summary, key points, and action items for a meeting.")
    def get_meeting_summary(auth_token: str, meeting_id: str) -> Optional[Dict[str, Any]]:
        eid = _resolve_entity_id(auth_token)
        return mcp_tools.get_meeting_summary(entity_id=eid, meeting_id=meeting_id)

    @server.tool(description="Update a meeting. Any field left as None is unchanged.")
    def update_meeting(
        auth_token: str,
        meeting_id: str,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        tags: Optional[List[str]] = None,
        is_favorite: Optional[bool] = None,
        action_items: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        eid = _resolve_entity_id(auth_token)
        return mcp_tools.update_meeting(
            entity_id=eid, meeting_id=meeting_id, title=title, summary=summary,
            tags=tags, is_favorite=is_favorite, action_items=action_items,
        )

    @server.tool(description="Permanently delete a meeting and its derived data.")
    def delete_meeting(auth_token: str, meeting_id: str) -> Dict[str, Any]:
        eid = _resolve_entity_id(auth_token)
        ok = mcp_tools.delete_meeting(entity_id=eid, meeting_id=meeting_id)
        return {"deleted": ok, "meeting_id": meeting_id}

    @server.tool(description="Search meetings by title / transcript / summary text.")
    def search_meetings(auth_token: str, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        eid = _resolve_entity_id(auth_token)
        return mcp_tools.search_meetings(entity_id=eid, query=query, limit=limit)

    @server.tool(description="List the available meeting templates (general, sales call, standup, etc.).")
    def list_meeting_templates() -> List[Dict[str, Any]]:
        return mcp_tools.list_meeting_templates()

    return server


# Module-level singleton, built on import so the FastAPI app can mount it.
_mcp_server = None


def get_mcp_server():
    global _mcp_server
    if _mcp_server is None:
        try:
            _mcp_server = build_server()
        except Exception as e:
            logger.warning(f"Could not build MCP server: {e}")
            _mcp_server = None
    return _mcp_server
