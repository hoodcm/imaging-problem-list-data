# Model Selection Notes

Last updated: 2026-02-24
Status: Active reference

## Current Defaults

1. Extraction model default: `google-gla:gemini-3-flash-preview`
2. Extraction fallback default: `openai:gpt-5.2`
3. Provider default reasoning:
   - `google`: `low`
   - `openai`: `medium`
   - `anthropic`: `medium`
   - `openrouter`: `medium`
   - `ollama`: `none`

## What We Learned (Chunk-Extraction Focus)

1. Prompt size and schema fit matter more than forcing higher reasoning.
2. Gemini Flash is the best default throughput baseline for chunk extraction.
3. GPT-5.2 is a strong fallback for resilience when primary provider calls fail.
4. Repeated Sonnet diagnostics showed 4.6 faster than 4.5 for this chunk task, but still slower than Flash/GPT defaults.
5. Gemini model-family reasoning settings must be model-aware:
   - `gemini-3.1-pro*`: supports `low|high`
   - `gemini-3-flash*`: supports `minimal|low|medium|high`

## Curated Common Models

Canonical source in code:
- `src/finding_extractor/llm/defaults.py`
- `src/finding_extractor/llm/model_settings.py` (`EXTRACTION_PRESETS`, `format_preset_help_summary()`)

1. `google-gla:gemini-3-flash-preview` (default extraction)
2. `openai:gpt-5.2` (default fallback)
3. `anthropic:claude-opus-4-6` (high-quality validator/extraction option)
4. `google-gla:gemini-3.1-pro-preview` (strong Google quality option)
5. `ollama:qwen3:30b-instruct` (local baseline, reasoning=`none`)
6. `ollama:qwen3:30b-thinking` (local thinking-capable model)
7. `ollama:gpt-oss:120b` (local heavy reasoning-capable model)

Reasoning notes for curated local models:
- `ollama:qwen3:30b-thinking`: all reasoning inputs accepted; runtime maps `none` to `think=false` and non-`none` to `think=true`
- `ollama:qwen3:30b-instruct`: `none` only
- `ollama:gpt-oss:120b`: `none|low|medium|high` accepted; `minimal` normalizes to `low`

## Operational Guidance

1. Start with defaults for routine extraction runs.
2. Move to `openai:gpt-5.2` directly for reliability testing or provider isolation.
3. `quality` preset is pinned to `anthropic:claude-opus-4-6` intentionally for maximum-quality review/extraction runs; use selectively when latency/cost are acceptable.
4. Re-run focused model comparison after major prompt/schema changes.

## Planned Improvements

1. Move reasoning compatibility rules to one table-driven registry to reduce branching logic.
2. Add an integration smoke matrix for common model/reasoning pairs, including:
   - `google-gla:gemini-3-flash-preview` + `low`
   - `google-gla:gemini-3.1-pro-preview` + `low`
   - `openai:gpt-5.2` + `low` (and `minimal` normalization)
   - `anthropic:claude-opus-4-6` + `low`
   - `ollama:qwen3:30b-instruct` + `none`
   - `ollama:qwen3:30b-thinking` + `low`
   - `ollama:gpt-oss:120b` + `medium`
