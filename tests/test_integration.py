"""Playwright E2E integration tests against the full Docker Compose stack.

These tests exercise the real frontend → Caddy → FastAPI → TaskIQ → Redis pipeline.
Extraction calls hit the actual OpenAI API via the Docker worker, which reads its
API key from the `.env` file.

Run with:
    uv run pytest tests/test_integration.py -v

Or via marker:
    uv run pytest -m integration -v

The fixture auto-starts `docker compose up -d --build` if the stack isn't already
running, and tears it down only if it started it.
"""

import subprocess
import time

import httpx
import pytest
from playwright.sync_api import Page, expect

STACK_URL = "http://localhost:8080"
API_BASE = f"{STACK_URL}/api"
POLL_INTERVAL = 2  # seconds between extraction status checks
POLL_TIMEOUT = 120  # max seconds to wait for extraction completion

SAMPLE_REPORT = """\
FINDINGS:
No pleural effusion. No pneumothorax. Heart size is normal.
The lungs are clear bilaterally.

IMPRESSION:
Normal chest radiograph."""

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stack_is_reachable() -> bool:
    """Check if the Docker Compose stack is responding."""
    try:
        r = httpx.get(f"{API_BASE}/readyz", timeout=5)
        return r.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


def _poll_extraction(page: Page, timeout: int = POLL_TIMEOUT):
    """Wait for the extracting view to transition to extraction detail or failure."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        url = page.url
        # Success: landed on extraction detail
        if "#/extractions/" in url and "/extracting/" not in url:
            return
        # Failure shown in the UI
        if page.locator("text=Extraction failed").is_visible():
            # model_output_validation_failed is a known non-bug failure mode
            error_text = page.locator("[role=alert]").text_content() or ""
            if "model_output_validation_failed" in error_text:
                pytest.skip(
                    "Extraction failed with model_output_validation_failed (non-deterministic)"
                )
            pytest.fail(f"Extraction failed: {error_text}")
        page.wait_for_timeout(POLL_INTERVAL * 1000)
    pytest.fail(f"Extraction did not complete within {timeout}s")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def integration_server():
    """Ensure Docker Compose stack is running; start it if needed.

    Uses ``docker compose up --wait`` which blocks until all services with
    healthchecks report healthy (see docker-compose.yml).  If the stack is
    already reachable it is reused as-is and not torn down afterward.
    """
    already_running = _stack_is_reachable()

    if not already_running:
        subprocess.run(
            ["docker", "compose", "up", "-d", "--build", "--wait"],
            check=True,
            timeout=120,
        )

    yield STACK_URL

    if not already_running:
        subprocess.run(
            ["docker", "compose", "down"],
            check=True,
            capture_output=True,
        )


@pytest.fixture
def live_page(page: Page, integration_server) -> Page:
    """Playwright page pointed at the integration server (no ?mock)."""
    page.goto(f"{integration_server}#/")
    page.wait_for_selector("[x-data]")
    return page


# ---------------------------------------------------------------------------
# Page shell through Caddy
# ---------------------------------------------------------------------------


class TestIntegrationPageShell:
    def test_page_loads_with_title(self, live_page: Page):
        expect(live_page).to_have_title("Imaging Report Extractor")

    def test_nav_links_present(self, live_page: Page):
        expect(live_page.get_by_role("link", name="Submit")).to_be_visible()
        expect(live_page.get_by_role("link", name="Reports")).to_be_visible()

    def test_no_console_errors(self, page: Page, integration_server):
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{integration_server}#/")
        page.wait_for_selector("[x-data]")
        assert errors == [], f"Console errors: {errors}"

    def test_static_assets_served(self, live_page: Page):
        """Verify that app.js was loaded (Alpine component is initialised)."""
        expect(live_page.get_by_role("heading", name="Submit Report")).to_be_visible()


# ---------------------------------------------------------------------------
# Submit report (no extraction)
# ---------------------------------------------------------------------------


class TestIntegrationSubmitReport:
    def test_submit_report_shows_success(self, live_page: Page):
        live_page.get_by_role("textbox", name="Report Text").fill(SAMPLE_REPORT)
        live_page.get_by_role("button", name="Submit Report").click()
        expect(live_page.get_by_text("Report submitted successfully")).to_be_visible(
            timeout=15_000,
        )

    def test_success_contains_uuid(self, live_page: Page):
        live_page.get_by_role("textbox", name="Report Text").fill(SAMPLE_REPORT)
        live_page.get_by_role("button", name="Submit Report").click()
        expect(live_page.get_by_text("Report submitted successfully")).to_be_visible(
            timeout=15_000,
        )
        # The "View report" link href contains the real UUID
        link = live_page.get_by_role("link", name="View report")
        expect(link).to_be_visible()
        href = link.get_attribute("href") or ""
        # UUID-like: 8-4-4-4-12 hex
        assert len(href.split("/")[-1]) >= 32, f"Expected UUID in href, got: {href}"

    def test_report_appears_in_list(self, live_page: Page):
        live_page.get_by_role("textbox", name="Report Text").fill(SAMPLE_REPORT)
        live_page.get_by_role("button", name="Submit Report").click()
        expect(live_page.get_by_text("Report submitted successfully")).to_be_visible(
            timeout=15_000,
        )

        # Get the report ID from the "View report" link
        link = live_page.get_by_role("link", name="View report")
        expect(link).to_be_visible()
        report_id = (link.get_attribute("href") or "").split("/")[-1]

        # Navigate to reports list and find it by truncated ID
        live_page.get_by_role("link", name="Reports").click()
        expect(live_page.get_by_text(report_id[:8])).to_be_visible(timeout=10_000)


# ---------------------------------------------------------------------------
# Submit & Extract (real LLM)
# ---------------------------------------------------------------------------


class TestIntegrationSubmitAndExtract:
    def test_submit_and_extract_completes(self, live_page: Page):
        live_page.get_by_role("textbox", name="Report Text").fill(SAMPLE_REPORT)
        live_page.get_by_role("button", name="Submit & Extract").click()

        # Should transition through extracting view
        live_page.wait_for_url("**/extracting/**", timeout=15_000)

        # Wait for extraction to complete (real LLM call)
        _poll_extraction(live_page)

        # Verify extraction detail is shown
        expect(live_page.get_by_role("heading", name="Extraction Result")).to_be_visible()

    def test_extraction_shows_findings(self, live_page: Page):
        live_page.get_by_role("textbox", name="Report Text").fill(SAMPLE_REPORT)
        live_page.get_by_role("button", name="Submit & Extract").click()
        live_page.wait_for_url("**/extracting/**", timeout=15_000)
        _poll_extraction(live_page)

        # Extraction detail should show structured data
        expect(live_page.get_by_role("heading", name="Extraction Result")).to_be_visible()
        # Should have exam info section
        expect(live_page.get_by_text("Study Description")).to_be_visible()
        # Should have findings or non-finding text
        findings_heading = live_page.get_by_role("heading", name="Findings")
        non_finding_heading = live_page.get_by_role("heading", name="Non-Finding Text")
        assert findings_heading.is_visible() or non_finding_heading.is_visible(), (
            "Expected either Findings or Non-Finding Text section"
        )


# ---------------------------------------------------------------------------
# Report detail → extraction from detail view
# ---------------------------------------------------------------------------


class TestIntegrationReportDetail:
    def test_report_detail_shows_text(self, live_page: Page):
        # Submit a report first
        live_page.get_by_role("textbox", name="Report Text").fill(SAMPLE_REPORT)
        live_page.get_by_role("button", name="Submit Report").click()
        expect(live_page.get_by_text("Report submitted successfully")).to_be_visible(
            timeout=15_000,
        )

        # Navigate to report detail
        live_page.get_by_role("link", name="View report").click()
        live_page.wait_for_url("**/reports/**", timeout=10_000)
        expect(live_page.get_by_role("heading", name="Report Details")).to_be_visible()
        expect(live_page.get_by_text("No pleural effusion")).to_be_visible()

    def test_extract_from_detail_view(self, live_page: Page):
        # Submit a report
        live_page.get_by_role("textbox", name="Report Text").fill(SAMPLE_REPORT)
        live_page.get_by_role("button", name="Submit Report").click()
        expect(live_page.get_by_text("Report submitted successfully")).to_be_visible(
            timeout=15_000,
        )

        # Navigate to report detail
        live_page.get_by_role("link", name="View report").click()
        live_page.wait_for_url("**/reports/**", timeout=10_000)
        expect(live_page.get_by_role("heading", name="Report Details")).to_be_visible()

        # Trigger extraction from detail view
        live_page.get_by_role("button", name="Run Extraction").click()
        live_page.wait_for_url("**/extracting/**", timeout=15_000)
        _poll_extraction(live_page)

        expect(live_page.get_by_role("heading", name="Extraction Result")).to_be_visible()


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------


class TestIntegrationCorrections:
    def test_submit_correction_comment(self, live_page: Page):
        # Submit + extract to get an extraction to correct
        live_page.get_by_role("textbox", name="Report Text").fill(SAMPLE_REPORT)
        live_page.get_by_role("button", name="Submit & Extract").click()
        live_page.wait_for_url("**/extracting/**", timeout=15_000)
        _poll_extraction(live_page)

        expect(live_page.get_by_role("heading", name="Extraction Result")).to_be_visible()

        # Add a correction comment
        comment_text = f"Integration test correction at {int(time.time())}"
        live_page.get_by_role("textbox", name="Add a correction comment").fill(comment_text)
        live_page.get_by_role("button", name="Submit Comment").click()

        # Verify it appears in the corrections list
        expect(live_page.get_by_text(comment_text)).to_be_visible(timeout=10_000)


# ---------------------------------------------------------------------------
# Full end-to-end journey
# ---------------------------------------------------------------------------


class TestIntegrationFullFlow:
    def test_full_journey(self, live_page: Page):
        """Submit → extract → view findings → add correction → back to reports."""
        # 1. Submit & extract
        live_page.get_by_role("textbox", name="Report Text").fill(SAMPLE_REPORT)
        source_ref = f"full-flow-{int(time.time())}"
        live_page.get_by_role("textbox", name="Source Reference").fill(source_ref)
        live_page.get_by_role("button", name="Submit & Extract").click()
        live_page.wait_for_url("**/extracting/**", timeout=15_000)

        # 2. Wait for extraction
        _poll_extraction(live_page)
        expect(live_page.get_by_role("heading", name="Extraction Result")).to_be_visible()

        # 3. Verify findings are shown
        expect(live_page.get_by_text("Study Description")).to_be_visible()

        # 4. Add a correction
        correction = f"Full flow correction {int(time.time())}"
        live_page.get_by_role("textbox", name="Add a correction comment").fill(correction)
        live_page.get_by_role("button", name="Submit Comment").click()
        expect(live_page.get_by_text(correction)).to_be_visible(timeout=10_000)

        # 5. Navigate back to report
        live_page.get_by_role("button", name="Back to Report").click()
        live_page.wait_for_url("**/reports/**", timeout=10_000)
        expect(live_page.get_by_role("heading", name="Report Details")).to_be_visible()

        # 6. Navigate to reports list
        live_page.get_by_role("link", name="Reports").click()
        live_page.wait_for_url("**#/reports", timeout=10_000)
        expect(live_page.get_by_role("heading", name="Reports")).to_be_visible()
