# Model Selection Notes

Last updated: 2026-02-18
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
   - `gemini-3-pro*`: supports `low|high`
   - `gemini-3-flash*`: supports `minimal|low|medium|high`

## Operational Guidance

1. Start with defaults for routine extraction runs.
2. Move to `openai:gpt-5.2` directly for reliability testing or provider isolation.
3. Use Anthropic quality profiles selectively when latency is acceptable.
4. Re-run focused model comparison after major prompt/schema changes.
