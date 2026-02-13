# Extraction Frontend Usage Guide

The extraction frontend is a browser-based UI for submitting radiology reports, triggering finding extraction, and reviewing results.

## Running the Frontend

### Development (no backend needed)

Serve the static files and open in mock mode:

```bash
cd extractor-ui
python3 -m http.server 8000
# Open http://localhost:8000/?mock
```

Mock mode (`?mock` query parameter) uses an in-memory mock API layer so no backend is required. All views are functional with sample data.

### Production (Docker Compose)

The full stack (Caddy + API + worker + Redis) runs via Docker Compose:

```bash
docker compose up -d --build
# Open http://localhost:8080 (no ?mock parameter)
```

Caddy serves the static files from `extractor-ui/` at `/` and proxies `/api/*` to the FastAPI backend. See [`docs/dev-ops.md`](../docs/dev-ops.md) for details.

## Views

### Submit Report

The landing page (`#/`). Paste a radiology report and submit it.

![Submit form](screenshots/submit-view.png)

**Fields:**
- **Report Text** (required): The radiology report to analyze.
- **Source Reference** (optional): An external identifier for the report.
- **Patient ID** (optional): Patient identifier (e.g., MRN) to associate with the report.
- **Exam Description** (optional): A hint like "CT Abdomen" to help the extraction model.
- **Model** (optional): Override the server's default extraction model (e.g., `openai:gpt-4o`).
- **Reasoning** (optional): Override the server's default reasoning effort level.

**Actions:**
- **Submit Report**: Saves the report only. Shows a success message with a link to the report.
- **Submit & Extract**: Saves the report and immediately starts extraction. Navigates to the progress view, then automatically to the extraction result when complete.

![Submit form with report filled in](screenshots/submit-filled.png)

### Reports List

Browse previously submitted reports (`#/reports`).

![Reports list](screenshots/reports-list.png)

- Click any row to view the report detail.
- Use **Prev/Next** to paginate (20 reports per page).
- Click **Refresh** to reload the current page.

### Report Detail

View a single report and its extraction history (`#/reports/{id}`).

![Report detail](screenshots/report-detail.png)

- Shows report text and metadata.
- **Run Extraction** triggers a new extraction with optional model/reasoning overrides.
- The **Extractions** table lists all prior extractions; click a row to view results.

### Extraction Progress

Shown while an extraction job is running (`#/reports/{id}/extracting/{job_id}`). Displays a spinner and polls the backend every 2 seconds. Automatically navigates to the extraction detail when the job completes. If the job fails, shows an error with a retry link.

### Extraction Detail

View the structured extraction results (`#/extractions/{id}`).

![Extraction detail](screenshots/extraction-detail.png)

Sections:
- **Exam Info**: Study description, modality, body part, study date.
- **Findings**: Each finding shows:
  - **Finding name** with **explicit label**
  - **Presence badge** (present/absent/possible/indeterminate)
  - **Location** (body region, specific anatomy, laterality) with explicit label
  - **Attributes** with explicit label (key-value pairs)
  - **Quote from Report** with explicit label (verbatim text excerpt)
  - **Edit this finding** button: Opens inline edit form for per-finding corrections
- **Non-Finding Text**: Categorized text segments that aren't findings (e.g., clinical history, technique).
- **Validation**: Warnings and errors from the output validator, if any.
- **Model Info**: Which model and reasoning level produced the extraction.
- **Corrections**: List of submitted corrections with author attribution.

#### Inline Finding Edits

Click **Edit this finding** on any finding card to open an inline edit form. This allows you to submit an `update_finding` correction targeting that specific finding.

**Editable fields:**
- **Presence**: Select from present, absent, possible, or indeterminate
- **Location** (body region): Text input for the anatomical region
- **Specific anatomy**: Text input for detailed anatomical location
- **Laterality**: Text input (left, right, bilateral, etc.)
- **Attributes**: JSON object input for custom key-value attributes (e.g., `{"size": "3mm", "change": "new"}`)
- **Comment** (optional): Explanation of why this correction was made

**Actions:**
- **Save Changes**: Submits an `update_finding` correction with your changes and closes the form
- **Cancel**: Closes the form without submitting

The inline edit form prefills with the finding's current values. After submission, the correction is recorded (visible in the Corrections section) and the form closes.

#### Global Comment-Only Corrections

Below the findings, a **Corrections** section provides:
- List of all corrections with type badges and author info
- **Add Comment** form: For extraction-level feedback (not tied to a specific finding)
- **Username selector**: Dropdown populated from registered users, defaults to `talkasab` when available

**Correction submission behavior:**
- Username is pre-selected automatically when users load successfully
- If users fail to load or the list is empty, correction submission is disabled and an error message is shown
- Both global comment submissions and finding-level edits require a valid user selection

**Note:** finding-level edits and global comments coexist — use finding edits for corrections to specific extracted findings, and global comments for overall feedback.

## Dark Mode

Toggle with the sun/moon button in the top-right corner. The preference is saved in localStorage and persists across sessions. Dark mode is active by default; choosing light mode opts out.
