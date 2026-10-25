"""HTTP client for the /assist endpoint.

Sends only {word, context}. No frames, no screenshots. Holds no AWS
credentials: authentication to API Gateway, if enabled, is an API key header.
"""
from __future__ import annotations

import time
from typing import Optional

import requests

from ..config import Config
from ..datatypes import AssistanceResult
from .schema import ValidationError, parse_assist_response, validate_assist_payload


class CloudError(RuntimeError):
    """kind is one of: not_configured, invalid_request, timeout, network,
    api_gateway, malformed_response, service_error"""

    def __init__(self, kind: str, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status = status


class AssistClient:
    def __init__(self, cfg: Config, session: Optional[requests.Session] = None) -> None:
        self.cfg = cfg
        self.session = session or requests.Session()

    def _url(self) -> str:
        base = self.cfg.api_url.rstrip("/")
        return base if base.endswith("/assist") else base + "/assist"

    def assist(self, word: str, context: str) -> AssistanceResult:
        if not self.cfg.api_url:
            raise CloudError("not_configured", "ASSIST_API_URL is not set")
        try:
            payload = validate_assist_payload({"word": word, "context": context})
        except ValidationError as exc:
            raise CloudError("invalid_request", exc.message) from exc

        headers = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            headers["x-api-key"] = self.cfg.api_key

        t0 = time.perf_counter()
        try:
            resp = self.session.post(
                self._url(),
                json=payload,
                headers=headers,
                timeout=(self.cfg.connect_timeout_s, self.cfg.read_timeout_s),
            )
        except requests.ReadTimeout as exc:
            raise CloudError("timeout", "the assistance service took too long to answer") from exc
        except requests.ConnectionError as exc:
            raise CloudError("network", "could not reach the assistance service") from exc
        except requests.Timeout as exc:
            raise CloudError("timeout", "the assistance service took too long to answer") from exc
        except requests.RequestException as exc:
            raise CloudError("network", f"request failed: {type(exc).__name__}") from exc
        latency_ms = (time.perf_counter() - t0) * 1000.0

        try:
            body = resp.json()
        except ValueError:
            if resp.status_code >= 400:
                raise CloudError("api_gateway", f"gateway returned HTTP {resp.status_code}", resp.status_code)
            raise CloudError("malformed_response", "response was not JSON", resp.status_code)

        if resp.status_code >= 400:
            msg = body.get("message") if isinstance(body, dict) else None
            if isinstance(body, dict) and isinstance(body.get("error"), dict):
                msg = body["error"].get("message", msg)
            raise CloudError("api_gateway", str(msg or f"HTTP {resp.status_code}"), resp.status_code)

        try:
            parsed = parse_assist_response(body)
        except ValidationError as exc:
            kind = "malformed_response" if exc.code == "malformed_response" else "service_error"
            raise CloudError(kind, exc.message) from exc

        return AssistanceResult(
            word=parsed.word,
            definition=parsed.definition,
            audio_b64=parsed.audio_b64,
            source="aws",
            api_latency_ms=latency_ms,
            server_timings=parsed.timings,
        )


class MockAssistClient:
    """OFFLINE MOCK. Used only when MOCK_CLOUD=1 or the user picks 'mock' in the UI.
    It does not call AWS, Bedrock or Polly and returns no audio. Results are
    tagged source="local-mock" so the UI can never present them as cloud output."""

    GLOSSARY = {
        "photosynthesis": "How green plants use sunlight, water, and air to make their own food.",
        "plants": "Living things that grow in soil and make food using light, such as trees and flowers.",
        "plant": "A living thing that grows in the ground and needs water and sunlight.",
        "chlorophyll": "The natural green color in plant leaves that catches sunlight energy.",
        "absorb": "To soak up liquid or light like a sponge.",
        "carbon": "A natural building block found in all living creatures.",
        "dioxide": "A gas in the air made of carbon and oxygen parts.",
        "sunlight": "Warm and bright natural light streaming down from the sun.",
        "oxygen": "A clean invisible gas in the air that animals and people breathe to live.",
        "transform": "To change smoothly from one shape or form into another.",
        "sustaining": "Keeping someone or something alive, healthy, and growing strong.",
        "creatures": "Living animals and insects that move and breathe on earth.",
        "energy": "The strength or power needed to move, work, and grow.",
        "natural": "Found in nature and made by the earth rather than by machines.",
        "process": "A clear set of steps followed one by one to complete a task.",
        "leaves": "The flat green parts of plants that collect light from the sky.",
        "ecosystem": "A community of animals, plants, and nature living together in harmony.",
        "organism": "Any single living creature, like an animal, plant, or bug.",
        "electromagnetic": "Energy waves made of electric and magnetic fields traveling together.",
        "bioluminescent": "Living creatures that can make their own glowing light in the dark.",
        "spectroscopic": "Using beams of light to study what materials are made of.",
        "extraordinary": "Very unusual, special, and amazing compared to normal things.",
        "mitochondria": "Tiny power generators inside cells that produce energy for life.",
        "cellular": "Relating to the tiny microscopic building blocks that form living things.",
        "respiration": "The gentle way living cells take in oxygen and release energy.",
        "gravity": "The invisible force pulling objects down toward the center of the earth.",
        "atmosphere": "The blanket of protective air and gases surrounding our planet.",
        "evaporation": "When warm water turns into invisible vapor and rises into the air.",
        "precipitation": "Water falling from the clouds down to the ground as rain or snow.",
        "condensation": "When cool air turns water vapor back into tiny visible liquid drops.",
        "metamorphosis": "A magical growth cycle, like a caterpillar turning into a butterfly.",
        "biodiversity": "The wonderful variety of different plants and animals living in an area.",
        "habitat": "The natural home or environment where an animal or plant lives.",
        "environment": "The natural world of land, air, and water around us.",
        "adaptation": "A helpful change that allows a creature to survive in its home.",
        "carnivore": "An animal that eats meat from other animals.",
        "herbivore": "An animal that eats only plants, leaves, and grass.",
        "omnivore": "An animal or person that eats both plants and meats.",
        "temperature": "How hot or cold something feels measured in degrees.",
        "velocity": "How fast something moves in a specific direction.",
        "acceleration": "Speeding up or getting faster over a period of time.",
        "friction": "The resistance created when two surfaces rub against each other.",
        "magnetism": "The invisible pulling force created between magnets.",
        "molecule": "A tiny group of atoms bonded tightly together.",
        "chemical": "A substance formed by combining different natural elements.",
        "comprehension": "Understanding what you read or hear clearly and easily.",
        "vocabulary": "All the wonderful words you know and use to speak and read.",
        "pronunciation": "Saying the sounds of a word correctly and smoothly.",
        "articulation": "Speaking clearly so each word is easy for others to hear.",
        "phonetic": "Matching the letters on the page to the sounds spoken aloud.",
        "syllable": "A single beat or chunk of sound inside a spoken word.",
        "dyslexia": "A unique way of thinking where words and letters are processed differently.",
        "assistance": "Help or support given to make reading smoother and more fun.",
        "confidence": "Feeling sure of yourself and believing in your ability to succeed.",
        "aptitude": "A natural talent or ability to learn and do certain tasks well.",
        "reasoning": "Thinking carefully and solving problems step by step.",
        "numerical": "Related to numbers, counting, and math.",
        "abstract": "Ideas and shapes rather than physical objects.",
        "verbal": "Using words and language to communicate.",
        "percentile": "A score showing how your result compares with other people out of 100.",
        "score": "The number of points or grade earned on a test.",
        "report": "A written summary showing results or information.",
        "question": "A sentence asking for an answer or test problem.",
        "test": "A check or quiz to see what you know.",
        "alison": "An online learning and certificate education platform.",
        "padmasri": "A person's given name.",
        "gandhi": "A family surname.",
    }

    def assist(self, word: str, context: str) -> AssistanceResult:
        t0 = time.perf_counter()
        w = word.lower().strip()
        definition = self.GLOSSARY.get(w)
        if not definition:
            # Friendly fallback definition
            definition = f"(Mock) {word.capitalize()} means a word or concept used here to explain {context.strip() if context else 'the topic'}."
        return AssistanceResult(
            word=word, definition=definition, audio_b64=None, source="local-mock",
            api_latency_ms=(time.perf_counter() - t0) * 1000.0, server_timings={},
        )
