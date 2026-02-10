"""Tests for runtime model-id validation policy."""

import pytest

from finding_extractor.model_policy import validate_model_id


def test_validate_model_id_accepts_openai():
    validate_model_id("openai:gpt-5-mini")


def test_validate_model_id_accepts_ollama():
    validate_model_id("ollama:llama3.3")


def test_validate_model_id_accepts_anthropic_45():
    validate_model_id("anthropic:claude-sonnet-4-5")


def test_validate_model_id_accepts_gemini3_gla():
    validate_model_id("google-gla:gemini-3-pro-preview")


def test_validate_model_id_rejects_google_vertex():
    with pytest.raises(ValueError, match="google-vertex models are not allowed"):
        validate_model_id("google-vertex:gemini-3-pro")


def test_validate_model_id_rejects_old_anthropic():
    with pytest.raises(ValueError, match="anthropic model must be version 4.5 or 4.6"):
        validate_model_id("anthropic:claude-sonnet-4-0")


def test_validate_model_id_rejects_old_gemini():
    with pytest.raises(ValueError, match="google model must be gemini-3\\* pro/flash"):
        validate_model_id("google-gla:gemini-2.5-pro")


def test_validate_model_id_rejects_bad_format():
    with pytest.raises(ValueError, match="model must use"):
        validate_model_id("gpt-5-mini")
