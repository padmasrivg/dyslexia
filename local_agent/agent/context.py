"""Context extraction: isolated word, containing sentence, optional neighbours.

Works on OCR WordBoxes. Words are put in reading order (line by line, left to
right), restricted to the focused word's column so two-column pages do not mix.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from ..datatypes import WordBox

_SENT_END = re.compile(r"[.!?]+[\"')\]]*$")
_STRIP = re.compile(r"^[^\w]+|[^\w]+$", re.UNICODE)


def clean_word(raw: str) -> str:
    return _STRIP.sub("", raw or "")


def is_valid_word(word: str, min_len: int = 2, max_len: int = 64) -> bool:
    return min_len <= len(word) <= max_len and any(c.isalpha() for c in word)


@dataclass
class ExtractedContext:
    word: str
    context: str


def _x_overlap(a: Sequence[int], b: Sequence[int]) -> float:
    inter = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    span = max(1, min(a[2] - a[0], b[2] - b[0]))
    return inter / span


def reading_order(words: Sequence[WordBox]) -> List[WordBox]:
    lines: dict[int, List[WordBox]] = {}
    for w in words:
        lines.setdefault(w.line_id, []).append(w)
    ordered: List[WordBox] = []
    for lid in sorted(lines, key=lambda k: min(w.bbox[1] for w in lines[k])):
        ordered.extend(sorted(lines[lid], key=lambda w: w.bbox[0]))
    return ordered


def _line_heights(words: Sequence[WordBox]) -> dict:
    by: dict[int, List[int]] = {}
    for w in words:
        by.setdefault(w.line_id, []).append(max(1, w.bbox[3] - w.bbox[1]))
    return {k: sorted(v)[len(v) // 2] for k, v in by.items()}


def extract_context(
    words: Sequence[WordBox],
    focused: WordBox,
    extra_sentences: int = 0,
    max_chars: int = 400,
) -> Optional[ExtractedContext]:
    word = clean_word(focused.text)
    if not is_valid_word(word):
        return None

    # keep the same column and a bounded vertical neighbourhood
    line_h = max(1, focused.bbox[3] - focused.bbox[1])
    focus_cy = (focused.bbox[1] + focused.bbox[3]) / 2
    by_line: dict[int, List[WordBox]] = {}
    for w in words:
        by_line.setdefault(w.line_id, []).append(w)
    own = by_line.get(focused.line_id, [focused])
    own_box = (min(w.bbox[0] for w in own), 0, max(w.bbox[2] for w in own), 1)
    near: List[WordBox] = []
    for lid, ws in by_line.items():
        line_box = (min(w.bbox[0] for w in ws), 0, max(w.bbox[2] for w in ws), 1)
        cy = sum((w.bbox[1] + w.bbox[3]) / 2 for w in ws) / len(ws)
        same_column = lid == focused.line_id or _x_overlap(line_box, own_box) >= 0.3
        if same_column and abs(cy - focus_cy) <= line_h * 6:
            near.extend(ws)
    ordered = reading_order(near)
    try:
        idx = next(i for i, w in enumerate(ordered) if w.bbox == focused.bbox and w.text == focused.text)
    except StopIteration:
        return ExtractedContext(word, word)

    # sentence boundaries over the token stream. A change in text size between
    # lines (a heading above a paragraph) also ends a sentence.
    heights = _line_heights(ordered)

    def style_break(a: WordBox, b: WordBox) -> bool:
        if a.line_id == b.line_id:
            return False
        ha, hb = heights[a.line_id], heights[b.line_id]
        return max(ha, hb) / float(min(ha, hb)) > 1.35

    def ends_before(i: int) -> bool:  # True if a sentence ends between token i-1 and i
        return bool(_SENT_END.search(ordered[i - 1].text)) or style_break(ordered[i - 1], ordered[i])

    start = idx
    while start > 0 and not ends_before(start):
        start -= 1
    end = idx
    while end < len(ordered) - 1 and not ends_before(end + 1):
        end += 1

    for _ in range(max(0, extra_sentences)):  # optional surrounding sentences
        while end < len(ordered) - 1:
            end += 1
            if _SENT_END.search(ordered[end].text):
                break
        if start > 0:
            start -= 1
            while start > 0 and not _SENT_END.search(ordered[start - 1].text):
                start -= 1

    text = " ".join(w.text for w in ordered[start:end + 1]).strip()
    if len(text) > max_chars:  # keep a window centred on the word
        pos = text.lower().find(focused.text.lower())
        lo = max(0, pos - max_chars // 2)
        text = text[lo:lo + max_chars].strip()
    return ExtractedContext(word=word, context=text or word)
