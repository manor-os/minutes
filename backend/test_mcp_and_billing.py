"""Tests for the MCP CRUD tools and the BYOK billing logic.

Everything runs in-process:
- DB: SQLite via SQLAlchemy (the production code uses Postgres, but the
  ORM definitions are portable; meetings table works on both).
- Manor billing: httpx is monkey-patched so charge_credits() captures
  the payload without making a network call.
- JWT helpers are real — we mint a token with local_auth_service and use
  it to drive the MCP tools through their public entry points.
"""
import os
import sys
import tempfile
import uuid
from typing import Any, Dict, List

# Configure env BEFORE any imports
os.environ["EDITION"] = "cloud"
os.environ["JWT_SECRET"] = "test-secret-for-mcp-billing"
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["MANOR_BASE_URL"] = "https://manor.test"
os.environ["MANOR_CLIENT_ID"] = "cid"
os.environ["MANOR_CLIENT_SECRET"] = "csec"
os.environ["MANOR_REDIRECT_URI"] = "https://m.test/cb"
os.environ["MANOR_SERVICE_API_KEY"] = "svc-key"
# Stop the OpenAI / OpenRouter clients from refusing to construct.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")
os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test-placeholder")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx
import json as _json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# --- Database: SQLite ------------------------------------------------------
# Patch get_db_session BEFORE anything imports it to look up the URL.
import database.db as dbmod

_engine = create_engine(os.environ["DATABASE_URL"], future=True)
_Session = sessionmaker(bind=_engine, expire_on_commit=False)

# Create tables fresh.
from database.models import Base, MeetingModel, MeetingStatusEnum
Base.metadata.create_all(bind=_engine)

dbmod.SessionLocal = _Session
dbmod.get_db_session = lambda: _Session()

# --- Helpers ---------------------------------------------------------------
results: List = []

def ok(label: str, cond: bool, extra: str = ""):
    tag = "OK  " if cond else "FAIL"
    results.append((tag, label))
    print(f"  [{tag}] {label}  {extra}")


def make_meeting(entity_id: int, **overrides) -> str:
    mid = uuid.uuid4().hex
    sess = _Session()
    try:
        m = MeetingModel(
            id=mid,
            title=overrides.get("title", f"Meeting {mid[:6]}"),
            audio_file=f"{mid}.webm",
            platform="phone_recorder",
            duration=overrides.get("duration", 300),
            status=overrides.get("status", MeetingStatusEnum.COMPLETED.value),
            transcript=overrides.get("transcript", "hello world"),
            summary=overrides.get("summary", "A summary."),
            key_points=overrides.get("key_points", ["one", "two"]),
            action_items=overrides.get("action_items", [{"task": "do thing"}]),
            entity_id=entity_id,
            tags=overrides.get("tags", "important,blue"),
            is_favorite=overrides.get("is_favorite", False),
        )
        sess.add(m)
        sess.commit()
        return mid
    finally:
        sess.close()


# --- 1. MCP tools (pure functions) ----------------------------------------
print("=== 1. MCP tools — list / get / update / delete / search ===")
from api import mcp_tools

ALICE = 1001
BOB = 2002  # different tenant — must not see Alice's meetings

m1 = make_meeting(ALICE, title="Q3 planning", tags="planning,strategy")
m2 = make_meeting(ALICE, title="Retro April", duration=600, is_favorite=True, tags="retro")
m3 = make_meeting(BOB, title="Bob's standup")

lst = mcp_tools.list_meetings(entity_id=ALICE)
ok("list returns alice's meetings (count)", lst["total"] == 2, f"got {lst['total']}")
ok("list excludes bob's meeting", all(m["id"] != m3 for m in lst["meetings"]))
ok("list excludes transcript by default", "transcript" not in lst["meetings"][0])

lst_fav = mcp_tools.list_meetings(entity_id=ALICE, favorite=True)
ok("favorite filter", lst_fav["total"] == 1 and lst_fav["meetings"][0]["id"] == m2)

lst_tag = mcp_tools.list_meetings(entity_id=ALICE, tag="planning")
ok("tag filter", lst_tag["total"] == 1 and lst_tag["meetings"][0]["id"] == m1)

lst_sort = mcp_tools.list_meetings(entity_id=ALICE, sort="longest")
ok("sort=longest puts m2 first", lst_sort["meetings"][0]["id"] == m2)

full = mcp_tools.get_meeting(entity_id=ALICE, meeting_id=m1)
ok("get_meeting returns full row with transcript", full and full["transcript"] == "hello world")
cross = mcp_tools.get_meeting(entity_id=BOB, meeting_id=m1)
ok("get_meeting is tenant-isolated (bob can't read alice's meeting)", cross is None)

transcript = mcp_tools.get_meeting_transcript(entity_id=ALICE, meeting_id=m1)
ok("get_meeting_transcript returns transcript", transcript and transcript["transcript"] == "hello world")

summary = mcp_tools.get_meeting_summary(entity_id=ALICE, meeting_id=m1)
ok("get_meeting_summary returns summary fields", summary and summary["summary"] == "A summary." and summary["key_points"] == ["one", "two"])

upd = mcp_tools.update_meeting(entity_id=ALICE, meeting_id=m1, title="Q3 plan (rev)", tags=["planning", "urgent"], is_favorite=True)
ok("update_meeting updates fields", upd["title"] == "Q3 plan (rev)" and upd["is_favorite"] is True)
ok("update_meeting persists tags as list", upd["tags"] == ["planning", "urgent"], f"got {upd['tags']}")
ok("update_meeting tenant-isolated (bob cannot)", mcp_tools.update_meeting(entity_id=BOB, meeting_id=m1, title="hack") is None)

hits = mcp_tools.search_meetings(entity_id=ALICE, query="Retro")
ok("search_meetings finds by title", len(hits) == 1 and hits[0]["id"] == m2)

ok("delete_meeting tenant-isolated", mcp_tools.delete_meeting(entity_id=BOB, meeting_id=m1) is False)
ok("delete_meeting deletes own meeting", mcp_tools.delete_meeting(entity_id=ALICE, meeting_id=m1) is True)
ok("after delete, list count is 1", mcp_tools.list_meetings(entity_id=ALICE)["total"] == 1)

# --- 2. MCP server: JWT -> entity_id resolution ---------------------------
print()
print("=== 2. MCP server auth (JWT -> entity_id) ===")
from api.services.local_auth_service import generate_token, _stable_entity_id

from api.mcp_server import _resolve_entity_id

email = "alice@manor.test"
alice_eid = _stable_entity_id(email)
alice_token = generate_token({"id": "u1", "email": email, "name": "Alice"})
ok("resolve_entity_id from JWT", _resolve_entity_id(alice_token) == alice_eid)

try:
    _resolve_entity_id("")
    ok("rejects empty token", False)
except ValueError:
    ok("rejects empty token", True)

try:
    _resolve_entity_id("not.a.jwt")
    ok("rejects junk token", False)
except ValueError:
    ok("rejects junk token", True)

# --- 3. MCP server: tools are wired and callable -------------------------
print()
print("=== 3. MCP server: tools registered ===")
from api.mcp_server import get_mcp_server
import anyio

server = get_mcp_server()
ok("MCP server builds", server is not None)
if server is not None:
    tool_list = anyio.run(server.list_tools)
    tool_names = sorted(t.name for t in tool_list)
    print("    registered tools:", tool_names)
    expected = {
        "list_meetings", "get_meeting", "get_meeting_transcript",
        "get_meeting_summary", "update_meeting", "delete_meeting",
        "search_meetings", "list_meeting_templates",
    }
    ok("all expected tools registered", expected.issubset(set(tool_names)),
       f"missing={expected - set(tool_names)}")

    # Call a tool end-to-end through FastMCP's dispatcher to confirm the
    # decorator wiring isn't subtly broken.
    eid = _stable_entity_id("e2e@manor.test")
    e2e_token = generate_token({"id": "u2", "email": "e2e@manor.test", "name": "E2E"})
    m_eid = make_meeting(eid, title="e2e check")
    res = anyio.run(server.call_tool, "get_meeting", {"auth_token": e2e_token, "meeting_id": m_eid})
    structured = res[1] if isinstance(res, tuple) and len(res) >= 2 else res
    # FastMCP wraps non-primitive returns as {"result": <obj>} in the structured channel.
    payload = structured.get("result") if isinstance(structured, dict) and "result" in structured else structured
    ok("call_tool('get_meeting') round-trips through FastMCP",
       isinstance(payload, dict) and payload.get("title") == "e2e check",
       f"got_title={payload.get('title') if isinstance(payload, dict) else type(payload)}")

# --- 4. BYOK billing ------------------------------------------------------
print()
print("=== 4. BYOK billing — Manor not charged when user pays the provider ===")
import api.services.manor_billing_service as billing_mod

captured: Dict[str, Any] = {}


def mock_transport(request: httpx.Request) -> httpx.Response:
    captured["url"] = str(request.url)
    captured["json"] = _json.loads(request.content.decode()) if request.content else {}
    captured["called"] = captured.get("called", 0) + 1
    return httpx.Response(200, json={"ok": True})


class _ShimHttpx:
    HTTPError = httpx.HTTPError
    Timeout = httpx.Timeout
    @staticmethod
    def Client(*a, **kw):
        kw.pop("timeout", None)
        return httpx.Client(transport=httpx.MockTransport(mock_transport), base_url="https://manor.test")


billing_mod.httpx = _ShimHttpx

# Make a Manor-linked user so billing kicks in.
from api.services.local_auth_service import init_users_table, upsert_oauth_user, get_manor_user_id_by_entity_id
# init_users_table uses raw psycopg2 — we're on SQLite, so re-create using ORM.
from sqlalchemy import Column, String, Integer
from database.models import Base as ORMBase
from sqlalchemy import text as sql_text

with _engine.begin() as conn:
    conn.execute(sql_text("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            name TEXT,
            manor_user_id TEXT,
            stt_api_key TEXT,
            stt_base_url TEXT,
            llm_api_key TEXT,
            llm_model TEXT,
            llm_base_url TEXT,
            webhook_url TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """))
    conn.execute(sql_text(
        "INSERT INTO users (id, email, password_hash, name, manor_user_id) "
        "VALUES ('u1', 'alice@manor.test', '!oauth', 'Alice', 'manor-uid-42')"
    ))

# Patch get_manor_user_id_by_entity_id to use SQLite via our engine.
def _sqlite_lookup(entity_id):
    with _engine.begin() as conn:
        rows = conn.execute(sql_text("SELECT email, manor_user_id FROM users WHERE manor_user_id IS NOT NULL")).fetchall()
    for email, mid in rows:
        if _stable_entity_id(email) == entity_id:
            return mid
    return None

import api.services.local_auth_service as las
las.get_manor_user_id_by_entity_id = _sqlite_lookup

# Now exercise the celery-side helper directly.
from celery_tasks import _charge_manor_credits

alice_eid_2 = _stable_entity_id("alice@manor.test")

# (a) Pure Manor: charge everything
captured.clear()
_charge_manor_credits(
    entity_id=alice_eid_2, transcription_minutes=5.0,
    input_tokens=1000, output_tokens=500, meeting_id="meeting-1",
    stt_byok=False, llm_byok=False,
)
ok("(a) Manor STT + Manor LLM: charged once", captured.get("called") == 1)
ok("    minutes billed", captured["json"]["usage"]["transcription_minutes"] == 5.0)
ok("    input_tokens billed", captured["json"]["usage"]["input_tokens"] == 1000)
ok("    output_tokens billed", captured["json"]["usage"]["output_tokens"] == 500)
ok("    idempotency key set", captured["json"]["idempotency_key"] == "meeting:meeting-1")

# (b) BYOK STT, Manor LLM
captured.clear()
_charge_manor_credits(
    entity_id=alice_eid_2, transcription_minutes=5.0,
    input_tokens=1000, output_tokens=500, meeting_id="meeting-2",
    stt_byok=True, llm_byok=False,
)
ok("(b) BYOK STT: still charged for LLM tokens", captured.get("called") == 1)
ok("    minutes zeroed out", captured["json"]["usage"]["transcription_minutes"] == 0)
ok("    tokens still billed", captured["json"]["usage"]["input_tokens"] == 1000)

# (c) Manor STT, BYOK LLM
captured.clear()
_charge_manor_credits(
    entity_id=alice_eid_2, transcription_minutes=5.0,
    input_tokens=1000, output_tokens=500, meeting_id="meeting-3",
    stt_byok=False, llm_byok=True,
)
ok("(c) BYOK LLM: still charged for STT minutes", captured.get("called") == 1)
ok("    minutes still billed", captured["json"]["usage"]["transcription_minutes"] == 5.0)
ok("    tokens zeroed out", captured["json"]["usage"]["input_tokens"] == 0 and captured["json"]["usage"]["output_tokens"] == 0)

# (d) Full BYOK
captured.clear()
_charge_manor_credits(
    entity_id=alice_eid_2, transcription_minutes=5.0,
    input_tokens=1000, output_tokens=500, meeting_id="meeting-4",
    stt_byok=True, llm_byok=True,
)
ok("(d) Full BYOK: Manor not called at all", captured.get("called", 0) == 0)

# (e) Non-Manor user (no manor_user_id linked): skip regardless
captured.clear()
random_eid = _stable_entity_id("bob@local.test")
_charge_manor_credits(
    entity_id=random_eid, transcription_minutes=5.0,
    input_tokens=1000, output_tokens=500, meeting_id="meeting-5",
    stt_byok=False, llm_byok=False,
)
ok("(e) Non-Manor user: not billed", captured.get("called", 0) == 0)

# --- 5. Realtime billing helper ------------------------------------------
print()
print("=== 5. Realtime session billing ===")
from api.routers.realtime import _charge_realtime_session

# Manor user, cloud STT, 180s session -> billed
captured.clear()
_charge_realtime_session(entity_id=alice_eid_2, session_id="sess-1", seconds_transcribed=180.0, stt_byok=False)
ok("realtime: cloud STT + Manor user -> charged", captured.get("called") == 1)
ok("    transcription_minutes = 3.0", captured["json"]["usage"]["transcription_minutes"] == 3.0)
ok("    idempotency key carries session id", captured["json"]["idempotency_key"] == "meeting:realtime:sess-1")

# BYOK STT -> skipped
captured.clear()
_charge_realtime_session(entity_id=alice_eid_2, session_id="sess-2", seconds_transcribed=180.0, stt_byok=True)
ok("realtime: BYOK STT -> not charged", captured.get("called", 0) == 0)

# No entity_id (anonymous ws) -> skipped
captured.clear()
_charge_realtime_session(entity_id=None, session_id="sess-3", seconds_transcribed=180.0, stt_byok=False)
ok("realtime: no entity_id -> not charged", captured.get("called", 0) == 0)

# Zero duration -> skipped
captured.clear()
_charge_realtime_session(entity_id=alice_eid_2, session_id="sess-4", seconds_transcribed=0.0, stt_byok=False)
ok("realtime: zero duration -> not charged", captured.get("called", 0) == 0)

print()
fails = [r for r in results if r[0].strip() == "FAIL"]
print(f"=== Summary: {len(results) - len(fails)}/{len(results)} checks passed ===")
sys.exit(1 if fails else 0)
