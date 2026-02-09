"""Smoke test runner for a running API server.

Task targets call this module; networking and polling logic live here.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class SmokeConfig:
    base_url: str
    report_text: str
    poll_seconds: int
    health_wait_seconds: int
    timeout_seconds: float


def _normalize_base_url(raw: str) -> str:
    return raw.rstrip("/")


def _expect_dict(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{context}: expected JSON object, got {type(value).__name__}")
    return value


def _expect_list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise RuntimeError(f"{context}: expected JSON list, got {type(value).__name__}")
    return value


def _request_json(
    client: httpx.Client,
    *,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    try:
        response = client.request(method=method, url=path, json=payload)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip()
        raise RuntimeError(f"{method} {path} failed ({exc.response.status_code}): {detail}") from exc
    except (httpx.RequestError, ValueError) as exc:
        raise RuntimeError(f"{method} {path} failed: {exc}") from exc


def _wait_for(
    action: Callable[[], Any | None],
    *,
    timeout_seconds: int,
    interval_seconds: float,
    timeout_message: str,
) -> Any:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = action()
            if result is not None:
                return result
        except Exception as exc:  # pragma: no cover - exercised in runtime smoke usage
            last_error = exc
        time.sleep(interval_seconds)
    if last_error is not None:
        raise RuntimeError(timeout_message) from last_error
    raise RuntimeError(timeout_message)


def run_smoke(config: SmokeConfig) -> None:
    print(f"Checking API health at {config.base_url}...")
    with httpx.Client(base_url=config.base_url, timeout=config.timeout_seconds) as client:
        _wait_for(
            lambda: _request_json(client, method="GET", path="/api/readyz"),
            timeout_seconds=config.health_wait_seconds,
            interval_seconds=1.0,
            timeout_message=(
                f"API did not become healthy within {config.health_wait_seconds}s "
                f"at {config.base_url}"
            ),
        )

        print("Creating report...")
        report_json = _expect_dict(
            _request_json(
                client,
                method="POST",
                path="/api/reports",
                payload={"report_text": config.report_text},
            ),
            "POST /api/reports",
        )
        report_id = str(report_json.get("id") or "")
        if not report_id:
            raise RuntimeError("POST /api/reports missing id")
        print(f"report_id={report_id}")

        print("Triggering extraction...")
        dispatch_json = _expect_dict(
            _request_json(
                client,
                method="POST",
                path=f"/api/reports/{report_id}/extract",
                payload={},
            ),
            "POST /api/reports/{id}/extract",
        )
        job_id = str(dispatch_json.get("job_id") or "")
        if not job_id:
            raise RuntimeError("POST /api/reports/{id}/extract missing job_id")
        print(f"job_id={job_id}")

        print("Polling job state...")

        def fetch_terminal_job() -> dict[str, Any] | None:
            current = _expect_dict(
                _request_json(client, method="GET", path=f"/api/jobs/{job_id}"),
                "GET /api/jobs/{id}",
            )
            status = str(current.get("status") or "")
            if status in {"completed", "failed"}:
                return current
            return None

        job_json = _expect_dict(
            _wait_for(
                fetch_terminal_job,
                timeout_seconds=config.poll_seconds,
                interval_seconds=1.0,
                timeout_message=f"Timed out waiting for terminal job status after {config.poll_seconds}s",
            ),
            "GET /api/jobs/{id}",
        )

        job_state = str(job_json.get("status") or "unknown")
        print(f"job_state={job_state}")
        print(f"job_json={json.dumps(job_json, separators=(',', ':'))}")
        if job_state == "failed":
            raise RuntimeError(f"Extraction job failed: {job_json.get('error')}")
        if job_state != "completed":
            raise RuntimeError(f"Unexpected terminal job status: {job_state}")

        print("Listing reports and report extractions...")
        report_count = len(
            _expect_list(_request_json(client, method="GET", path="/api/reports"), "GET /api/reports")
        )
        report_extractions = _expect_list(
            _request_json(client, method="GET", path=f"/api/reports/{report_id}/extractions"),
            "GET /api/reports/{id}/extractions",
        )
        print(f"report_count={report_count}")
        print(f"report_extractions_count={len(report_extractions)}")

        extraction_id = str(job_json.get("extraction_id") or "")
        if not extraction_id:
            raise RuntimeError("Completed job missing extraction_id")

        print("Fetching extraction detail...")
        extraction_json = _expect_dict(
            _request_json(client, method="GET", path=f"/api/extractions/{extraction_id}"),
            "GET /api/extractions/{id}",
        )
        print(f"extraction_id={extraction_id}")
        print(f"extraction_model={extraction_json.get('model_name')}")

        print("Creating + listing one correction...")
        correction_json = _expect_dict(
            _request_json(
                client,
                method="POST",
                path=f"/api/extractions/{extraction_id}/corrections",
                payload={"correction_type": "comment", "comment": "smoke", "created_by": "smoke-script"},
            ),
            "POST /api/extractions/{id}/corrections",
        )
        correction_id = str(correction_json.get("id") or "")
        if not correction_id:
            raise RuntimeError("POST /api/extractions/{id}/corrections missing id")
        corrections = _expect_list(
            _request_json(client, method="GET", path=f"/api/extractions/{extraction_id}/corrections"),
            "GET /api/extractions/{id}/corrections",
        )
        print(f"correction_id={correction_id}")
        print(f"corrections_count={len(corrections)}")
        print("Smoke test completed.")


def parse_args() -> SmokeConfig:
    parser = argparse.ArgumentParser(description="Run API smoke test against a running backend.")
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://localhost:8001"))
    parser.add_argument(
        "--report-text",
        default=os.getenv("REPORT_TEXT", "FINDINGS: No pleural effusion."),
    )
    parser.add_argument("--poll-seconds", type=int, default=int(os.getenv("POLL_SECONDS", "60")))
    parser.add_argument(
        "--health-wait-seconds",
        type=int,
        default=int(os.getenv("HEALTH_WAIT_SECONDS", "60")),
    )
    parser.add_argument("--timeout-seconds", type=float, default=float(os.getenv("REQUEST_TIMEOUT", "10")))
    args = parser.parse_args()
    return SmokeConfig(
        base_url=_normalize_base_url(args.base_url),
        report_text=args.report_text,
        poll_seconds=args.poll_seconds,
        health_wait_seconds=args.health_wait_seconds,
        timeout_seconds=args.timeout_seconds,
    )


def main() -> None:
    run_smoke(parse_args())


if __name__ == "__main__":
    main()
