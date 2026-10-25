"""Local HTTP API used by the React interface (see docs/API.md).

Binds to 127.0.0.1 by default. Because it can start screen capture, requests
that carry an Origin header are only accepted from the allowed UI origins.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Optional

import cv2
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

class CloudConfigBody(BaseModel):
    api_url: str
    api_key: str = ""

from .demo import start_demo_thread
from .pipeline import AssistantPipeline

DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


class StartBody(BaseModel):
    mode: str = "demo"
    monitor: Optional[int] = None
    camera: Optional[int] = None
    region: Optional[list[int]] = Field(default=None, min_length=4, max_length=4)
    cloud: str = "mock"
    flip_camera: bool = False


class ScreenFrameBody(BaseModel):
    image: str


class FocusBody(BaseModel):
    x: Optional[float] = None
    y: Optional[float] = None



def create_app(pipeline: AssistantPipeline, static_dir: Optional[Path] = None) -> FastAPI:
    app = FastAPI(title="Dyslexia Vision Assistant, local agent", docs_url=None, redoc_url=None)
    cfg = pipeline.cfg
    own = [f"http://{cfg.server_host}:{cfg.server_port}", f"http://localhost:{cfg.server_port}"]
    allowed = set(DEV_ORIGINS + own)

    app.add_middleware(CORSMiddleware, allow_origins=DEV_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and origin not in allowed:
            return JSONResponse({"ok": False, "error": {"kind": "forbidden_origin", "message": "origin not allowed"}}, status_code=403)
        return await call_next(request)

    @app.get("/api/state")
    def state() -> dict:
        return pipeline.snapshot()

    @app.get("/api/frame.jpg")
    def frame() -> Response:
        return Response(pipeline.frame_jpeg(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/stream")
    async def stream() -> StreamingResponse:
        async def gen():
            last = -1
            idle_sent = 0
            while True:
                fid = pipeline.frame_id
                if fid != last or (not pipeline.running and idle_sent < 1):
                    last = fid
                    idle_sent += 0 if pipeline.running else 1
                    data = pipeline.frame_jpeg()
                    yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(data)).encode() + b"\r\n\r\n" + data + b"\r\n"
                if pipeline.running:
                    idle_sent = 0
                await asyncio.sleep(0.03)

        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame", headers={"Cache-Control": "no-store"})

    @app.post("/api/start")
    def start(body: StartBody) -> dict:
        region = tuple(body.region) if body.region else None
        return pipeline.start(body.mode, body.monitor, body.camera, region, body.cloud, flip_camera=body.flip_camera)  # type: ignore[arg-type]

    @app.post("/api/stop")
    def stop() -> dict:
        pipeline.stop()
        return {"ok": True}

    @app.post("/api/camera/flip")
    def toggle_camera_flip() -> dict:
        flipped = pipeline.toggle_camera_flip()
        return {"ok": True, "flipped": flipped}

    @app.post("/api/screen/frame")
    def screen_frame(body: ScreenFrameBody) -> dict:
        import base64
        import numpy as np
        raw = body.image
        if "," in raw:
            raw = raw.split(",", 1)[1]
        try:
            buf = base64.b64decode(raw)
            nparr = np.frombuffer(buf, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception as exc:
            return {"ok": False, "error": f"invalid image: {exc}"}
        if img is None:
            return {"ok": False, "error": "could not decode image"}
        words, sentences = pipeline.ingest_screen_frame(img)
        return {"ok": True, "words": [w.to_dict() for w in words], "sentences": sentences}


    @app.post("/api/focus")
    def focus(body: FocusBody) -> dict:
        pipeline.set_focus(body.x, body.y)
        return {"ok": True}

    @app.post("/api/config")
    def config(body: dict[str, Any]) -> dict:
        allowed_keys = {"dwell_threshold_s", "cooldown_s", "overlay_seconds", "use_clahe", "use_adaptive_threshold"}
        try:
            return {"ok": True, "config": pipeline.apply_config({k: v for k, v in body.items() if k in allowed_keys})}
        except (TypeError, ValueError):
            return {"ok": False, "error": {"kind": "invalid_config", "message": "values must be numbers or booleans"}}

    @app.post("/api/cloud/config")
    def set_cloud_config(body: CloudConfigBody) -> dict:
        pipeline.cfg.api_url = body.api_url.strip()
        pipeline.cfg.api_key = body.api_key.strip()
        root = Path(__file__).resolve().parent.parent
        try:
            env_path = root / ".env"
            lines = []
            if env_path.is_file():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if not line.startswith("ASSIST_API_URL=") and not line.startswith("ASSIST_API_KEY="):
                        lines.append(line)
            lines.append(f"ASSIST_API_URL={body.api_url.strip()}")
            if body.api_key.strip():
                lines.append(f"ASSIST_API_KEY={body.api_key.strip()}")
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            pass
        return {"ok": True, "api_url": pipeline.cfg.api_url}

    @app.get("/api/cloud/mode")
    def get_cloud_mode() -> dict:
        return {
            "ok": True,
            "mode": "mock" if pipeline.cfg.mock_cloud else ("aws" if pipeline.cfg.cloud_configured else "auto"),
            "cloud": pipeline.cloud_kind,
            "configured": pipeline.cfg.cloud_configured,
            "mock_default": True,
        }

    @app.post("/api/cloud/mode")
    def set_cloud_mode(body: dict[str, Any]) -> dict:
        mode = str(body.get("mode", "mock")).lower()
        if mode not in ("mock", "aws", "auto"):
            return {"ok": False, "error": {"kind": "invalid_mode", "message": "mode must be mock, aws, or auto"}}
        pipeline.cfg.mock_cloud = (mode == "mock")
        if pipeline.running:
            pipeline._build_client(mode)
        return {"ok": True, "mode": mode, "cloud": pipeline.cloud_kind}

    @app.post("/api/pdf/extract")
    async def extract_pdf(file: UploadFile = File(...)) -> dict:
        try:
            import io
            from pypdf import PdfReader
            contents = await file.read()
            reader = PdfReader(io.BytesIO(contents))
            pages_text = []
            for p in reader.pages:
                t = p.extract_text()
                if t:
                    pages_text.append(t)
            full_text = "\n\n".join(pages_text).strip()
            return {"ok": True, "text": full_text, "pages": len(reader.pages)}
        except Exception as e:
            return {"ok": False, "error": {"kind": "pdf_read_error", "message": str(e)}}

    @app.post("/api/demo/run")
    def demo_run() -> dict:
        if not pipeline.running:
            return {"ok": False, "error": {"kind": "not_running", "message": "Start the assistant first"}}
        if start_demo_thread(pipeline) is None:
            return {"ok": False, "error": {"kind": "demo_busy", "message": "A demo run is already in progress"}}
        return {"ok": True}

    @app.get("/api/devices")
    def devices(probe_cameras: bool = False) -> dict:
        from .capture.screen_capture import ScreenFrameGrabber

        try:
            monitors = [
                {"index": i, "left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}
                for i, m in enumerate(ScreenFrameGrabber.list_monitors())
            ]
        except Exception:
            monitors = []
        cams: list[dict] = []
        if probe_cameras:
            import sys
            for i in range(4):
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(i)
                if cap.isOpened():
                    cams.append({"index": i})
                cap.release()
        return {"monitors": monitors, "cameras": cams, "cameras_probed": probe_cameras}

    @app.get("/api/audio/latest.mp3")
    def audio() -> Response:
        data = pipeline.latest_audio()
        if not data:
            return JSONResponse({"ok": False, "error": {"kind": "no_audio", "message": "No audio available"}}, status_code=404)
        return Response(data, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})

    @app.post("/api/audio/replay")
    def replay() -> dict:
        return {"ok": pipeline.replay_audio()}

    @app.post("/api/assist/dismiss")
    def dismiss() -> dict:
        pipeline.dismiss()
        return {"ok": True}

    @app.get("/api/gemini/config")
    def get_gemini_config() -> dict:
        from .cloud.gemini_client import get_gemini_api_key
        key = get_gemini_api_key()
        return {
            "ok": True,
            "configured": bool(key),
            "masked_key": (key[:4] + "..." + key[-4:]) if len(key) >= 10 else ("configured" if key else "")
        }

    @app.post("/api/gemini/config")
    def set_gemini_config(body: dict[str, Any]) -> dict:
        key = str(body.get("api_key", "")).strip()
        os.environ["GEMINI_API_KEY"] = key
        root = Path(__file__).resolve().parent.parent
        try:
            env_path = root / ".env"
            lines = []
            if env_path.is_file():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if not line.startswith("GEMINI_API_KEY="):
                        lines.append(line)
            if key:
                lines.append(f"GEMINI_API_KEY={key}")
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            pass
        return {"ok": True, "configured": bool(key)}

    @app.get("/api/explain/{word}")
    def get_word_explanation(word: str, context: str = "") -> dict:
        w = word.strip().strip(".,;:!?()[]{}\"'")
        # 1. First attempt: Inbuilt Gemini AI explanation (with context)
        try:
            from .cloud.gemini_client import explain_word_with_gemini
            gemini_explanation = explain_word_with_gemini(w, context)
            if gemini_explanation:
                return {
                    "ok": True,
                    "word": w,
                    "definition": gemini_explanation,
                    "source": "gemini",
                }
        except Exception:
            pass

        # 2. Second attempt: Local glossary dictionary / assist client
        try:
            from .cloud.api_client import MockAssistClient
            client = getattr(pipeline, "_client", None) or MockAssistClient()
            res = client.assist(w, context)
            clean_def = res.definition.replace("(Mock) ", "").strip()
            return {
                "ok": True,
                "word": res.word,
                "definition": clean_def,
                "source": "glossary",
            }
        except Exception:
            return {
                "ok": True,
                "word": w,
                "definition": f"{w.capitalize()} is an important word used in this sentence to describe the topic.",
                "source": "fallback",
            }

    if static_dir and static_dir.is_dir() and (static_dir / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets") if (static_dir / "assets").is_dir() else None

        @app.get("/{path:path}")
        def spa(path: str) -> Response:
            candidate = (static_dir / path).resolve()
            if path and candidate.is_file() and static_dir.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(
                static_dir / "index.html",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
            )

    return app
