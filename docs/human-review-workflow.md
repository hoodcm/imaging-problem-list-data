# Human Review Workflow (Gold Extractions)

This is the fastest operational workflow for creating gold extractions from `sample_data/example3` today.

## Goal

- Generate one candidate extraction JSON per report.
- Human reviewers overread and correct each candidate.
- Corrected files become the gold set.

## Inputs and Outputs

- Input reports: `sample_data/example3/*.txt`
- Candidate outputs: `sample_data/example3/<report_id>.extracted.json`
- Gold outputs: `sample_data/example3/<report_id>.gold.v1.json`

`<report_id>` here is the source filename stem (for example `s52060840`).

## Step 1: Batch-generate candidate extraction files

Run from repo root:

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

Optional model controls:

```bash
uv run --env-file .env finding-extractor-batch run sample_data/example3 \
  --glob "*.txt" \
  --workers 8 \
  --model anthropic:claude-sonnet-4-5 \
  --reasoning high \
  --timeout-seconds 600 \
  --retries 2 \
  --validate \
  --resume \
  --mode detached \
  --allow-slow
```

Equivalent Taskfile command:

```bash
task extract:example3
```

Detached mode status check:

```bash
uv run finding-extractor-batch status --run-id <run_id> --watch
```

## Step 2: Human overread using extractor UI + JSON editor

Run UI stack if needed:

```bash
docker compose up -d --build
```

Open `http://localhost:8080`.

Per report:

1. Open the source text file `sample_data/example3/<report_id>.txt`.
2. Paste it into extractor UI and run extraction (same model/reasoning used in batch).
3. Review findings/non-finding sections in UI for readability and obvious misses.
4. Open `sample_data/example3/<report_id>.extracted.json` in an editor.
5. Apply corrections directly to JSON until it reflects adjudicated truth.

Note: current UI supports comment corrections, not full structured save-as-gold editing. Gold is finalized in the JSON file.

## Step 3: Promote reviewed files to gold

When a candidate is fully reviewed:

```bash
cp sample_data/example3/<report_id>.extracted.json \
   sample_data/example3/<report_id>.gold.v1.json
```

Do this only after reviewer adjudication is complete.

## Step 4: Validate all gold files

```bash
uv run python - <<'PY'
from pathlib import Path
from finding_extractor.models import ExtractedReportFindings

gold_files = sorted(Path("sample_data/example3").glob("*.gold.v1.json"))
if not gold_files:
    raise SystemExit("No gold files found.")

for path in gold_files:
    ExtractedReportFindings.model_validate_json(path.read_text(encoding="utf-8"))
    print(f"valid {path}")
PY
```

## Definition of Done

- Every `*.txt` in `sample_data/example3` has a corresponding `*.extracted.json`.
- Every completed human review has a corresponding validated `*.gold.v1.json`.
- Gold files parse as `ExtractedReportFindings` without schema errors.
