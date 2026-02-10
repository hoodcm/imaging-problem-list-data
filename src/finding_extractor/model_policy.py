"""Shared model ID policy and parsing helpers."""

from __future__ import annotations

import re
from collections.abc import Callable

OPENAI_SKIP_TOKENS = (
    "audio",
    "embed",
    "embedding",
    "image",
    "moderation",
    "omni",
    "realtime",
    "search",
    "transcribe",
    "tts",
    "whisper",
)
ANTHROPIC_ALLOWED_MAJOR = 4
ANTHROPIC_ALLOWED_MINORS = {5, 6}
GOOGLE_ALLOWED_MAJOR = 3
GOOGLE_ALLOWED_TIERS = {"pro", "flash"}

ANTHROPIC_RE_A = re.compile(
    r"^claude-(?P<tier>opus|sonnet|haiku)-(?P<major>\d+)-(?P<minor>\d+)(?:-(?P<stamp>\d{8}))?$"
)
ANTHROPIC_RE_B = re.compile(
    r"^claude-(?P<major>\d+)-(?P<minor>\d+)-(?P<tier>opus|sonnet|haiku)(?:-(?P<stamp>\d{8}))?$"
)
GOOGLE_RE = re.compile(
    r"^gemini-(?P<major>\d+)(?:\.(?P<minor>\d+))?-(?P<tier>pro|flash)(?:-(?P<suffix>[a-z0-9.-]+))?$"
)
OPENAI_RE = re.compile(
    r"^gpt-(?P<major>\d+)(?:\.(?P<minor>\d+))?(?:-(?P<tier>mini|nano))?(?:-(?P<suffix>[a-z0-9.-]+))?$"
)

KNOWN_PROVIDER_PREFIXES = {
    "openai",
    "openai-chat",
    "openai-responses",
    "anthropic",
    "google-gla",
    "ollama",
}


ModelScore = tuple[int, int, int, int]
ModelParser = Callable[[str], tuple[str, ModelScore] | None]


def provider_from_model_id(model_id: str) -> str | None:
    """Return normalized provider name for known model prefixes."""
    if ":" not in model_id:
        return None
    prefix = model_id.split(":", maxsplit=1)[0]
    provider_map = {
        "openai": "openai",
        "openai-chat": "openai",
        "openai-responses": "openai",
        "anthropic": "anthropic",
        "google-gla": "google",
        "ollama": "ollama",
    }
    return provider_map.get(prefix)


def canonical_model_key(model_id: str) -> tuple[str, str] | None:
    """Return `(provider, raw_model_id)` with provider aliases normalized."""
    provider = provider_from_model_id(model_id)
    if provider is None or ":" not in model_id:
        return None
    _, raw_model_id = model_id.split(":", maxsplit=1)
    return provider, raw_model_id


def model_ids_equivalent(lhs: str, rhs: str) -> bool:
    """Compare model IDs with provider-alias normalization."""
    lhs_key = canonical_model_key(lhs)
    rhs_key = canonical_model_key(rhs)
    if lhs_key is None or rhs_key is None:
        return lhs == rhs
    return lhs_key == rhs_key


def output_model_prefix(provider: str) -> str:
    """Choose output prefix for provider model IDs."""
    if provider != "google":
        return provider
    return "google-gla"


def _suffix_stamp_rank(suffix: str | None) -> int:
    if not suffix:
        return 0
    digits = suffix.replace("-", "")
    if len(digits) == 8 and digits.isdigit():
        return int(digits)
    return 0


def _pick_latest_by_tier(
    model_ids: set[str],
    parser: ModelParser,
) -> list[tuple[str, str]]:
    chosen: dict[str, tuple[ModelScore, str]] = {}
    for model_id in sorted(model_ids):
        parsed = parser(model_id)
        if parsed is None:
            continue
        tier, score = parsed
        current = chosen.get(tier)
        if current is None:
            chosen[tier] = (score, model_id)
            continue
        current_score, current_model_id = current
        if score > current_score or (score == current_score and model_id > current_model_id):
            chosen[tier] = (score, model_id)
    return [(tier, model_id) for tier, (_, model_id) in chosen.items()]


def _parse_openai(model_id: str) -> tuple[str, ModelScore] | None:
    lowered = model_id.lower()
    if not lowered.startswith("gpt-"):
        return None
    if any(token in lowered for token in OPENAI_SKIP_TOKENS):
        return None
    match = OPENAI_RE.match(lowered)
    if match is None:
        return None
    tier = match.group("tier") or "base"
    major = int(match.group("major"))
    minor = int(match.group("minor") or "0")
    suffix = match.group("suffix")
    stable_rank = 1 if suffix is None else 0
    return tier, (major, minor, stable_rank, _suffix_stamp_rank(suffix))


def _parse_anthropic(model_id: str) -> tuple[str, ModelScore] | None:
    lowered = model_id.lower()
    if not lowered.startswith("claude-"):
        return None
    match = ANTHROPIC_RE_A.match(lowered) or ANTHROPIC_RE_B.match(lowered)
    if match is None:
        return None
    tier = match.group("tier")
    major = int(match.group("major"))
    minor = int(match.group("minor"))
    if major != ANTHROPIC_ALLOWED_MAJOR or minor not in ANTHROPIC_ALLOWED_MINORS:
        return None
    stamp = match.group("stamp")
    stable_rank = 1 if stamp is None else 0
    return tier, (major, minor, stable_rank, _suffix_stamp_rank(stamp))


def _parse_google(model_id: str) -> tuple[str, ModelScore] | None:
    lowered = model_id.lower()
    if not lowered.startswith("gemini-"):
        return None
    match = GOOGLE_RE.match(lowered)
    if match is None:
        return None
    tier = match.group("tier")
    major = int(match.group("major"))
    minor = int(match.group("minor") or "0")
    if major != GOOGLE_ALLOWED_MAJOR or tier not in GOOGLE_ALLOWED_TIERS:
        return None
    suffix = match.group("suffix")
    stable_rank = 1 if suffix is None else 0
    return tier, (major, minor, stable_rank, _suffix_stamp_rank(suffix))


def select_sota_model_ids(provider: str, model_ids: set[str]) -> list[tuple[str, str]]:
    """Select latest per family/tier to avoid exposing superseded models."""
    if provider == "openai":
        selected = _pick_latest_by_tier(model_ids, _parse_openai)
    elif provider == "anthropic":
        selected = _pick_latest_by_tier(model_ids, _parse_anthropic)
    elif provider == "google":
        selected = _pick_latest_by_tier(model_ids, _parse_google)
    else:
        selected = []

    if selected:
        return sorted(selected, key=lambda item: (item[0], item[1]))

    # Known providers use strict parsing/policy filters; unmatched models are excluded.
    if provider in {"openai", "anthropic", "google"}:
        return []

    # Unknown providers use permissive fallback.
    return [("default", model_id) for model_id in sorted(model_ids)[:3]]


def validate_model_id(model_id: str) -> None:
    """Validate a runtime model ID against project policy."""
    if ":" not in model_id:
        raise ValueError("model must use '<provider>:<model-id>' format")

    prefix, raw_model_id = model_id.split(":", maxsplit=1)
    if not raw_model_id.strip():
        raise ValueError("model id suffix must be non-empty")

    if prefix == "google-vertex":
        raise ValueError("google-vertex models are not allowed; use google-gla:*")

    if prefix not in KNOWN_PROVIDER_PREFIXES:
        raise ValueError(f"unsupported model provider '{prefix}'")

    provider = provider_from_model_id(model_id)
    if provider == "anthropic" and not select_sota_model_ids("anthropic", {raw_model_id}):
        raise ValueError("anthropic model must be version 4.5 or 4.6")

    if provider == "google" and not select_sota_model_ids("google", {raw_model_id}):
        raise ValueError("google model must be gemini-3* pro/flash with google-gla prefix")
