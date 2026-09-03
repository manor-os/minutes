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
def _get_effective_llm_key() -> str:
    return (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()


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
    elif not _get_effective_llm_key():
        logger.error(
            "[startup] No LLM API key is set in the celery worker environment — "
            "Summarization & speaker ID will fail. Set OPENAI_API_KEY or OPENROUTER_API_KEY in .env / docker-compose."
        )
    else:
        logger.info("[startup] LLM API key present")


_check_required_env()


#: Errors that will never succeed on a second attempt.  Listed explicitly
#: because most of them subclass OSError and would otherwise be mistaken for
#: transient network trouble.
PERMANENT_ERRORS = (
    FileNotFoundError, IsADirectoryError, NotADirectoryError,
    PermissionError, ValueError,
)
TRANSIENT_ERRORS = (ConnectionError, TimeoutError, OSError)


def is_transient_error(exc: BaseException) -> bool:
    """Should processing be retried for this error?"""
    if isinstance(exc, PERMANENT_ERRORS):
        return False
    message = str(exc).lower()
    return (
        isinstance(exc, TRANSIENT_ERRORS)
        or "timeout" in message
        or "connection" in message
    )


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
    # Ack only after the task finishes.  With the default (ack on delivery) a
    # worker restart or OOM kill mid-transcription silently dropped the task
    # and left the meeting in PROCESSING with nothing working on it.
    task_acks_late=True,
    # Don't let one worker hoard queued meetings it may never get to.
    worker_prefetch_multiplier=1,
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
        user_stt_base_url = None
        user_llm_key = None
        user_llm_base_url = None
        user_llm_model = None
        try:
            import psycopg2, psycopg2.extras
            # Resolve the owner of this meeting to load their API keys
            meeting_row = db.query(MeetingModel).filter(MeetingModel.id == meeting_id).first()
            owner_id = meeting_row.created_by_user_id if meeting_row else None

            user_conn = psycopg2.connect(
                os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/meeting_notes"),
                cursor_factory=psycopg2.extras.RealDictCursor
            )
            try:
                with user_conn.cursor() as cur:
                    if owner_id:
                        # Query by the exact user who owns this meeting (id is UUID)
                        cur.execute(
                            "SELECT stt_api_key, stt_base_url, llm_api_key, llm_base_url, llm_model FROM users "
                            "WHERE id::text = %s OR email = %s LIMIT 1",
                            (owner_id, owner_id)
                        )
                    else:
                        # No owner info — fall back to any user with keys configured
                        cur.execute(
                            "SELECT stt_api_key, stt_base_url, llm_api_key, llm_base_url, llm_model FROM users "
                            "WHERE (stt_api_key IS NOT NULL AND stt_api_key != '') "
                            "   OR (llm_api_key IS NOT NULL AND llm_api_key != '') "
                            "LIMIT 1"
                        )
                    user_row = cur.fetchone()
                    if user_row:
                        user_stt_key = user_row.get("stt_api_key") or None
                        user_stt_base_url = user_row.get("stt_base_url") or None
                        user_llm_key = user_row.get("llm_api_key") or None
                        user_llm_base_url = user_row.get("llm_base_url") or None
                        user_llm_model = user_row.get("llm_model") or None
                        logger.info(
                            f"Loaded user config from DB (owner={owner_id}) — "
                            f"STT: {'set' if user_stt_key else 'not set'}, "
                            f"stt_base_url: {user_stt_base_url or '(none)'}, "
                            f"LLM: {'set' if user_llm_key else 'not set'}, "
                            f"llm_base_url: {user_llm_base_url or '(none)'}, "
                            f"llm_model: {user_llm_model or '(default)'}"
                        )
            finally:
                user_conn.close()
        except Exception as e:
            logger.warning(f"Could not load user API keys from DB: {e}")

        # Manor accounts are billed by Manor itself: their summarization calls
        # go through the Manor LLM gateway, so no local provider key is needed
        # and a key the user saved in Settings is never used for them.
        manor_route = False
        try:
            route_row = db.query(MeetingModel.auth_source).filter(MeetingModel.id == meeting_id).first()
            manor_route = bool(route_row and (route_row[0] or "local") == "manor")
        except Exception as e:
            logger.warning(f"Could not resolve meeting auth_source for {meeting_id}: {e}")
        if manor_route:
            user_llm_key = user_llm_base_url = user_llm_model = None

        # Check local mode env vars
        stt_mode = os.getenv("STT_MODE", "cloud")
        llm_mode = os.getenv("LLM_MODE", "cloud")
        logger.info(f"Processing modes: STT={stt_mode}, LLM={llm_mode}")

        from api.services.llm_config import get_openrouter_base_url
        _default_base_url = get_openrouter_base_url()

        # If llm_api_key is not set, fall back to stt_api_key (same proxy key)
        effective_user_llm_key = user_llm_key or user_stt_key
        effective_user_llm_base_url = user_llm_base_url or user_stt_base_url

        # Determine which keys to use: user's key > env var > default proxy
        effective_stt_key = user_stt_key or os.getenv("OPENAI_API_KEY", "").strip()
        effective_llm_key = (
            effective_user_llm_key
            or os.getenv("OPENROUTER_API_KEY", "").strip()
            or os.getenv("OPENAI_API_KEY", "").strip()
        )

        if stt_mode != "local" and not effective_stt_key:
            raise RuntimeError(
                "No OpenAI API key available for Whisper transcription. "
                "Please configure your OpenAI key in Settings, or set OPENAI_API_KEY env var."
            )
        if llm_mode != "local" and not manor_route and not effective_llm_key:
            raise RuntimeError(
                "No LLM API key available for summarization. "
                "Please configure your LLM key in Settings, or set OPENROUTER_API_KEY env var."
            )

        # Override env vars so services pick up user's keys and base URLs
        if user_stt_key:
            os.environ["OPENAI_API_KEY"] = user_stt_key
        # STT base URL: only override when explicitly configured — OpenAI SDK defaults to api.openai.com
        if user_stt_base_url:
            os.environ["OPENAI_BASE_URL"] = user_stt_base_url
        elif os.getenv("OPENAI_BASE_URL"):
            pass  # keep existing env var
        else:
            # Not configured — let the SDK use api.openai.com (remove any stale value)
            os.environ.pop("OPENAI_BASE_URL", None)

        # LLM key: user llm key > user stt key (same proxy) > env var
        os.environ["OPENROUTER_API_KEY"] = effective_llm_key
        # LLM base URL: user setting > default proxy
        os.environ["OPENROUTER_BASE_URL"] = effective_user_llm_base_url or _default_base_url

        # LLM model: user setting > env var (get_llm_model() reads LLM_MODEL)
        if user_llm_model:
            os.environ["LLM_MODEL"] = user_llm_model

        logger.info(
            # .get(), not []: the branch above deliberately pops OPENAI_BASE_URL
            # when no STT base URL is configured, so indexing it raised KeyError
            # here — before `meeting` was loaded, which meant the failure handler
            # could not mark the meeting FAILED and it stayed in PROCESSING.
            f"Effective config — STT base: {os.environ.get('OPENAI_BASE_URL') or '(OpenAI default)'}, "
            f"LLM base: {os.environ.get('OPENROUTER_BASE_URL') or '(default)'}, "
            f"LLM model: {os.environ.get('LLM_MODEL', '(default)')}, "
            f"LLM key source: {'user_llm' if user_llm_key else 'user_stt' if user_stt_key else 'env'}"
        )

        transcription_service = None if stt_mode == "local" else TranscriptionService()
        logger.info(f"LLM key for summarization: {'set (' + str(len(os.getenv('OPENROUTER_API_KEY', ''))) + ' chars)' if os.getenv('OPENROUTER_API_KEY') else 'NOT SET'}, OPENAI_API_KEY: {'set' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}")
        if llm_mode == "local" or manor_route:
            # Manor meetings get a gateway-backed service once the meeting row
            # (entity / creator) is loaded below.
            summarization_service = None
        else:
            summarization_service = SummarizationService()

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

        if manor_route and llm_mode != "local":
            from api.services.llm_config import resolve_llm
            gateway_client, gateway_model = resolve_llm(
                route="manor",
                manor_ctx={
                    "entity_id": meeting.entity_id,
                    "user_id": meeting.created_by_user_id,
                    "business_type": "meeting_note",
                },
            )
            summarization_service = SummarizationService(client=gateway_client, model=gateway_model)
            logger.info(f"Meeting {meeting_id}: summarization routed through the Manor LLM gateway")
        
        # Resolve audio file path via storage backend
        store = storage()
        local_audio_path = None
        temp_file = False
        try:
            # audio_filepath might be a storage key (filename) or a legacy full path
            from api.services.storage_service import LocalStorage

            # Remote backends hand back a downloaded temp file we must delete;
            # LocalStorage hands back the real file, which we must not.
            store_is_remote = not isinstance(store, LocalStorage)

            if store.exists(audio_filepath):
                local_audio_path = store.get_local_path(audio_filepath)
                temp_file = store_is_remote
            elif os.path.exists(audio_filepath):
                # Legacy full path — still works for backward compat
                local_audio_path = audio_filepath
            else:
                # Try just the filename portion
                basename = os.path.basename(audio_filepath)
                if store.exists(basename):
                    local_audio_path = store.get_local_path(basename)
                    temp_file = store_is_remote
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

            # Collapse Whisper repetition-loop hallucinations ("Dr. Dr. Dr. ...")
            # before diarization and summarization see the transcript
            from api.services.transcript_cleaning import clean_transcription
            transcript_text, segments = clean_transcription(transcript_text, segments)

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

            # Manor meetings were billed by the Manor gateway as each call ran;
            # BYO meetings ran on the user's own key. Nothing to report here.

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

        # Retry on transient errors (network, timeout).
        #
        # Two traps here, both of which used to strand meetings in PROCESSING:
        #   * FileNotFoundError (and PermissionError, IsADirectoryError...)
        #     subclass OSError, so a permanently missing audio file was retried
        #     as if it were a blip.
        #   * self.retry() raises, skipping the FAILED bookkeeping below.  Once
        #     retries run out, self.retry(exc=e) re-raises the original error
        #     straight out of the task, so nothing ever marked the meeting
        #     failed and it span forever.
        # So: exclude permanent errors, and stop retrying one attempt early so
        # the last attempt falls through and records the failure.
        looks_transient = is_transient_error(e)
        if looks_transient and self.request.retries < self.max_retries:
            logger.warning(f"Transient error for meeting {meeting_id}, retrying... (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=e)
        if looks_transient:
            logger.error(f"Meeting {meeting_id} exhausted {self.max_retries} retries; marking failed")

        # Release anything this session is holding before writing the failure.
        try:
            db.rollback()
        except Exception:
            pass

        # Update status to failed and stash the error in meeting_metadata so the UI
        # can show the actual reason instead of a generic "this may be due to..." list.
        # Written through a fresh session keyed by meeting_id rather than the
        # `meeting` object: the error can fire before that row is ever loaded
        # (a missing API key raises above the query), and `if meeting:` then
        # skipped this entirely and left the meeting in PROCESSING.
        from api.services.processing_dispatch import MeetingStatusStore
        MeetingStatusStore().mark_failed(meeting_id, e)

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
    """Mark meetings stuck in PROCESSING past the timeout as FAILED.

    This is the backstop for every way a task can vanish without running its
    own error handler — worker killed mid-task, broker restarted, container
    replaced.  Without it a meeting sits in PROCESSING indefinitely and the UI
    spins forever.  Requires `celery beat` to be running (see the celery-beat
    service in docker-compose.yml).
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy.orm.attributes import flag_modified
    from loguru import logger

    timeout_hours = float(os.getenv("PROCESSING_TIMEOUT_HOURS", "2"))

    db = get_db_session()
    try:
        # meetings.updated_at is TIMESTAMP WITHOUT TIME ZONE holding UTC
        # wall-clock (migration 001 defaults it to CURRENT_TIMESTAMP and its
        # BEFORE UPDATE trigger refreshes it).  Compare against a naive UTC
        # value: an aware one would be cast using the session's TimeZone and
        # silently skew the cutoff wherever that isn't UTC.
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=timeout_hours)
        stale = db.query(MeetingModel).filter(
            MeetingModel.status == MeetingStatusEnum.PROCESSING.value,
            MeetingModel.updated_at < cutoff
        ).all()
        for meeting in stale:
            meeting.status = MeetingStatusEnum.FAILED.value
            meeting.meeting_metadata = {
                **(meeting.meeting_metadata or {}),
                "processing_error": f"Processing timed out after {timeout_hours} hours",
                "processing_error_type": "TimeoutError",
            }
            # SQLAlchemy does not detect in-place JSON mutation; without this
            # the error never reached the database and the UI showed no reason.
            flag_modified(meeting, "meeting_metadata")
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
