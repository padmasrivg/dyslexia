"""Runtime configuration for the local agent.

Every value can be overridden with an environment variable (see .env.example).
No AWS credentials are ever read here: the local agent only knows the public
API Gateway URL and an optional API key that identifies the app to the gateway.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _b(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    # Cloud
    api_url: str = field(default_factory=lambda: os.getenv("ASSIST_API_URL", "").strip())
    api_key: str = field(default_factory=lambda: os.getenv("ASSIST_API_KEY", "").strip())
    mock_cloud: bool = field(default_factory=lambda: _b("MOCK_CLOUD", True))
    connect_timeout_s: float = field(default_factory=lambda: _f("API_CONNECT_TIMEOUT_S", 3.0))
    read_timeout_s: float = field(default_factory=lambda: _f("API_READ_TIMEOUT_S", 20.0))

    # Focus and dwell
    dwell_threshold_s: float = field(default_factory=lambda: _f("DWELL_THRESHOLD_S", 1.5))
    cooldown_s: float = field(default_factory=lambda: _f("COOLDOWN_S", 6.0))
    focus_padding_px: int = field(default_factory=lambda: _i("FOCUS_PADDING_PX", 2))
    # Seconds of focus loss tolerated before the dwell timer resets (cursor jitter)
    focus_grace_s: float = field(default_factory=lambda: _f("FOCUS_GRACE_S", 0.15))

    # Vision
    frame_width: int = field(default_factory=lambda: _i("FRAME_WIDTH", 1280))
    detect_interval_s: float = field(default_factory=lambda: _f("DETECT_INTERVAL_S", 0.8))
    min_ocr_confidence: float = field(default_factory=lambda: _f("MIN_OCR_CONFIDENCE", 0.60))
    min_detect_confidence: float = field(default_factory=lambda: _f("MIN_DETECT_CONFIDENCE", 0.30))
    dbnet_model_path: str = field(default_factory=lambda: os.getenv("DBNET_MODEL", "models/dbnet.onnx"))
    ocr_lang: str = field(default_factory=lambda: os.getenv("OCR_LANG", "eng"))
    use_clahe: bool = field(default_factory=lambda: _b("USE_CLAHE", True))
    use_adaptive_threshold: bool = field(default_factory=lambda: _b("USE_ADAPTIVE_THRESHOLD", False))

    # Capture
    capture_fps: int = field(default_factory=lambda: _i("CAPTURE_FPS", 15))
    monitor_index: int = field(default_factory=lambda: _i("MONITOR_INDEX", 1))
    camera_index: int = field(default_factory=lambda: _i("CAMERA_INDEX", 0))

    # Context
    context_extra_sentences: int = field(default_factory=lambda: _i("CONTEXT_EXTRA_SENTENCES", 0))
    max_context_chars: int = field(default_factory=lambda: _i("MAX_CONTEXT_CHARS", 400))

    # Audio and server
    local_audio: bool = field(default_factory=lambda: _b("LOCAL_AUDIO", True))
    server_host: str = field(default_factory=lambda: os.getenv("AGENT_HOST", "127.0.0.1"))
    server_port: int = field(default_factory=lambda: _i("AGENT_PORT", 8765))
    # How long an explanation stays on the overlay
    overlay_seconds: float = field(default_factory=lambda: _f("OVERLAY_SECONDS", 10.0))

    @property
    def cloud_configured(self) -> bool:
        return bool(self.api_url)
