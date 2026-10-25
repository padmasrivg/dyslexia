# Dyslexia Agentic Vision Assistant

OpenCV AI Competition 2026 project. A local computer-vision agent watches a screen or a camera, reads the text,
notices when a learner stays on one word for 1.5 seconds, sends only that word and its sentence to AWS, and shows and speaks a
one-sentence explanation written for a reader with dyslexia.

```
Camera / Screen -> OpenCV preprocessing -> Text detection (DBNet ONNX or classical fallback) -> OCR (Tesseract)
-> Focus tracking (cursor) -> Dwell engine (1.5 s) -> STUCK_WORD -> API Gateway -> Lambda
-> Bedrock (Claude) + Polly -> local overlay (cv2.rectangle + text) and audio -> READING
```

## What is implemented and what is not

| Component | Status |
|---|---|
| Screen capture (MSS, monitor or region), camera (`cv2.VideoCapture`), prepared demo page | Implemented. Demo input is labelled SIMULATION everywhere. |
| Preprocessing: resize, grayscale, CLAHE, adaptive threshold, each switchable; benchmark with `python -m local_agent.vision.preprocessing --bench` | Implemented |
| Text detection | `DBNetDetector` (cv2.dnn, needs an ONNX file, none bundled, see `models/README.md`) and a classical morphology fallback. The active one is reported in the UI. |
| OCR | Tesseract through pytesseract, word boxes mapped back to frame coordinates, lines read in parallel |
| Focus tracking | OS cursor (pynput) and a web pointer from the UI. `FocusSource` is the seam for gaze; `GazeSource` is a stub that raises. Eye tracking is not implemented. |
| Dwell engine, state machine (IDLE, READING, FOCUSING, STUCK_WORD, REQUESTING_ASSISTANCE, ASSISTING, ERROR), duplicate-request guard, cooldown | Implemented and tested |
| Context extraction (word, sentence, optional neighbours; heading and column aware) | Implemented |
| AWS: API Gateway REST + Lambda + Bedrock Converse + Polly, IAM role, CloudWatch logs and alarms (`backend/template.yaml`) | Written and cfn-lint clean. **Not deployed or run against real AWS in this build**, so Bedrock access, the IAM role and Polly neural support are unverified. |
| Offline mock cloud (`MOCK_CLOUD=1` or choose Mock) | Canned text, no audio, tagged `local-mock` and labelled MOCK in the UI |
| React + Vite + Tailwind interface (Dashboard, Live Assistant, Diagnostics, Privacy and data flow) | Implemented, served by the agent from `frontend/dist` |
| Metrics (capture, preprocess, detection, OCR, focus, dwell, API round trip, derived gateway overhead, Lambda, Bedrock, Polly, total, FPS) | Measured with `perf_counter` in this process or returned by the Lambda. Nothing is pre-filled. |

Design notes: Haikei, Watermelon UI and Manus were not used. The header wave is a hand-written flat SVG in the style of Haikei
layered waves, and the motion uses the `motion` library in the style of Motion Primitives.

## Quick start (no AWS needed)

```bash
sudo apt install tesseract-ocr            # macOS: brew install tesseract
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
(cd frontend && npm install && npm run build)
python -m local_agent.main                # then open http://127.0.0.1:8765
```
Choose Demo simulation, Cloud: Mock, Start, then Run guided demo. Headless check without any UI:
`python -m local_agent.main --headless --mode demo --cloud mock` prints the real events and timings as JSON.

Frontend development: `cd frontend && npm run dev` (port 5173, proxies `/api` to the agent).

## With AWS

1. Deploy `backend/` (see `backend/README.md`): choose a Bedrock model available in your region, enable access, `sam build && sam deploy --guided`.
2. Copy `.env.example` to `.env`, set `ASSIST_API_URL` and `ASSIST_API_KEY`. No AWS credentials go in the local app.
3. Start the agent and pick Cloud: Auto or AWS.

## Using screen and camera modes

* Screen: captures a monitor or region. Put the reading material on another monitor or select a region, otherwise the agent reads its own UI. The real mouse pointer is the focus source.
* Camera: the page is shown in the Live view and you point at it with the mouse or the Previous and Next word buttons. Printed text must be sharp and well lit; OCR quality depends on it.
* Large pages with many lines take longer to OCR. OCR runs only when the picture changes, and the video loop never waits for it.

## Tests

`python -m pytest` runs 200+ tests: geometry, dwell, state machine, schema, context, client failures, vision, pipeline flow and failure paths,
the local API, the Lambda handler with stubbed AWS clients, and a local contract integration test through the real client.
`tests/integration/test_live_aws.py` runs against a deployed stack when `ASSIST_API_URL` is set and is skipped otherwise.
The live AWS test has not been run.

## Layout

`local_agent/` vision, focus, agent, cloud client, audio, pipeline, API server. `backend/` Lambda and SAM template. `frontend/` React app.
`docs/` API contract, privacy, demo script. `models/` optional DBNet ONNX. `tests/`.
Privacy details: `docs/PRIVACY.md`. Local API contract: `docs/API.md`.

## Known limits

Tesseract needs reasonable print size; handwriting and stylised fonts will fail and show as low confidence. Reading order across complex multi-column layouts is approximate.
The classical fallback detector assumes dark text on a plain background. Gaze tracking is future work.
