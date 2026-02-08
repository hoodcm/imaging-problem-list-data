#!/usr/bin/env bash
set -euo pipefail

# Smoke test for the running API server.
# Requires: curl, jq
# Optional env vars:
#   BASE_URL (default: http://localhost:8001)
#   REPORT_TEXT (default: "FINDINGS: No pleural effusion.")
#   POLL_SECONDS (default: 60)

BASE_URL="${BASE_URL:-http://localhost:8001}"
REPORT_TEXT="${REPORT_TEXT:-FINDINGS: No pleural effusion.}"
POLL_SECONDS="${POLL_SECONDS:-60}"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required" >&2
  exit 1
fi

echo "Checking API health at ${BASE_URL}..."
curl -fsS "${BASE_URL}/api/reports" >/dev/null

echo "Creating report..."
report_json="$(
  curl -fsS -X POST "${BASE_URL}/api/reports" \
    -H "Content-Type: application/json" \
    -d "$(jq -cn --arg report_text "$REPORT_TEXT" '{report_text: $report_text}')"
)"
report_id="$(echo "$report_json" | jq -r '.id')"
echo "report_id=${report_id}"

echo "Triggering extraction..."
extract_json="$(
  curl -fsS -X POST "${BASE_URL}/api/reports/${report_id}/extract" \
    -H "Content-Type: application/json" \
    -d '{}'
)"
job_id="$(echo "$extract_json" | jq -r '.job_id')"
echo "job_id=${job_id}"

echo "Polling job state..."
job_json="{}"
job_state="unknown"
for _ in $(seq 1 "$POLL_SECONDS"); do
  job_json="$(curl -fsS "${BASE_URL}/api/jobs/${job_id}")"
  job_state="$(echo "$job_json" | jq -r '.status')"
  if [[ "$job_state" == "completed" || "$job_state" == "failed" ]]; then
    break
  fi
  sleep 1
done

echo "job_state=${job_state}"
echo "job_json=${job_json}"

if [[ "$job_state" != "completed" && "$job_state" != "failed" ]]; then
  echo "Timed out waiting for terminal job status after ${POLL_SECONDS}s." >&2
  exit 1
fi

if [[ "$job_state" == "failed" ]]; then
  echo "Extraction job failed: $(echo "$job_json" | jq -r '.error')" >&2
  exit 1
fi

echo "Listing reports and report extractions..."
report_count="$(curl -fsS "${BASE_URL}/api/reports" | jq 'length')"
report_extractions_json="$(curl -fsS "${BASE_URL}/api/reports/${report_id}/extractions")"
report_extractions_count="$(echo "$report_extractions_json" | jq 'length')"
echo "report_count=${report_count}"
echo "report_extractions_count=${report_extractions_count}"

extraction_id="$(echo "$job_json" | jq -r '.extraction_id // empty')"
if [[ -z "$extraction_id" ]]; then
  echo "No extraction_id present for completed job." >&2
  exit 1
fi

echo "Fetching extraction detail..."
extraction_json="$(curl -fsS "${BASE_URL}/api/extractions/${extraction_id}")"
echo "extraction_id=${extraction_id}"
echo "extraction_model=$(echo "$extraction_json" | jq -r '.model_name')"

echo "Creating + listing one correction..."
correction_json="$(
  curl -fsS -X POST "${BASE_URL}/api/extractions/${extraction_id}/corrections" \
    -H "Content-Type: application/json" \
    -d '{"correction_type":"comment","comment":"smoke","created_by":"smoke-script"}'
)"
correction_id="$(echo "$correction_json" | jq -r '.id')"
corrections_count="$(curl -fsS "${BASE_URL}/api/extractions/${extraction_id}/corrections" | jq 'length')"
echo "correction_id=${correction_id}"
echo "corrections_count=${corrections_count}"

echo "Smoke test completed."
