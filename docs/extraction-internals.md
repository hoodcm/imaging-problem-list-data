# Finding Extractor Internals

Architecture and design notes for contributors working on the extraction agent.

## Module Map

| File | Role |
|------|------|
| `agent.py` | Agent construction, provider settings, prompt building, validation |
| `models.py` | Pydantic models for extraction input/output (`ReportExtraction`, etc.) |
| `examples.py` | Few-shot examples embedded in instructions |
| `cli.py` | Click CLI orchestrating extraction, validation, and optional persistence |
| `store.py` | SQLite persistence (see `docs/persistence-internals.md`) |

## How Multi-Provider Settings Work

Pydantic AI routes to providers based on the model string prefix (`openai:`, `anthropic:`, `google-gla:`, `ollama:`, etc.) and accepts provider-specific settings via TypedDict subclasses of `ModelSettings`. There is **no built-in unified reasoning/thinking abstraction** — each provider uses different keys:

| Provider | Settings key | Values |
|----------|-------------|--------|
| OpenAI | `openai_reasoning_effort` | `minimal`, `low`, `medium`, `high` |
| Anthropic | `anthropic_thinking` | `{"type": "enabled", "budget_tokens": N}` or `{"type": "disabled"}` |
| Google | `google_thinking_config` | `{"thinking_level": "MINIMAL"\|"LOW"\|"MEDIUM"\|"HIGH"}` |
| Ollama | *(none)* | No thinking support |

Our code maps a unified `--reasoning` flag to each provider's native API:

```
CLI --reasoning flag
    → _detect_provider(model_string)    # "openai" | "anthropic" | "google" | "ollama"
    → _get_model_settings(model, level) # dispatches to per-provider builder
        → _build_openai_settings()      # returns OpenAIChatModelSettings | None
        → _build_anthropic_settings()   # returns AnthropicModelSettings | None
        → _build_google_settings()      # returns GoogleModelSettings | None
```

### Provider Detection

`_detect_provider()` maps prefix strings to canonical provider names. Multiple prefixes can map to one provider (e.g., `openai`, `openai-chat`, `openai-responses` all map to `"openai"`). A bare model name with no `:` returns `None`.

### Settings Builders

Each `_build_*_settings()` function takes a reasoning level string and returns the provider-appropriate TypedDict (or `None` if no settings are needed).

**Anthropic's "none" is special:** Unlike OpenAI and Google (where `"none"` returns `None` meaning "don't send settings"), Anthropic returns an explicit `{"type": "disabled"}` dict. This is necessary because the agent may have thinking enabled by default, and `None` would leave those defaults in place rather than disabling them. See the known issue below.

### Anthropic Thinking Budgets

The current budget mapping is provisional:

| Level | `budget_tokens` | `max_tokens` |
|-------|----------------|-------------|
| minimal | 1,024 | 8,192 |
| low | 1,024 | 8,192 |
| medium | 4,096 | 8,192 |
| high | 10,240 | 16,384 |

These were chosen as reasonable starting points. `budget_tokens` is how many tokens the model can spend on internal reasoning; `max_tokens` is the total response limit (must be > `budget_tokens`). Tune these based on real extraction runs once Anthropic is in active use.

## Settings Flow Through the System

Settings are applied at two levels:

1. **Agent level** — `create_agent()` calls `_get_model_settings(model)` with no explicit reasoning param, getting the provider's default. This becomes the agent's `model_settings`.
2. **Run level** — `extract_findings()` optionally builds override settings when `reasoning` is explicitly passed, and provides them via `agent.run(model_settings=...)`.

Pydantic AI merges run-level settings over agent-level settings (simple dict union).

## Known Issues

### `--reasoning none` is ineffective for OpenAI and Google

When `--reasoning none` is passed:
- `_build_openai_settings("none")` returns `None`
- `extract_findings()` sees `run_settings = None` and skips the override
- The agent's default settings (`medium` reasoning) remain in effect
- **Result:** User asked for "none" but gets "medium"

This happens because `None` is overloaded to mean both "this provider doesn't need settings" and "don't override the agent defaults." Anthropic works correctly because its builder returns an explicit disable dict.

**Fix approach:** Refactor `extract_findings()` so settings are always passed at run time rather than baked into the agent at creation. This eliminates the need to distinguish "no settings" from "clear settings." Alternatively, the builders could return an empty dict `{}` for "none" instead of `None`, which would merge over the agent defaults and effectively clear provider-specific keys.

### No input validation on the Python API

The CLI validates reasoning levels via `click.Choice`, but calling `extract_findings(reasoning="ultra")` directly produces an unhelpful `KeyError` from the Anthropic/Google builders. A `ValueError` with a clear message would be better.

## Testing

```bash
uv run pytest tests/test_extraction.py -v
```

Key test classes:
- `TestDetectProvider` — prefix → provider mapping
- `TestMultiProviderSettings` — per-provider settings construction, defaults, edge cases
- `TestModelSettings` — backward-compat smoke tests for OpenAI (the original provider)

The tests are pure unit tests on `_detect_provider()` and `_get_model_settings()`. They do **not** mock pydantic-ai's `Agent` or make API calls.

## Future Work

- **Fix `--reasoning none` override** — see known issue above. Small refactor of `extract_findings()`.
- **Input validation** — add a `ValueError` for invalid reasoning levels at the `_get_model_settings` boundary.
- **Mock integration tests** — exercise `create_agent()` → `agent.run()` with mocked provider responses to catch regressions in the settings-to-API-call pipeline.
- **Anthropic budget tuning** — run real extractions with Anthropic models and adjust `ANTHROPIC_THINKING_BUDGETS` based on quality/cost tradeoffs.
- **Ollama thinking support** — some Ollama models (e.g., `qwen3`) support a `think` parameter. If pydantic-ai adds Ollama thinking settings, wire them in.
- **Per-model defaults** — the current code defaults by provider (all OpenAI models get `medium`). The old code had per-model defaults (GPT-5.1/5.2 defaulted to `none`). If model-specific defaults matter, `_detect_provider` could return richer info.
