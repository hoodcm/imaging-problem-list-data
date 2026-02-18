# Finding Extractor Usage

Extract structured findings from radiology reports using an LLM agent.

## How Extraction Works (High-Level)

At runtime, the extractor uses one shared orchestration path across CLI, API worker jobs, batch runs, and evals.

1. Parse report sections deterministically.
2. Keep extraction scope to `findings` and `impression`.
3. Chunk those sections (impression list-aware, semantic grouping for longer text).
4. Run chunk extraction sub-agents in parallel (dedicated chunk prompt + `ChunkExtraction` schema).
5. Start coding each chunk result as it completes (deterministic first, LLM adjudication for ambiguous candidates).
6. Merge + dedupe findings, optionally run targeted re-extraction review, then finalize output.
7. Emit status stages throughout; return JSON and optionally persist to SQLite.

```mermaid
flowchart LR
    A[Report Text] --> B[Sectionize<br/>findings + impression]
    B --> C[Chunking<br/>list + semantic]
    C --> D[Parallel chunk extraction]
    D --> E[Inline coding per chunk<br/>deterministic + adjudication]
    D --> F[Merge + dedupe]
    E --> F
    F --> G[Optional validator review<br/>targeted re-extract]
    G --> H[Final extraction JSON]
    H --> I[Optional DB persistence]
```

For implementation-level details and full stage contracts, see `docs/extraction-internals.md`.

## Quick Start

```bash
uv run finding-extractor report.txt
```

Output is JSON with extracted findings, locations, attributes, and non-finding text segments.
Coding is enabled by default and attached inline at `findings[].coding` when available.

## Choosing a Model

Pass any [pydantic-ai model string](https://ai.pydantic.dev/models/) via `--model` or the `IPL_MODEL` env var.

| Provider | Example `--model` value | API key env var |
|----------|------------------------|-----------------|
| OpenAI | `openai:gpt-5.2` (fallback default) | `OPENAI_API_KEY` |
| Anthropic | `anthropic:claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| Google | `google-gla:gemini-3-flash-preview` (default) | `GOOGLE_API_KEY` |
| OpenRouter | `openrouter:meta-llama/llama-3.1-70b` | `OPENROUTER_API_KEY` |
| Ollama | `ollama:llama4` | *(none, local)* |

```bash
# Anthropic
uv run finding-extractor report.txt -m anthropic:claude-sonnet-4-5

# Google
uv run finding-extractor report.txt -m google-gla:gemini-3-flash-preview

# OpenRouter (aggregates many providers)
uv run finding-extractor report.txt -m openrouter:meta-llama/llama-3.1-70b

# Local Ollama (see Ollama setup below)
uv run finding-extractor report.txt -m ollama:llama4
```

### Ollama Setup

Ollama runs models locally without API keys. You must:

1. **Install and start Ollama:** Follow [ollama.com](https://ollama.com)
2. **Pull a model:** `ollama pull llama4`
3. **Set base URL:** `export OLLAMA_BASE_URL=http://localhost:11434`

The `OLLAMA_BASE_URL` environment variable is required — Ollama uses an OpenAI-compatible API, and PydanticAI needs to know where to find it.

```bash
export OLLAMA_BASE_URL=http://localhost:11434
uv run finding-extractor report.txt -m ollama:llama4
```

## Reasoning / Thinking Level

The `--reasoning` flag controls how much "thinking" the model does before responding. Higher levels improve extraction quality at the cost of latency and tokens.

```bash
uv run finding-extractor report.txt --reasoning high
uv run finding-extractor report.txt --reasoning none
```

Levels: `none`, `minimal`, `low`, `medium`, `high`

Reasoning defaults are provider-specific (`openai=medium`, `anthropic=medium`, `google=low`, `openrouter=medium`, `ollama=none`). You can override with `--reasoning` or `IPL_REASONING`.

Configuration details (env vars, `config.toml`, precedence, and secrets policy):
- `docs/configuration.md`

## All CLI Options

```
finding-extractor <report_file> [OPTIONS]

Options:
  --exam-type TEXT          Exam description for context (e.g., "CT Chest")
  --output, -o PATH         Write JSON to file instead of stdout
  --model, -m TEXT          Model string (default: google-gla:gemini-3-flash-preview)
  --reasoning, -r LEVEL     none | minimal | low | medium | high
  --format, -f FORMAT       json (default) | table
  --validate / --no-validate  Run post-extraction coverage analysis
  --store / --no-store      Persist to SQLite (default: --no-store)
  --db-path PATH            SQLite path (default: IPL_DB_PATH or .finding_extractor.db)
  --logfire / --no-logfire  Enable or disable Logfire observability for this run
  --verbose                 Emit INFO-level logs for this run
```

### `--validate` semantics

`--validate` runs a **coverage analysis** that checks whether all report text lines are accounted for by extracted findings or non-finding text segments. It does **not** perform verbatim quote checking — that is handled automatically by the agent's output validator, which retries the model when quotes don't match. As a result, `--validate` always returns `is_valid=True` with no `verbatim_errors`; it only produces `coverage_warnings`.

## Logfire Observability

Logfire is optional and disabled by default.

```bash
# Enable globally for API/worker/CLI runs via env
export IPL_LOGFIRE_ENABLED=true

# Enable only for one CLI invocation
uv run finding-extractor report.txt --logfire
```

For complete Logfire env options and defaults, see `docs/configuration.md`.

Supported instrumentation in this project includes:
- `pydantic_ai` agent runs
- `httpx` model/provider HTTP calls
- FastAPI request handling
- SQLAlchemy database operations
- Redis operations

## Logging Output Controls

Structured logging is configured via env vars:

```bash
export IPL_LOG_LEVEL=WARNING
export IPL_LOG_JSON=false
```

- `IPL_LOG_LEVEL`: `CRITICAL|ERROR|WARNING|INFO|DEBUG|NOTSET` (also accepts `WARN`)
- `finding-extractor --verbose ...`: one-run override to emit `INFO` logs.
- `IPL_LOG_JSON`: emit machine-readable JSON logs when `true`

## Python API

```python
from finding_extractor.extraction_agent import extract_findings

result = await extract_findings(
    report_text="FINDINGS: Clear lungs. No pleural effusion.",
    exam_description="Chest XR",
    model="anthropic:claude-sonnet-4-5",
    reasoning="high",
    # Optional: receive progress messages during extraction
    # status_callback=async_fn_that_takes_a_string,
)

for finding in result.extraction.findings:
    print(f"{finding.finding_name}: {finding.presence}")
```

## Output Format

The JSON output contains:

- `exam_info` — study description, date, modality, body part
- `findings[]` — each with `finding_name`, `presence`, `location`, `attributes`, `report_text`, and optional `coding`
- `non_finding_text[]` — technique, indication, impression, etc.
- `findings[].coding.finding_code` — OIFM coding status (`coded|unmapped`), selected code, method, candidates
- `findings[].coding.location_code` — anatomic location coding status (`coded|unmapped`), selected code, method, candidates

Use `--format table` for a human-readable summary instead of JSON.

## Persistence

Use `--store` to persist reports/extractions to SQLite. See `docs/persistence-usage.md` for details.

## Batch Extraction CLI

For many reports at once, use `finding-extractor-batch` (local in-process runner).

Interactive mode:

```bash
uv run --env-file .env finding-extractor-batch run sample_data/example3 \
  --glob "*.txt" \
  --workers 4 \
  --model openai:gpt-5-mini \
  --reasoning medium \
  --validate \
  --resume \
  --mode interactive \
  --allow-slow
```

Detached mode:

```bash
uv run --env-file .env finding-extractor-batch run sample_data/example3 \
  --glob "*.txt" \
  --mode detached \
  --allow-slow
```

Watch detached status:

```bash
uv run finding-extractor-batch status --run-id <run_id> --watch
```

Configuration defaults for workers, timeouts, retries, run dir, and suffix can be set via:
- env vars (`IPL_BATCH_*`)
- `config.toml` (`[ipl]`)

Batch runs also use a runtime preflight guard:
- `--max-predicted-runtime-seconds` (default `900`)
- `--allow-slow` to explicitly override when long runs are intentional

Reference:
- `docs/configuration.md`
