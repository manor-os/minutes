"""
Meeting Note Taker API - Handles meeting recordings, transcription, and summarization
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import os
import httpx
from pathlib import Path

import sys
from pathlib import Path

# Add parent directory to path for imports
backend_dir = Path(__file__).parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from collections import defaultdict
from time import time as _time

from api.models.meeting import Meeting, MeetingStatus
from api.services.audio_service import AudioService
from api.services.transcription_service import TranscriptionService
from api.services.summarization_service import SummarizationService
from api.middleware.auth_middleware import get_authenticated_user
from loguru import logger
from api.services.storage_service import storage

# Rate limiting for uploads
_upload_attempts: dict = defaultdict(list)
UPLOAD_RATE_LIMIT = 20  # max uploads per window
UPLOAD_RATE_WINDOW = 3600  # per hour (seconds)

router = APIRouter(prefix="/api/meetings", tags=["meetings"])

# Initialize services
audio_service = AudioService()
transcription_service = TranscriptionService()
summarization_service = SummarizationService()

# Storage directory (legacy fallback for direct file paths)
STORAGE_DIR = Path("storage/meetings")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload")
async def upload_meeting_audio(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    metadata: str = Form(...),
    user: dict = Depends(get_authenticated_user)
):
    """
    Upload meeting audio file and start processing
    """
    try:
        # Upload rate limiting per user
        user_id = str(user.get('entity_id', 'anon'))
        now = _time()
        _upload_attempts[user_id] = [t for t in _upload_attempts[user_id] if now - t < UPLOAD_RATE_WINDOW]
        if len(_upload_attempts[user_id]) >= UPLOAD_RATE_LIMIT:
            raise HTTPException(status_code=429, detail="Upload limit reached. Please try again later.")
        _upload_attempts[user_id].append(now)

        # Parse metadata
        metadata_dict = json.loads(metadata)

        # Save audio file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Ensure file has proper extension for Whisper API
        original_filename = audio.filename or "meeting_audio"
        # Extract extension from filename or content type, default to .webm
        file_extension = None
        if original_filename and '.' in original_filename:
            file_extension = Path(original_filename).suffix.lower()
        elif audio.content_type:
            # Map content types to extensions
            content_type_map = {
                'audio/webm': '.webm',
                'audio/mp3': '.mp3',
                'audio/wav': '.wav',
                'audio/m4a': '.m4a',
                'audio/ogg': '.ogg',
                'audio/mpeg': '.mp3',
                'audio/x-m4a': '.m4a'
            }
            file_extension = content_type_map.get(audio.content_type, '.webm')
        else:
            file_extension = '.webm'  # Default to webm for browser recordings
        
        # Ensure extension is one of the supported formats
        supported_extensions = ['.webm', '.mp3', '.wav', '.m4a', '.ogg', '.flac', '.mp4', '.mpeg', '.mpga', '.oga']
        if file_extension not in supported_extensions:
            file_extension = '.webm'  # Fallback to webm
        
        # Create filename with proper extension
        base_filename = Path(original_filename).stem if original_filename else "meeting_audio"
        filename = f"{timestamp}_{base_filename}{file_extension}"
        filepath = STORAGE_DIR / filename
        
        # Check file size for early rejection
        content_length = audio.size
        if content_length and content_length > 500 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large. Maximum 500MB.")

        content = await audio.read()
        # Save via storage backend (key = just the filename)
        store = storage()
        store.save(content, filename)
        # Also keep a local path reference for legacy compatibility
        filepath = STORAGE_DIR / filename
        if not filepath.exists():
            # For local storage, file is already there. For MinIO, write locally too
            # so ffprobe/celery can access it immediately
            with open(filepath, "wb") as f:
                f.write(content)
        
        # Validate file was written correctly
        if not filepath.exists() or filepath.stat().st_size == 0:
            raise HTTPException(
                status_code=400, 
                detail="Audio file is empty or failed to save. Please check the recording."
            )
        
        # Check minimum file size (at least 1KB for a valid audio file)
        if filepath.stat().st_size < 1024:
            raise HTTPException(
                status_code=400,
                detail=f"Audio file is too small ({filepath.stat().st_size} bytes). Please ensure the recording captured audio."
            )
        
        # Create meeting record
        # Determine platform: prefer 'source' field, then 'platform', default based on source
        source = metadata_dict.get("source", "")
        platform = metadata_dict.get("platform", "")
        
        if source == "browser_extension":
            final_platform = platform if platform and platform != "unknown" else "browser_extension"
        elif source == "phone_recorder":
            final_platform = "phone_recorder"
        else:
            final_platform = platform or metadata_dict.get("source", "unknown")
        
        # Calculate actual audio duration from file using ffprobe
        from api.services.audio_service import AudioService
        audio_service = AudioService()
        actual_duration = audio_service.get_audio_duration(str(filepath))
        # Use actual duration if available, otherwise fall back to metadata duration
        duration = int(actual_duration) if actual_duration > 0 else metadata_dict.get("duration", 0)
        
        meeting = Meeting(
            title=metadata_dict.get("title", "Untitled Meeting"),
            audio_file=filename,
            platform=final_platform,
            duration=duration,
            status=MeetingStatus.UPLOADING,  # Start with uploading status
            meeting_metadata=metadata_dict,  # Use meeting_metadata instead of metadata
            created_at=datetime.now()
        )
        
        # Get entity_id and user_id from authenticated user
        entity_id = user.get('entity_id')
        if not entity_id:
            raise HTTPException(
                status_code=400,
                detail="User entity_id is required. Please ensure you are logged in with a valid Manor AI account."
            )
        # Ensure entity_id is a string
        entity_id = str(entity_id)
        
        # Get user_id from the authenticated user object
        user_id = user.get('user_id') or user.get('userId')
        
        # Save meeting to database with entity_id and user_id (status will be "uploading")
        meeting_id = await save_meeting(meeting, entity_id=str(entity_id), user_id=str(user_id) if user_id else None)
        
        # Update status to processing after upload completes
        # This will be done in a background task after the response is sent
        def update_status_and_start_processing():
            import time
            from database.db import SessionLocal
            from database.models import MeetingModel
            from sqlalchemy import update
            
            # Small delay to ensure file is fully written
            time.sleep(0.5)
            
            # Update status to processing
            db = SessionLocal()
            try:
                db.execute(
                    update(MeetingModel)
                    .where(MeetingModel.id == meeting_id)
                    .values(status=MeetingStatusEnum.PROCESSING.value)
                )
                db.commit()
                logger.info(f"Updated meeting {meeting_id} status from uploading to processing")
            except Exception as e:
                logger.warning(f"Failed to update status to processing: {str(e)}")
                db.rollback()
            finally:
                db.close()
            
            # Start Celery task for processing
            try:
                meeting_language = metadata_dict.get("language") or None
                result = process_meeting_task.delay(meeting_id, str(filepath), language=meeting_language)
                logger.info(f"✅ Celery task started for meeting {meeting_id}, task ID: {result.id}, language: {meeting_language}")
            except Exception as e:
                logger.warning(f"⚠️  Warning: Failed to start Celery task: {str(e)}")
                logger.warning(f"⚠️  Meeting {meeting_id} saved but processing failed to start. Can be retried later.")
        
        # Add to background tasks - this will run after response is sent
        background_tasks.add_task(update_status_and_start_processing)
        
        # Get the saved meeting to return immediately (don't wait for processing)
        saved_meeting = await get_meeting_by_id(meeting_id, entity_id=str(entity_id))
        
        return JSONResponse({
            "success": True,
            "meeting_id": meeting_id,
            "meeting": saved_meeting.to_dict() if saved_meeting else None,
            "message": "Audio uploaded successfully. Processing started."
        })
        
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


@router.get("/list")
async def list_meetings(
    page: int = 1,
    per_page: int = 20,
    status: Optional[str] = None,
    q: Optional[str] = None,
    sort: Optional[str] = "newest",
    favorite: Optional[bool] = None,
    tag: Optional[str] = None,
    user: dict = Depends(get_authenticated_user)
):
    """
    List all meetings with optional filtering, filtered by user's entity_id

    Query parameters:
        page: Page number (default 1)
        per_page: Items per page (default 20, max 100)
        q: Search by title, transcript, or summary (case-insensitive)
        sort: One of "newest" (default), "oldest", "longest", "shortest"
        status: Filter by status: "completed", "processing", "failed", "uploading"
        favorite: Filter favorites only (true)
        tag: Filter by tag (LIKE match)
    """
    import math
    try:
        # Get entity_id from authenticated user
        entity_id = user.get('entity_id')
        if not entity_id:
            raise HTTPException(
                status_code=400,
                detail="User entity_id is required. Please ensure you are logged in with a valid Manor AI account."
            )

        # Validate and clamp pagination parameters
        page = max(1, page)
        per_page = max(1, min(100, per_page))
        offset = (page - 1) * per_page

        # Validate sort parameter
        valid_sorts = {"newest", "oldest", "longest", "shortest"}
        if sort and sort not in valid_sorts:
            sort = "newest"

        # Fetch meetings from database, filtered by entity_id
        meetings, total = await get_meetings(
            limit=per_page, offset=offset, status=status,
            entity_id=str(entity_id), q=q, sort=sort,
            favorite=favorite, tag=tag, count_total=True
        )
        total_pages = math.ceil(total / per_page) if total > 0 else 1

        return JSONResponse({
            "success": True,
            "meetings": [meeting.to_dict() for meeting in meetings],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch meetings: {str(e)}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


@router.get("/usage-stats", name="usage_stats_before_meeting_id")
async def get_usage_stats_redirect(user: dict = Depends(get_authenticated_user)):
    """Redirect to actual usage-stats handler (must be before /{meeting_id} catch-all)"""
    return await get_usage_stats(user)


@router.get("/audio/{filename:path}")
async def serve_audio(filename: str, user: dict = Depends(get_authenticated_user)):
    """Serve audio file from storage."""
    from fastapi.responses import StreamingResponse
    store = storage()
    if not store.exists(filename):
        raise HTTPException(status_code=404, detail="Audio file not found")

    data = store.load(filename)
    ext = Path(filename).suffix.lower()
    content_type = {
        ".webm": "audio/webm", ".mp3": "audio/mpeg", ".wav": "audio/wav",
        ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".flac": "audio/flac",
    }.get(ext, "application/octet-stream")

    from io import BytesIO
    return StreamingResponse(BytesIO(data), media_type=content_type, headers={
        "Content-Disposition": f'inline; filename="{filename}"'
    })


@router.post("/bulk-delete")
async def bulk_delete_meetings(request: Request, user: dict = Depends(get_authenticated_user)):
    """
    Delete multiple meetings at once, with entity_id access check
    """
    try:
        entity_id = user.get('entity_id')
        if not entity_id:
            raise HTTPException(status_code=400, detail="User entity_id is required.")

        body = await request.json()
        meeting_ids = body.get('meeting_ids', [])
        if not meeting_ids or not isinstance(meeting_ids, list):
            raise HTTPException(status_code=400, detail="meeting_ids must be a non-empty list")

        db = get_db_session()
        try:
            # Find meetings belonging to this entity
            meetings = db.query(MeetingModel).filter(
                MeetingModel.id.in_(meeting_ids),
                MeetingModel.entity_id == str(entity_id)
            ).all()

            # Delete audio files from storage
            for meeting in meetings:
                if meeting.audio_file:
                    try:
                        store = storage()
                        store.delete(meeting.audio_file)
                    except Exception as e:
                        logger.warning(f"Could not delete audio file {meeting.audio_file}: {str(e)}")
                    if os.path.exists(meeting.audio_file):
                        try:
                            os.remove(meeting.audio_file)
                        except Exception:
                            pass

            # Delete from database
            count = db.query(MeetingModel).filter(
                MeetingModel.id.in_(meeting_ids),
                MeetingModel.entity_id == str(entity_id)
            ).delete(synchronize_session=False)
            db.commit()

            return JSONResponse({
                "success": True,
                "deleted_count": count,
                "message": f"Deleted {count} meeting(s)"
            })
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to bulk delete: {str(e)}")
            raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")
        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to bulk delete meetings: {str(e)}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


@router.get("/search")
async def search_meetings(
    q: str,
    limit: int = 20,
    user: dict = Depends(get_authenticated_user)
):
    """Search across all meetings with context snippets."""
    try:
        entity_id = str(user.get('entity_id', ''))
        if not entity_id:
            raise HTTPException(status_code=400, detail="Authentication required")

        limit = min(limit, 50)

        from database.db import SessionLocal
        from database.models import MeetingModel
        from sqlalchemy import or_

        db = SessionLocal()
        try:
            search = f"%{q}%"
            meetings = (
                db.query(MeetingModel)
                .filter(
                    MeetingModel.entity_id == entity_id,
                    MeetingModel.status == "completed",
                    or_(
                        MeetingModel.title.ilike(search),
                        MeetingModel.transcript.ilike(search),
                        MeetingModel.summary.ilike(search),
                    ),
                )
                .order_by(MeetingModel.created_at.desc())
                .limit(limit)
                .all()
            )

            results = []
            q_lower = q.lower()
            for m in meetings:
                # Find context snippet in transcript
                snippet = None
                match_in = []

                if m.title and q_lower in m.title.lower():
                    match_in.append("title")

                if m.transcript and q_lower in m.transcript.lower():
                    match_in.append("transcript")
                    idx = m.transcript.lower().index(q_lower)
                    start = max(0, idx - 80)
                    end = min(len(m.transcript), idx + len(q) + 80)
                    snippet = ("..." if start > 0 else "") + m.transcript[start:end] + ("..." if end < len(m.transcript) else "")

                if m.summary and q_lower in m.summary.lower():
                    match_in.append("summary")
                    if not snippet:
                        idx = m.summary.lower().index(q_lower)
                        start = max(0, idx - 80)
                        end = min(len(m.summary), idx + len(q) + 80)
                        snippet = ("..." if start > 0 else "") + m.summary[start:end] + ("..." if end < len(m.summary) else "")

                results.append({
                    "id": m.id,
                    "title": m.title,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "duration": m.duration,
                    "match_in": match_in,
                    "snippet": snippet or (m.summary[:150] + "..." if m.summary and len(m.summary) > 150 else m.summary or ""),
                })

            return JSONResponse({"success": True, "results": results, "query": q, "count": len(results)})
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


@router.patch("/{meeting_id}/favorite")
async def toggle_favorite(meeting_id: str, user: dict = Depends(get_authenticated_user)):
    """
    Toggle is_favorite for a meeting
    """
    try:
        entity_id = user.get('entity_id')
        if not entity_id:
            raise HTTPException(status_code=400, detail="User entity_id is required.")

        db = get_db_session()
        try:
            db_meeting = db.query(MeetingModel).filter(
                MeetingModel.id == meeting_id,
                MeetingModel.entity_id == str(entity_id)
            ).first()
            if not db_meeting:
                raise HTTPException(status_code=404, detail="Meeting not found")

            db_meeting.is_favorite = not bool(db_meeting.is_favorite)
            db.commit()

            return JSONResponse({
                "success": True,
                "is_favorite": bool(db_meeting.is_favorite)
            })
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to toggle favorite: {str(e)}")
            raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")
        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to toggle favorite: {str(e)}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


@router.patch("/{meeting_id}/tags")
async def update_tags(meeting_id: str, request: Request, user: dict = Depends(get_authenticated_user)):
    """
    Update tags for a meeting
    """
    try:
        entity_id = user.get('entity_id')
        if not entity_id:
            raise HTTPException(status_code=400, detail="User entity_id is required.")

        body = await request.json()
        tags = body.get('tags', [])
        if not isinstance(tags, list):
            raise HTTPException(status_code=400, detail="tags must be a list of strings")

        db = get_db_session()
        try:
            db_meeting = db.query(MeetingModel).filter(
                MeetingModel.id == meeting_id,
                MeetingModel.entity_id == str(entity_id)
            ).first()
            if not db_meeting:
                raise HTTPException(status_code=404, detail="Meeting not found")

            # Store as comma-separated string
            db_meeting.tags = ",".join(t.strip() for t in tags if t.strip()) if tags else None
            db.commit()

            return JSONResponse({
                "success": True,
                "tags": [t.strip() for t in db_meeting.tags.split(",") if t.strip()] if db_meeting.tags else []
            })
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update tags: {str(e)}")
            raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")
        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update tags: {str(e)}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


@router.post("/{meeting_id}/share")
async def create_share_link(meeting_id: str, user: dict = Depends(get_authenticated_user)):
    """Generate a share token for a meeting, returning a public share URL."""
    try:
        entity_id = user.get('entity_id')
        if not entity_id:
            raise HTTPException(status_code=400, detail="User entity_id is required.")

        db = get_db_session()
        try:
            db_meeting = db.query(MeetingModel).filter(
                MeetingModel.id == meeting_id,
                MeetingModel.entity_id == str(entity_id)
            ).first()

            if not db_meeting:
                raise HTTPException(status_code=404, detail="Meeting not found")

            # If already has a share token, return it
            if db_meeting.share_token:
                return JSONResponse({
                    "success": True,
                    "share_token": db_meeting.share_token,
                })

            # Generate new token
            import uuid as _uuid
            token = _uuid.uuid4().hex
            db_meeting.share_token = token
            db.commit()

            return JSONResponse({
                "success": True,
                "share_token": token,
            })
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create share link: {str(e)}")
            raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")
        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create share link: {str(e)}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


@router.delete("/{meeting_id}/share")
async def revoke_share_link(meeting_id: str, user: dict = Depends(get_authenticated_user)):
    """Remove the share token for a meeting, revoking public access."""
    try:
        entity_id = user.get('entity_id')
        if not entity_id:
            raise HTTPException(status_code=400, detail="User entity_id is required.")

        db = get_db_session()
        try:
            db_meeting = db.query(MeetingModel).filter(
                MeetingModel.id == meeting_id,
                MeetingModel.entity_id == str(entity_id)
            ).first()

            if not db_meeting:
                raise HTTPException(status_code=404, detail="Meeting not found")

            db_meeting.share_token = None
            db.commit()

            return JSONResponse({"success": True, "message": "Share link revoked"})
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to revoke share link: {str(e)}")
            raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")
        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to revoke share link: {str(e)}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


@router.get("/shared/{share_token}")
async def get_shared_meeting(share_token: str):
    """Public endpoint - fetch a meeting by its share token. No auth required."""
    db = get_db_session()
    try:
        db_meeting = db.query(MeetingModel).filter(
            MeetingModel.share_token == share_token
        ).first()

        if not db_meeting:
            raise HTTPException(status_code=404, detail="Shared meeting not found or link has been revoked")

        return JSONResponse({
            "success": True,
            "meeting": {
                "title": db_meeting.title,
                "summary": db_meeting.summary,
                "key_points": db_meeting.key_points,
                "action_items": db_meeting.action_items,
                "transcript": db_meeting.transcript,
                "duration": db_meeting.duration,
                "created_at": db_meeting.created_at.isoformat() if db_meeting.created_at else None,
            }
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch shared meeting: {str(e)}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")
    finally:
        db.close()


@router.get("/templates")
async def list_templates():
    """List available meeting templates."""
    from api.services.meeting_templates import get_all_templates
    return {"success": True, "templates": get_all_templates()}


@router.post("/{meeting_id}/chat")
async def chat_with_meeting(meeting_id: str, request: Request, user: dict = Depends(get_authenticated_user)):
    """Ask a question about a meeting's content using AI. Returns streaming SSE response."""
    from fastapi.responses import StreamingResponse
    import httpx as _httpx

    entity_id = str(user.get('entity_id', ''))
    meeting = await get_meeting_by_id(meeting_id, entity_id=entity_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    body = await request.json()
    question = body.get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    # Build context from meeting data
    context_parts = []
    if meeting.title:
        context_parts.append(f"Meeting title: {meeting.title}")
    if meeting.summary:
        context_parts.append(f"Summary:\n{meeting.summary}")
    if meeting.key_points:
        points = meeting.key_points if isinstance(meeting.key_points, list) else []
        if points:
            context_parts.append("Key points:\n" + "\n".join(
                f"- {p}" if isinstance(p, str) else f"- {p.get('text', p.get('description', str(p)))}"
                for p in points
            ))
    if meeting.transcript:
        transcript = meeting.transcript
        if len(transcript) > 8000:
            transcript = transcript[:8000] + "\n...(transcript truncated)"
        context_parts.append(f"Transcript:\n{transcript}")

    context = "\n\n".join(context_parts)
    system_prompt = "You are a helpful assistant that answers questions about meeting content. Use only the provided meeting data to answer. If the answer isn't in the meeting data, say so. Be concise."
    user_prompt = f"Meeting data:\n{context}\n\nQuestion: {question}"

    llm_mode = os.getenv("LLM_MODE", "cloud")

    async def stream_response():
        try:
            if llm_mode == "local":
                # Ollama streaming
                ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434")
                ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
                async with _httpx.AsyncClient(timeout=7200.0) as client:
                    async with client.stream(
                        "POST",
                        f"{ollama_url}/api/generate",
                        json={
                            "model": ollama_model,
                            "prompt": user_prompt,
                            "system": system_prompt,
                            "stream": True,
                            "options": {"temperature": 0.3},
                        },
                    ) as resp:
                        async for line in resp.aiter_lines():
                            if line:
                                try:
                                    chunk = json.loads(line)
                                    token = chunk.get("response", "")
                                    if token:
                                        yield f"data: {json.dumps({'token': token})}\n\n"
                                    if chunk.get("done"):
                                        break
                                except json.JSONDecodeError:
                                    pass
            else:
                # OpenAI/OpenRouter streaming
                service = SummarizationService()
                stream = service.client.chat.completions.create(
                    model=service.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=1000,
                    stream=True,
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        yield f"data: {json.dumps({'token': delta.content})}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            logger.error(f"Chat stream failed: {e}")
            yield f"data: {json.dumps({'error': 'Failed to generate answer'})}\n\n"

    return StreamingResponse(stream_response(), media_type="text/event-stream")


@router.get("/{meeting_id}")
async def get_meeting(meeting_id: str, user: dict = Depends(get_authenticated_user)):
    """
    Get meeting details by ID, with entity_id access check
    """
    try:
        # Get entity_id from authenticated user
        entity_id = user.get('entity_id')
        if not entity_id:
            raise HTTPException(
                status_code=400,
                detail="User entity_id is required. Please ensure you are logged in with a valid Manor AI account."
            )
        
        meeting = await get_meeting_by_id(meeting_id, entity_id=str(entity_id))
        
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        return JSONResponse({
            "success": True,
            "meeting": meeting.to_dict()
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch meeting: {str(e)}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


@router.get("/{meeting_id}/transcript")
async def get_transcript(meeting_id: str, user: dict = Depends(get_authenticated_user)):
    """
    Get meeting transcript, with entity_id access check
    """
    try:
        # Get entity_id from authenticated user
        entity_id = user.get('entity_id')
        if not entity_id:
            raise HTTPException(
                status_code=400,
                detail="User entity_id is required. Please ensure you are logged in with a valid Manor AI account."
            )
        
        meeting = await get_meeting_by_id(meeting_id, entity_id=str(entity_id))
        
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        if not meeting.transcript:
            raise HTTPException(status_code=404, detail="Transcript not available")
        
        return JSONResponse({
            "success": True,
            "transcript": meeting.transcript
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch transcript: {str(e)}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


@router.get("/{meeting_id}/summary")
async def get_summary(meeting_id: str, user: dict = Depends(get_authenticated_user)):
    """
    Get meeting summary, with entity_id access check
    """
    try:
        # Get entity_id from authenticated user
        entity_id = user.get('entity_id')
        if not entity_id:
            raise HTTPException(
                status_code=400,
                detail="User entity_id is required. Please ensure you are logged in with a valid Manor AI account."
            )
        
        meeting = await get_meeting_by_id(meeting_id, entity_id=str(entity_id))
        
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        if not meeting.summary:
            raise HTTPException(status_code=404, detail="Summary not available")
        
        return JSONResponse({
            "success": True,
            "summary": meeting.summary
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch summary: {str(e)}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


@router.patch("/{meeting_id}")
async def update_meeting(meeting_id: str, request: Request, user: dict = Depends(get_authenticated_user)):
    """
    Update meeting summary, title, or action_items, with entity_id access check
    """
    try:
        # Get entity_id from authenticated user
        entity_id = user.get('entity_id')
        if not entity_id:
            raise HTTPException(
                status_code=400,
                detail="User entity_id is required. Please ensure you are logged in with a valid Manor AI account."
            )
        
        body = await request.json()
        summary = body.get('summary')
        title = body.get('title')
        action_items = body.get('action_items')
        
        meeting = await get_meeting_by_id(meeting_id, entity_id=str(entity_id))
        
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        # Update meeting in database
        db = get_db_session()
        try:
            db_meeting = db.query(MeetingModel).filter(
                MeetingModel.id == meeting_id,
                MeetingModel.entity_id == str(entity_id)
            ).first()
            
            if not db_meeting:
                raise HTTPException(status_code=404, detail="Meeting not found")
            
            if summary is not None:
                db_meeting.summary = summary
            if title is not None:
                db_meeting.title = title
            if action_items is not None:
                # Validate action_items format
                if not isinstance(action_items, list):
                    raise HTTPException(status_code=400, detail="action_items must be a list")
                # Store directly - get_json_column_type() handles JSON serialization
                db_meeting.action_items = action_items if action_items else None
            
            db.commit()
            
            # Get updated meeting
            updated_meeting = await get_meeting_by_id(meeting_id, entity_id=str(entity_id))
            
            return JSONResponse({
                "success": True,
                "message": "Meeting updated successfully",
                "meeting": updated_meeting.to_dict() if updated_meeting else None
            })
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update meeting: {str(e)}")
            raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")
        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update meeting: {str(e)}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


@router.post("/{meeting_id}/retry")
async def retry_processing(meeting_id: str, background_tasks: BackgroundTasks, user: dict = Depends(get_authenticated_user)):
    """
    Retry processing a failed meeting, with entity_id access check
    """
    try:
        # Get entity_id from authenticated user
        entity_id = user.get('entity_id')
        if not entity_id:
            raise HTTPException(
                status_code=400,
                detail="User entity_id is required. Please ensure you are logged in with a valid Manor AI account."
            )
        
        meeting = await get_meeting_by_id(meeting_id, entity_id=str(entity_id))
        
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        # Check if meeting has an audio file
        if not meeting.audio_file:
            raise HTTPException(status_code=400, detail="Audio file not found. Cannot retry processing.")
        # Verify file exists in storage
        try:
            store = storage()
            if not store.exists(meeting.audio_file) and not os.path.exists(meeting.audio_file):
                raise HTTPException(status_code=400, detail="Audio file not found in storage. Cannot retry processing.")
        except HTTPException:
            raise
        except Exception:
            pass  # Storage check failed, try anyway
        
        # Update status to PROCESSING
        db = get_db_session()
        try:
            db_meeting = db.query(MeetingModel).filter(
                MeetingModel.id == meeting_id,
                MeetingModel.entity_id == str(entity_id)
            ).first()
            if not db_meeting:
                raise HTTPException(status_code=404, detail="Meeting not found")
            
            db_meeting.status = MeetingStatusEnum.PROCESSING.value
            db.commit()
            
            # Start processing in background
            def start_celery_task():
                try:
                    result = process_meeting_task.delay(meeting_id, meeting.audio_file)
                    print(f"✅ Retry: Celery task started for meeting {meeting_id}, task ID: {result.id}")
                except Exception as e:
                    print(f"⚠️  Warning: Failed to start Celery task for retry: {str(e)}")
            
            background_tasks.add_task(start_celery_task)
            
            return JSONResponse({
                "success": True,
                "message": "Processing restarted successfully",
                "meeting_id": meeting_id
            })
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to retry processing: {str(e)}")
            raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")
        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry processing: {str(e)}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


@router.get("/assets")
async def get_assets_list(user: dict = Depends(get_authenticated_user)):
    """Get list of assets for the authenticated user's entity"""
    return JSONResponse({"success": True, "assets": []})


@router.get("/staff/list")
async def get_staff_list(user: dict = Depends(get_authenticated_user)):
    """Get staff list for the user's entity"""
    return JSONResponse({"success": True, "staff": []})


@router.post("/{meeting_id}/action-items/{action_index}/create-ticket")
async def create_ticket_from_action_item(
    meeting_id: str,
    action_index: int,
    request: Request,
    user: dict = Depends(get_authenticated_user)
):
    """Create a ticket from an action item (not available in this edition)"""
    raise HTTPException(status_code=501, detail="Ticket creation is not available in this edition")


@router.delete("/{meeting_id}")
async def delete_meeting(meeting_id: str, user: dict = Depends(get_authenticated_user)):
    """
    Delete a meeting and its associated files, with entity_id access check
    """
    try:
        # Get entity_id from authenticated user
        entity_id = user.get('entity_id')
        if not entity_id:
            raise HTTPException(
                status_code=400,
                detail="User entity_id is required. Please ensure you are logged in with a valid Manor AI account."
            )
        
        meeting = await get_meeting_by_id(meeting_id, entity_id=str(entity_id))
        
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        # Delete audio file from storage
        if meeting.audio_file:
            try:
                store = storage()
                store.delete(meeting.audio_file)
            except Exception as e:
                logger.warning(f"Could not delete audio file: {str(e)}")
            # Also try legacy full-path deletion
            if os.path.exists(meeting.audio_file):
                try:
                    os.remove(meeting.audio_file)
                except Exception:
                    pass
        
        # Delete from database with entity_id check
        await delete_meeting_from_db(meeting_id, entity_id=str(entity_id))
        
        return JSONResponse({
            "success": True,
            "message": "Meeting deleted successfully"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete meeting: {str(e)}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


# Database imports
import uuid
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from database.db import get_db_session
from database.models import MeetingModel, MeetingStatusEnum

# Celery imports
try:
    from celery_tasks import process_meeting_task
except ImportError:
    # Fallback if celery_tasks is not available
    def process_meeting_task(*args, **kwargs):
        pass


# Helper functions for database operations
async def save_meeting(meeting: Meeting, entity_id, user_id=None) -> str:
    """Save meeting to database and return ID
    
    Args:
        meeting: Meeting object to save
        entity_id: Entity ID for multi-tenant isolation (required)
        user_id: User ID who recorded the meeting (optional)
    """
    db = get_db_session()
    try:
        meeting_id = str(uuid.uuid4())
        
        # Convert status enum to string value
        status_value = meeting.status
        if hasattr(status_value, 'value'):
            status_value = status_value.value
        elif not isinstance(status_value, str):
            status_value = str(status_value)
        
        db_meeting = MeetingModel(
            id=meeting_id,
            title=meeting.title,
            audio_file=meeting.audio_file,
            platform=meeting.platform,
            duration=meeting.duration,
            status=status_value,  # Store as string
            meeting_metadata=meeting.meeting_metadata,  # Use meeting_metadata
            entity_id=entity_id,  # Store entity_id for multi-tenant isolation
            created_by_user_id=user_id,  # Store user_id who recorded the meeting
            created_at=meeting.created_at
        )
        
        db.add(db_meeting)
        db.commit()
        return meeting_id
    except Exception as e:
        db.rollback()
        print(f"Error saving meeting: {str(e)}")
        raise e
    finally:
        db.close()


async def get_meetings(limit: int = 20, offset: int = 0, status: Optional[str] = None, entity_id: Optional[int] = None, q: Optional[str] = None, sort: Optional[str] = "newest", favorite: Optional[bool] = None, tag: Optional[str] = None, count_total: bool = False):
    """Get meetings from database, filtered by entity_id for multi-tenant isolation

    Args:
        limit: Maximum number of meetings to return
        offset: Number of meetings to skip
        status: Optional status filter
        entity_id: Entity ID to filter by (required for multi-tenant isolation)
        q: Optional search query - matches title, transcript, or summary (case-insensitive)
        sort: Sort order - "newest", "oldest", "longest", "shortest"
        favorite: Optional boolean - if True, filter favorites only
        tag: Optional string - filter by tag (LIKE match)
        count_total: If True, return (meetings, total_count) tuple

    Returns:
        List[Meeting] if count_total is False, else (List[Meeting], int)
    """
    from sqlalchemy import or_
    db = get_db_session()
    try:
        query = db.query(MeetingModel)

        # Filter by entity_id - required for multi-tenant isolation
        if entity_id is not None:
            query = query.filter(MeetingModel.entity_id == entity_id)
        else:
            # If no entity_id provided, return empty list for security
            logger.warning("get_meetings called without entity_id - returning empty list for security")
            return ([], 0) if count_total else []

        if status:
            # Convert string status to enum
            try:
                status_enum = MeetingStatusEnum(status.lower())
                query = query.filter(MeetingModel.status == status_enum)
            except ValueError:
                # Invalid status, ignore filter
                pass

        # Search filter: match title, transcript, or summary (case-insensitive)
        if q:
            search_pattern = f"%{q}%"
            query = query.filter(
                or_(
                    MeetingModel.title.ilike(search_pattern),
                    MeetingModel.transcript.ilike(search_pattern),
                    MeetingModel.summary.ilike(search_pattern),
                )
            )

        # Favorite filter
        if favorite is True:
            query = query.filter(MeetingModel.is_favorite == True)

        # Tag filter (LIKE match on comma-separated tags column)
        if tag:
            query = query.filter(MeetingModel.tags.ilike(f"%{tag}%"))

        # Get total count before pagination (if requested)
        total = query.count() if count_total else None

        # Sort order
        if sort == "oldest":
            query = query.order_by(MeetingModel.created_at.asc())
        elif sort == "longest":
            query = query.order_by(MeetingModel.duration.desc())
        elif sort == "shortest":
            query = query.order_by(MeetingModel.duration.asc())
        else:
            # Default: newest first
            query = query.order_by(MeetingModel.created_at.desc())

        meetings = query.offset(offset).limit(limit).all()

        # Convert database models to Pydantic models
        result = []
        for meeting in meetings:
            try:
                # Get the meeting data as dict - include user info
                meeting_dict = meeting.to_dict(include_user_info=True)
                logger.debug(f"Meeting {meeting.id} dict keys: {list(meeting_dict.keys())}, created_by_user_name: {meeting_dict.get('created_by_user_name')}")
                # Convert to Meeting Pydantic model
                # Use model_validate to allow extra fields
                meeting_obj = Meeting.model_validate(meeting_dict)
                result.append(meeting_obj)
            except Exception as e:
                logger.error(f"Error converting meeting {meeting.id}: {str(e)}")
                # Skip this meeting if conversion fails
                continue

        if count_total:
            return result, total
        return result
    except Exception as e:
        print(f"Error fetching meetings: {str(e)}")
        raise
    finally:
        db.close()


async def get_meeting_by_id(meeting_id: str, entity_id: str = None) -> Optional[Meeting]:
    """Get meeting by ID from database, with entity_id check for multi-tenant isolation

    Args:
        meeting_id: Meeting ID to retrieve
        entity_id: Entity ID to verify access (REQUIRED for multi-tenant isolation)

    Returns:
        Meeting if found and entity_id matches, None otherwise

    Raises:
        ValueError: If entity_id is not provided
    """
    if not entity_id:
        logger.error(f"get_meeting_by_id called without entity_id for meeting {meeting_id} - this is a bug")
        raise ValueError("entity_id is required for get_meeting_by_id")

    db = get_db_session()
    try:
        query = db.query(MeetingModel).filter(
            MeetingModel.id == meeting_id,
            MeetingModel.entity_id == str(entity_id)
        )
        
        db_meeting = query.first()
        
        if not db_meeting:
            return None
        
        # Include user info when returning meeting
        return Meeting(**db_meeting.to_dict(include_user_info=True))
    finally:
        db.close()


async def delete_meeting_from_db(meeting_id: str, entity_id: str = None):
    """Delete meeting from database, with entity_id check for multi-tenant isolation

    Args:
        meeting_id: Meeting ID to delete
        entity_id: Entity ID to verify access (REQUIRED for multi-tenant isolation)

    Raises:
        ValueError: If entity_id is not provided
    """
    if not entity_id:
        logger.error(f"delete_meeting_from_db called without entity_id for meeting {meeting_id} - this is a bug")
        raise ValueError("entity_id is required for delete_meeting_from_db")

    db = get_db_session()
    try:
        query = db.query(MeetingModel).filter(
            MeetingModel.id == meeting_id,
            MeetingModel.entity_id == str(entity_id)
        )
        
        db_meeting = query.first()
        
        if db_meeting:
            db.delete(db_meeting)
            db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


async def process_meeting_async(meeting_id: str, audio_filepath: str):
    """
    Process meeting audio asynchronously using Celery
    """
    try:
        # Start Celery task
        result = process_meeting_task.delay(meeting_id, audio_filepath)
        print(f"✅ Celery task started for meeting {meeting_id}, task ID: {result.id}")
        return result
    except Exception as e:
        print(f"❌ Error starting Celery task: {str(e)}")
        # Fallback: process synchronously (not recommended for production)
        print("⚠️  Falling back to synchronous processing...")
        try:
            from celery_tasks import process_meeting_task
            # Call directly (synchronous)
            process_meeting_task(meeting_id, audio_filepath)
        except Exception as sync_error:
            print(f"❌ Synchronous processing also failed: {str(sync_error)}")
            raise


@router.get("/usage-stats")
async def get_usage_stats(user: dict = Depends(get_authenticated_user)):
    """Get usage statistics for the authenticated user"""
    entity_id = user.get('entity_id')
    if not entity_id:
        raise HTTPException(status_code=400, detail="entity_id required")

    try:
        from datetime import datetime, timedelta
        from sqlalchemy import func as sa_func, cast, Date

        db = get_db_session()
        try:
            now = datetime.now()
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            # Total stats for completed meetings
            base_query = db.query(MeetingModel).filter(
                MeetingModel.entity_id == str(entity_id),
                MeetingModel.status == MeetingStatusEnum.COMPLETED.value
            )

            total_meetings = base_query.count()

            # Sum duration
            total_seconds = db.query(
                sa_func.coalesce(sa_func.sum(MeetingModel.duration), 0)
            ).filter(
                MeetingModel.entity_id == str(entity_id),
                MeetingModel.status == MeetingStatusEnum.COMPLETED.value
            ).scalar()

            # Meetings this month
            meetings_this_month = base_query.filter(
                MeetingModel.created_at >= month_start
            ).count()

            # Token cost aggregation - iterate completed meetings
            completed_meetings = base_query.all()
            total_tokens = 0
            total_cost = 0.0
            for m in completed_meetings:
                if m.token_cost and isinstance(m.token_cost, dict):
                    total_tokens += int(m.token_cost.get('total_tokens', 0) or 0)
                    total_cost += float(m.token_cost.get('total_cost', 0) or 0)

            # Daily breakdown (last 7 days)
            week_ago = now - timedelta(days=7)
            daily_rows = db.query(
                cast(MeetingModel.created_at, Date).label('day'),
                sa_func.count(MeetingModel.id).label('count'),
                sa_func.coalesce(sa_func.sum(MeetingModel.duration), 0).label('seconds')
            ).filter(
                MeetingModel.entity_id == str(entity_id),
                MeetingModel.created_at >= week_ago
            ).group_by(
                cast(MeetingModel.created_at, Date)
            ).order_by(
                cast(MeetingModel.created_at, Date)
            ).all()

            # Build daily data for last 7 days
            daily = []
            for i in range(7):
                day = (now - timedelta(days=6 - i)).strftime('%Y-%m-%d')
                row = next((r for r in daily_rows if str(r.day) == day), None)
                daily.append({
                    "date": day,
                    "meetings": row.count if row else 0,
                    "minutes": round(row.seconds / 60, 1) if row else 0,
                })

            return {
                "total_meetings": total_meetings,
                "total_minutes": round(total_seconds / 60, 1),
                "total_tokens": total_tokens,
                "total_cost": round(total_cost, 4),
                "meetings_this_month": meetings_this_month,
                "daily": daily,
            }
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting usage stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to load usage statistics")

