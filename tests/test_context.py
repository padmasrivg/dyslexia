from local_agent.agent.context import clean_word, extract_context
from local_agent.datatypes import WordBox
from tests.conftest import LINE1, LINE2, make_words


def find(words, text):
    return next(w for w in words if w.text == text)


def page():
    title = make_words(0, 100, ["Plants", "and", "Light"], h=40)
    l1 = make_words(1, 240, LINE1)
    l2 = make_words(2, 332, LINE2)
    return title + l1 + l2


def test_first_sentence():
    ws = page()
    c = extract_context(ws, find(ws, "Photosynthesis"))
    assert c.word == "Photosynthesis"
    assert c.context == " ".join(LINE1)


def test_mid_sentence_word():
    ws = page()
    c = extract_context(ws, find(ws, "green"))
    assert c.word == "green" and c.context == " ".join(LINE1)


def test_sentence_spanning_two_lines():
    l1 = make_words(1, 240, "Chlorophyll gives leaves their green colour".split())
    l2 = make_words(2, 332, "and captures energy. Next one.".split())
    ws = l1 + l2
    c = extract_context(ws, find(ws, "green"))
    assert c.context == "Chlorophyll gives leaves their green colour and captures energy."
    c = extract_context(ws, find(ws, "captures"))
    assert c.context == c.context and c.context.startswith("Chlorophyll")


def test_heading_not_merged():
    ws = page()
    c = extract_context(ws, find(ws, "Photosynthesis"))
    assert "Plants" not in c.context
    c = extract_context(ws, find(ws, "Light"))
    assert c.context == "Plants and Light"


def test_two_columns_do_not_mix():
    left = make_words(1, 240, "Left column words here without end".split(), x0=90)
    right = make_words(2, 240, "Right column words are here".split(), x0=800)
    ws = left + right
    c = extract_context(ws, find(ws, "column"))
    assert "Right" not in c.context
    c = extract_context(ws, find(ws, "are"))
    assert "Left" not in c.context


def test_extra_sentences():
    ws = page()
    plain = extract_context(ws, find(ws, "Photosynthesis"), extra_sentences=0)
    more = extract_context(ws, find(ws, "Photosynthesis"), extra_sentences=1)
    assert len(more.context) > len(plain.context)
    assert more.context.endswith("the air.")


def test_max_chars_keeps_word():
    words = make_words(1, 240, ["alpha"] * 30 + ["Zebra"] + ["omega"] * 30 + ["end."])
    c = extract_context(words, find(words, "Zebra"), max_chars=80)
    assert len(c.context) <= 80 and "Zebra" in c.context


def test_punctuation_stripped():
    ws = [WordBox("(food.)", (10, 10, 80, 35), 0.9, 1)]
    assert extract_context(ws, ws[0]).word == "food"
    assert clean_word('"hello,"') == "hello"


def test_invalid_tokens_return_none():
    for t in ("123", "a", "...", "42.5"):
        w = WordBox(t, (10, 10, 50, 35), 0.9, 1)
        assert extract_context([w], w) is None


def test_focused_not_in_list_falls_back_to_word():
    w = WordBox("lonely", (10, 10, 80, 35), 0.9, 1)
    c = extract_context([], w)
    assert c.word == "lonely" and c.context == "lonely"
