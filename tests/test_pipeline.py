"""Pipeline behaviour with fake OCR, grabber and cloud client (real detector, state machine, dwell)."""
import threading
import time

import pytest
from fastapi.testclient import TestClient

from local_agent.capture.base import CaptureError
from local_agent.capture.demo_source import DemoFrameGrabber
from local_agent.cloud.api_client import CloudError
from local_agent.config import Config
from local_agent.datatypes import AssistanceResult, WordBox
from local_agent.pipeline import AssistantPipeline
from local_agent.server import create_app

# Words laid out on the demo page (coordinates are what the fake OCR reports)
WORDS = [
    WordBox("Photosynthesis", (92, 240, 298, 265), 0.95, 1),
    WordBox("is", (308, 240, 327, 260), 0.95, 1),
    WordBox("the", (335, 240, 379, 260), 0.95, 1),
    WordBox("process.", (389, 245, 493, 265), 0.95, 1),
]
CENTER = lambda w: ((w.bbox[0] + w.bbox[2]) / 2 / 1280, (w.bbox[1] + w.bbox[3]) / 2 / 720)


class FakeOcr:
    name = "fake-ocr"

    def __init__(self, words=None, fail=False):
        self.words, self.fail = list(words if words is not None else WORDS), fail

    def read_regions(self, gray, regions):
        if self.fail:
            raise RuntimeError("ocr exploded")
        return list(self.words) if regions else []


class FakeClient:
    def __init__(self, exc=None, gate=None):
        self.calls, self.exc, self.gate = [], exc, gate

    def assist(self, word, context):
        self.calls.append((word, context))
        if self.gate:
            self.gate.wait(5)
        if self.exc:
            raise self.exc
        return AssistanceResult(word, f"{word} means something simple.", None, "aws", 120.0,
                                {"lambda_ms": 100.0, "bedrock_ms": 70.0, "polly_ms": 20.0})


def make(client=None, ocr=None, dwell=0.3, **cfg_over):
    cfg = Config()
    cfg.dwell_threshold_s, cfg.cooldown_s, cfg.capture_fps = dwell, 5.0, 30
    cfg.overlay_seconds, cfg.local_audio, cfg.detect_interval_s = 1.0, False, 0.1
    for k, v in cfg_over.items():
        setattr(cfg, k, v)
    p = AssistantPipeline(cfg)
    p.sm.error_hold_s = 0.4
    fc = client or FakeClient()
    import local_agent.pipeline as mod
    orig_ocr, orig_build = mod.create_ocr, p._build_client
    mod.create_ocr = lambda lang: ocr or FakeOcr()
    p._build_client = lambda cloud: (setattr(p, "_client", fc), setattr(p, "cloud_kind", "aws"))
    res = p.start("demo")
    mod.create_ocr = orig_ocr
    assert res["ok"], res
    return p, fc


def wait(cond, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def names(p):
    return [e["name"] for e in p.snapshot()["events"]]


@pytest.fixture
def pipes():
    made = []
    yield made
    for p in made:
        p.stop()


def test_full_loop_and_metrics(pipes):
    p, fc = make(); pipes.append(p)
    assert wait(lambda: p.snapshot()["words"])
    p.set_focus(*CENTER(WORDS[0]))
    keep = threading.Event()
    threading.Thread(target=lambda: [p.set_focus(*CENTER(WORDS[0])) or time.sleep(0.05) for _ in range(120) if not keep.is_set()], daemon=True).start()
    assert wait(lambda: "reading_resumed" in names(p), 8)
    keep.set()
    order = names(p)
    expected = ["reading_started", "text_detected", "focus_started", "dwell_threshold_reached", "stuck_word",
                "request_sent", "response_received", "word_highlighted", "reading_resumed"]
    first = [n for i, n in enumerate(order) if n in expected and n not in order[:i]]
    assert first == expected
    assert len(fc.calls) == 1                       # no duplicate request while focus stayed
    assert fc.calls[0][0] == "Photosynthesis" and fc.calls[0][1].startswith("Photosynthesis is the process")
    t = p.snapshot()["metrics"]["timings"]
    for k in ("frame_capture", "preprocess", "text_detection", "ocr", "focus_detection", "dwell_to_trigger",
              "api_roundtrip", "lambda_total", "bedrock", "polly", "apigw_overhead", "total_assistance"):
        assert k in t, k
    assert t["apigw_overhead"]["last_ms"] == pytest.approx(20.0)


def hold(p, w, secs):
    end = time.time() + secs
    while time.time() < end:
        p.set_focus(*CENTER(w)); time.sleep(0.04)


def test_low_confidence_sends_nothing(pipes):
    low = [WordBox("Photosynthesis", (92, 240, 298, 265), 0.2, 1)]
    p, fc = make(ocr=FakeOcr(low)); pipes.append(p)
    assert wait(lambda: p.snapshot()["words"])
    hold(p, low[0], 1.2)
    assert not fc.calls
    assert "stuck_word" in names(p) and "request_sent" not in names(p)
    assert p.sm.state.value in ("READING", "FOCUSING")


def test_non_word_text_is_not_focusable(pipes):
    p, fc = make(ocr=FakeOcr([WordBox("42", (92, 240, 150, 265), 0.95, 1)])); pipes.append(p)
    assert wait(lambda: p.snapshot()["words"])
    hold(p, p.latest_words()[0], 1.0)
    assert not fc.calls


def test_no_text_does_not_crash(pipes):
    p, fc = make(ocr=FakeOcr([])); pipes.append(p)
    assert wait(lambda: p.snapshot()["status"]["notice"] == "no_text")
    assert p.snapshot()["metrics"]["fps"] is None or p.snapshot()["running"]


def test_ocr_failures_reach_error_then_recover(pipes):
    ocr = FakeOcr(fail=True)
    p, fc = make(ocr=ocr, detect_interval_s=0.05); pipes.append(p)
    assert wait(lambda: p.snapshot()["status"]["state"] == "ERROR", 10)
    assert p.snapshot()["status"]["error"]["kind"] == "vision_failed"
    assert p.snapshot()["running"] and p.frame_id > 0
    ocr.fail = False
    assert wait(lambda: p.snapshot()["status"]["state"] in ("READING", "FOCUSING"), 10)


@pytest.mark.parametrize("kind", ["timeout", "network", "api_gateway", "service_error", "malformed_response"])
def test_cloud_failure_kinds_then_recovery(pipes, kind):
    fc = FakeClient(exc=CloudError(kind, "boom"))
    p, _ = make(client=fc); pipes.append(p)
    assert wait(lambda: p.snapshot()["words"])
    hold(p, WORDS[0], 1.5)
    assert wait(lambda: p.snapshot()["status"]["error"] is not None or p.sm.last_error is not None)
    assert p.sm.last_error[0] == kind
    assert p.snapshot()["metrics"]["counters"]["assist_errors"] == 1
    assert p.snapshot()["running"]
    fc.exc = None
    assert wait(lambda: p.sm.state.value in ("READING", "FOCUSING"), 5)
    p.set_focus(None, None); time.sleep(0.4)
    hold(p, WORDS[3], 1.5)                          # a different word works afterwards
    assert wait(lambda: len(fc.calls) == 2, 5)


def test_inflight_request_blocks_duplicates_and_stop_is_safe(pipes):
    gate = threading.Event()
    fc = FakeClient(gate=gate)
    p, _ = make(client=fc); pipes.append(p)
    assert wait(lambda: p.snapshot()["words"])
    hold(p, WORDS[0], 1.2)
    hold(p, WORDS[3], 1.2)                          # second word while first request in flight
    assert len(fc.calls) == 1
    p.stop(); gate.set(); time.sleep(0.2)           # late result after stop is ignored
    assert p.snapshot()["status"]["state"] == "IDLE"


def test_capture_failure_goes_to_error(pipes):
    p, fc = make(); pipes.append(p)
    def boom():
        raise CaptureError("screen gone")
    p._grabber._grab_raw = boom
    assert wait(lambda: p.snapshot()["status"]["state"] == "ERROR")
    assert p.snapshot()["status"]["error"]["kind"] == "capture_failed"


def test_start_failures(monkeypatch):
    import local_agent.pipeline as mod
    p = AssistantPipeline(Config())
    class Bad:
        def __init__(self, *a, **k): pass
        def open(self): raise CaptureError("no camera")
    monkeypatch.setattr(mod, "CameraFrameGrabber", Bad)
    assert p.start("camera")["error"]["kind"] == "camera_unavailable"
    monkeypatch.setattr(mod, "create_ocr", lambda lang: None)
    assert p.start("demo")["error"]["kind"] == "ocr_unavailable"
    monkeypatch.setattr(mod, "create_ocr", lambda lang: FakeOcr())
    cfg = Config(); cfg.api_url = ""
    assert AssistantPipeline(cfg).start("demo", cloud="aws")["error"]["kind"] == "not_configured"
    assert p.start("bogus")["error"]["kind"] == "invalid_mode"


# ---- server ------------------------------------------------------------
def test_server_endpoints(monkeypatch):
    import local_agent.pipeline as mod
    monkeypatch.setattr(mod, "create_ocr", lambda lang: FakeOcr())
    cfg = Config(); cfg.api_url = ""
    p = AssistantPipeline(cfg)
    c = TestClient(create_app(p))
    s = c.get("/api/state").json()
    for k in ("running", "status", "input", "config", "words", "focus", "assistance", "metrics", "events", "log", "demo"):
        assert k in s
    assert c.get("/api/audio/latest.mp3").status_code == 404
    assert c.post("/api/start", json={"mode": "demo", "cloud": "mock"}).json()["ok"]
    try:
        assert wait(lambda: c.get("/api/state").json()["words"])
        assert c.get("/api/frame.jpg").content[:2] == b"\xff\xd8"
        assert c.post("/api/focus", json={"x": 0.1, "y": 0.2}).json()["ok"]
        out = c.post("/api/config", json={"dwell_threshold_s": 99, "evil": 1}).json()
        assert out["config"]["dwell_threshold_s"] == 10.0 and "evil" not in out["config"]
        assert c.get("/api/state", headers={"Origin": "http://evil.example"}).status_code == 403
        assert c.get("/api/state", headers={"Origin": "http://localhost:5173"}).status_code == 200
    finally:
        assert c.post("/api/stop").json()["ok"]
    assert c.get("/api/state").json()["status"]["state"] == "IDLE"
