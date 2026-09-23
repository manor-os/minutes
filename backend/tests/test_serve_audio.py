"""API-level tests for GET /api/meetings/audio/{filename}.

Runs the real router against a sqlite DB and a temp LocalStorage backend,
covering: owner download from the storage backend, the legacy local-disk
fallback, ownership enforcement, path-traversal rejection, and unknown files.
"""
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, MeetingModel
from api.routers import meetings
from api.middleware.auth_middleware import get_authenticated_user
from api.services import storage_service

AUDIO_BYTES = b"\x1aE\xdf\xa3fake-webm-bytes-for-test"


def _add_meeting(session_factory, filename, entity_id="ent-1"):
    db = session_factory()
    db.add(MeetingModel(
        id=f"m-{filename}", title="Test meeting", audio_file=filename,
        platform="phone_recorder", entity_id=entity_id,
    ))
    db.commit()
    db.close()


@pytest.fixture()
def env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(meetings, "get_db_session", lambda: session_factory())

    store_dir = tmp_path / "backend_store"
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    monkeypatch.setattr(
        storage_service, "_storage_instance",
        storage_service.LocalStorage(str(store_dir)),
    )
    monkeypatch.setattr(meetings, "STORAGE_DIR", legacy_dir)

    app = FastAPI()
    app.include_router(meetings.router)
    app.dependency_overrides[get_authenticated_user] = lambda: {"entity_id": "ent-1"}
    return {
        "client": TestClient(app),
        "sessions": session_factory,
        "store_dir": store_dir,
        "legacy_dir": legacy_dir,
    }


def test_owner_downloads_from_storage_backend(env):
    _add_meeting(env["sessions"], "rec1.webm")
    storage_service.storage().save(AUDIO_BYTES, "rec1.webm")

    r = env["client"].get("/api/meetings/audio/rec1.webm")
    assert r.status_code == 200
    assert r.content == AUDIO_BYTES
    assert r.headers["content-type"].startswith("audio/webm")


def test_falls_back_to_local_dir_when_backend_missing(env):
    # File exists only on local disk (pre-MinIO upload / local copy),
    # not in the storage backend
    _add_meeting(env["sessions"], "rec2.webm")
    (env["legacy_dir"] / "rec2.webm").write_bytes(AUDIO_BYTES)

    r = env["client"].get("/api/meetings/audio/rec2.webm")
    assert r.status_code == 200
    assert r.content == AUDIO_BYTES


def test_non_owner_gets_404(env):
    _add_meeting(env["sessions"], "rec3.webm", entity_id="someone-else")
    storage_service.storage().save(AUDIO_BYTES, "rec3.webm")

    r = env["client"].get("/api/meetings/audio/rec3.webm")
    assert r.status_code == 404


def test_path_traversal_rejected(env):
    r = env["client"].get("/api/meetings/audio/..%2F..%2Fetc%2Fpasswd")
    assert r.status_code == 400


def test_unknown_file_404(env):
    r = env["client"].get("/api/meetings/audio/nope.webm")
    assert r.status_code == 404


def test_file_missing_everywhere_404(env):
    # Meeting row exists but the bytes are gone from both storage and disk
    _add_meeting(env["sessions"], "rec4.webm")
    r = env["client"].get("/api/meetings/audio/rec4.webm")
    assert r.status_code == 404
