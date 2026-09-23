"""Integration tests for the HTTP MCP endpoint (/api/mcp).

Runs the real FastMCP streamable-HTTP app (stateless JSON mode) behind the
authentication wrapper, against a sqlite database: verifies auth rejection,
tool listing, tool calls, and entity isolation.
"""
import json
import os

import pytest

os.environ.setdefault("MEETING_NOTE_TAKER_API_KEY", "test-mcp-api-key")

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("mcp")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, MeetingModel

API_KEY = os.environ["MEETING_NOTE_TAKER_API_KEY"]
RPC_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def _rpc(method: str, params: dict | None = None, id: int = 1) -> dict:
    body = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        body["params"] = params
    return body


# Module-scoped: FastMCP's session manager can only be started once per
# process, so all tests share one app/client instance.
@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import mcp_server.server as server_mod
    from api.mcp_http import AuthenticatedMCPApp, mcp_lifespan

    tmp_path = tmp_path_factory.mktemp("mcp")
    engine = create_engine(f"sqlite:///{tmp_path / 'mcp.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    original_get_db_session = server_mod.get_db_session
    server_mod.get_db_session = lambda: session_factory()

    # The api_key_service singleton reads its key at import time, which can
    # precede this module in a full-suite run — set it explicitly.
    from api.services.api_key_service import api_key_service
    original_api_key = api_key_service.valid_api_key
    api_key_service.valid_api_key = API_KEY

    db = session_factory()
    db.add(MeetingModel(
        id="m-ent1", title="Quarterly planning sync", audio_file="a.webm",
        platform="phone_recorder", entity_id="ent-1",
        transcript="We agreed to ship the mobile release in Q4.",
        summary="Planning summary", key_points=["Ship mobile in Q4"],
        action_items=[{"task": "Draft plan", "assignee": "A", "due_date": "TBD"}],
        status="completed",
    ))
    db.add(MeetingModel(
        id="m-ent2", title="Other tenant meeting", audio_file="b.webm",
        platform="phone_recorder", entity_id="ent-2", status="completed",
    ))
    db.commit()
    db.close()

    app = FastAPI(lifespan=mcp_lifespan)
    app.mount("/api/mcp", AuthenticatedMCPApp())
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        server_mod.get_db_session = original_get_db_session
        api_key_service.valid_api_key = original_api_key


def test_unauthenticated_request_is_rejected(client):
    r = client.post("/api/mcp/", headers=RPC_HEADERS, json=_rpc("tools/list"))
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"


def test_wrong_api_key_is_rejected(client):
    r = client.post(
        "/api/mcp/",
        headers={**RPC_HEADERS, "X-API-Key": "nope", "X-Entity-Id": "ent-1"},
        json=_rpc("tools/list"),
    )
    assert r.status_code == 401


def test_api_key_without_entity_is_rejected(client):
    r = client.post(
        "/api/mcp/",
        headers={**RPC_HEADERS, "X-API-Key": API_KEY},
        json=_rpc("tools/list"),
    )
    assert r.status_code == 401


def _auth_headers(entity: str) -> dict:
    return {**RPC_HEADERS, "X-API-Key": API_KEY, "X-Entity-Id": entity}


def test_tools_list(client):
    r = client.post("/api/mcp/", headers=_auth_headers("ent-1"),
                    json=_rpc("tools/list"))
    assert r.status_code == 200
    tools = {t["name"] for t in r.json()["result"]["tools"]}
    assert {"search_meetings", "get_transcript", "get_summary",
            "list_recent_meetings", "get_action_items",
            "get_meeting_details", "get_meeting_stats"} <= tools


def _call_tool(client, entity: str, name: str, arguments: dict) -> str:
    r = client.post(
        "/api/mcp/", headers=_auth_headers(entity),
        json=_rpc("tools/call", {"name": name, "arguments": arguments}),
    )
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert not result.get("isError"), result
    return result["content"][0]["text"]


def test_search_meetings_scoped_to_entity(client):
    text = _call_tool(client, "ent-1", "search_meetings",
                      {"query": "mobile release"})
    assert "Quarterly planning sync" in text
    assert "Other tenant meeting" not in text

    # The other tenant must not see ent-1's meeting
    text2 = _call_tool(client, "ent-2", "search_meetings",
                       {"query": "mobile release"})
    assert "Quarterly planning sync" not in text2


def test_get_transcript_cross_tenant_denied(client):
    text = _call_tool(client, "ent-1", "get_transcript", {"meeting_id": "m-ent1"})
    assert "mobile release in Q4" in text

    # Same meeting id under the wrong entity resolves to nothing
    text2 = _call_tool(client, "ent-2", "get_transcript", {"meeting_id": "m-ent1"})
    assert "mobile release in Q4" not in text2


def test_get_summary(client):
    text = _call_tool(client, "ent-1", "get_summary", {"meeting_id": "m-ent1"})
    assert "Planning summary" in text
    assert "Ship mobile in Q4" in text
