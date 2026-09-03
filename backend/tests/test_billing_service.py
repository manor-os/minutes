import pytest
import respx
import httpx

from api.services import billing_service as bs


@pytest.fixture(autouse=True)
def manor_client_env(monkeypatch):
    monkeypatch.setenv("MANOR_OAUTH_CLIENT_ID", "minutes-cloud")
    monkeypatch.setenv("MANOR_OAUTH_CLIENT_SECRET", "minutes-secret")
    monkeypatch.setenv("MANOR_API_BASE_URL", "https://manor.test")


def test_classify_manor_auth_source():
    assert bs.classify({"auth_source": "manor", "entity_id": "42"}) == "manor"


def test_classify_google_is_manor_billed():
    assert bs.classify({"auth_source": "google", "entity_id": "42"}) == "manor"


def test_classify_local_when_no_auth_source():
    assert bs.classify({"entity_id": "abc"}) == "byo"


def test_classify_byo_when_auth_source_local():
    assert bs.classify({"auth_source": "local"}) == "byo"


def test_ensure_credit_passes_when_unlocked():
    class Auth:
        def check_credit_available(self, entity_id):
            return True
    bs.ensure_credit("42", auth=Auth())  # no raise


def test_ensure_credit_raises_when_locked():
    class Auth:
        def check_credit_available(self, entity_id):
            return False
    with pytest.raises(bs.CreditExhaustedError):
        bs.ensure_credit("42", auth=Auth())


def test_ensure_credit_blocks_when_no_entity():
    with pytest.raises(bs.CreditExhaustedError):
        bs.ensure_credit("", auth=object())


@respx.mock
def test_ensure_credit_preflights_manor_gateway_with_client_credentials():
    route = respx.get("https://manor.test/api/v1/llm/credit").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    bs.ensure_credit("01JZENTITY", user_id="usr_1")  # no raise

    assert route.called
    headers = route.calls.last.request.headers
    assert headers["x-manor-client-id"] == "minutes-cloud"
    assert headers["x-manor-client-secret"] == "minutes-secret"
    assert headers["x-manor-entity-id"] == "01JZENTITY"
    assert headers["x-manor-user-id"] == "usr_1"


@respx.mock
def test_ensure_credit_raises_when_gateway_says_402():
    respx.get("https://manor.test/api/v1/llm/credit").mock(
        return_value=httpx.Response(402, json={"detail": "Credit balance exhausted"})
    )
    with pytest.raises(bs.CreditExhaustedError):
        bs.ensure_credit("01JZENTITY")


@respx.mock
def test_ensure_credit_fails_open_on_gateway_outage():
    respx.get("https://manor.test/api/v1/llm/credit").mock(side_effect=httpx.ConnectError("down"))
    bs.ensure_credit("01JZENTITY")  # no raise


@respx.mock
def test_ensure_credit_fails_open_on_unexpected_status():
    respx.get("https://manor.test/api/v1/llm/credit").mock(return_value=httpx.Response(500))
    bs.ensure_credit("01JZENTITY")  # no raise


def test_ensure_credit_fails_open_when_gateway_not_configured(monkeypatch):
    monkeypatch.delenv("MANOR_OAUTH_CLIENT_SECRET", raising=False)
    bs.ensure_credit("01JZENTITY")  # no raise; the gateway rejects the real call instead


def test_no_local_usage_reporting_remains():
    # Manor bills every gateway call itself; Minutes must not keep a side
    # channel that could double-charge or point at a retired backend.
    assert not hasattr(bs, "report_usage")


class _StatusErr(Exception):
    def __init__(self, status_code):
        super().__init__("err")
        self.status_code = status_code


class _StreamErr(Exception):
    def __init__(self, body, code=None):
        super().__init__("err")
        self.body = body
        self.code = code


def test_is_credit_exhausted_error_matches_http_402():
    assert bs.is_credit_exhausted_error(_StatusErr(402))
    assert not bs.is_credit_exhausted_error(_StatusErr(500))


def test_is_credit_exhausted_error_matches_stream_error_event():
    assert bs.is_credit_exhausted_error(_StreamErr({"message": "x", "type": "insufficient_credit", "code": 402}))
    assert bs.is_credit_exhausted_error(_StreamErr({"error": {"code": 402}}))
    assert bs.is_credit_exhausted_error(_StreamErr({}, code=402))
    assert not bs.is_credit_exhausted_error(_StreamErr({"message": "boom", "type": "server_error", "code": 500}))
    assert not bs.is_credit_exhausted_error(RuntimeError("boom"))
