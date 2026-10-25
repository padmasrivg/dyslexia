"""API client (network failure handling), vision modules, capture, focus sources, audio."""
import base64
import shutil

import cv2
import numpy as np
import pytest
import requests

from local_agent.audio.audio_player import AudioError, AudioPlayer, decode_audio
from local_agent.capture.base import CaptureError, normalise_width
from local_agent.capture.camera_capture import CameraFrameGrabber
from local_agent.capture.demo_source import DemoFrameGrabber, render_sample_page
from local_agent.cloud.api_client import AssistClient, CloudError, MockAssistClient
from local_agent.config import Config
from local_agent.datatypes import Frame
from local_agent.focus.cursor_tracker import GazeSource, WebPointerSource
from local_agent.vision.ocr import create_ocr
from local_agent.vision.preprocessing import PreprocessConfig, Preprocessor
from local_agent.vision.text_detection import ClassicalDetector, TextRegion, create_detector, detect_regions, merge_overlapping


class Resp:
    def __init__(self, status=200, body=None, text=None):
        self.status_code, self._body, self.text = status, body, text

    def json(self):
        if self._body is None:
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


GOOD = {"status": "success", "word": "plants", "definition": "Plants grow.", "audio": "QQ==", "timings": {"lambda_ms": 100}}


def client(resp=None, exc=None, key=""):
    cfg = Config(); cfg.api_url, cfg.api_key = "https://x.example/prod", key
    s = FakeSession(resp, exc)
    return AssistClient(cfg, s), s


def test_client_sends_only_word_and_context():
    c, s = client(Resp(200, GOOD), key="k1")
    r = c.assist("plants", "Plants grow.")
    assert set(s.calls[0]["json"]) == {"word", "context"}      # privacy guarantee: no frames
    assert s.calls[0]["url"] == "https://x.example/prod/assist"
    assert s.calls[0]["headers"]["x-api-key"] == "k1"
    assert isinstance(s.calls[0]["timeout"], tuple)
    assert r.source == "aws" and r.server_timings["lambda_ms"] == 100


def test_client_no_key_header_when_unset():
    c, s = client(Resp(200, GOOD))
    c.assist("plants", "Plants grow.")
    assert "x-api-key" not in s.calls[0]["headers"]


@pytest.mark.parametrize("kwargs,kind", [
    ({"exc": requests.Timeout()}, "timeout"),
    ({"exc": requests.ConnectionError()}, "network"),
    ({"resp": Resp(403, {"message": "Forbidden"})}, "api_gateway"),
    ({"resp": Resp(429, {"status": "error", "error": {"code": "service_busy", "message": "busy"}})}, "api_gateway"),
    ({"resp": Resp(502, None, "<html>")}, "api_gateway"),
    ({"resp": Resp(200, None, "oops")}, "malformed_response"),
    ({"resp": Resp(200, {"status": "error", "error": {"code": "x", "message": "m"}})}, "service_error"),
    ({"resp": Resp(200, {"status": "success", "word": "a"})}, "malformed_response"),
])
def test_client_failures(kwargs, kind):
    c, _ = client(**kwargs)
    with pytest.raises(CloudError) as e:
        c.assist("plants", "Plants grow.")
    assert e.value.kind == kind


def test_client_local_validation_and_not_configured():
    c, s = client(Resp(200, GOOD))
    with pytest.raises(CloudError) as e:
        c.assist("bad word", "ctx")
    assert e.value.kind == "invalid_request" and not s.calls
    with pytest.raises(CloudError) as e:
        c.assist("word", "")
    assert e.value.kind == "invalid_request"
    cfg = Config(); cfg.api_url = ""
    with pytest.raises(CloudError) as e:
        AssistClient(cfg).assist("word", "ctx")
    assert e.value.kind == "not_configured"


def test_mock_client_is_labelled():
    r = MockAssistClient().assist("photosynthesis", "ctx")
    assert r.source == "local-mock" and r.audio_b64 is None


# ---- vision ----------------------------------------------------------
def test_preprocessing_is_configurable():
    img = render_sample_page()
    assert "mask" not in Preprocessor(PreprocessConfig(clahe=False)).run(img)
    out = Preprocessor(PreprocessConfig(adaptive_threshold=True)).run(img)
    assert out["mask"].shape == out["gray"].shape and out["gray"].ndim == 2


def test_classical_detector_finds_lines():
    pre = Preprocessor().run(render_sample_page())
    regions = detect_regions(ClassicalDetector(), pre)
    assert len(regions) >= 4
    assert all(r.bbox[2] > r.bbox[0] and r.bbox[3] > r.bbox[1] and 0 < r.confidence <= 1 for r in regions)


def test_merge_and_factory_fallback():
    m = merge_overlapping([TextRegion((0, 0, 100, 20), 0.5), TextRegion((5, 0, 105, 20), 0.9)])
    assert len(m) == 1 and m[0].confidence == 0.9
    assert "fallback" in create_detector("models/does-not-exist.onnx").name


@pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract binary missing")
def test_ocr_reads_word_with_bbox_inside_line():
    pre = Preprocessor().run(render_sample_page())
    regions = detect_regions(ClassicalDetector(), pre)
    words = create_ocr().read_regions(pre["gray"], regions)
    hit = [w for w in words if w.text.lower().startswith("photosynthesis")]
    assert hit and hit[0].confidence > 0.6
    line = next(r for r in regions if r.bbox[1] < hit[0].bbox[1] < r.bbox[3])
    assert line.bbox[0] - 5 <= hit[0].bbox[0] and hit[0].bbox[2] <= line.bbox[2] + 5


# ---- capture / focus / audio ------------------------------------------
def test_capture_helpers(monkeypatch):
    img, scale = normalise_width(np.zeros((100, 200, 3), np.uint8), 100)
    assert img.shape[1] == 100 and scale == 0.5
    assert DemoFrameGrabber(640).grab().image.shape[1] == 640

    class Closed:
        def isOpened(self): return False
        def release(self): pass
    monkeypatch.setattr(cv2, "VideoCapture", lambda *a: Closed())
    with pytest.raises(CaptureError):
        CameraFrameGrabber(7).open()


def test_web_pointer_and_gaze():
    f = Frame(image=np.zeros((100, 200, 3), np.uint8), scale=1.0)
    p = WebPointerSource(stale_after_s=0.05)
    assert p.position(f) is None
    p.set_normalised(0.5, 0.5)
    assert p.position(f) == (100.0, 50.0)
    p.set_normalised(1.5, 0.5)
    assert p.position(f) is None
    p.set_normalised(0.1, 0.1)
    import time; time.sleep(0.08)
    assert p.position(f) is None
    with pytest.raises(NotImplementedError):
        GazeSource().position(f)


def test_audio_decode_and_player(monkeypatch):
    with pytest.raises(AudioError):
        decode_audio("%%%")
    with pytest.raises(AudioError):
        decode_audio(base64.b64encode(b"tiny").decode())
    errors = []
    monkeypatch.setattr("local_agent.audio.audio_player._player_command", lambda p: None)
    pl = AudioPlayer(on_error=errors.append)
    pl.play_b64(base64.b64encode(b"x" * 100).decode())   # returns immediately
    import time
    for _ in range(40):
        if errors: break
        time.sleep(0.05)
    assert errors and "no audio player" in errors[0]
