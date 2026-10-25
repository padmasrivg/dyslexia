"""Shared fixtures: fake grabber, OCR and cloud client, and a pipeline harness."""
from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional

import numpy as np
import pytest

from local_agent import pipeline as pipeline_mod
from local_agent.capture.base import CaptureError
from local_agent.capture.demo_source import render_sample_page
from local_agent.cloud.api_client import CloudError
from local_agent.config import Config
from local_agent.datatypes import AssistanceResult, WordBox
from local_agent.pipeline import AssistantPipeline


def wait_for(cond: Callable[[], bool], timeout: float = 8.0, step: float = 0.01) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()


def make_words(line_id: int, y1: int, texts: List[str], conf: float = 0.95, x0: int = 90, h: int = 25) -> List[WordBox]:
    out, x = [], x0
    for t in texts:
        w = max(20, 14 * len(t))
        out.append(WordBox(t, (x, y1, x + w, y1 + h), conf, line_id))
        x += w + 10
    return out


LINE1 = "Photosynthesis is the process by which green plants make food.".split()
LINE2 = "Leaves absorb sunlight and take in carbon dioxide from the air.".split()


def sample_words(conf: float = 0.95) -> List[WordBox]:
    return make_words(1, 240, LINE1, conf) + make_words(2, 332, LINE2, conf)


def center_norm(w: WordBox, size=(1280, 720)):
    return (w.bbox[0] + w.bbox[2]) / 2 / size[0], (w.bbox[1] + w.bbox[3]) / 2 / size[1]


class FakeGrabber:
    name = "demo"

    def __init__(self, image: Optional[np.ndarray] = None, fail: bool = False) -> None:
        from local_agent.datatypes import Frame
        self._Frame = Frame
        self.image = render_sample_page() if image is None else image
        self.fail = fail
        self.closed = False

    def open(self):
        return None

    def grab(self):
        if self.fail:
            raise CaptureError("fake capture failure")
        return self._Frame(image=self.image.copy(), scale=1.0, origin=(0, 0), source="demo", captured_at=time.time())

    def close(self):
        self.closed = True


class FakeOcr:
    name = "fake-ocr"

    def __init__(self, words=None, fail_times: int = 0, always_fail: bool = False) -> None:
        self.words = sample_words() if words is None else words
        self.fail_times = fail_times
        self.always_fail = always_fail
        self.calls = 0

    def read_regions(self, gray, regions):
        self.calls += 1
        if self.always_fail or self.calls <= self.fail_times:
            raise RuntimeError("fake ocr failure")
        return list(self.words)


class FakeClient:
    def __init__(self, error_kind: Optional[str] = None, block: Optional[threading.Event] = None,
                 timings=None, latency_ms: float = 400.0, audio: Optional[str] = None) -> None:
        self.error_kind = error_kind
        self.block = block
        self.calls: List[tuple] = []
        self.entered = threading.Event()
        self.finished = threading.Event()
        self.timings = timings or {}
        self.latency_ms = latency_ms
        self.audio = audio

    def assist(self, word: str, context: str) -> AssistanceResult:
        self.calls.append((word, context))
        self.entered.set()
        try:
            if self.block is not None:
                self.block.wait(10)
            if self.error_kind:
                raise CloudError(self.error_kind, f"fake {self.error_kind}")
            return AssistanceResult(word, f"{word} means something simple.", self.audio, "aws",
                                    self.latency_ms, dict(self.timings))
        finally:
            self.finished.set()


class Harness:
    def __init__(self, pipe, ocr, client, grabber):
        self.pipe, self.ocr, self.client, self.grabber = pipe, ocr, client, grabber

    def event_names(self) -> List[str]:
        return [e["name"] for e in self.pipe.snapshot()["events"]]

    def state(self) -> str:
        return self.pipe.sm.state.value

    def focus_word(self, w: WordBox) -> None:
        x, y = center_norm(w)
        self.pipe.set_focus(x, y)

    def keep_focus(self, w: WordBox, stop: threading.Event) -> threading.Thread:
        """The web pointer goes stale after 2 s; refresh it in the background."""
        def run():
            while not stop.is_set():
                self.focus_word(w)
                time.sleep(0.05)
        t = threading.Thread(target=run, daemon=True)
        t.start()
        return t


def test_config(**kw) -> Config:
    cfg = Config(api_url="", api_key="", mock_cloud=False)
    cfg.dwell_threshold_s = 0.3
    cfg.cooldown_s = 5.0
    cfg.capture_fps = 30
    cfg.overlay_seconds = 1.5
    cfg.local_audio = False
    cfg.detect_interval_s = 0.05
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


@pytest.fixture
def harness_factory(monkeypatch):
    made: List[Harness] = []

    def make(words=None, ocr: Optional[FakeOcr] = None, client: Optional[FakeClient] = None,
             grabber: Optional[FakeGrabber] = None, cfg: Optional[Config] = None, start: bool = True) -> Harness:
        ocr = ocr or FakeOcr(words)
        client = client or FakeClient()
        grabber = grabber or FakeGrabber()
        pipe = AssistantPipeline(cfg or test_config())
        monkeypatch.setattr(pipeline_mod, "create_ocr", lambda lang="eng": ocr)
        monkeypatch.setattr(pipeline_mod, "DemoFrameGrabber", lambda width=1280: grabber)

        def build(self_, cloud):
            self_._client, self_.cloud_kind, self_.cloud_reason = client, "aws", "fake"
        monkeypatch.setattr(AssistantPipeline, "_build_client", build)
        h = Harness(pipe, ocr, client, grabber)
        made.append(h)
        if start:
            res = pipe.start("demo")
            assert res == {"ok": True}, res
        return h

    yield make
    for h in made:
        h.pipe.stop()
