# Finding Extractor Internals

Architecture and design notes for contributors working on the extraction agent.

## Module Map

| File | Role |
|------|------|
| `agent.py` | Agent construction, provider settings, prompt building, validation, reasoning validation |
| `models.py` | Pydantic models for extraction input/output (`ReportExtraction`, `ExtractionResult`, `ExtractionUsage`, `ReasoningLevel`) |
| `examples.py` | Few-shot examples embedded in instructions |
| `extraction_pipeline.py` | Shared pipeline: model validation, extraction, optional validation/persistence, status callback threading. Used by both `cli.py` and `batch_cli.py` |
| `cli.py` | Click CLI — thin wrapper that creates a status callback and delegates to `run_extraction_pipeline()` |
| `batch_cli.py` | Batch extraction CLI — concurrent multi-file extraction using `run_extraction_pipeline()` |
| `store.py` | SQLite persistence (see `docs/persistence-internals.md`) |

## How Multi-Provider Settings Work

Pydantic AI routes to providers based on the model string prefix (`openai:`, `anthropic:`, `google-gla:`, `ollama:`, etc.) and accepts provider-specific settings via TypedDict subclasses of `ModelSettings`. There is **no built-in unified reasoning/thinking abstraction** — each provider uses different keys:

| Provider | Settings key | Values |
|----------|-------------|--------|
| OpenAI | `openai_reasoning_effort` | `none`, `minimal`, `low`, `medium`, `high` |
| Anthropic | `anthropic_thinking` | `{"type": "enabled", "budget_tokens": N}` or `{"type": "disabled"}` |
| Google | `google_thinking_config` | `{"thinking_level": "NONE"\|"MINIMAL"\|"LOW"\|"MEDIUM"\|"HIGH"}` |
| Ollama | *(none)* | No thinking support; only `reasoning="none"` is accepted |

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

Each `_build_*_settings()` function takes a reasoning level string and returns the provider-appropriate TypedDict. All known providers return explicit settings for every level including `"none"`:

- **OpenAI:** `_build_openai_settings("none")` returns `OpenAIChatModelSettings(openai_reasoning_effort="none")`.
- **Google:** `_build_google_settings("none")` returns `GoogleModelSettings(google_thinking_config={"thinking_level": "NONE"})`.
- **Anthropic:** `_build_anthropic_settings("none")` returns `AnthropicModelSettings(anthropic_thinking={"type": "disabled"})`.
- **Ollama:** Returns `None` (no settings support). Only `reasoning="none"` is accepted; other levels are rejected by validation.

### Anthropic Thinking Budgets

The current budget mapping is provisional:

| Level | `budget_tokens` | `max_tokens` |
|-------|----------------|-------------|
| minimal | 1,024 | 8,192 |
| low | 1,024 | 8,192 |
| medium | 4,096 | 8,192 |
| high | 10,240 | 16,384 |

These were chosen as reasonable starting points. `budget_tokens` is how many tokens the model can spend on internal reasoning; `max_tokens` is the total response limit (must be > `budget_tokens`). Tune these based on real extraction runs once Anthropic is in active use.

## Verbatim Validation and Output Retries

The agent enforces that every `report_text` and `non_finding_text.text` field is a verbatim substring of the original report. This is checked in two places:

1. **Output validator** (`validate_verbatim` on the agent) — runs after each model response. If quotes don't match, raises `ModelRetry` to give the model another attempt. The agent is configured with `output_retries=3` (4 total attempts).
2. **Post-extraction validation** (`validate_extraction`) — runs after the agent completes, producing a `ValidationResult` stored alongside the extraction. This is informational and does not block.

Both checks use `_verbatim_match()`, which tries exact substring matching first, then falls back to whitespace-normalized matching (`_normalize_ws` collapses all whitespace runs to single spaces). This tolerates the most common model failure mode: adding/removing trailing spaces, collapsing newlines, or introducing double spaces.

If the model fails all 4 attempts, pydantic-ai raises `UnexpectedModelBehavior`, which the task worker maps to `extraction_failed:model_output_validation_failed`.

## Settings Flow Through the System

Settings are applied at two levels:

1. **Agent level** — `create_agent()` calls `_get_model_settings(model)` with no explicit reasoning param, getting the provider's default. This becomes the agent's `model_settings`.
2. **Run level** — `extract_findings()` optionally builds override settings when `reasoning` is explicitly passed, and provides them via `agent.run(model_settings=...)`.

Pydantic AI merges run-level settings over agent-level settings (simple dict union).

## Reasoning Validation

Reasoning levels are validated at multiple layers:

### Type System

`ReasoningLevel` is a `Literal["none", "minimal", "low", "medium", "high"]` defined in `models.py`. The runtime constant `VALID_REASONING_LEVELS` in `agent.py` is derived from this type via `get_args(ReasoningLevel)`, keeping a single source of truth.

### Validation Functions

Both functions are in `agent.py`:

- `validate_reasoning(reasoning)` — checks the value is in `VALID_REASONING_LEVELS`. Raises `ValueError` if not. Returns the validated `ReasoningLevel`.
- `validate_reasoning_for_model(model, reasoning)` — calls `validate_reasoning()` internally, then checks provider compatibility via `PROVIDER_SUPPORTED_REASONING`. Ollama only supports `"none"`; others support all levels. Raises `ValueError` for incompatible combos.

### Where Validation Runs

- **CLI / Batch CLI:** `click.Choice` constrains to valid levels; `run_extraction_pipeline()` in `extraction_pipeline.py` calls `validate_reasoning_for_model()` before extraction.
- **API:** `api_services.enqueue_extraction_job()` calls `validate_reasoning_for_model()`, returning `422` on failure.
- **Worker:** `tasks._run_extraction_impl()` calls `validate_reasoning_for_model()` as defense-in-depth.

## Status Callback

Progress messages flow through two levels:

### Pipeline level (`extraction_pipeline.py`)

`run_extraction_pipeline()` accepts an optional `status_callback` parameter — `Callable[[str], Awaitable[None]] | None`. It emits orchestration-level messages via an internal `_emit()` helper and passes the same callback down to `extract_findings()`:

| Point | Message |
|---|---|
| Before model validation | `"Validating model configuration..."` |
| Before validation pass | `"Validating extraction results..."` |
| Before DB write | `"Saving to database..."` |
| After completion | `"Done."` |

### Agent level (`agent.py`)

`extract_findings()` accepts the same `status_callback`, stores it on `ExtractorDeps`, and invokes it via `_emit_status()` at three points:

| Point | Message |
|---|---|
| Before `agent.run()` | `"Calling model..."` |
| On verbatim validation retry | `"Retrying: verbatim validation failed (N error(s))"` |
| After `agent.run()` | `"Model call complete, processing results"` |

### How callers wire it

- **CLI** (`cli.py`): `_run_pipeline()` creates a closure that calls `click.echo(f"  {message}", err=True)` and passes it to `run_extraction_pipeline()`
- **Worker** (`tasks.py`): creates a closure that calls `store.update_job_status_message(job_id, message)` and passes it directly to `extract_findings()` (worker has its own pipeline, doesn't use `extraction_pipeline.py`)
- **Batch CLI** (`batch_cli.py`): calls `run_extraction_pipeline()` without a callback (defaults to `None`, silent)

When `status_callback` is `None`, both `_emit()` and `_emit_status()` are no-ops.

## Usage and Token Accounting

`extract_findings()` returns `ExtractionResult` (a frozen dataclass) containing both the `ReportExtraction` and an optional `ExtractionUsage`:

```python
@dataclass(frozen=True)
class ExtractionResult:
    extraction: ReportExtraction
    usage: ExtractionUsage | None
```

`ExtractionUsage` captures:
- `requests` — number of API requests (including retries)
- `input_tokens`, `output_tokens` — token counts
- `cache_read_tokens`, `cache_write_tokens` — cache-related tokens
- `duration_ms` — wall-clock time for the extraction (measured via `time.monotonic()`)
- `details` — provider-specific extras as `dict[str, int]`

Usage capture is best-effort: failures are logged at `DEBUG` level but do not block extraction.

Usage flows through the system as:
1. `agent.py` captures from `result.usage()` after `agent.run()` completes, returns via `ExtractionResult.usage`
2. `extraction_pipeline.py` unwraps `ExtractionResult`, passes `usage` to `store.create_extraction()` and includes it in `StorageMetadata`
3. `store.py` persists in dedicated nullable columns on the `extractions` table
4. `api_models.py` includes `usage` field in `ExtractionSummaryResponse` and `ExtractionDetailResponse`
5. `cli.py` displays token counts and duration in both JSON (`_storage.usage`) and table (`PERSISTENCE` block) output

## Testing

```bash
uv run pytest tests/test_extraction.py -v
```

Key test classes:
- `TestDetectProvider` — prefix → provider mapping
- `TestMultiProviderSettings` — per-provider settings construction, defaults, edge cases
- `TestModelSettings` — backward-compat smoke tests for OpenAI (the original provider)
- `TestReasoningValidation` — valid/invalid levels, model+reasoning compatibility
- `TestOpenAINoneSettings` — verifies `reasoning="none"` returns explicit settings
- `TestExtractionResult` — `ExtractionResult` and `ExtractionUsage` data classes
- `TestEmitStatus` — `_emit_status` no-op when callback is `None`, invocation when present

The tests are pure unit tests on `_detect_provider()`, `_get_model_settings()`, and validation functions. They do **not** mock pydantic-ai's `Agent` or make API calls.

## Future Work

- **Mock integration tests** — exercise `create_agent()` → `agent.run()` with mocked provider responses to catch regressions in the settings-to-API-call pipeline.
- **Anthropic budget tuning** — run real extractions with Anthropic models and adjust `ANTHROPIC_THINKING_BUDGETS` based on quality/cost tradeoffs.
- **Ollama thinking support** — some Ollama models (e.g., `qwen3`) support a `think` parameter. If pydantic-ai adds Ollama thinking settings, wire them in.
- **Per-model defaults** — the current code defaults by provider (all OpenAI models get `medium`). If model-specific defaults matter, `_detect_provider` could return richer info.
- **Cost tracking** — aggregate usage data per model for cost comparison dashboards.
- **Latency-based model selection** — use `duration_ms` data to inform model routing for real-time vs. batch use cases.
