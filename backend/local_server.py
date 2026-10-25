"""Tiny local dev server that wraps backend/lambda_handler.py.

It converts HTTP requests into API Gateway proxy events and calls the real
handler, so the REAL Amazon Bedrock and Amazon Polly are used through whatever
AWS credentials/profile you have configured locally (AWS_PROFILE, AWS_REGION,
etc.). It is for developers only: it does NOT emulate API Gateway (no API key
check, no request model validation, no throttling) and must not be exposed to a
network. It binds to 127.0.0.1 only.

Run from the project root:
    export AWS_REGION=us-east-1
    export BEDROCK_MODEL_ID=<model id or inference profile id>
    python3 -m backend.local_server            # listens on http://127.0.0.1:9000

Then point the local agent at it:  ASSIST_API_URL=http://127.0.0.1:9000/assist
Other settings (POLLY_VOICE_ID, POLLY_ENGINE, ...) are read from the environment.
"""
from __future__ import annotations

import json
import os
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

from backend import lambda_handler as lh

HOST = "127.0.0.1"
PORT = 9000


class _Ctx:
    def __init__(self) -> None:
        self.aws_request_id = str(uuid.uuid4())


class AssistHandler(BaseHTTPRequestHandler):
    server_version = "AssistDev/1.0"

    def _send(self, result: dict) -> None:
        body = (result.get("body") or "").encode("utf-8")
        self.send_response(result["statusCode"])
        for k, v in result.get("headers", {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _invoke(self, method: str, body: str | None) -> None:
        event = {
            "httpMethod": method,
            "path": self.path,
            "headers": {k: v for k, v in self.headers.items()},
            "body": body,
            "isBase64Encoded": False,
        }
        self._send(lh.lambda_handler(event, _Ctx()))

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._invoke("OPTIONS", None)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?")[0].rstrip("/") != "/assist":
            self._send({"statusCode": 404, "headers": {"Content-Type": "application/json"},
                        "body": json.dumps({"message": "Not Found"})})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        # Read at most one byte past the handler limit so oversize bodies get a 413.
        raw = self.rfile.read(min(length, lh.MAX_BODY_BYTES + 1))
        self._invoke("POST", raw.decode("utf-8", errors="replace"))

    def log_message(self, fmt, *args) -> None:  # keep request paths only
        print("%s %s" % (self.address_string(), fmt % args))


def main() -> None:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not os.environ.get("BEDROCK_MODEL_ID"):
        print("warning: BEDROCK_MODEL_ID is not set; requests will return 500 service_misconfigured")
    with HTTPServer((HOST, PORT), AssistHandler) as srv:
        print(f"Local assist server on http://{HOST}:{PORT}/assist (real Bedrock + Polly)")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
