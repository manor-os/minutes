"""Pure CRUD functions used by the MCP server.

These functions take `entity_id` directly (not a JWT) so they're easy to
unit-test without spinning up a transport. Auth/JWT decoding happens one
layer up in `mcp_server.py`.

Every function enforces multi-tenant isolation by scoping queries to the
caller's `entity_id` — a wrong/missing entity_id returns 'not found',
never another tenant's data.
"""
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import or_

from database.db import get_db_session
from database.models import MeetingModel, MeetingStatusEnum


_ALLOWED_SORTS = {"newest", "oldest", "longest", "shortest"}


def _meeting_to_dict(m: MeetingModel) -> Dict[str, Any]:
    """Shrink the full meeting row into the shape MCP clients usually need —
    excludes the full transcript (often very large; fetch separately)."""
    d = m.to_dict()
    d.pop("transcript", None)
    return d


def list_meetings(
    entity_id: int,
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "newest",
    favorite: Optional[bool] = None,
    tag: Optional[str] = None,
) -> Dict[str, Any]:
    """List the caller's meetings, with filtering, search, pagination."""
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    if sort not in _ALLOWED_SORTS:
        sort = "newest"

    db = get_db_session()
    try:
        q = db.query(MeetingModel).filter(MeetingModel.entity_id == entity_id)
        if status:
            try:
                q = q.filter(MeetingModel.status == MeetingStatusEnum(status.lower()).value)
            except ValueError:
                pass
        if search:
            pat = f"%{search}%"
            q = q.filter(or_(
                MeetingModel.title.ilike(pat),
                MeetingModel.transcript.ilike(pat),
                MeetingModel.summary.ilike(pat),
            ))
        if favorite is True:
            q = q.filter(MeetingModel.is_favorite == True)  # noqa: E712
        if tag:
            q = q.filter(MeetingModel.tags.ilike(f"%{tag}%"))

        total = q.count()
        if sort == "oldest":
            q = q.order_by(MeetingModel.created_at.asc())
        elif sort == "longest":
            q = q.order_by(MeetingModel.duration.desc())
        elif sort == "shortest":
            q = q.order_by(MeetingModel.duration.asc())
        else:
            q = q.order_by(MeetingModel.created_at.desc())

        rows = q.offset(offset).limit(limit).all()
        return {
            "meetings": [_meeting_to_dict(m) for m in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    finally:
        db.close()


def get_meeting(entity_id: int, meeting_id: str) -> Optional[Dict[str, Any]]:
    """Fetch one meeting (full row, including transcript) for the caller."""
    db = get_db_session()
    try:
        m = db.query(MeetingModel).filter(
            MeetingModel.id == meeting_id,
            MeetingModel.entity_id == entity_id,
        ).first()
        return m.to_dict() if m else None
    finally:
        db.close()


def get_meeting_transcript(entity_id: int, meeting_id: str) -> Optional[Dict[str, Any]]:
    """Just the transcript (+ speaker segments) for the caller's meeting."""
    db = get_db_session()
    try:
        m = db.query(MeetingModel).filter(
            MeetingModel.id == meeting_id,
            MeetingModel.entity_id == entity_id,
        ).first()
        if not m:
            return None
        md = m.meeting_metadata or {}
        return {
            "id": m.id,
            "title": m.title,
            "transcript": m.transcript,
            "speaker_segments": md.get("speaker_segments", []),
            "speakers": md.get("speakers", []),
            "duration": m.duration,
        }
    finally:
        db.close()


def get_meeting_summary(entity_id: int, meeting_id: str) -> Optional[Dict[str, Any]]:
    """Summary + key_points + action_items for the caller's meeting."""
    db = get_db_session()
    try:
        m = db.query(MeetingModel).filter(
            MeetingModel.id == meeting_id,
            MeetingModel.entity_id == entity_id,
        ).first()
        if not m:
            return None
        return {
            "id": m.id,
            "title": m.title,
            "summary": m.summary,
            "key_points": m.key_points,
            "action_items": m.action_items,
            "status": m.status,
        }
    finally:
        db.close()


def update_meeting(
    entity_id: int,
    meeting_id: str,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    tags: Optional[List[str]] = None,
    is_favorite: Optional[bool] = None,
    action_items: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Partial update. Only fields supplied are touched."""
    db = get_db_session()
    try:
        m = db.query(MeetingModel).filter(
            MeetingModel.id == meeting_id,
            MeetingModel.entity_id == entity_id,
        ).first()
        if not m:
            return None
        if title is not None:
            m.title = title
        if summary is not None:
            m.summary = summary
        if tags is not None:
            # The DB column stores a comma-separated string.
            m.tags = ",".join(str(t).strip() for t in tags if str(t).strip()) or None
        if is_favorite is not None:
            m.is_favorite = bool(is_favorite)
        if action_items is not None:
            m.action_items = action_items or None
        db.commit()
        db.refresh(m)
        return m.to_dict()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def delete_meeting(entity_id: int, meeting_id: str) -> bool:
    """Hard-delete the caller's meeting. Returns True if a row was deleted."""
    db = get_db_session()
    try:
        m = db.query(MeetingModel).filter(
            MeetingModel.id == meeting_id,
            MeetingModel.entity_id == entity_id,
        ).first()
        if not m:
            return False
        db.delete(m)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def search_meetings(entity_id: int, query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Convenience: same as list_meetings(..., search=query, sort='newest')."""
    return list_meetings(entity_id=entity_id, limit=limit, search=query)["meetings"]


def list_meeting_templates() -> List[Dict[str, Any]]:
    """Templates aren't tenant-scoped — anyone can see the catalogue."""
    try:
        from api.services.meeting_templates import get_all_templates
        return get_all_templates()
    except Exception as e:
        logger.warning(f"Could not load meeting templates: {e}")
        return []
