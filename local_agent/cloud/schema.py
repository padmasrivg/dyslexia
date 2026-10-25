"""Request and response validation for the /assist contract.

The same limits are enforced again inside the Lambda (backend/lambda_handler.py)
and by the API Gateway request model (backend/template.yaml). Validating on the
client first avoids a pointless network round trip.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

MAX_WORD_LEN = 64
MAX_CONTEXT_LEN = 600
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", _CONTROL.sub("", s)).strip()


def validate_assist_payload(payload: Any) -> dict:
    """Return a cleaned payload or raise ValidationError."""
    if not isinstance(payload, dict):
        raise ValidationError("invalid_payload", "payload must be a JSON object")
    word, context = payload.get("word"), payload.get("context")
    if not isinstance(word, str) or not isinstance(context, str):
        raise ValidationError("invalid_payload", "word and context must be strings")
    word, context = _clean(word), _clean(context)
    if not word:
        raise ValidationError("empty_word", "word is empty")
    if len(word) > MAX_WORD_LEN or " " in word:
        raise ValidationError("invalid_word", "word must be a single token of at most 64 characters")
    if not any(c.isalpha() for c in word):
        raise ValidationError("invalid_word", "word must contain a letter")
    if not context:
        raise ValidationError("empty_context", "context is empty")
    if len(context) > MAX_CONTEXT_LEN:
        raise ValidationError("context_too_long", "context exceeds 600 characters")
    return {"word": word, "context": context}


@dataclass
class ParsedResponse:
    word: str
    definition: str
    audio_b64: Optional[str]
    timings: dict


def parse_assist_response(body: Any) -> ParsedResponse:
    """Validate the Lambda response. Raises ValidationError on a malformed body."""
    if not isinstance(body, dict):
        raise ValidationError("malformed_response", "response is not a JSON object")
    status = body.get("status")
    if status not in ("success", "partial"):
        err = body.get("error") or {}
        code = err.get("code", "service_error") if isinstance(err, dict) else "service_error"
        msg = err.get("message", "service reported an error") if isinstance(err, dict) else "service error"
        raise ValidationError(str(code), str(msg))
    definition = body.get("definition")
    word = body.get("word")
    if not isinstance(definition, str) or not definition.strip() or not isinstance(word, str):
        raise ValidationError("malformed_response", "missing word or definition")
    # "partial" means the definition is valid but Polly failed, so audio is absent
    audio = body.get("audio")
    if audio is not None and not isinstance(audio, str):
        raise ValidationError("malformed_response", "audio must be a base64 string")
    timings = body.get("timings") if isinstance(body.get("timings"), dict) else {}
    return ParsedResponse(word=word, definition=definition.strip(), audio_b64=audio or None, timings=timings)
