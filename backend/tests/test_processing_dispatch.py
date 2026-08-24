import pytest

from api.services import processing_dispatch as pd


class FakeStore:
    """In-memory stand-in for the meetings table."""

    def __init__(self, status):
        self.status = status
        self.error = None
        # Lets a test simulate the worker racing ahead between the enqueue
        # and the compare-and-set that follows it.
        self.on_get_status = None

    def get_status(self, meeting_id):
        return self.status

    def compare_and_set(self, meeting_id, expect, new):
        if self.status != expect:
            return False
        self.status = new
        return True

    def mark_failed(self, meeting_id, error):
        self.status = "failed"
        self.error = str(error)


def ok_enqueue(task_id="task-1"):
    class Result:
        id = task_id

    def _enqueue(meeting_id, audio_ref, language):
        _enqueue.calls.append((meeting_id, audio_ref, language))
        return Result()

    _enqueue.calls = []
    return _enqueue


def broken_enqueue(exc=None):
    def _enqueue(meeting_id, audio_ref, language):
        raise exc or ConnectionError("Error 111 connecting to redis:6379. Connection refused.")

    return _enqueue


def test_marks_processing_after_successful_enqueue():
    store = FakeStore("uploading")
    enqueue = ok_enqueue()

    task_id = pd.dispatch_processing("m1", "audio.webm", language="en", enqueue=enqueue, store=store)

    assert task_id == "task-1"
    assert store.status == "processing"
    assert enqueue.calls == [("m1", "audio.webm", "en")]


def test_marks_failed_when_broker_is_unreachable():
    store = FakeStore("uploading")

    with pytest.raises(pd.EnqueueFailed):
        pd.dispatch_processing("m1", "audio.webm", enqueue=broken_enqueue(), store=store)

    assert store.status == "failed"
    assert "redis" in store.error.lower()


def test_never_leaves_meeting_in_processing_when_enqueue_fails():
    """The bug this module exists to prevent: PROCESSING with no task behind it."""
    store = FakeStore("uploading")

    with pytest.raises(pd.EnqueueFailed):
        pd.dispatch_processing("m1", "audio.webm", enqueue=broken_enqueue(), store=store)

    assert store.status != "processing"


def test_retry_from_failed_moves_back_to_processing():
    store = FakeStore("failed")

    pd.dispatch_processing("m1", "audio.webm", enqueue=ok_enqueue(), store=store)

    assert store.status == "processing"


def test_does_not_clobber_a_meeting_the_worker_already_completed():
    """Worker may finish before dispatch gets to update the row."""
    store = FakeStore("uploading")

    def racing_enqueue(meeting_id, audio_ref, language):
        store.status = "completed"  # worker won the race

        class Result:
            id = "task-1"

        return Result()

    pd.dispatch_processing("m1", "audio.webm", enqueue=racing_enqueue, store=store)

    assert store.status == "completed"


def test_does_not_clobber_a_meeting_the_worker_already_failed():
    store = FakeStore("uploading")

    def racing_enqueue(meeting_id, audio_ref, language):
        store.status = "failed"

        class Result:
            id = "task-1"

        return Result()

    pd.dispatch_processing("m1", "audio.webm", enqueue=racing_enqueue, store=store)

    assert store.status == "failed"


def test_enqueue_failure_reports_the_underlying_cause():
    store = FakeStore("uploading")

    with pytest.raises(pd.EnqueueFailed) as excinfo:
        pd.dispatch_processing(
            "m1", "audio.webm", enqueue=broken_enqueue(OSError("broker gone")), store=store
        )

    assert "broker gone" in str(excinfo.value)
