"""Hand meeting-processing work to Celery and keep the meeting's status honest.

Ordering matters here.  The original upload/retry handlers committed
``status=processing`` *first* and enqueued the Celery task *second*, inside a
``try/except`` that only logged a warning.  When the broker was unreachable the
meeting was left in PROCESSING with no task behind it and no error recorded —
permanently, since nothing else ever moves a meeting out of PROCESSING.

So: enqueue first, and only claim PROCESSING once the broker has accepted the
task.  If the enqueue fails, the meeting goes to FAILED with the real reason
attached, which is something the user can see and retry from.
"""
from loguru import logger


class EnqueueFailed(Exception):
    """The processing task could not be handed to the broker."""


class MeetingStatusStore:
    """The slice of the meetings table that dispatch needs to touch."""

    def __init__(self, session_factory=None):
        self._session_factory = session_factory

    def _session(self):
        if self._session_factory is not None:
            return self._session_factory()
        from database.db import SessionLocal

        return SessionLocal()

    def get_status(self, meeting_id):
        from database.models import MeetingModel

        db = self._session()
        try:
            row = db.query(MeetingModel.status).filter(MeetingModel.id == meeting_id).first()
            return row[0] if row else None
        finally:
            db.close()

    def compare_and_set(self, meeting_id, expect, new):
        """Set status to ``new`` only if it is still ``expect``.

        The worker may have already advanced the row (it sets PROCESSING on
        pickup and COMPLETED/FAILED when done) before we get here, so an
        unconditional write could resurrect a finished meeting.
        """
        from sqlalchemy import update

        from database.models import MeetingModel

        db = self._session()
        try:
            result = db.execute(
                update(MeetingModel)
                .where(MeetingModel.id == meeting_id, MeetingModel.status == expect)
                .values(status=new)
            )
            db.commit()
            return result.rowcount > 0
        except Exception as exc:
            db.rollback()
            logger.warning(f"Could not update status for meeting {meeting_id}: {exc}")
            return False
        finally:
            db.close()

    def mark_failed(self, meeting_id, error):
        """Record FAILED plus the reason, so the UI shows a cause not a spinner."""
        from sqlalchemy.orm.attributes import flag_modified

        from database.models import MeetingModel, MeetingStatusEnum

        db = self._session()
        try:
            meeting = db.query(MeetingModel).filter(MeetingModel.id == meeting_id).first()
            if not meeting:
                return
            meeting.status = MeetingStatusEnum.FAILED.value
            meeting.meeting_metadata = {
                **(meeting.meeting_metadata or {}),
                "processing_error": str(error)[:500],
                "processing_error_type": type(error).__name__,
            }
            # SQLAlchemy does not detect in-place JSON mutation on its own.
            flag_modified(meeting, "meeting_metadata")
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning(f"Could not persist failure for meeting {meeting_id}: {exc}")
        finally:
            db.close()


def _default_enqueue(meeting_id, audio_ref, language):
    from celery_tasks import process_meeting_task

    return process_meeting_task.delay(meeting_id, audio_ref, language=language)


def dispatch_processing(meeting_id, audio_ref, language=None, *, enqueue=None, store=None):
    """Queue processing for ``meeting_id`` and reflect the outcome in its status.

    Returns the Celery task id.  Raises :class:`EnqueueFailed` — after marking
    the meeting FAILED with the reason — if the broker refused the task.
    """
    enqueue = enqueue or _default_enqueue
    store = store if store is not None else MeetingStatusStore()

    previous_status = store.get_status(meeting_id)

    try:
        result = enqueue(meeting_id, audio_ref, language)
    except Exception as exc:
        logger.error(f"Failed to enqueue processing for meeting {meeting_id}: {exc}")
        store.mark_failed(meeting_id, exc)
        raise EnqueueFailed(str(exc)) from exc

    task_id = getattr(result, "id", None)
    store.compare_and_set(meeting_id, previous_status, "processing")
    logger.info(
        f"Queued processing for meeting {meeting_id} (task={task_id}, language={language})"
    )
    return task_id
