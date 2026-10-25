"""Google Gemini AI integration for dyslexia-friendly word explanations.

Uses Google Gemini (Gemini 1.5 Flash / Gemini 2.0 Flash) to generate
child-friendly, one-sentence plain-English explanations tailored for
readers with dyslexia.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional
import requests

logger = logging.getLogger("gemini")

GEMINI_SYSTEM_PROMPT = (
    "You explain words to a 9-year-old child with dyslexia.\n"
    "Rules:\n"
    "- Explain the word clearly in the context of the sentence provided.\n"
    "- Write exactly ONE short sentence of at most 18 words.\n"
    "- Use common, simple, easy-to-read words. No jargon, no code fences, no extra text.\n"
    "- Make it warm, encouraging, and easy to understand.\n"
    "- Return ONLY the explanation sentence."
)


def get_gemini_api_key() -> str:
    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if key:
        return key

    from pathlib import Path
    root = Path(__file__).resolve().parent.parent.parent
    for env_path in [root / ".env", root / "backend" / ".env"]:
        if env_path.is_file():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    if k in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                        val = v.strip().strip('"').strip("'")
                        if val:
                            os.environ[k] = val
                            return val
            except Exception:
                pass
    return ""


_EXPLANATION_CACHE: dict[str, str] = {}


def get_dictionary_definition(word: str) -> Optional[str]:
    """Fetch high-speed dictionary definition from Datamuse as a reliable fallback."""
    w = word.strip().lower()
    if not w:
        return None
    try:
        url = f"https://api.datamuse.com/words?sp={w}&md=d&max=1"
        resp = requests.get(url, headers={"User-Agent": "DyslexiaVision/1.0"}, timeout=3.0)
        if resp.status_code == 200:
            data = resp.json()
            if data and "defs" in data[0] and data[0]["defs"]:
                raw_def = data[0]["defs"][0]
                # Format: "n\tA verbal or written request..."
                if "\t" in raw_def:
                    parts = raw_def.split("\t", 1)
                    clean_def = parts[1].strip()
                else:
                    clean_def = raw_def.strip()
                # Clean and capitalize
                if clean_def:
                    clean_def = clean_def[0].upper() + clean_def[1:]
                    if not clean_def.endswith("."):
                        clean_def += "."
                    return f"{word.capitalize()}: {clean_def}"
    except Exception:
        pass
    return None


def explain_word_with_gemini(word: str, context: str = "", api_key: Optional[str] = None) -> Optional[str]:
    w = word.strip().strip(".,;:!?()[]{}\"'")
    if not w:
        return None

    cache_key = f"{w.lower()}|{context.strip().lower()}"
    if cache_key in _EXPLANATION_CACHE:
        return _EXPLANATION_CACHE[cache_key]

    key = (api_key or get_gemini_api_key()).strip()
    
    # Priority list of working models with active quota
    models = [
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
    ]


    prompt = (
        f"You explain words clearly to a reader with dyslexia.\n"
        f"Rules:\n"
        f"- Explain the word clearly in the context of the sentence.\n"
        f"- Write exactly ONE friendly, simple sentence of at most 18 words.\n"
        f"- Use everyday words. No markdown, no bold asterisks, no quotes.\n"
        f"- Return ONLY the explanation sentence.\n\n"
        f"Word: '{w}'\n"
        f"Sentence context: '{context or w}'"
    )

    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 100,
        },
    }

    if key:
        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            try:
                r = requests.post(url, json=payload, timeout=6.0)
                if r.status_code == 200:
                    data = r.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            raw_text = parts[0].get("text", "").strip()
                            # Clean markdown formatting like **word** and quotes
                            cleaned = raw_text.replace("**", "").replace("*", "").strip("\"'").replace("\n", " ").strip()
                            if cleaned:
                                _EXPLANATION_CACHE[cache_key] = cleaned
                                return cleaned
                elif r.status_code in (404, 429):
                    # Quota exceeded or model not found, try next candidate model
                    continue
                else:
                    logger.debug(f"Gemini {model} returned {r.status_code}: {r.text[:200]}")
            except Exception as exc:
                logger.debug(f"Gemini call to {model} failed: {exc}")

    # Fallback: Datamuse dictionary definition
    dict_def = get_dictionary_definition(w)
    if dict_def:
        _EXPLANATION_CACHE[cache_key] = dict_def
        return dict_def

    return None

