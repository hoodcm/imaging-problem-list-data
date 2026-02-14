# Stream Provider Expansion: Stage 5 Provider/Model Capability Work

Last updated: 2026-02-14
Status: Active

## Stage definition

Stage 5 means expanding provider/model support safely after earlier extraction/eval foundations are in place.

## Scope

1. Refactor provider settings builders out of `agent.py` into dedicated module.
2. Expand model capability/discovery path for local models.
3. Add safe profile presets and maintain model-policy validation.

## Focus areas

1. Keep provider behavior explicit for reasoning/thinking settings.
2. Prevent drift between discovery metadata and runtime policy validation.
3. Preserve existing API contracts while broadening supported model inventory.

## Out of scope

1. Stage 6 chunking/orchestration changes.
2. Coding bridge logic.

## Acceptance criteria

1. Provider settings code is modular and easier to extend/test.
2. Model catalog includes richer capability metadata for decision-making.
3. Existing tests remain green; add provider-focused regression tests.

## Progress

### 2026-02-14: Provider Refactoring + OpenRouter Support (Slice 1) ✓

**Shipped:**
- Created `src/finding_extractor/providers.py` module:
  * Extracted reasoning configuration constants and provider detection from `agent.py`
  * Provider-specific settings builders for OpenAI, Anthropic, Google, OpenRouter, Ollama
  * Public API: `detect_provider()`, `get_model_settings()`, `validate_reasoning_for_model()`
- Added OpenRouter provider support:
  * Provider prefix: `openrouter:` (e.g., `openrouter:anthropic/claude-sonnet-4-5`)
  * Reasoning: effort-based (low/medium/high), maps `minimal` → `low`
  * Config: `OPENROUTER_API_KEY` environment variable
  * Model policy: permissive validation (similar to ollama)
  * Catalog: discovery deferred (model space too large for SOTA filtering)
- Updated `agent.py`: imports from `providers`, re-exports `validate_reasoning_for_model` for backward compatibility
- Expanded test coverage:
  * 11 new OpenRouter tests (settings builder, detection, reasoning validation)
  * 6 new Anthropic budget token verification tests (all reasoning levels)
  * 3 new Google thinking level completeness tests
  * All 385 tests passing, lint clean
- Updated `model_policy.py`, `config.py`, `model_catalog.py` for OpenRouter registration

**Module boundaries:**
- `providers.py`: Provider-specific settings configuration and detection (public API)
- `agent.py`: Extraction orchestration, uses `providers` module for settings
- `model_policy.py`: Model ID validation, SOTA filtering (distinct from runtime detection)
- `model_catalog.py`: Model discovery and caching (OpenRouter noted as available, no dynamic discovery)

**Next:** Model capability metadata expansion, profile presets, or local model discovery paths.
