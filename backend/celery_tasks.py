"""
Celery tasks for async meeting processing
"""
from celery import Celery
import os
import httpx
from dotenv import load_dotenv
from pathlib import Path

from api.services.transcription_service import TranscriptionService
from api.services.summarization_service import SummarizationService
from api.services.storage_service import storage
from database.db import get_db_session
from database.models import MeetingModel, MeetingStatusEnum

load_dotenv()


# Startup-time sanity check: log loud warnings if any of the keys we depend on
# are missing.  Failing here would crash the worker; logging makes it visible
# in `docker logs meeting-note-celery` while still letting the worker boot.
def _check_required_env() -> None:
    from loguru import logger
    stt_mode = os.getenv("STT_MODE", "cloud")
    llm_mode = os.getenv("LLM_MODE", "cloud")
    logger.info(f"[startup] STT_MODE={stt_mode}, LLM_MODE={llm_mode}")

    if stt_mode == "local":
        logger.info("[startup] Using local faster-whisper — no OPENAI_API_KEY required for STT")
    elif not (os.getenv("OPENAI_API_KEY") or "").strip():
        logger.error(
            "[startup] OPENAI_API_KEY is not set in the celery worker environment — "
            "Whisper transcription will fail. Set it in .env / docker-compose."
        )
    else:
        logger.info("[startup] OPENAI_API_KEY present")

    if llm_mode == "local":
        logger.info(f"[startup] Using local Ollama ({os.getenv('OLLAMA_MODEL', 'qwen2.5:3b')}) — no OPENROUTER_API_KEY required for LLM")
    elif not (os.getenv("OPENROUTER_API_KEY") or "").strip():
        logger.error(
            "[startup] OPENROUTER_API_KEY is not set in the celery worker environment — "
            "Summarization & speaker ID will fail. Set it in .env / docker-compose."
        )
    else:
        logger.info("[startup] OPENROUTER_API_KEY present")


_check_required_env()


def _report_token_usage(entity_id: int, input_tokens: int, output_tokens: int) -> None:
    """No-op: token usage reporting removed."""
    pass

# Celery configuration
celery_app = Celery(
    "meeting_note_taker",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(
    name="process_meeting",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    time_limit=7200,
    soft_time_limit=7000,
)
def process_meeting_task(self, meeting_id: str, audio_filepath: str, language: str = None):
    """
    Process meeting audio asynchronously:
    1. Transcribe audio
    2. Generate summary
    3. Extract key points and action items
    """
    import traceback
    from loguru import logger

    db = get_db_session()
    meeting = None

    try:
        # In community mode, try to get user's API keys from the database
        user_stt_key = None
        user_llm_key = None
        try:
            meeting_row = db.query(MeetingModel).filter(MeetingModel.id == meeting_id).first()
            if meeting_row and meeting_row.created_by_user_id:
                from api.services.local_auth_service import get_user_by_email
                # created_by_user_id might be a UUID or email — try to find the user
                import psycopg2, psycopg2.extras
                user_conn = psycopg2.connect(
                    os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/meeting_notes"),
                    cursor_factory=psycopg2.extras.RealDictCursor
                )
                try:
                    with user_conn.cursor() as cur:
                        cur.execute("SELECT stt_api_key, llm_api_key FROM users LIMIT 1")
                        user_row = cur.fetchone()
                        if user_row:
                            user_stt_key = user_row.get("stt_api_key") or None
                            user_llm_key = user_row.get("llm_api_key") or None
                finally:
                    user_conn.close()
        except Exception as e:
            logger.debug(f"Could not load user API keys: {e}")

        # Check local mode env vars
        stt_mode = os.getenv("STT_MODE", "cloud")
        llm_mode = os.getenv("LLM_MODE", "cloud")
        logger.info(f"Processing modes: STT={stt_mode}, LLM={llm_mode}")

        # Determine which keys to use: user's key > env var
        effective_stt_key = user_stt_key or os.getenv("OPENAI_API_KEY", "").strip()
        effective_llm_key = user_llm_key or os.getenv("OPENROUTER_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()

        if stt_mode != "local" and not effective_stt_key:
            raise RuntimeError(
                "No OpenAI API key available for Whisper transcription. "
                "Please configure your OpenAI key in Settings, or set OPENAI_API_KEY env var."
            )
        if llm_mode != "local" and not effective_llm_key:
            raise RuntimeError(
                "No LLM API key available for summarization. "
                "Please configure your LLM key in Settings, or set OPENROUTER_API_KEY env var."
            )

        # Override env vars so services pick up user's keys
        if user_stt_key:
            os.environ["OPENAI_API_KEY"] = user_stt_key
        if user_llm_key:
            os.environ["OPENROUTER_API_KEY"] = user_llm_key

        transcription_service = None if stt_mode == "local" else TranscriptionService()
        logger.info(f"LLM key for summarization: {'set (' + str(len(os.getenv('OPENROUTER_API_KEY', ''))) + ' chars)' if os.getenv('OPENROUTER_API_KEY') else 'NOT SET'}, OPENAI_API_KEY: {'set' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}")
        summarization_service = None if llm_mode == "local" else SummarizationService()

        logger.info(f"Starting processing for meeting {meeting_id}")
        
        # Get meeting from database
        meeting = db.query(MeetingModel).filter(MeetingModel.id == meeting_id).first()

        if not meeting:
            raise ValueError(f"Meeting {meeting_id} not found")

        if meeting.status == MeetingStatusEnum.COMPLETED.value:
            logger.info(f"Meeting {meeting_id} already completed, skipping")
            return {"status": "already_completed", "meeting_id": meeting_id}

        # Update status to processing
        meeting.status = MeetingStatusEnum.PROCESSING
        db.commit()
        logger.info(f"Meeting {meeting_id} status updated to PROCESSING")
        
        # Resolve audio file path via storage backend
        store = storage()
        local_audio_path = None
        temp_file = False
        try:
            # audio_filepath might be a storage key (filename) or a legacy full path
            if store.exists(audio_filepath):
                local_audio_path = store.get_local_path(audio_filepath)
                temp_file = not isinstance(store, type(store))  # temp if not local
            elif os.path.exists(audio_filepath):
                # Legacy full path — still works for backward compat
                local_audio_path = audio_filepath
            else:
                # Try just the filename portion
                basename = os.path.basename(audio_filepath)
                if store.exists(basename):
                    local_audio_path = store.get_local_path(basename)
                    temp_file = True
                else:
                    raise FileNotFoundError(f"Audio file not found: {audio_filepath}")

            # Check file size
            file_size = os.path.getsize(local_audio_path)
            if file_size == 0:
                raise ValueError(f"Audio file is empty (0 bytes): {audio_filepath}")
            if file_size < 1024:
                logger.warning(f"Audio file is very small ({file_size} bytes), may be corrupted")
                raise ValueError(f"Audio file is too small ({file_size} bytes). Minimum: 1KB")

            logger.info(f"Transcribing audio: {local_audio_path} (storage key: {audio_filepath})")
            # Transcribe audio with timestamps for speaker identification
            if stt_mode == "local":
                from api.services.local_transcription_service import transcribe_local
                logger.info("Using local faster-whisper for transcription")
                local_result = transcribe_local(local_audio_path, language=language)
                transcript_text = local_result.get("text", "")
                segments = local_result.get("segments", [])
                transcript_data = {
                    "text": transcript_text,
                    "segments": segments,
                    "cost": {
                        "service": f"faster-whisper-{os.getenv('WHISPER_MODEL_SIZE', 'base')}",
                        "duration_seconds": local_result.get("duration", 0),
                        "duration_minutes": round(local_result.get("duration", 0) / 60, 2),
                        "total_cost": 0.0,
                        "currency": "USD",
                    },
                }
            else:
                transcript_data = transcription_service.transcribe_with_timestamps(local_audio_path, language=language)
                transcript_text = transcript_data.get("text", "")
                segments = transcript_data.get("segments", [])

            logger.info(f"Transcription completed, length: {len(transcript_text)} characters")

            # Run speaker diarization on segments
            try:
                from api.services.diarization_service import diarize_with_segments
                if segments and local_audio_path:
                    num_speakers = (meeting.meeting_metadata or {}).get("num_speakers", 2)
                    segments = diarize_with_segments(local_audio_path, segments, num_speakers=int(num_speakers))
                    logger.info(f"Speaker diarization complete: {len(set(s.get('speaker', '') for s in segments))} speakers detected")
            except Exception as e:
                logger.warning(f"Speaker diarization failed (non-critical): {e}")

            if not transcript_text or len(transcript_text.strip()) == 0:
                raise ValueError("Transcription returned empty result")

            # Check if transcript is too short (likely noise or corrupted)
            if len(transcript_text.strip()) < 20:
                logger.warning(f"Transcript is very short ({len(transcript_text)} chars), may be corrupted or contain only noise")
                # Still save it, but mark it appropriately
                speaker_segments = [{"speaker": "Speaker 1", "text": transcript_text, "start_time": None, "end_time": None}]
                unique_speakers = ["Speaker 1"]  # Initialize unique_speakers
            else:
                # Use diarized segments (speakers already assigned by diarization_service)
                speaker_segments = [
                    {
                        "speaker": seg.get("speaker", "Speaker 1"),
                        "text": seg.get("text", ""),
                        "start_time": seg.get("start"),
                        "end_time": seg.get("end"),
                    }
                    for seg in segments
                ]
                unique_speakers = list(set(seg.get("speaker", "Speaker 1") for seg in segments))
                logger.info(f"Using diarized segments: {len(unique_speakers)} speakers")

            # Resolve meeting template from metadata
            template_id = "general"
            if meeting.meeting_metadata and isinstance(meeting.meeting_metadata, dict):
                template_id = meeting.meeting_metadata.get("template", "general")

            # Generate comprehensive meeting notes (use transcript_text, not transcript)
            logger.info(f"Generating meeting notes ({'local Ollama' if llm_mode == 'local' else 'cloud LLM'}, template={template_id})...")
            try:
                if llm_mode == "local":
                    from api.services.local_summarization_service import (
                        summarize_local,
                        extract_key_points_local,
                        extract_action_items_local,
                    )
                    summary_text, summary_usage = summarize_local(transcript_text, template_id=template_id)
                    key_points, kp_usage = extract_key_points_local(transcript_text, template_id=template_id)
                    action_items, ai_usage = extract_action_items_local(transcript_text, template_id=template_id)
                    notes = {
                        "summary": summary_text,
                        "key_points": key_points,
                        "action_items": action_items,
                        "token_cost": {
                            "summary": {"tokens": summary_usage.get("total_tokens", 0), "cost": 0.0, "prompt_tokens": summary_usage.get("prompt_tokens", 0), "completion_tokens": summary_usage.get("completion_tokens", 0)},
                            "key_points": {"tokens": kp_usage.get("total_tokens", 0), "cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0},
                            "action_items": {"tokens": ai_usage.get("total_tokens", 0), "cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0},
                            "total_tokens": summary_usage.get("total_tokens", 0) + kp_usage.get("total_tokens", 0) + ai_usage.get("total_tokens", 0),
                            "total_cost": 0.0,
                            "currency": "USD",
                        },
                    }
                else:
                    notes = summarization_service.generate_meeting_notes(transcript_text, template_id=template_id)
                logger.info(f"Meeting notes generated: summary={bool(notes.get('summary'))}, key_points={len(notes.get('key_points', []))}")
            except Exception as notes_error:
                logger.error(f"Error generating meeting notes: {str(notes_error)}")
                # If summarization fails but we have a transcript, still save the transcript
                # and provide a basic summary
                notes = {
                    "summary": f"Meeting transcript recorded ({len(transcript_text)} characters). Summarization failed — please retry.",
                    "key_points": [],
                    "action_items": [],
                    "token_cost": {
                        "summary": {"tokens": 0, "cost": 0.0},
                        "key_points": {"tokens": 0, "cost": 0.0},
                        "action_items": {"tokens": 0, "cost": 0.0},
                        "total_tokens": 0,
                        "total_cost": 0.0,
                        "currency": "USD"
                    }
                }

            # Calculate total token cost (transcription + summarization)
            transcription_cost = transcript_data.get("cost", {})
            summarization_cost = notes.get("token_cost", {})

            total_cost = {
                "transcription": {
                    "service": transcription_cost.get("service", "whisper-1"),
                    "duration_seconds": transcription_cost.get("duration_seconds"),
                    "duration_minutes": transcription_cost.get("duration_minutes", 0),
                    "cost": transcription_cost.get("total_cost", 0.0),
                    "currency": transcription_cost.get("currency", "USD")
                },
                "summarization": summarization_cost,
                "total_cost": round(transcription_cost.get("total_cost", 0.0) + summarization_cost.get("total_cost", 0.0), 6),
                "currency": "USD"
            }

            summarization_tokens = notes.get("token_cost", {})
            _report_token_usage(
                entity_id=meeting.entity_id,
                input_tokens=summarization_tokens.get("summary", {}).get("prompt_tokens", 0)
                    + summarization_tokens.get("key_points", {}).get("prompt_tokens", 0)
                    + summarization_tokens.get("action_items", {}).get("prompt_tokens", 0),
                output_tokens=summarization_tokens.get("summary", {}).get("completion_tokens", 0)
                    + summarization_tokens.get("key_points", {}).get("completion_tokens", 0)
                    + summarization_tokens.get("action_items", {}).get("completion_tokens", 0),
            )

            # Update meeting with results
            meeting.transcript = transcript_text
            # Store speaker-segmented transcript in meeting_metadata
            if meeting.meeting_metadata is None:
                meeting.meeting_metadata = {}
            meeting.meeting_metadata["speaker_segments"] = speaker_segments
            meeting.meeting_metadata["speakers"] = unique_speakers
            meeting.summary = notes.get("summary", "")
            meeting.key_points = notes.get("key_points", [])
            meeting.action_items = notes.get("action_items", [])
            meeting.token_cost = total_cost
            meeting.status = MeetingStatusEnum.COMPLETED

            db.commit()
            logger.info(f"Meeting {meeting_id} processing completed successfully")

            # Fire webhook notification (best-effort, never fail the task)
            try:
                from api.services.local_auth_service import get_webhook_url_by_entity_id
                webhook_url = get_webhook_url_by_entity_id(meeting.entity_id)
                if webhook_url:
                    from api.services.webhook_service import send_webhook_notification_sync
                    send_webhook_notification_sync(webhook_url, {
                        "title": meeting.title,
                        "summary": meeting.summary,
                        "key_points": meeting.key_points,
                        "action_items": meeting.action_items,
                        "duration": meeting.duration,
                    })
            except Exception as wh_err:
                logger.debug(f"Webhook notification skipped: {wh_err}")

            return {
                "success": True,
                "meeting_id": meeting_id,
                "status": "completed",
                "transcript_length": len(transcript_text),
                "has_summary": bool(notes.get("summary")),
                "speaker_count": len(set(seg.get("speaker", "Unknown") for seg in speaker_segments))
            }
        finally:
            # Clean up temp file if we downloaded from MinIO
            if temp_file and local_audio_path and os.path.exists(local_audio_path):
                try:
                    os.unlink(local_audio_path)
                except Exception:
                    pass

    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"❌ Error processing meeting {meeting_id}: {str(e)}")
        logger.error(f"Traceback: {error_trace}")

        # Retry on transient errors (network, timeout)
        transient_errors = (ConnectionError, TimeoutError, OSError)
        if isinstance(e, transient_errors) or "timeout" in str(e).lower() or "connection" in str(e).lower():
            logger.warning(f"Transient error for meeting {meeting_id}, retrying... (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=e)

        # Update status to failed and stash the error in meeting_metadata so the UI
        # can show the actual reason instead of a generic "this may be due to..." list.
        if meeting:
            try:
                meeting.status = MeetingStatusEnum.FAILED
                if meeting.meeting_metadata is None:
                    meeting.meeting_metadata = {}
                meeting.meeting_metadata = {
                    **meeting.meeting_metadata,
                    "processing_error": str(e)[:500],  # Truncate for safety
                    "processing_error_type": type(e).__name__,
                }
                # SQLAlchemy needs an explicit flag for in-place JSON updates.
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(meeting, "meeting_metadata")
                db.commit()
            except Exception as commit_err:
                logger.warning(f"Could not persist failure metadata: {commit_err}")
                db.rollback()

        return {
            "success": False,
            "meeting_id": meeting_id,
            "error": str(e)[:500],
        }
    finally:
        if db:
            db.close()


@celery_app.task(name="cleanup_stale_meetings")
def cleanup_stale_meetings():
    """Mark meetings stuck in PROCESSING for over 2 hours as FAILED."""
    from datetime import datetime, timedelta
    from loguru import logger

    db = get_db_session()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=2)
        stale = db.query(MeetingModel).filter(
            MeetingModel.status == MeetingStatusEnum.PROCESSING.value,
            MeetingModel.updated_at < cutoff
        ).all()
        for meeting in stale:
            meeting.status = MeetingStatusEnum.FAILED.value
            if not meeting.meeting_metadata:
                meeting.meeting_metadata = {}
            meeting.meeting_metadata["processing_error"] = "Processing timed out after 2 hours"
            meeting.meeting_metadata["processing_error_type"] = "TimeoutError"
            logger.warning(f"Marked stale meeting {meeting.id} as failed (stuck since {meeting.updated_at})")
        db.commit()
        return {"cleaned": len(stale)}
    except Exception as e:
        db.rollback()
        logger.error(f"Cleanup failed: {e}")
        return {"error": str(e)}
    finally:
        db.close()


celery_app.conf.beat_schedule = {
    "cleanup-stale-meetings": {
        "task": "cleanup_stale_meetings",
        "schedule": 600.0,  # Every 10 minutes
    },
}

