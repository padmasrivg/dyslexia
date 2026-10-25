import pytest

from local_agent.cloud.schema import ValidationError, parse_assist_response, validate_assist_payload


def err(payload):
    with pytest.raises(ValidationError) as ei:
        validate_assist_payload(payload)
    return ei.value.code


def test_valid():
    assert validate_assist_payload({"word": "plants", "context": "Green plants."}) == {
        "word": "plants", "context": "Green plants."}


def test_trim_collapse_and_control_chars():
    out = validate_assist_payload({"word": "  pla\x00nts \n", "context": "a \t b\x07\n\n c\x7f "})
    assert out == {"word": "plants", "context": "a b c"}


def test_rejections():
    assert err({"word": "", "context": "x"}) == "empty_word"
    assert err({"word": " \x00 ", "context": "x"}) == "empty_word"
    assert err({"word": "two words", "context": "x"}) == "invalid_word"
    assert err({"word": "1234", "context": "x"}) == "invalid_word"
    assert err({"word": "a" * 65, "context": "x"}) == "invalid_word"
    assert err({"word": "word", "context": "  "}) == "empty_context"
    assert err({"word": "word", "context": "x" * 601}) == "context_too_long"
    assert err(["word"]) == "invalid_payload"
    assert err("word") == "invalid_payload"
    assert err({"word": 5, "context": "x"}) == "invalid_payload"
    assert err({"word": "w", "context": None}) == "invalid_payload"
    assert err({"word": "w"}) == "invalid_payload"


def test_limits_are_inclusive():
    assert validate_assist_payload({"word": "a" * 64, "context": "x" * 600})


def test_parse_success_and_partial():
    p = parse_assist_response({"status": "success", "word": "w", "definition": " d ", "audio": "QUJD",
                               "timings": {"lambda_ms": 5}})
    assert (p.word, p.definition, p.audio_b64, p.timings) == ("w", "d", "QUJD", {"lambda_ms": 5})
    p = parse_assist_response({"status": "partial", "word": "w", "definition": "d", "audio": None})
    assert p.audio_b64 is None and p.timings == {}


def test_parse_error_status():
    with pytest.raises(ValidationError) as ei:
        parse_assist_response({"status": "error", "error": {"code": "bedrock_failed", "message": "boom"}})
    assert ei.value.code == "bedrock_failed" and ei.value.message == "boom"
    with pytest.raises(ValidationError) as ei:
        parse_assist_response({"status": "error"})
    assert ei.value.code == "service_error"


@pytest.mark.parametrize("body", [
    {"status": "success", "word": "w"},
    {"status": "success", "word": "w", "definition": "  "},
    {"status": "success", "definition": "d"},
    {"status": "success", "word": "w", "definition": "d", "audio": 12},
    [], "x", None,
])
def test_parse_malformed(body):
    with pytest.raises(ValidationError) as ei:
        parse_assist_response(body)
    assert ei.value.code == "malformed_response"
