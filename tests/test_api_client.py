import json

import pytest
import requests

from local_agent.cloud.api_client import AssistClient, CloudError, MockAssistClient
from local_agent.config import Config

OK_BODY = {"status": "success", "word": "plants", "definition": "Living things.", "audio": "QUJD",
           "timings": {"lambda_ms": 100, "bedrock_ms": 60, "polly_ms": 30}}


class FakeResp:
    def __init__(self, status=200, body=None, text=None):
        self.status_code = status
        self._body, self._text = body, text

    def json(self):
        if self._text is not None:
            raise ValueError("not json")
        return self._body


class FakeSession:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc, self.calls = resp, exc, []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if self.exc:
            raise self.exc
        return self.resp


def cfg(url="https://api.example.com/prod", key=""):
    return Config(api_url=url, api_key=key, connect_timeout_s=3.0, read_timeout_s=20.0)


def kind(client, word="plants", context="Green plants grow."):
    with pytest.raises(CloudError) as ei:
        client.assist(word, context)
    return ei.value


def test_success_and_request_shape():
    s = FakeSession(FakeResp(200, OK_BODY))
    r = AssistClient(cfg(), s).assist("plants", "Green  plants grow.")
    assert (r.word, r.definition, r.audio_b64, r.source) == ("plants", "Living things.", "QUJD", "aws")
    assert r.server_timings["lambda_ms"] == 100 and r.api_latency_ms >= 0
    call = s.calls[0]
    assert set(call["json"].keys()) == {"word", "context"}  # privacy guarantee
    assert call["json"] == {"word": "plants", "context": "Green plants grow."}
    assert call["url"] == "https://api.example.com/prod/assist"
    assert call["timeout"] == (3.0, 20.0)
    json.dumps(call["json"])


def test_headers_api_key_only_when_configured():
    s = FakeSession(FakeResp(200, OK_BODY))
    AssistClient(cfg(key=""), s).assist("plants", "x y")
    assert set(s.calls[0]["headers"]) == {"Content-Type"}
    s = FakeSession(FakeResp(200, OK_BODY))
    AssistClient(cfg(key="k123"), s).assist("plants", "x y")
    assert set(s.calls[0]["headers"]) == {"Content-Type", "x-api-key"}
    assert s.calls[0]["headers"]["x-api-key"] == "k123"


def test_url_assist_appended_once():
    for u in ("https://a.com/prod/assist", "https://a.com/prod/", "https://a.com/prod/assist/"):
        s = FakeSession(FakeResp(200, OK_BODY))
        AssistClient(cfg(url=u), s).assist("plants", "x y")
        assert s.calls[0]["url"] == "https://a.com/prod/assist"


def test_not_configured_and_invalid_request_make_no_call():
    s = FakeSession(FakeResp(200, OK_BODY))
    assert kind(AssistClient(cfg(url=""), s)).kind == "not_configured"
    assert kind(AssistClient(cfg(), s), word="two words").kind == "invalid_request"
    assert kind(AssistClient(cfg(), s), context="").kind == "invalid_request"
    assert s.calls == []


def test_timeout_and_network():
    assert kind(AssistClient(cfg(), FakeSession(exc=requests.Timeout()))).kind == "timeout"
    assert kind(AssistClient(cfg(), FakeSession(exc=requests.ConnectionError()))).kind == "network"
    assert kind(AssistClient(cfg(), FakeSession(exc=requests.RequestException()))).kind == "network"


@pytest.mark.parametrize("status,body,msg", [
    (403, {"message": "Forbidden"}, "Forbidden"),
    (429, {"message": "Too Many Requests"}, "Too Many Requests"),
    (500, {"error": {"code": "x", "message": "Internal"}}, "Internal"),
    (500, {}, "HTTP 500"),
])
def test_http_errors_with_json(status, body, msg):
    e = kind(AssistClient(cfg(), FakeSession(FakeResp(status, body))))
    assert e.kind == "api_gateway" and e.status == status and msg in e.message


def test_http_502_html():
    e = kind(AssistClient(cfg(), FakeSession(FakeResp(502, text="<html>Bad Gateway</html>"))))
    assert e.kind == "api_gateway" and e.status == 502


def test_200_non_json():
    e = kind(AssistClient(cfg(), FakeSession(FakeResp(200, text="<html>"))))
    assert e.kind == "malformed_response"


def test_200_error_status_and_malformed_body():
    body = {"status": "error", "error": {"code": "bedrock_failed", "message": "model down"}}
    e = kind(AssistClient(cfg(), FakeSession(FakeResp(200, body))))
    assert e.kind == "service_error" and "model down" in e.message
    assert kind(AssistClient(cfg(), FakeSession(FakeResp(200, {"status": "success"})))).kind == "malformed_response"
    assert kind(AssistClient(cfg(), FakeSession(FakeResp(200, [1])))).kind == "malformed_response"


def test_mock_client():
    r = MockAssistClient().assist("Photosynthesis", "ctx")
    assert r.source == "local-mock" and r.audio_b64 is None and r.definition
    assert "plants" in r.definition.lower()
    assert "Mock" in MockAssistClient().assist("zzz", "c").definition
