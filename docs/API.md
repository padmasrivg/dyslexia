# Local agent API

The Python local agent (`python -m local_agent.main`) serves a small HTTP API on
`http://127.0.0.1:8765`. The React interface is a client of this API. The
computer-vision pipeline never depends on the UI: it runs the same with or
without a browser attached.

All JSON responses use `Content-Type: application/json`. Times are seconds
unless the name ends in `_ms`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/state` | Full snapshot, poll every 150 to 250 ms |
| GET | `/api/stream` | `multipart/x-mixed-replace` MJPEG of the annotated frame |
| GET | `/api/frame.jpg` | Single latest annotated frame (JPEG) |
| POST | `/api/start` | Start the pipeline |
| POST | `/api/stop` | Stop the pipeline |
| POST | `/api/focus` | Report the pointer position inside the frame |
| POST | `/api/config` | Change thresholds while running |
| POST | `/api/demo/run` | Scripted pointer sweep for the demo (simulation of the pointer only) |
| GET | `/api/devices` | Monitors and cameras the agent can open |
| GET | `/api/audio/latest.mp3` | Latest Polly audio (404 when none) |
| POST | `/api/audio/replay` | Replay latest audio through the local player |
| POST | `/api/assist/dismiss` | Hide the current explanation and return to READING |

### POST /api/start

```json
{
  "mode": "demo",
  "monitor": 1,
  "camera": 0,
  "region": [0, 0, 1280, 720],
  "cloud": "auto"
}
```

* `mode`: `screen`, `camera` or `demo`. `demo` renders a prepared reading page
  and is always labelled simulation. Detection and OCR still run for real on its pixels.
* `monitor`, `camera`, `region` (left, top, width, height in desktop pixels): optional.
* `cloud`: `auto` (AWS when `ASSIST_API_URL` is set, else mock), `aws`, `mock`.
  Mock never calls AWS and returns no audio.

Returns `{ "ok": true }` or `{ "ok": false, "error": { "kind": "...", "message": "..." } }` (HTTP 200 for
expected failures such as `camera_unavailable`, so the UI can show the message).

### POST /api/focus

`{ "x": 0.42, "y": 0.31 }` normalised to the frame (0..1), or `{ "x": null, "y": null }` when the pointer
leaves the frame. Send at most every 30 ms.

### POST /api/config

Any of `dwell_threshold_s`, `cooldown_s`, `overlay_seconds`, `use_clahe`, `use_adaptive_threshold`.

### POST /api/demo/run

Moves the focus point along the first text line to the word `Photosynthesis`
and holds it there. Only the pointer movement is scripted. The dwell timer,
state machine, AWS request, Bedrock, Polly and overlay are the real pipeline.
Valid in any mode where the focus source is the web pointer (demo mode).

## GET /api/state

```json
{
  "server_time": 1767890000.12,
  "running": true,
  "status": {
    "state": "FOCUSING",
    "label": "FOCUS DETECTED",
    "error": null,
    "notice": null
  },
  "input": {
    "mode": "demo",
    "simulation": true,
    "frame": { "width": 1280, "height": 720 },
    "detector": "classical-morphology (fallback, no DBNet model loaded)",
    "ocr": "tesseract",
    "focus_source": "web-pointer",
    "cloud": "mock",
    "cloud_reason": "ASSIST_API_URL is not set",
    "audio_player": true
  },
  "config": {
    "dwell_threshold_s": 1.5,
    "cooldown_s": 6.0,
    "overlay_seconds": 10.0,
    "use_clahe": true,
    "use_adaptive_threshold": false,
    "min_ocr_confidence": 0.6
  },
  "words": [
    { "text": "Photosynthesis", "bbox": [90, 258, 300, 290], "confidence": 0.93, "line_id": 1 }
  ],
  "regions": [ { "bbox": [88, 250, 1100, 296], "confidence": 0.9 } ],
  "focus": {
    "word": "Photosynthesis",
    "bbox": [90, 258, 300, 290],
    "dwell_s": 0.8,
    "threshold_s": 1.5,
    "progress": 0.53,
    "in_cooldown": false,
    "point": [140, 270]
  },
  "assistance": {
    "id": 3,
    "word": "Photosynthesis",
    "context": "Photosynthesis is the process by which green plants make food.",
    "definition": "Photosynthesis is how plants use sunlight to make their food.",
    "source": "aws",
    "has_audio": true,
    "audio_url": "/api/audio/latest.mp3?id=3",
    "bbox": [90, 258, 300, 290],
    "created_at": 1767890001.2,
    "expires_at": 1767890011.2,
    "active": true,
    "timings": {
      "api_roundtrip_ms": 1432.1,
      "apigw_overhead_ms": 210.4,
      "lambda_ms": 1180.0,
      "bedrock_ms": 760.2,
      "polly_ms": 390.8,
      "total_assistance_ms": 1500.0
    }
  },
  "demo": { "running": false },
  "last_request": { "word": "Photosynthesis", "context": "Photosynthesis is ...", "sent_at": 1767890000.1 },
  "metrics": {
    "fps": 14.6,
    "timings": {
      "frame_capture": { "last_ms": 4.1, "avg_ms": 4.0, "max_ms": 9.2, "samples": 60 }
    },
    "counters": { "frames": 812, "ocr_runs": 3, "ocr_skipped_static": 120, "assist_requests": 1, "assist_errors": 0 }
  },
  "events": [ { "id": 17, "t": 1767890000.1, "name": "stuck_word", "detail": "Photosynthesis" } ],
  "log": [ { "t": 1767890000.1, "level": "info", "message": "STUCK_WORD: Photosynthesis" } ]
}
```

Notes

* `status.state` is one of `IDLE READING FOCUSING STUCK_WORD REQUESTING_ASSISTANCE ASSISTING ERROR`.
  `status.label` is the plain-text label for display: `READY`, `READING`, `FOCUS DETECTED`, `ANALYZING`,
  `ASSISTANCE READY`, `ERROR`.
* `status.error` is `{ "kind": "...", "message": "..." }` while in ERROR, otherwise null.
  `status.notice` is a non-fatal message (for example `low_confidence` or `no_text`).
* `input.cloud` is `aws`, `mock` or `none`. When it is `mock`, the interface must say so wherever the
  explanation is shown. `assistance.source` is `aws` or `local-mock`.
* `metrics.timings` keys (all recorded with `time.perf_counter`, nothing invented):
  `frame_capture`, `preprocess`, `text_detection`, `ocr`, `focus_detection`, `dwell_to_trigger`,
  `render`, `frame_total`, `api_roundtrip`, `apigw_overhead`, `lambda_total`, `bedrock`, `polly`,
  `total_assistance`. A key is absent until it has at least one sample. `apigw_overhead` is derived
  (round trip minus Lambda time) and includes network time.
* `metrics.counters` keys: `frames`, `ocr_runs`, `ocr_skipped_static`, `assist_requests`, `assist_errors`,
  `assist_blocked_duplicate`, `capture_errors`.
* `events[].name` values in demo order: `reading_started`, `text_detected`, `focus_started`,
  `dwell_threshold_reached`, `stuck_word`, `request_sent`, `response_received`, `word_highlighted`,
  `audio_played`, `reading_resumed`. Only the last 40 events are kept.
* `assistance` is null before the first assistance. `active` is false once the overlay expired.
