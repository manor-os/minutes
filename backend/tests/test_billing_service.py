import pytest
import respx
import httpx

from api.services import billing_service as bs


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
def test_report_usage_posts_payload(monkeypatch):
    monkeypatch.setenv("JAVA_HOST", "http://java.test")
    route = respx.post("http://java.test/business/tokenLog/record").mock(
        return_value=httpx.Response(200, json={})
    )
    bs.report_usage(
        entity_id="42", user_id="u1", client_name="acme",
        input_tokens=100, output_tokens=50, business_type="meeting_note",
    )
    assert route.called
    sent = route.calls.last.request
    import json as _json
    body = _json.loads(sent.content)
    assert body["entityId"] == "42"
    assert body["userId"] == "u1"
    assert body["clientName"] == "acme"
    assert body["inputToken"] == 100
    assert body["outputToken"] == 50
    assert body["totalToken"] == 150
    assert body["businessType"] == "meeting_note"


def test_report_usage_noop_on_zero_tokens():
    bs.report_usage(entity_id="42", user_id="u", client_name="c",
                    input_tokens=0, output_tokens=0, business_type="x")


def test_report_usage_swallows_errors(monkeypatch):
    monkeypatch.setenv("JAVA_HOST", "http://127.0.0.1:1")  # nothing listening
    bs.report_usage(entity_id="42", user_id="u", client_name="c",
                    input_tokens=1, output_tokens=1, business_type="x")
