"""
Minutes MCP server: meeting tools for the Manor AI platform.

Served over streamable HTTP by ``api.mcp_http`` (mounted at ``/api/mcp``),
which authenticates the caller and binds the acting entity — and, when the
caller names one, the acting user — to request-scoped context variables
before any tool runs. Every tool reads that context, so a request can only
ever see its own tenant's meetings.

Tool surface (kept in step with Manor's ``manor_mcp_minutes`` module):
search_meetings, get_transcript, get_summary, list_recent_meetings,
get_action_items, chat_with_meeting, get_meeting_details, get_meeting_stats.

``chat_with_meeting`` needs a model. MCP callers are Manor entities, so the
call goes through the Manor LLM gateway billed to that entity (route
"manor" in ``api.services.llm_config``); a deployment without Manor client
credentials falls back to the server's own key, exactly like the community
edition's web chat.
"""
import contextvars
import json
from typing import Optional

from loguru import logger
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import func, or_

from database.db import get_db_session  # module attribute: tests swap it for a sqlite session factory
from database.models import MeetingModel

# Stateless JSON-RPC over HTTP: one request, one response, no session
# handshake — that is what Manor's bridge speaks. Host checking is the
# reverse proxy's job; the outer ASGI wrapper already authenticates.
mcp = FastMCP(
    "minutes",
    instructions=(
        "Meeting notes recorded with Minutes: search meetings, read transcripts, "
        "summaries and action items, and ask questions about a meeting."
    ),
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

_entity_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("minutes_mcp_entity_id", default=None)
_user_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("minutes_mcp_user_id", default=None)


def set_request_entity_id(entity_id) -> contextvars.Token:
    return _entity_ctx.set(str(entity_id))


def reset_request_entity_id(token: contextvars.Token) -> None:
    _entity_ctx.reset(token)


def set_request_user_id(user_id) -> contextvars.Token:
    return _user_ctx.set(str(user_id) if user_id else None)


def reset_request_user_id(token: contextvars.Token) -> None:
    _user_ctx.reset(token)


class NoEntityContext(RuntimeError):
    """A tool ran outside an authenticated request."""


def current_entity_id() -> str:
    entity_id = _entity_ctx.get()
    if not entity_id:
        raise NoEntityContext("MCP tool called without an authenticated entity")
    return entity_id


def current_user_id() -> Optional[str]:
    return _user_ctx.get()


# ── helpers ──

MAX_LIMIT = 50
NOT_FOUND = "Meeting not found."


def _clamp(limit, default: int) -> int:
    try:
        value = int(limit) if limit is not None else default
    except (TypeError, ValueError):
        value = default
    return max(1, min(MAX_LIMIT, value))


def _dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, default=str, indent=2)


def _load_meeting(db, meeting_id: str):
    """The meeting, only if it belongs to the acting entity."""
    if not meeting_id:
        return None
    return (
        db.query(MeetingModel)
        .filter(MeetingModel.id == str(meeting_id), MeetingModel.entity_id == current_entity_id())
        .first()
    )


def _brief(meeting: MeetingModel) -> dict:
    return {
        "id": meeting.id,
        "title": meeting.title,
        "status": meeting.status.value if hasattr(meeting.status, "value") else meeting.status,
        "platform": meeting.platform,
        "duration_seconds": meeting.duration or 0,
        "created_at": meeting.created_at.isoformat() if meeting.created_at else None,
    }


def _snippet(text: Optional[str], query: str, width: int = 160) -> str:
    if not text:
        return ""
    lowered, needle = text.lower(), query.lower()
    at = lowered.find(needle)
    if at < 0:
        return text[:width]
    start = max(0, at - width // 3)
    return ("…" if start else "") + text[start:start + width] + ("…" if start + width < len(text) else "")


def _normalized_action_items(meeting: MeetingModel) -> list:
    items = meeting.action_items if isinstance(meeting.action_items, list) else []
    return [item if isinstance(item, dict) else {"task": str(item)} for item in items]


def _normalized_key_points(meeting: MeetingModel) -> list:
    points = meeting.key_points if isinstance(meeting.key_points, list) else []
    return [p if isinstance(p, str) else (p.get("text") or p.get("description") or str(p)) for p in points]


# ── tools ──


@mcp.tool()
def search_meetings(query: str, limit: int = 10) -> str:
    """Search the entity's meetings by title or transcript content."""
    query = (query or "").strip()
    if not query:
        return _dump([])
    pattern = f"%{query}%"
    db = get_db_session()
    try:
        rows = (
            db.query(MeetingModel)
            .filter(
                MeetingModel.entity_id == current_entity_id(),
                or_(MeetingModel.title.ilike(pattern), MeetingModel.transcript.ilike(pattern),
                    MeetingModel.summary.ilike(pattern)),
            )
            .order_by(MeetingModel.created_at.desc())
            .limit(_clamp(limit, 10))
            .all()
        )
        return _dump([
            {**_brief(m), "snippet": _snippet(m.transcript or m.summary, query)} for m in rows
        ])
    finally:
        db.close()


@mcp.tool()
def list_recent_meetings(limit: int = 10) -> str:
    """List the entity's most recent meetings."""
    db = get_db_session()
    try:
        rows = (
            db.query(MeetingModel)
            .filter(MeetingModel.entity_id == current_entity_id())
            .order_by(MeetingModel.created_at.desc())
            .limit(_clamp(limit, 10))
            .all()
        )
        return _dump([_brief(m) for m in rows])
    finally:
        db.close()


@mcp.tool()
def get_transcript(meeting_id: str) -> str:
    """Get the full transcript of a meeting."""
    db = get_db_session()
    try:
        meeting = _load_meeting(db, meeting_id)
        if meeting is None:
            return NOT_FOUND
        return meeting.transcript or "This meeting has no transcript yet."
    finally:
        db.close()


@mcp.tool()
def get_summary(meeting_id: str) -> str:
    """Get a meeting's AI summary, key points, and action items."""
    db = get_db_session()
    try:
        meeting = _load_meeting(db, meeting_id)
        if meeting is None:
            return NOT_FOUND
        return _dump({
            "id": meeting.id,
            "title": meeting.title,
            "summary": meeting.summary or "",
            "key_points": _normalized_key_points(meeting),
            "action_items": _normalized_action_items(meeting),
        })
    finally:
        db.close()


@mcp.tool()
def get_action_items(meeting_id: str) -> str:
    """Get the action items recorded for a meeting."""
    db = get_db_session()
    try:
        meeting = _load_meeting(db, meeting_id)
        if meeting is None:
            return NOT_FOUND
        return _dump(_normalized_action_items(meeting))
    finally:
        db.close()


@mcp.tool()
def get_meeting_details(meeting_id: str) -> str:
    """Get a meeting's metadata: title, time, duration, platform, status, participants."""
    db = get_db_session()
    try:
        meeting = _load_meeting(db, meeting_id)
        if meeting is None:
            return NOT_FOUND
        metadata = meeting.meeting_metadata if isinstance(meeting.meeting_metadata, dict) else {}
        return _dump({
            **_brief(meeting),
            "participants": metadata.get("participants") or metadata.get("speakers") or [],
            "language": metadata.get("language"),
            "template": metadata.get("template"),
            "tags": [t.strip() for t in meeting.tags.split(",") if t.strip()] if meeting.tags else [],
            "is_favorite": bool(meeting.is_favorite),
            "has_transcript": bool(meeting.transcript),
            "has_summary": bool(meeting.summary),
            "updated_at": meeting.updated_at.isoformat() if meeting.updated_at else None,
        })
    finally:
        db.close()


@mcp.tool()
def get_meeting_stats() -> str:
    """Get aggregate meeting statistics for the entity (counts, duration totals)."""
    db = get_db_session()
    try:
        entity_id = current_entity_id()
        by_status = dict(
            db.query(MeetingModel.status, func.count(MeetingModel.id))
            .filter(MeetingModel.entity_id == entity_id)
            .group_by(MeetingModel.status)
            .all()
        )
        total_seconds = (
            db.query(func.coalesce(func.sum(MeetingModel.duration), 0))
            .filter(MeetingModel.entity_id == entity_id)
            .scalar()
        ) or 0
        return _dump({
            "total_meetings": sum(by_status.values()),
            "by_status": {str(k): int(v) for k, v in by_status.items()},
            "total_duration_seconds": int(total_seconds),
            "total_duration_minutes": round(int(total_seconds) / 60, 1),
        })
    finally:
        db.close()


# ── chat ──

CHAT_SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions about meeting content. "
    "Use only the provided meeting data to answer. If the answer isn't in the "
    "meeting data, say so. Be concise."
)
TRANSCRIPT_CHAR_LIMIT = 8000


def build_chat_messages(meeting: MeetingModel, question: str) -> list:
    """Same grounding the web chat uses, from the ORM row."""
    parts = []
    if meeting.title:
        parts.append(f"Meeting title: {meeting.title}")
    if meeting.summary:
        parts.append(f"Summary:\n{meeting.summary}")
    points = _normalized_key_points(meeting)
    if points:
        parts.append("Key points:\n" + "\n".join(f"- {p}" for p in points))
    items = _normalized_action_items(meeting)
    if items:
        parts.append("Action items:\n" + "\n".join(
            f"- {i.get('task') or i.get('description') or i}" for i in items
        ))
    if meeting.transcript:
        transcript = meeting.transcript
        if len(transcript) > TRANSCRIPT_CHAR_LIMIT:
            transcript = transcript[:TRANSCRIPT_CHAR_LIMIT] + "\n...(transcript truncated)"
        parts.append(f"Transcript:\n{transcript}")
    return [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {"role": "user", "content": f"Meeting data:\n{chr(10).join(chr(10) + p for p in parts)}\n\nQuestion: {question}"},
    ]


def resolve_chat_llm(entity_id: str, user_id: Optional[str]):
    """(client, model) for an MCP chat: Manor gateway billed to the entity,
    or the server key when this deployment has no Manor client credentials."""
    from api.services.llm_config import ManorGatewayNotConfigured, get_llm_model, get_openrouter_client, resolve_llm

    try:
        return resolve_llm(
            route="manor",
            manor_ctx={"entity_id": entity_id, "user_id": user_id, "business_type": "meeting_chat"},
        )
    except ManorGatewayNotConfigured:
        logger.warning("Minutes MCP chat: no Manor client credentials, using the server LLM key")
        return get_openrouter_client(), get_llm_model()


@mcp.tool()
def chat_with_meeting(meeting_id: str, question: str) -> str:
    """Ask a question about a specific meeting; answered from its transcript."""
    question = (question or "").strip()
    if not question:
        return "Question is required."
    db = get_db_session()
    try:
        meeting = _load_meeting(db, meeting_id)
        if meeting is None:
            return NOT_FOUND
        messages = build_chat_messages(meeting, question)
        entity_id = current_entity_id()
    finally:
        db.close()

    from api.services.billing_service import is_credit_exhausted_error
    from api.services.messages import message as user_message

    client, model = resolve_chat_llm(entity_id, current_user_id())
    try:
        response = client.chat.completions.create(
            model=model, messages=messages, temperature=0.3, max_tokens=1000,
        )
    except Exception as exc:  # surfaced as tool text so the agent can relay it
        if is_credit_exhausted_error(exc):
            return user_message("credit_exhausted", "en")
        logger.error(f"Minutes MCP chat failed: {exc}")
        return f"Failed to generate an answer: {type(exc).__name__}"
    content = (response.choices[0].message.content or "").strip() if response.choices else ""
    return content or "The model returned no answer."
