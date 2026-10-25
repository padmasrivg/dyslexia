"""LOCAL contract integration test. This is NOT a test of AWS.

What runs for real: local_agent.cloud.api_client.AssistClient (real `requests`
over real TCP on an ephemeral 127.0.0.1 port) and backend.lambda_handler (the real
handler code, fed API Gateway style proxy events).
What is stubbed: the Bedrock and Polly boto3 clients. API Gateway itself (API key
check, request model, throttling) is not emulated. It verifies that the client
and the handler agree on the wire contract and that failures map to the expected
CloudError.kind values. tests/integration/test_live_aws.py is the real-AWS check.
"""
import base64
import io
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from botocore.exceptions import ClientError

from backend import lambda_handler as lh
from local_agent.cloud.api_client import AssistClient, CloudError
from local_agent.config import Config

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00stub-mp3-bytes"
SENTENCE = "Photosynthesis is how plants turn sunlight into food."


class StubBedrock:
    exc = None

    def converse(self, **kw):
        if self.exc:
            raise self.exc
        return {"output": {"message": {"content": [{"text": json.dumps({"definition": SENTENCE})}]}}}


class StubPolly:
    def synthesize_speech(self, **kw):
        return {"AudioStream": io.BytesIO(MP3)}


class _Ctx:
    aws_request_id = "local-req"


class Fixture:
    """Mutable behaviour switch for the fake gateway."""
    override = None   # callable(handler) -> bool handled
    pre_delay = 0.0
    seen_headers = None


@pytest.fixture
def stack(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "stub-model")
    bedrock = StubBedrock()
    monkeypatch.setattr(lh, "get_bedrock_client", lambda: bedrock)
    monkeypatch.setattr(lh, "get_polly_client", lambda: StubPolly())
    fx = Fixture()

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *a):
            pass

        def _send(self, status, body, ctype="application/json", headers=None):
            raw = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(n).decode()
            fx.seen_headers = dict(self.headers)
            if fx.override and fx.override(self):
                return
            if fx.pre_delay:
                time.sleep(fx.pre_delay)
            if self.path != "/prod/assist":
                return self._send(403, '{"message":"Missing Authentication Token"}')
            event = {"httpMethod": "POST", "path": self.path, "headers": dict(self.headers),
                     "body": raw, "isBase64Encoded": False}
            res = lh.lambda_handler(event, _Ctx())
            self._send(res["statusCode"], res["body"])

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    fx.url = f"http://127.0.0.1:{srv.server_address[1]}/prod/assist"
    fx.bedrock = bedrock
    try:
        yield fx
    finally:
        srv.shutdown()
        srv.server_close()


def client(url, read_timeout=5.0, api_key=""):
    cfg = Config()
    cfg.api_url, cfg.api_key = url, api_key
    cfg.connect_timeout_s, cfg.read_timeout_s = 2.0, read_timeout
    return AssistClient(cfg)


def cerr(code):
    return ClientError({"Error": {"Code": code, "Message": "AWS-INTERNAL-TEXT"}}, "Converse")


def test_success_end_to_end(stack):
    r = client(stack.url, api_key="k123").assist("photosynthesis", "Plants use photosynthesis to eat.")
    assert r.word == "photosynthesis" and r.definition == SENTENCE
    assert base64.b64decode(r.audio_b64) == MP3
    assert r.source == "aws"
    assert set(r.server_timings) == {"bedrock_ms", "polly_ms", "lambda_ms"}
    assert r.api_latency_ms > 0
    assert stack.seen_headers["x-api-key"] == "k123"


def test_url_without_assist_suffix_gets_it_added(stack):
    base = stack.url[: -len("/assist")]
    assert client(base).assist("cat", "The cat sat.").definition == SENTENCE


@pytest.mark.parametrize("code,status", [("ThrottlingException", 429), ("AccessDeniedException", 502),
                                         ("ModelTimeoutException", 504)])
def test_handler_errors_become_api_gateway_kind(stack, code, status):
    stack.bedrock.exc = cerr(code)
    with pytest.raises(CloudError) as ei:
        client(stack.url).assist("cat", "The cat sat on the mat.")
    assert ei.value.kind == "api_gateway" and ei.value.status == status
    assert "AWS-INTERNAL-TEXT" not in ei.value.message


def test_partial_when_polly_down(stack, monkeypatch):
    class Dead:
        def synthesize_speech(self, **kw):
            raise ClientError({"Error": {"Code": "ServiceFailureException", "Message": "x"}}, "S")
    monkeypatch.setattr(lh, "get_polly_client", lambda: Dead())
    r = client(stack.url).assist("cat", "The cat sat.")
    assert r.definition == SENTENCE and r.audio_b64 is None


def test_html_error_page(stack):
    stack.override = lambda h: h._send(502, "<html><body>Bad Gateway</body></html>", "text/html") or True
    with pytest.raises(CloudError) as ei:
        client(stack.url).assist("cat", "The cat sat.")
    assert ei.value.kind == "api_gateway" and ei.value.status == 502


def test_html_with_200_is_malformed(stack):
    stack.override = lambda h: h._send(200, "<html>captive portal</html>", "text/html") or True
    with pytest.raises(CloudError) as ei:
        client(stack.url).assist("cat", "The cat sat.")
    assert ei.value.kind == "malformed_response"


def test_malformed_json_200(stack):
    stack.override = lambda h: h._send(200, '{"status": "succ') or True
    with pytest.raises(CloudError) as ei:
        client(stack.url).assist("cat", "The cat sat.")
    assert ei.value.kind == "malformed_response"


def test_success_status_but_missing_definition(stack):
    stack.override = lambda h: h._send(200, json.dumps({"status": "success", "word": "cat"})) or True
    with pytest.raises(CloudError) as ei:
        client(stack.url).assist("cat", "The cat sat.")
    assert ei.value.kind == "malformed_response"


def test_error_body_with_200_is_service_error(stack):
    body = {"status": "error", "error": {"code": "bedrock_error", "message": "failed"}}
    stack.override = lambda h: h._send(200, json.dumps(body)) or True
    with pytest.raises(CloudError) as ei:
        client(stack.url).assist("cat", "The cat sat.")
    assert ei.value.kind == "service_error"


def test_gateway_403_missing_key(stack):
    with pytest.raises(CloudError) as ei:
        client(stack.url.replace("/prod/assist", "/other")).assist("cat", "The cat sat.")
    assert ei.value.kind == "api_gateway" and ei.value.status == 403


def test_connection_refused():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with pytest.raises(CloudError) as ei:
        client(f"http://127.0.0.1:{port}/assist").assist("cat", "The cat sat.")
    assert ei.value.kind == "network"


def test_client_read_timeout(stack):
    stack.pre_delay = 2.0
    t0 = time.perf_counter()
    with pytest.raises(CloudError) as ei:
        client(stack.url, read_timeout=0.5).assist("cat", "The cat sat.")
    assert ei.value.kind == "timeout"
    assert time.perf_counter() - t0 < 1.9


def test_invalid_word_rejected_client_side(stack):
    stack.override = lambda h: pytest.fail("request must not reach the server")
    with pytest.raises(CloudError) as ei:
        client(stack.url).assist("two words", "The cat sat.")
    assert ei.value.kind == "invalid_request"


def test_empty_context_rejected_client_side(stack):
    with pytest.raises(CloudError) as ei:
        client(stack.url).assist("cat", "   ")
    assert ei.value.kind == "invalid_request"


def test_server_side_validation_still_enforced(stack):
    """Bypass the client-side check: the handler must reject the same input itself."""
    import requests
    r = requests.post(stack.url, json={"word": "cat", "context": ""}, timeout=3)
    assert r.status_code == 400 and r.json()["error"]["code"] == "empty_context"


def test_not_configured():
    with pytest.raises(CloudError) as ei:
        client("").assist("cat", "The cat sat.")
    assert ei.value.kind == "not_configured"
