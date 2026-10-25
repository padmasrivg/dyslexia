"""LIVE test against a deployed stack. Skipped unless ASSIST_API_URL is set.

    export ASSIST_API_URL=https://<id>.execute-api.<region>.amazonaws.com/prod/assist
    export ASSIST_API_KEY=<api key value>
    python3 -m pytest tests/integration/test_live_aws.py -q

This calls real API Gateway, Bedrock and Polly and may incur small charges.
"""
import base64
import os

import pytest
import requests

URL = os.environ.get("ASSIST_API_URL", "").strip()
KEY = os.environ.get("ASSIST_API_KEY", "").strip()

pytestmark = pytest.mark.skipif(not URL, reason="ASSIST_API_URL not set (live AWS test)")


def _url():
    return URL if URL.rstrip("/").endswith("/assist") else URL.rstrip("/") + "/assist"


def test_live_assist_returns_definition_and_mp3():
    headers = {"Content-Type": "application/json"}
    if KEY:
        headers["x-api-key"] = KEY
    r = requests.post(_url(), headers=headers, timeout=30, json={
        "word": "photosynthesis",
        "context": "Plants use photosynthesis to make food from sunlight.",
    })
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["status"] in ("success", "partial")
    assert body["status"] == "success", f"audio unavailable: {body.get('warnings')}"
    assert 0 < len(body["definition"]) <= 240
    assert body["audio_format"] == "mp3"
    audio = base64.b64decode(body["audio"], validate=True)
    assert len(audio) > 100
    assert audio[:3] == b"ID3" or (audio[0] == 0xFF and (audio[1] & 0xE0) == 0xE0), "not MP3"
    assert {"bedrock_ms", "polly_ms", "lambda_ms"} <= set(body["timings"])
