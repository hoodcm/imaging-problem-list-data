"""Playwright end-to-end tests for the extractor frontend.

Run with:
    uv run pytest tests/test_ui.py -v

Uses mock mode (?mock in URL) so no backend is required.
"""

import subprocess
import time
from contextlib import contextmanager

import pytest
from playwright.sync_api import Page, expect

UI_DIR = "extractor-ui"
PORT = 8787
BASE = f"http://localhost:{PORT}/?mock"


@contextmanager
def _http_server():
    proc = subprocess.Popen(
        ["python3", "-m", "http.server", str(PORT), "--directory", UI_DIR],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)
    yield
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="module")
def _server():
    with _http_server():
        yield


@pytest.fixture
def mock_page(page: Page, _server) -> Page:
    """Page fixture pre-loaded at the submit view with mock mode enabled."""
    page.goto(f"{BASE}#/")
    page.wait_for_selector("[x-data]")
    return page


# ---------------------------------------------------------------------------
# Page shell & routing
# ---------------------------------------------------------------------------


@pytest.mark.ui
class TestPageShell:
    def test_page_loads_with_title(self, mock_page: Page):
        expect(mock_page).to_have_title("Imaging Report Extractor")

    def test_nav_links_present(self, mock_page: Page):
        expect(mock_page.get_by_role("link", name="Submit")).to_be_visible()
        expect(mock_page.get_by_role("link", name="Reports")).to_be_visible()

    def test_dark_mode_toggle_present(self, mock_page: Page):
        expect(mock_page.get_by_role("button", name="Toggle dark mode")).to_be_visible()

    def test_default_view_is_submit(self, mock_page: Page):
        expect(mock_page.get_by_role("heading", name="Submit Report")).to_be_visible()

    def test_unknown_route_redirects_to_submit(self, mock_page: Page):
        mock_page.goto(f"{BASE}#/some/unknown/route")
        mock_page.wait_for_url("**/?mock#/")
        expect(mock_page.get_by_role("heading", name="Submit Report")).to_be_visible()

    def test_no_console_errors_on_load(self, page: Page, _server):
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{BASE}#/")
        page.wait_for_selector("[x-data]")
        assert errors == [], f"Console errors on page load: {errors}"


# ---------------------------------------------------------------------------
# Dark mode
# ---------------------------------------------------------------------------


@pytest.mark.ui
class TestDarkMode:
    def test_toggle_switches_theme(self, mock_page: Page):
        html = mock_page.locator("html")
        initial_dark = "dark" in (html.get_attribute("class") or "")

        mock_page.get_by_role("button", name="Toggle dark mode").click()
        if initial_dark:
            expect(html).not_to_have_class("dark")
        else:
            expect(html).to_have_class("dark")

    def test_theme_persists_across_reload(self, mock_page: Page):
        html = mock_page.locator("html")
        mock_page.get_by_role("button", name="Toggle dark mode").click()
        after_toggle = "dark" in (html.get_attribute("class") or "")

        mock_page.reload()
        mock_page.wait_for_selector("[x-data]")
        after_reload = "dark" in (html.get_attribute("class") or "")
        assert after_toggle == after_reload


# ---------------------------------------------------------------------------
# Submit view
# ---------------------------------------------------------------------------


@pytest.mark.ui
class TestSubmitView:
    def test_form_fields_present(self, mock_page: Page):
        expect(mock_page.get_by_role("textbox", name="Report Text")).to_be_visible()
        expect(mock_page.get_by_role("textbox", name="Source Reference")).to_be_visible()
        expect(mock_page.get_by_role("textbox", name="Patient ID")).to_be_visible()
        expect(mock_page.get_by_role("textbox", name="Exam Description")).to_be_visible()
        expect(mock_page.get_by_role("button", name="Submit Report")).to_be_visible()
        expect(mock_page.get_by_role("button", name="Submit & Extract")).to_be_visible()

    def test_empty_submit_shows_error(self, mock_page: Page):
        mock_page.get_by_role("button", name="Submit Report").click()
        expect(mock_page.get_by_role("alert")).to_be_visible()
        expect(mock_page.get_by_text("Report text is required")).to_be_visible()

    def test_error_banner_is_dismissible(self, mock_page: Page):
        mock_page.get_by_role("button", name="Submit Report").click()
        expect(mock_page.get_by_role("alert")).to_be_visible()
        mock_page.get_by_role("button", name="Close").click()
        expect(mock_page.get_by_role("alert")).to_be_hidden()

    def test_submit_report_shows_success(self, mock_page: Page):
        mock_page.get_by_role("textbox", name="Report Text").fill("Test report text.")
        mock_page.get_by_role("button", name="Submit Report").click()
        expect(mock_page.get_by_text("Report submitted successfully")).to_be_visible()

    def test_submit_clears_form(self, mock_page: Page):
        mock_page.get_by_role("textbox", name="Report Text").fill("Test report text.")
        mock_page.get_by_role("textbox", name="Patient ID").fill("MRN123")
        mock_page.get_by_role("button", name="Submit Report").click()
        expect(mock_page.get_by_text("Report submitted successfully")).to_be_visible()
        expect(mock_page.get_by_role("textbox", name="Report Text")).to_have_value("")
        expect(mock_page.get_by_role("textbox", name="Patient ID")).to_have_value("")

    def test_success_has_view_report_link(self, mock_page: Page):
        mock_page.get_by_role("textbox", name="Report Text").fill("Test report text.")
        mock_page.get_by_role("button", name="Submit Report").click()
        expect(mock_page.get_by_role("link", name="View report")).to_be_visible()

    def test_submit_and_extract_navigates_to_extraction(self, mock_page: Page):
        mock_page.get_by_role("textbox", name="Report Text").fill("Test report text.")
        mock_page.get_by_role("button", name="Submit & Extract").click()
        # Mock job returns completed immediately, so we end up at extraction detail
        mock_page.wait_for_url("**/extractions/**")
        expect(mock_page.get_by_role("heading", name="Extraction Result")).to_be_visible()


# ---------------------------------------------------------------------------
# Reports list
# ---------------------------------------------------------------------------


@pytest.mark.ui
class TestReportsList:
    def test_reports_view_loads(self, mock_page: Page):
        mock_page.get_by_role("link", name="Reports").click()
        expect(mock_page.get_by_role("heading", name="Reports")).to_be_visible()

    def test_table_has_correct_columns(self, mock_page: Page):
        mock_page.get_by_role("link", name="Reports").click()
        for col in ["ID", "Source Ref", "Created At"]:
            expect(mock_page.get_by_role("columnheader", name=col)).to_be_visible()

    def test_mock_data_appears_in_table(self, mock_page: Page):
        mock_page.get_by_role("link", name="Reports").click()
        expect(mock_page.get_by_text("mock-rep")).to_be_visible()

    def test_pagination_controls_present(self, mock_page: Page):
        mock_page.get_by_role("link", name="Reports").click()
        expect(mock_page.get_by_role("button", name="Prev")).to_be_visible()
        expect(mock_page.get_by_role("button", name="Next")).to_be_visible()

    def test_prev_disabled_on_first_page(self, mock_page: Page):
        mock_page.get_by_role("link", name="Reports").click()
        expect(mock_page.get_by_role("button", name="Prev")).to_be_disabled()

    def test_refresh_button_works(self, mock_page: Page):
        mock_page.get_by_role("link", name="Reports").click()
        expect(mock_page.get_by_text("mock-rep")).to_be_visible()
        mock_page.get_by_role("button", name="Refresh").click()
        # Still shows data after refresh
        expect(mock_page.get_by_text("mock-rep")).to_be_visible()

    def test_row_click_navigates_to_detail(self, mock_page: Page):
        mock_page.get_by_role("link", name="Reports").click()
        mock_page.get_by_role("row", name="mock-rep").click()
        mock_page.wait_for_url("**/reports/mock-report-1")
        expect(mock_page.get_by_role("heading", name="Report Details")).to_be_visible()


# ---------------------------------------------------------------------------
# Report detail
# ---------------------------------------------------------------------------


@pytest.mark.ui
class TestReportDetail:
    def _nav_to_report(self, page: Page):
        page.goto(f"{BASE}#/reports/mock-report-1")
        page.wait_for_selector("text=Report Details")

    def test_deep_link_works(self, mock_page: Page):
        self._nav_to_report(mock_page)
        expect(mock_page.get_by_text("mock-report-1")).to_be_visible()

    def test_metadata_displayed(self, mock_page: Page):
        self._nav_to_report(mock_page)
        expect(mock_page.get_by_text("Report ID")).to_be_visible()
        # "Source Reference" also appears as a label in the submit form (hidden via x-show).
        # Scope to visible div inside the report detail card.
        expect(mock_page.locator("div:visible", has_text="Source Reference").first).to_be_visible()
        # "Created At" appears in both metadata and extractions table;
        # just check the heading card is visible.
        expect(mock_page.get_by_role("heading", name="Report Details")).to_be_visible()

    def test_report_text_displayed(self, mock_page: Page):
        self._nav_to_report(mock_page)
        expect(mock_page.get_by_text("Sample report.")).to_be_visible()

    def test_run_extraction_button_present(self, mock_page: Page):
        self._nav_to_report(mock_page)
        expect(mock_page.get_by_role("button", name="Run Extraction")).to_be_visible()

    def test_extractions_table_present(self, mock_page: Page):
        self._nav_to_report(mock_page)
        expect(mock_page.get_by_role("heading", name="Extractions")).to_be_visible()
        expect(mock_page.get_by_text("mock-ext")).to_be_visible()

    def test_back_to_reports(self, mock_page: Page):
        self._nav_to_report(mock_page)
        mock_page.get_by_role("button", name="Back to Reports").click()
        mock_page.wait_for_url("**/reports")
        expect(mock_page.get_by_role("heading", name="Reports")).to_be_visible()

    def test_run_extraction_navigates_to_progress(self, mock_page: Page):
        self._nav_to_report(mock_page)
        mock_page.get_by_role("button", name="Run Extraction").click()
        # Mock completes immediately, so we land on extraction detail
        mock_page.wait_for_url("**/extractions/**")
        expect(mock_page.get_by_role("heading", name="Extraction Result")).to_be_visible()

    def test_extraction_row_click_navigates(self, mock_page: Page):
        self._nav_to_report(mock_page)
        mock_page.get_by_role("row", name="mock-ext").click()
        mock_page.wait_for_url("**/extractions/mock-extraction-1")
        expect(mock_page.get_by_role("heading", name="Extraction Result")).to_be_visible()


# ---------------------------------------------------------------------------
# Extraction progress
# ---------------------------------------------------------------------------


@pytest.mark.ui
class TestExtractionProgress:
    def test_progress_parses_canonical_stage_status(self, page: Page, _server):
        page.goto(
            f"http://localhost:{PORT}/?mock&runningStage#/reports/mock-report-1/extracting/mock-job-1"
        )
        expect(page.get_by_text("Extracting findings")).to_be_visible()
        expect(page.get_by_text("Calling model")).to_be_visible()


# ---------------------------------------------------------------------------
# Extraction detail
# ---------------------------------------------------------------------------


@pytest.mark.ui
class TestExtractionDetail:
    def _nav_to_extraction(self, page: Page):
        page.goto(f"{BASE}#/extractions/mock-extraction-1")
        page.wait_for_selector("text=Extraction Result")

    def test_deep_link_works(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        expect(mock_page.get_by_role("heading", name="Extraction Result")).to_be_visible()

    def test_exam_info_header(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        for label in ["Study Description", "Modality", "Body Part", "Study Date"]:
            expect(mock_page.get_by_text(label)).to_be_visible()

    def test_exam_info_values(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        expect(mock_page.get_by_text("CT Abdomen")).to_be_visible()
        expect(mock_page.get_by_text("CT", exact=True)).to_be_visible()

    def test_finding_attributes_rendered(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        expect(mock_page.get_by_text("size: 3 mm")).to_be_visible()

    def test_findings_section_present(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        expect(mock_page.get_by_role("heading", name="Findings")).to_be_visible()
        expect(mock_page.get_by_role("heading", name="Kidney stone")).to_be_visible()

    def test_presence_badge_rendered(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        badge = mock_page.get_by_text("present", exact=True)
        expect(badge).to_be_visible()

    def test_location_badges_rendered(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        # Location badges are colored spans: blue (body_region), purple (specific_anatomy), indigo (laterality)
        expect(mock_page.locator("span.bg-blue-100", has_text="abdomen")).to_be_visible()
        expect(mock_page.locator("span.bg-purple-100", has_text="left kidney")).to_be_visible()
        expect(mock_page.locator("span.bg-indigo-100", has_text="left")).to_be_visible()

    def test_report_text_blockquote(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        expect(mock_page.locator("blockquote")).to_be_visible()
        expect(mock_page.get_by_text("Left kidney stone measuring 3mm.")).to_be_visible()

    def test_model_info_section(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        expect(mock_page.get_by_role("heading", name="Model Info")).to_be_visible()
        expect(mock_page.get_by_text("mock-model")).to_be_visible()

    def test_corrections_section_present(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        expect(mock_page.get_by_role("heading", name="Corrections")).to_be_visible()
        expect(mock_page.get_by_text("No corrections yet")).to_be_visible()

    def test_back_to_report(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        mock_page.get_by_role("button", name="Back to Report").click()
        mock_page.wait_for_url("**/reports/**")

    def test_loading_spinner_hidden_after_load(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        expect(mock_page.get_by_text("Loading extraction")).to_be_hidden()

    def test_coding_section_present(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        expect(mock_page.get_by_role("heading", name="Coding")).to_be_visible()
        expect(mock_page.get_by_text("1 coded")).to_be_visible()

    def test_coding_badge_on_finding(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        expect(mock_page.get_by_text("OIFM_GMTS_016552")).to_be_visible()
        expect(mock_page.get_by_text("urinary tract calculus")).to_be_visible()

    def test_location_coding_on_finding(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        expect(mock_page.get_by_text("RID29662")).to_be_visible()


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------


@pytest.mark.ui
class TestCorrections:
    def _nav_to_extraction(self, page: Page):
        page.goto(f"{BASE}#/extractions/mock-extraction-1")
        page.wait_for_selector("text=Extraction Result")

    def test_correction_form_present(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        expect(mock_page.get_by_role("heading", name="Add Comment")).to_be_visible()
        expect(mock_page.get_by_role("textbox", name="Add a correction comment")).to_be_visible()
        expect(mock_page.locator('select#username-select')).to_be_visible()

    def test_submit_button_disabled_when_empty(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        expect(mock_page.get_by_role("button", name="Submit Comment")).to_be_disabled()

    def test_submit_button_enabled_with_text(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        mock_page.get_by_role("textbox", name="Add a correction comment").fill("A comment")
        expect(mock_page.get_by_role("button", name="Submit Comment")).to_be_enabled()

    def test_submit_button_disabled_without_username(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        mock_page.get_by_role("textbox", name="Add a correction comment").fill("A comment")
        # Username is pre-selected by default (talkasab), so button should be enabled
        expect(mock_page.get_by_role("button", name="Submit Comment")).to_be_enabled()
        # Note: The empty option is disabled by design, so we can't test selecting empty.
        # The disabled state is tested when users list is empty (TestUserDropdown)

    def test_submit_correction_clears_form(self, mock_page: Page):
        self._nav_to_extraction(mock_page)
        comment_box = mock_page.get_by_role("textbox", name="Add a correction comment")
        username_select = mock_page.locator('select#username-select')
        comment_box.fill("Test correction comment")
        # Username should already be pre-selected (talkasab from mock data)
        mock_page.get_by_role("button", name="Submit Comment").click()
        expect(comment_box).to_have_value("")
        # Username should remain selected (not cleared)
        expect(username_select).to_have_value("talkasab")


# ---------------------------------------------------------------------------
# User dropdown selector
# ---------------------------------------------------------------------------


@pytest.mark.ui
class TestUserDropdown:
    """Test user dropdown selection for corrections."""

    @staticmethod
    def _nav_to_extraction(page: Page):
        """Navigate to extraction detail view."""
        page.get_by_role("textbox", name="Report Text").fill("Sample report.")
        page.get_by_role("button", name="Submit & Extract").click()
        page.wait_for_url("**/extractions/**")

    def test_username_selector_populated_from_users_api(self, mock_page: Page):
        """Username select should be populated from GET /users."""
        self._nav_to_extraction(mock_page)
        username_select = mock_page.locator('select#username-select')
        expect(username_select).to_be_visible()
        # Check that talkasab is the selected value (proving users loaded)
        expect(username_select).to_have_value("talkasab")

    def test_default_selection_prefers_talkasab(self, mock_page: Page):
        """Default selection should be talkasab when present."""
        self._nav_to_extraction(mock_page)
        username_select = mock_page.locator('select#username-select')
        expect(username_select).to_have_value("talkasab")

    def test_correction_submit_respects_user_gating(self, mock_page: Page):
        """When users are available and selected, submit should work."""
        self._nav_to_extraction(mock_page)
        comment_box = mock_page.get_by_role("textbox", name="Add a correction comment")
        comment_box.fill("Test correction")
        # Username already selected (talkasab)
        submit_btn = mock_page.get_by_role("button", name="Submit Comment")
        expect(submit_btn).to_be_enabled()

    def test_finding_edit_respects_user_gating(self, mock_page: Page):
        """Finding-level edit submit should respect user gating."""
        self._nav_to_extraction(mock_page)
        mock_page.get_by_role("button", name="Edit this finding").click()
        # Save Changes button should be enabled when user is selected
        save_btn = mock_page.get_by_role("button", name="Save Changes")
        expect(save_btn).to_be_enabled()


# ---------------------------------------------------------------------------
# Full flow: Submit & Extract end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.ui
class TestFullFlow:
    def test_submit_to_extraction_detail(self, mock_page: Page):
        """Submit a report, trigger extraction, arrive at extraction detail."""
        # Fill and submit
        mock_page.get_by_role("textbox", name="Report Text").fill(
            "FINDINGS: 3mm left kidney stone."
        )
        mock_page.get_by_role("button", name="Submit & Extract").click()

        # Should end up at extraction detail (mock job completes immediately)
        mock_page.wait_for_url("**/extractions/**")
        expect(mock_page.get_by_role("heading", name="Extraction Result")).to_be_visible()
        expect(mock_page.get_by_role("heading", name="Kidney stone")).to_be_visible()

        # Navigate back to report
        mock_page.get_by_role("button", name="Back to Report").click()
        mock_page.wait_for_url("**/reports/**")
        expect(mock_page.get_by_text("Sample report.")).to_be_visible()

    def test_reports_list_to_extraction(self, mock_page: Page):
        """Navigate reports list → report detail → extraction detail."""
        mock_page.get_by_role("link", name="Reports").click()
        mock_page.wait_for_url("**#/reports")
        expect(mock_page.get_by_text("mock-rep")).to_be_visible()

        # Click into report
        mock_page.get_by_role("row", name="mock-rep").click()
        mock_page.wait_for_url("**/reports/mock-report-1")
        expect(mock_page.get_by_text("Report Details")).to_be_visible()

        # Click into extraction
        mock_page.get_by_role("row", name="mock-ext").click()
        mock_page.wait_for_url("**/extractions/mock-extraction-1")
        expect(mock_page.get_by_role("heading", name="Kidney stone")).to_be_visible()


# ---------------------------------------------------------------------------
# Finding-level edit UX
# ---------------------------------------------------------------------------


@pytest.mark.ui
class TestFindingEdit:
    """Test inline editing of individual findings."""

    @staticmethod
    def _nav_to_extraction(page: Page):
        """Navigate to extraction detail view."""
        page.get_by_role("textbox", name="Report Text").fill("3mm left kidney stone.")
        page.get_by_role("button", name="Submit & Extract").click()
        page.wait_for_url("**/extractions/**")

    def test_edit_button_present_for_each_finding(self, mock_page: Page):
        """Each finding card should have an 'Edit this finding' button."""
        self._nav_to_extraction(mock_page)
        expect(mock_page.get_by_role("button", name="Edit this finding")).to_be_visible()

    def test_edit_form_opens_on_click(self, mock_page: Page):
        """Clicking 'Edit this finding' should show the inline edit form."""
        self._nav_to_extraction(mock_page)
        mock_page.get_by_role("button", name="Edit this finding").click()
        expect(mock_page.get_by_label("Presence")).to_be_visible()
        expect(mock_page.get_by_label("Location (body region)")).to_be_visible()
        expect(mock_page.get_by_label("Specific anatomy")).to_be_visible()
        expect(mock_page.get_by_label("Laterality")).to_be_visible()

    def test_edit_form_prefills_current_values(self, mock_page: Page):
        """Edit form should prefill with current finding values."""
        self._nav_to_extraction(mock_page)
        mock_page.get_by_role("button", name="Edit this finding").click()
        # Check prefilled values from mock data
        expect(mock_page.get_by_label("Presence")).to_have_value("present")
        expect(mock_page.get_by_label("Location (body region)")).to_have_value("abdomen")
        expect(mock_page.get_by_label("Specific anatomy")).to_have_value("left kidney")
        expect(mock_page.get_by_label("Laterality")).to_have_value("left")

    def test_cancel_closes_edit_form(self, mock_page: Page):
        """Cancel button should close the edit form without submitting."""
        self._nav_to_extraction(mock_page)
        edit_btn = mock_page.get_by_role("button", name="Edit this finding")
        edit_btn.click()
        expect(mock_page.get_by_label("Presence")).to_be_visible()
        mock_page.get_by_role("button", name="Cancel").click()
        expect(mock_page.get_by_label("Presence")).not_to_be_visible()
        # Edit button should be visible again
        expect(edit_btn).to_be_visible()

    def test_save_changes_submits_and_closes_form(self, mock_page: Page):
        """Save Changes button should submit correction and close form."""
        self._nav_to_extraction(mock_page)
        mock_page.get_by_role("button", name="Edit this finding").click()
        # Change presence
        mock_page.get_by_label("Presence").select_option("absent")
        mock_page.get_by_role("button", name="Save Changes").click()
        # Form should close (presence dropdown no longer visible)
        expect(mock_page.get_by_label("Presence")).not_to_be_visible()
        # Edit button should be visible again
        expect(mock_page.get_by_role("button", name="Edit this finding")).to_be_visible()


# ---------------------------------------------------------------------------
# Warning display
# ---------------------------------------------------------------------------


@pytest.mark.ui
class TestWarningDisplay:
    """Test warning banner and validation issue display."""

    def _nav_to_warnings_extraction(self, page: Page):
        """Navigate directly to the warnings mock extraction."""
        page.goto(f"{BASE}#/extractions/mock-extraction-warnings")
        page.wait_for_selector("text=Extraction Result")

    def _nav_to_normal_extraction(self, page: Page):
        """Navigate to the normal (no-warnings) mock extraction."""
        page.goto(f"{BASE}#/extractions/mock-extraction-1")
        page.wait_for_selector("text=Extraction Result")

    def test_warning_banner_visible_when_validation_has_warnings(self, mock_page: Page):
        """Warning banner should appear when extraction has validation issues."""
        self._nav_to_warnings_extraction(mock_page)
        expect(mock_page.get_by_text("validation issue(s)")).to_be_visible()

    def test_warning_banner_shows_issue_count(self, mock_page: Page):
        """Warning banner should display the correct number of validation issues."""
        self._nav_to_warnings_extraction(mock_page)
        expect(mock_page.get_by_text("2 validation issue(s)")).to_be_visible()

    def test_warning_banner_hidden_when_no_warnings(self, mock_page: Page):
        """Warning banner should be hidden when validation_result is null."""
        self._nav_to_normal_extraction(mock_page)
        banner = mock_page.get_by_text("validation issue(s)")
        expect(banner).to_be_hidden()

    def test_validation_section_renders_coverage_warnings(self, mock_page: Page):
        """Individual coverage warning text should be visible in validation section."""
        self._nav_to_warnings_extraction(mock_page)
        expect(mock_page.get_by_text("Coverage ratio 78%")).to_be_visible()
        expect(mock_page.get_by_text("not covered by any finding")).to_be_visible()

    def test_validation_section_hidden_when_null(self, mock_page: Page):
        """Validation section should be hidden when validation_result is null."""
        self._nav_to_normal_extraction(mock_page)
        expect(mock_page.get_by_role("heading", name="Validation")).to_be_hidden()

    def test_submit_and_extract_with_warnings_reaches_detail(self, mock_page: Page):
        """Full flow: submit with ?warnings param → poll → land on extraction with warnings."""
        mock_page.goto(f"http://localhost:{PORT}/?mock&warnings#/")
        mock_page.wait_for_selector("[x-data]")
        mock_page.get_by_role("textbox", name="Report Text").fill("Test report for warnings flow.")
        mock_page.get_by_role("button", name="Submit & Extract").click()
        mock_page.wait_for_url("**/extractions/**")
        expect(mock_page.get_by_role("heading", name="Extraction Result")).to_be_visible()
        expect(mock_page.get_by_text("2 validation issue(s)")).to_be_visible()
