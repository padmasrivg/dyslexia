"""Entry point.

    python -m local_agent.main                       serve the API (and the built UI if present)
    python -m local_agent.main --mode demo           also start the demo input immediately
    python -m local_agent.main --headless --mode demo --seconds 40
                                                     run the whole loop without any UI and
                                                     print the real events and timings as JSON
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Silence OpenCV internal C++ warnings (especially MSMF error spam on Windows)
os.environ.setdefault("OPENCV_LOG_LEVEL", "OFF")
os.environ.setdefault("OPENCV_VIDEOIO_PRIORITY_MSMF", "0")
try:
    import cv2
    cv2.setLogLevel(cv2.LOG_LEVEL_ERROR)
except Exception:
    pass


def load_env_file(path: Path) -> None:
    """Minimal .env reader. Existing environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def run_headless(mode: str, seconds: float, cloud: str) -> int:
    from .config import Config
    from .demo import run_demo_sweep
    from .pipeline import AssistantPipeline

    pipe = AssistantPipeline(Config())
    res = pipe.start(mode, cloud=cloud)
    if not res["ok"]:
        print(json.dumps(res, indent=2))
        return 2
    ok = False
    try:
        if mode == "demo":
            th = threading.Thread(target=lambda: globals().__setitem__("_ok", run_demo_sweep(pipe, timeout_s=seconds)))
            th.start()
            th.join(seconds)
            ok = bool(globals().get("_ok"))
            time.sleep(pipe.cfg.overlay_seconds + 0.5 if ok else 0.5)
        else:
            time.sleep(seconds)
    finally:
        snap = pipe.snapshot()
        pipe.stop()
    print(json.dumps({
        "assistance_produced": ok, "input": snap["input"], "status": snap["status"],
        "assistance": snap["assistance"], "events": [e["name"] for e in snap["events"]],
        "metrics": snap["metrics"], "log": snap["log"][-8:],
    }, indent=2, default=str))
    return 0 if (ok or mode != "demo") else 1


def main(argv=None) -> int:
    load_env_file(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Dyslexia Agentic Vision Assistant, local agent")
    ap.add_argument("--mode", choices=["screen", "camera", "demo"], help="start this input immediately")
    ap.add_argument("--cloud", choices=["auto", "aws", "mock"], default="mock")
    ap.add_argument("--headless", action="store_true", help="no server, print results as JSON")
    ap.add_argument("--seconds", type=float, default=40.0)
    args = ap.parse_args(argv)

    if args.headless:
        return run_headless(args.mode or "demo", args.seconds, args.cloud)

    import uvicorn

    from .config import Config
    from .pipeline import AssistantPipeline
    from .server import create_app

    cfg = Config()
    pipe = AssistantPipeline(cfg)
    app = create_app(pipe, ROOT / "frontend" / "dist")
    if args.mode:
        print(json.dumps(pipe.start(args.mode, cloud=args.cloud)))
    print(f"Local agent on http://{cfg.server_host}:{cfg.server_port}  (cloud: {'AWS' if cfg.cloud_configured else 'not configured, mock available'})")
    uvicorn.run(app, host=cfg.server_host, port=cfg.server_port, log_level="warning")
    pipe.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
