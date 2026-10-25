"""The perception-decision-action loop.

    capture -> preprocess -> detect -> OCR -> focus -> dwell -> state machine
            -> (STUCK_WORD only) cloud request -> overlay + audio -> READING

Threads
  capture/render  grabs frames, evaluates focus and dwell on every frame,
                  draws the overlay and publishes JPEGs. Never blocks on OCR or the network.
  vision          detection + OCR, only when the picture changed. Publishes a TextMap.
  cloud           one worker; the state machine guarantees at most one request in flight.
  audio           MP3 playback in a daemon thread (see audio/audio_player.py).

Everything shown in the UI is read from `snapshot()`, which only contains
values measured or produced by this process.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple

import cv2
import numpy as np

from .agent.context import clean_word, extract_context, is_valid_word
from .agent.state_machine import AgentStateMachine, State
from .audio.audio_player import AudioError, AudioPlayer
from .capture.base import CaptureError, FrameGrabber
from .capture.camera_capture import CameraFrameGrabber
from .capture.demo_source import DemoFrameGrabber
from .capture.screen_capture import ScreenFrameGrabber
from .cloud.api_client import AssistClient, CloudError, MockAssistClient
from .cloud.schema import ValidationError, validate_assist_payload
from .config import Config
from .datatypes import AssistanceResult, Frame, TextRegion, WordBox
from .focus.cursor_tracker import FocusSource, SystemCursorSource, WebPointerSource
from .focus.dwell_engine import DwellEngine, DwellEvent, Target
from .focus.geometry import find_focused
from .metrics import Metrics
from .overlay import placeholder_frame, render_frame
from .vision.ocr import OcrEngine, create_ocr
from .vision.preprocessing import PreprocessConfig, Preprocessor
from .vision.text_detection import TextDetector, create_detector, detect_regions

MAX_REGIONS = 120


@dataclass
class TextMap:
    words: List[WordBox] = field(default_factory=list)
    regions: List[TextRegion] = field(default_factory=list)
    frame_id: int = 0


class FocusRouter(FocusSource):
    """Web pointer wins while it is fresh; otherwise the OS cursor (screen mode)."""

    def __init__(self, web: WebPointerSource, system: Optional[FocusSource]) -> None:
        self.web, self.system = web, system

    @property
    def name(self) -> str:  # type: ignore[override]
        return f"web-pointer + {self.system.name}" if self.system else "web-pointer"

    def position(self, frame: Frame):
        p = self.web.position(frame)
        if p is not None or self.system is None:
            return p
        return self.system.position(frame)


class AssistantPipeline:
    def __init__(self, cfg: Optional[Config] = None) -> None:
        self.cfg = cfg or Config()
        self.metrics = Metrics()
        self.sm = AgentStateMachine()
        self.dwell = DwellEngine(self.cfg.dwell_threshold_s, self.cfg.cooldown_s, self.cfg.focus_grace_s)
        self.web_pointer = WebPointerSource()
        self.audio = AudioPlayer(
            enabled=self.cfg.local_audio,
            on_error=lambda m: self._log("error", m, notice="audio_failed"),
            on_start=lambda: self._event("audio_played", "local player started"),
        )
        self._lock = threading.RLock()
        self._events: Deque[dict] = deque(maxlen=40)
        self._log_lines: Deque[dict] = deque(maxlen=60)
        self._event_id = 0
        self._stop = threading.Event()
        self._threads: List[threading.Thread] = []
        self._pool: Optional[ThreadPoolExecutor] = None
        self._run_id = 0
        self.running = False

        self._grabber: Optional[FrameGrabber] = None
        self._detector: Optional[TextDetector] = None
        self._ocr: Optional[OcrEngine] = None
        self._pre = Preprocessor(self._pre_cfg())
        self._focus: Optional[FocusSource] = None
        self._client = None
        self.cloud_kind, self.cloud_reason = "none", ""
        self.mode, self.simulation = "idle", False

        self._text_map = TextMap()
        self._frame_shape: Tuple[int, int] = (0, 0)
        self._pending: Optional[Tuple[int, Frame]] = None
        self._pending_evt = threading.Event()
        self._force_detect = False
        self._jpeg: Optional[bytes] = None
        self.frame_id = 0
        self._idle_jpeg = self._encode(placeholder_frame("Assistant is stopped. Choose an input to start."))

        self._focus_info: dict = {}
        self._focus_point: Optional[Tuple[float, float]] = None
        self._assistance: Optional[dict] = None
        self._latest_audio: Optional[bytes] = None
        self._last_request: Optional[dict] = None
        self._notice: Optional[str] = None
        self._notice_at = 0.0
        self._demo_running = False
        self._had_text = False
        self._sentences: list[dict] = []
        self._flip_camera_pref = False

    # ------------------------------------------------------------------ utils
    def _pre_cfg(self) -> PreprocessConfig:
        return PreprocessConfig(clahe=self.cfg.use_clahe, adaptive_threshold=self.cfg.use_adaptive_threshold)

    @staticmethod
    def _encode(img: np.ndarray, quality: int = 80) -> bytes:
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes() if ok else b""

    def _log(self, level: str, message: str, notice: Optional[str] = None) -> None:
        with self._lock:
            self._log_lines.append({"t": time.time(), "level": level, "message": message})
            if notice:
                self._notice, self._notice_at = notice, time.time()

    def _event(self, name: str, detail: str = "") -> None:
        with self._lock:
            self._event_id += 1
            self._events.append({"id": self._event_id, "t": time.time(), "name": name, "detail": detail})

    # ------------------------------------------------------------- lifecycle
    def _build_client(self, cloud: str) -> None:
        if cloud == "aws" or (cloud == "auto" and not self.cfg.mock_cloud and self.cfg.cloud_configured):
            if not self.cfg.cloud_configured:
                raise RuntimeError("ASSIST_API_URL is not set")
            self._client, self.cloud_kind, self.cloud_reason = AssistClient(self.cfg), "aws", self.cfg.api_url
        else:
            self._client, self.cloud_kind = MockAssistClient(), "mock"
            self.cloud_reason = "Offline mock mode (default, zero AWS cost)" if cloud in ("mock", "auto") else "mock selected"

    def start(self, mode: str = "demo", monitor: Optional[int] = None, camera: Optional[int] = None,
              region: Optional[Tuple[int, int, int, int]] = None, cloud: str = "mock",
              flip_camera: Optional[bool] = None) -> dict:
        if self.running:
            self.stop()
        if mode not in ("screen", "camera", "demo"):
            return {"ok": False, "error": {"kind": "invalid_mode", "message": f"unknown mode {mode!r}"}}
        try:
            if mode == "screen":
                grabber: FrameGrabber = ScreenFrameGrabber(
                    monitor if monitor is not None else self.cfg.monitor_index, region, self.cfg.frame_width)
            elif mode == "camera":
                if flip_camera is not None:
                    self._flip_camera_pref = bool(flip_camera)
                effective_flip = getattr(self, "_flip_camera_pref", False)
                grabber = CameraFrameGrabber(
                    camera if camera is not None else self.cfg.camera_index,
                    self.cfg.frame_width,
                    flip_horizontal=effective_flip,
                )
            else:
                grabber = DemoFrameGrabber(self.cfg.frame_width)
            grabber.open()
        except CaptureError as exc:
            kind = "camera_unavailable" if mode == "camera" else "screen_unavailable"
            self._log("error", f"{kind}: {exc}")
            return {"ok": False, "error": {"kind": kind, "message": str(exc)}}

        try:
            self._ocr = create_ocr(self.cfg.ocr_lang, mode=mode)
        except TypeError:
            self._ocr = create_ocr(self.cfg.ocr_lang)
        if self._ocr is None:
            grabber.close()
            msg = "No OCR engine found. Install RapidOCR or Tesseract (see README)."
            self._log("error", msg)
            return {"ok": False, "error": {"kind": "ocr_unavailable", "message": msg}}
        try:
            self._build_client(cloud)
        except RuntimeError as exc:
            grabber.close()
            return {"ok": False, "error": {"kind": "not_configured", "message": str(exc)}}

        self._detector = create_detector(self.cfg.dbnet_model_path)
        self._grabber = grabber
        self.mode, self.simulation = mode, mode == "demo"
        system = None
        if mode == "screen":
            try:
                system = SystemCursorSource()
            except RuntimeError as exc:
                self._log("warn", f"{exc}; using the web pointer only")
        self._focus = FocusRouter(self.web_pointer, system)

        self.metrics = Metrics()
        self.dwell = DwellEngine(self.cfg.dwell_threshold_s, self.cfg.cooldown_s, self.cfg.focus_grace_s)
        self._pre = Preprocessor(self._pre_cfg())
        self._text_map, self._assistance, self._latest_audio = TextMap(), None, None
        self._sentences = []
        self._last_request, self._notice, self._had_text = None, None, False
        self._events.clear()
        self._pending, self._force_detect = None, True
        self.sm.stop()
        self.sm.start()
        self._event("reading_started", mode)
        self._log("info", f"started in {mode} mode, detector: {self._detector.name}, OCR: {self._ocr.name}, cloud: {self.cloud_kind}")

        self._stop.clear()
        self._run_id += 1
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cloud")
        self.running = True
        self._threads = [
            threading.Thread(target=self._capture_loop, args=(self._run_id,), daemon=True, name="capture"),
            threading.Thread(target=self._vision_loop, args=(self._run_id,), daemon=True, name="vision"),
        ]
        for t in self._threads:
            t.start()
        return {"ok": True}

    def stop(self) -> None:
        self._stop.set()
        self._pending_evt.set()
        self.running = False
        self._run_id += 1  # invalidates in-flight cloud callbacks
        for t in self._threads:
            if t is not threading.current_thread():
                t.join(timeout=3)
        self._threads = []
        if self._pool:
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool = None
        if self._grabber:
            try:
                self._grabber.close()
            except Exception:
                pass
            finally:
                self._grabber = None
        self.audio.stop()
        self.sm.stop()
        self.mode, self.simulation = "idle", False
        with self._lock:
            self._jpeg = None
            self._text_map = TextMap()
            self._had_text = False
            self._focus_info, self._focus_point = {}, None
            self._assistance = None
        self.web_pointer.set_normalised(None, None)

    # ----------------------------------------------------------- vision loop
    def _vision_loop(self, run_id: int) -> None:
        last_small: Optional[np.ndarray] = None
        last_run = 0.0
        failures = 0
        while not self._stop.is_set() and run_id == self._run_id:
            self._pending_evt.wait(0.25)
            self._pending_evt.clear()
            pending = self._pending
            if pending is None:
                continue
            fid, frame = pending
            now = time.monotonic()
            gray_small = cv2.GaussianBlur(
                cv2.resize(cv2.cvtColor(frame.image, cv2.COLOR_BGR2GRAY), (160, 90), interpolation=cv2.INTER_AREA), (5, 5), 0)
            changed = last_small is None or float(np.mean(cv2.absdiff(gray_small, last_small))) > 1.5
            due = now - last_run >= self.cfg.detect_interval_s
            if not (self._force_detect or (changed and due)):
                if not changed:
                    self.metrics.count("ocr_skipped_static")
                continue
            self._force_detect = False
            last_small, last_run = gray_small, now
            try:
                with self.metrics.timer("preprocess"):
                    pre = self._pre.run(frame.image)
                with self.metrics.timer("text_detection"):
                    regions = detect_regions(self._detector, pre, self.cfg.min_detect_confidence)[:MAX_REGIONS]
                with self.metrics.timer("ocr"):
                    if hasattr(self._ocr, "read_with_sentences"):
                        words, sentences = self._ocr.read_with_sentences(pre["gray"], regions)
                        # If camera is horizontally mirrored and no words detected, try unflipped gray
                        if not words and self._grabber and getattr(self._grabber, "flip_horizontal", False):
                            unflipped_gray = cv2.flip(pre["gray"], 1)
                            alt_words, alt_sentences = self._ocr.read_with_sentences(unflipped_gray, None)
                            if alt_words:
                                W = pre["gray"].shape[1]
                                remapped_words = []
                                for w in alt_words:
                                    b = w.bbox
                                    remapped_bbox = (max(0, W - b[2]), b[1], min(W, W - b[0]), b[3])
                                    remapped_words.append(WordBox(text=w.text, bbox=remapped_bbox, confidence=w.confidence, line_id=w.line_id))
                                words = remapped_words
                                sentences = alt_sentences
                    else:
                        words = self._ocr.read_regions(pre["gray"], regions) if regions else []
                        sentences = []

                    if words and not sentences:
                        grouped: dict[int, list] = {}
                        for w in words:
                            lid = getattr(w, "line_id", 0)
                            grouped.setdefault(lid, []).append(w)
                        sentences = [
                            {
                                "line_id": lid,
                                "text": " ".join(w.text for w in wrds),
                                "confidence": round(sum(w.confidence for w in wrds) / max(1, len(wrds)), 3),
                                "words": [w.to_dict() for w in wrds],
                            }
                            for lid, wrds in grouped.items()
                        ]
                self.metrics.count("ocr_runs")
                failures = 0
            except Exception as exc:  # detection or OCR failure must not kill the loop
                failures += 1
                self.metrics.count("vision_errors")
                self._log("error", f"vision pass failed: {type(exc).__name__}: {exc}", notice="vision_failed")
                if failures >= 3:
                    self.sm.fail("vision_failed", "text detection or OCR keeps failing")
                    failures = 0
                self._force_detect = True  # a failed pass on a static page must be retried
                self._stop.wait(0.3)
                continue
            with self._lock:
                self._text_map = TextMap(words, regions, fid)
                self._sentences = sentences
                if not words:
                    self._notice, self._notice_at = "no_text", time.time()
                elif self._notice == "no_text":
                    self._notice = None
            if words and not self._had_text:
                self._event("text_detected", f"{len(words)} words in {len(sentences)} sentences")
            self._had_text = bool(words)

    # ---------------------------------------------------------- capture loop
    def _capture_loop(self, run_id: int) -> None:
        period = 1.0 / max(1, self.cfg.capture_fps)
        consecutive = 0
        shown_id = 0
        while not self._stop.is_set() and run_id == self._run_id:
            t_loop = time.perf_counter()
            try:
                with self.metrics.timer("frame_capture"):
                    frame = self._grabber.grab()
                consecutive = 0
            except CaptureError as exc:
                consecutive += 1
                self.metrics.count("capture_errors")
                self._log("error", f"capture failed: {exc}")
                if consecutive >= 5:
                    self.sm.fail("capture_failed", str(exc))
                self._stop.wait(0.2)
                continue
            except Exception as exc:
                self.sm.fail("capture_failed", f"{type(exc).__name__}: {exc}")
                self._stop.wait(0.5)
                continue

            self.metrics.count("frames")
            self._frame_shape = frame.image.shape[:2]
            self._pending = (self.frame_id + 1, frame)
            self._pending_evt.set()

            if self.sm.maybe_recover():
                self._event("recovered", "")
            try:
                self._tick(frame, run_id)
            except Exception as exc:  # a bug in decision logic must not stop the video
                self._log("error", f"decision step failed: {type(exc).__name__}: {exc}")

            with self.metrics.timer("render"):
                with self._lock:
                    words = self._text_map.words
                    fi = dict(self._focus_info)
                    assist = self._assistance if (self._assistance and self._assistance.get("active")) else None
                    pt = self._focus_point
                img = render_frame(
                    frame.image, words, self.cfg.min_ocr_confidence,
                    focus_bbox=fi.get("bbox"), focus_progress=fi.get("progress", 0.0),
                    assistance=assist, simulation=self.simulation, focus_point=pt,
                )
                jpeg = self._encode(img)
            with self._lock:
                self._jpeg = jpeg
                self.frame_id += 1
            self.metrics.record("frame_total", (time.perf_counter() - t_loop) * 1000.0)
            self.metrics.tick_frame()
            self._stop.wait(max(0.0, period - (time.perf_counter() - t_loop)))

    # ------------------------------------------------------------ decisions
    def _tick(self, frame: Frame, run_id: int) -> None:
        now = time.monotonic()
        with self._lock:
            tm = self._text_map
            assist = self._assistance

        # Overlay expiry: ASSISTING -> READING
        if assist and assist.get("active") and time.time() >= assist["expires_at"]:
            self._end_assistance("overlay expired")

        t0 = time.perf_counter()
        point = self._focus.position(frame) if self._focus else None
        focusable = [i for i, w in enumerate(tm.words) if is_valid_word(clean_word(w.text))]
        idx = find_focused(point, [tm.words[i].bbox for i in focusable], self.cfg.focus_padding_px)
        word = tm.words[focusable[idx]] if idx is not None else None
        self.metrics.record("focus_detection", (time.perf_counter() - t0) * 1000.0)

        # While assistance is in progress or on screen the dwell clock is paused
        accepting = self.sm.state in (State.READING, State.FOCUSING)
        target = Target(word.text, word.bbox) if (word and accepting) else None
        status = self.dwell.update(target, now)

        if status.target is not None and self.sm.state == State.READING:
            if self.sm.focus_started():
                self._event("focus_started", clean_word(status.target.text))
        elif status.target is None and self.sm.state == State.FOCUSING:
            self.sm.focus_lost()

        with self._lock:
            self._focus_point = point
            self._focus_info = {
                "word": clean_word(status.target.text) if status.target else None,
                "bbox": list(status.target.bbox) if status.target else None,
                "dwell_s": round(status.dwell_s, 3),
                "threshold_s": status.threshold_s,
                "progress": round(status.progress, 3),
                "in_cooldown": status.in_cooldown,
                "point": [round(point[0]), round(point[1])] if point else None,
            }

        if status.event == DwellEvent.STUCK and word is not None:
            self._on_stuck(word, tm, status.dwell_s, run_id)

    def _on_stuck(self, word: WordBox, tm: TextMap, dwell_s: float, run_id: int) -> None:
        self.metrics.record("dwell_to_trigger", dwell_s * 1000.0)
        self._event("dwell_threshold_reached", f"{dwell_s:.2f}s")
        if not self.sm.stuck():
            self.metrics.count("assist_blocked_duplicate")
            self._log("info", "duplicate trigger ignored by the state machine")
            return
        t_stuck = time.perf_counter()
        self._event("stuck_word", clean_word(word.text))
        self._log("info", f"STUCK_WORD: {word.text}")

        if word.confidence < self.cfg.min_ocr_confidence:
            self.sm.cancel_to_reading("low confidence")
            self._log("warn", f"OCR confidence {word.confidence:.2f} below threshold, no request sent", notice="low_confidence")
            return
        ctx = extract_context(tm.words, word, self.cfg.context_extra_sentences, self.cfg.max_context_chars)
        if ctx is None:
            self.sm.cancel_to_reading("empty text")
            self._log("warn", "no usable word text, no request sent", notice="empty_text")
            return
        try:
            payload = validate_assist_payload({"word": ctx.word, "context": ctx.context})
        except ValidationError as exc:
            self.sm.cancel_to_reading("invalid payload")
            self._log("warn", f"payload rejected locally: {exc.message}", notice=exc.code)
            return
        if not self.sm.begin_request():  # pragma: no cover - guarded by stuck()
            return
        with self._lock:
            self._last_request = {**payload, "sent_at": time.time()}
        self.metrics.count("assist_requests")
        self._event("request_sent", payload["word"])
        client, pool = self._client, self._pool
        if client is None or pool is None:
            self.sm.cancel_to_reading("stopped")
            return
        pool.submit(self._call_cloud, client, payload, tuple(word.bbox), t_stuck, run_id)

    # ----------------------------------------------------------- cloud side
    def _call_cloud(self, client, payload: dict, bbox: tuple, t_stuck: float, run_id: int) -> None:
        try:
            result = None
            from .cloud.api_client import MockAssistClient
            if isinstance(client, MockAssistClient):
                try:
                    from .cloud.gemini_client import explain_word_with_gemini
                    g_def = explain_word_with_gemini(payload["word"], payload.get("context", ""))
                    if g_def:
                        result = AssistanceResult(
                            word=payload["word"],
                            definition=g_def,
                            audio_b64=None,
                            source="inbuilt",
                            api_latency_ms=120.0,
                            server_timings={},
                        )
                except Exception:
                    result = None

            if result is None:
                result = client.assist(payload["word"], payload["context"])
        except CloudError as exc:
            self._cloud_failed(exc.kind, exc.message, run_id)
            return
        except Exception as exc:
            self._cloud_failed("service_error", f"{type(exc).__name__}", run_id)
            return
        if run_id != self._run_id:
            return
        self._cloud_ok(result, payload, bbox, t_stuck)

    def _cloud_failed(self, kind: str, message: str, run_id: int) -> None:
        if run_id != self._run_id:
            return
        self.metrics.count("assist_errors")
        self._log("error", f"assistance failed ({kind}): {message}")
        self.sm.fail(kind, message)

    def _cloud_ok(self, result: AssistanceResult, payload: dict, bbox: tuple, t_stuck: float) -> None:
        st = result.server_timings or {}
        lam = st.get("lambda_ms")
        m = self.metrics
        m.record("api_roundtrip", result.api_latency_ms)
        if isinstance(lam, (int, float)):
            m.record("lambda_total", float(lam))
            m.record("apigw_overhead", max(0.0, result.api_latency_ms - float(lam)))
        for key, name in (("bedrock_ms", "bedrock"), ("polly_ms", "polly")):
            if isinstance(st.get(key), (int, float)):
                m.record(name, float(st[key]))
        total_ms = (time.perf_counter() - t_stuck) * 1000.0
        m.record("total_assistance", total_ms)

        now = time.time()
        timings = {
            "api_roundtrip_ms": round(result.api_latency_ms, 1),
            "apigw_overhead_ms": round(max(0.0, result.api_latency_ms - float(lam)), 1) if isinstance(lam, (int, float)) else None,
            "lambda_ms": lam, "bedrock_ms": st.get("bedrock_ms"), "polly_ms": st.get("polly_ms"),
            "total_assistance_ms": round(total_ms, 1),
        }
        with self._lock:
            aid = (self._assistance or {}).get("id", 0) + 1
            self._latest_audio = None
            self._assistance = {
                "id": aid, "word": payload["word"], "context": payload["context"],
                "definition": result.definition, "source": result.source,
                "has_audio": bool(result.audio_b64), "audio_url": f"/api/audio/latest.mp3?id={aid}" if result.audio_b64 else None,
                "bbox": list(bbox), "created_at": now, "expires_at": now + self.cfg.overlay_seconds,
                "active": True, "timings": timings,
            }
        if not self.sm.assistance_ready():
            return
        self._event("response_received", f"{result.source}, {result.api_latency_ms:.0f} ms")
        self._event("word_highlighted", payload["word"])
        self._log("info", f"assistance ready ({result.source}): {result.definition}")
        if result.audio_b64:
            try:
                self.audio.play_b64(result.audio_b64)
                with self._lock:
                    self._latest_audio = self.audio.last_audio
            except AudioError as exc:
                self._log("error", f"bad audio from service: {exc}", notice="audio_failed")

    def _end_assistance(self, why: str) -> None:
        with self._lock:
            if self._assistance:
                self._assistance["active"] = False
        if self.sm.assistance_done():
            self._event("reading_resumed", why)

    # ---------------------------------------------------------- public API
    def dismiss(self) -> None:
        self.audio.stop()
        self._end_assistance("dismissed")

    def replay_audio(self) -> bool:
        data = self._latest_audio
        if not data:
            return False
        import base64

        self.audio.play_b64(base64.b64encode(data).decode())
        return True

    def latest_audio(self) -> Optional[bytes]:
        return self._latest_audio

    def set_focus(self, x: Optional[float], y: Optional[float]) -> None:
        self.web_pointer.set_normalised(x, y)

    def apply_config(self, changes: dict) -> dict:
        c = self.cfg
        if "dwell_threshold_s" in changes:
            c.dwell_threshold_s = min(10.0, max(0.3, float(changes["dwell_threshold_s"])))
            self.dwell.threshold_s = c.dwell_threshold_s
        if "cooldown_s" in changes:
            c.cooldown_s = min(60.0, max(0.0, float(changes["cooldown_s"])))
            self.dwell.cooldown_s = c.cooldown_s
        if "overlay_seconds" in changes:
            c.overlay_seconds = min(60.0, max(2.0, float(changes["overlay_seconds"])))
        for k in ("use_clahe", "use_adaptive_threshold"):
            if k in changes:
                setattr(c, k, bool(changes[k]))
                self._pre = Preprocessor(self._pre_cfg())
                self._force_detect = True
        return self.config_dict()

    def config_dict(self) -> dict:
        c = self.cfg
        return {
            "dwell_threshold_s": c.dwell_threshold_s, "cooldown_s": c.cooldown_s,
            "overlay_seconds": c.overlay_seconds, "use_clahe": c.use_clahe,
            "use_adaptive_threshold": c.use_adaptive_threshold, "min_ocr_confidence": c.min_ocr_confidence,
        }

    def frame_jpeg(self) -> bytes:
        with self._lock:
            return self._jpeg or self._idle_jpeg

    def latest_words(self) -> List[WordBox]:
        with self._lock:
            return list(self._text_map.words)

    def frame_size(self) -> Tuple[int, int]:
        h, w = self._frame_shape
        return w, h

    def set_demo_running(self, flag: bool) -> None:
        self._demo_running = flag

    def toggle_camera_flip(self) -> bool:
        from .capture.camera_capture import CameraFrameGrabber
        if isinstance(self._grabber, CameraFrameGrabber):
            flipped = self._grabber.toggle_flip()
            self._flip_camera_pref = flipped
            self._force_detect = True
            return flipped
        self._flip_camera_pref = not getattr(self, "_flip_camera_pref", False)
        return self._flip_camera_pref

    @property
    def camera_flipped(self) -> bool:
        from .capture.camera_capture import CameraFrameGrabber
        if isinstance(self._grabber, CameraFrameGrabber):
            return self._grabber.flip_horizontal
        return getattr(self, "_flip_camera_pref", False)

    def ingest_screen_frame(self, frame_bgr: np.ndarray) -> Tuple[List[WordBox], List[dict]]:
        """Ingest a live screen frame captured directly by the client browser."""
        if frame_bgr is None or frame_bgr.size == 0:
            return [], []

        if self._ocr is None:
            self._ocr = create_ocr(self.cfg.ocr_lang, mode="screen")
        if self._detector is None:
            self._detector = create_detector(self.cfg.dbnet_model_path)

        self.metrics.count("frames")
        self._frame_shape = frame_bgr.shape[:2]
        self.frame_id += 1
        fid = self.frame_id

        try:
            with self.metrics.timer("preprocess"):
                pre = self._pre.run(frame_bgr)
            with self.metrics.timer("text_detection"):
                regions = detect_regions(self._detector, pre, self.cfg.min_detect_confidence)[:MAX_REGIONS]
            with self.metrics.timer("ocr"):
                if hasattr(self._ocr, "read_with_sentences"):
                    words, sentences = self._ocr.read_with_sentences(pre["gray"], regions)
                else:
                    words = self._ocr.read_regions(pre["gray"], regions)
                    sentences = []
            self.metrics.count("ocr_runs")
        except Exception as exc:
            self._log("error", f"screen frame OCR failed: {exc}")
            words, regions, sentences = [], [], []

        with self._lock:
            self._text_map = TextMap(words, regions, fid)
            self._sentences = sentences
            self._jpeg = self._encode(frame_bgr)
            if not words:
                self._notice, self._notice_at = "no_text", time.time()
            elif self._notice == "no_text":
                self._notice = None

        if words and not self._had_text:
            self._event("text_detected", f"{len(words)} words in {len(sentences)} sentences from live screen")
        self._had_text = bool(words)
        return words, sentences

    def snapshot(self) -> dict:
        with self._lock:
            tm = self._text_map
            assist = dict(self._assistance) if self._assistance else None
            if assist and assist["active"] and time.time() >= assist["expires_at"]:
                assist["active"] = False
            notice = self._notice if time.time() - self._notice_at < 8 else None
            err = self.sm.last_error if self.sm.state == State.ERROR else None
            w, h = self.frame_size()
            words_data = [w_.to_dict() for w_ in tm.words] if self.running else []
            regions_data = [r.to_dict() for r in tm.regions] if self.running else []
            return {
                "server_time": time.time(),
                "running": self.running,
                "status": {
                    "state": self.sm.state.value, "label": self.sm.label,
                    "error": {"kind": err[0], "message": err[1]} if err else None,
                    "notice": notice,
                },
                "input": {
                    "mode": self.mode, "simulation": self.simulation,
                    "frame": {"width": w, "height": h},
                    "detector": self._detector.name if self._detector else None,
                    "ocr": self._ocr.name if self._ocr else None,
                    "focus_source": self._focus.name if self._focus else None,
                    "cloud": self.cloud_kind, "cloud_reason": self.cloud_reason,
                    "audio_player": self.audio.available(),
                },
                "config": self.config_dict(),
                "words": words_data,
                "regions": regions_data,
                "sentences": list(self._sentences) if self.running and hasattr(self, "_sentences") and self._sentences else [],
                "camera_flipped": self.camera_flipped,
                "focus": dict(self._focus_info) if self._focus_info else {
                    "word": None, "bbox": None, "dwell_s": 0.0, "threshold_s": self.cfg.dwell_threshold_s,
                    "progress": 0.0, "in_cooldown": False, "point": None},
                "assistance": assist,
                "last_request": dict(self._last_request) if self._last_request else None,
                "demo": {"running": self._demo_running},
                "metrics": self.metrics.snapshot(),
                "events": list(self._events),
                "log": list(self._log_lines)[-25:],
            }
