"""Pydantic AI agent for extracting structured findings from radiology reports.

This module defines the extraction agent with:
- Instructions with detailed extraction guidance
- Few-shot examples
- Model configuration with reasoning/thinking support (OpenAI, Anthropic, Google, Ollama)
- Structured output via Tool Output mode (default)
- Post-extraction validation
"""

import os

from anthropic.types.beta.beta_thinking_config_disabled_param import (
    BetaThinkingConfigDisabledParam,
)
from anthropic.types.beta.beta_thinking_config_enabled_param import (
    BetaThinkingConfigEnabledParam,
)
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.anthropic import AnthropicModelSettings
from pydantic_ai.models.google import GoogleModelSettings
from pydantic_ai.models.openai import OpenAIChatModelSettings
from pydantic_ai.settings import ModelSettings

from finding_extractor.examples import get_formatted_examples
from finding_extractor.models import ExtractorDeps, ReportExtraction, ValidationResult

# Default model configuration
DEFAULT_MODEL = "openai:gpt-5-mini"

# Default reasoning level per provider (when --reasoning is omitted)
PROVIDER_DEFAULT_REASONING: dict[str, str] = {
    "openai": "medium",
    "anthropic": "medium",
    "google": "medium",
    "ollama": "none",
}

# Anthropic thinking budget mapping: level -> (budget_tokens, max_tokens)
ANTHROPIC_THINKING_BUDGETS: dict[str, tuple[int, int]] = {
    "minimal": (1024, 8192),
    "low": (1024, 8192),
    "medium": (4096, 8192),
    "high": (10240, 16384),
}

INSTRUCTIONS = """\
You are a medical AI specialized in extracting structured findings from radiology reports.

Your task is to read a radiology report and extract all clinical findings into a structured format.

## CORE INSTRUCTIONS

1. **Read systematically** — Go through the report section by section
2. **Extract ALL findings** — including present, absent, possible, and indeterminate findings
3. **Use concise clinical names** — e.g., "renal calculus", "hepatic steatosis", "pneumonia"
4. **Normal findings are absent abnormalities**:
    - "clear lungs" → "pulmonary airspace abnormality", absent
    - "normal cardiac silhouette" → "cardiomegaly", absent
    - "normal lung volumes" → "pulmonary volume abnormality", absent
5. **When quoting report text, BE EXACT** — verbatim excerpts only, never paraphrase
6. **Infer location from context** — use exam type and report section to determine body_region when not explicitly stated
7. **Extract all relevant attributes** — size, acuity, change_from_prior, severity, count, morphology
8. **Handle multiple instances** — create separate findings for each distinct instance \
(e.g., right vs left kidney stones)
9. **Classify non-finding text** — technique, indication, comparison, clinical history, \
and impression go in non_finding_text
10. **Use "possible" presence** — for hedged/uncertain language like "raising the possibility of", \
"suggestive of", "cannot exclude"

## PRESENCE VALUES

- **present**: The finding is explicitly stated as present
- **absent**: The finding is explicitly stated as absent \
(e.g., "no ascites", "normal hilar contours", "unremarkable")
- **indeterminate**: Cannot be determined from the report
- **possible**: Hedged/uncertain language \
("raising the possibility of", "suggestive of", "cannot exclude")

## ATTRIBUTE KEYS TO WATCH FOR

- **size**: measurements like "3 mm", "4-5 mm", "4.2 cm"
- **acuity**: "acute", "chronic", "healed", "old", "subacute"
- **change_from_prior**: "stable", "unchanged", "new", "larger", "increased", "decreased", \
"resolved", "similar in size and number"
- **severity**: "mild", "moderate", "severe", "advanced"
- **count**: "2", "multiple", "bilateral", "several"
- **morphology**: "nonobstructing", "calcified", "flowing osteophytes", "focal", "diffuse"

## LOCATION GUIDANCE

The body_region MUST be one of: "chest", "abdomen", "pelvis", "head", "neck", "spine", "upper extremity", "lower extremity", "breast"

If you can't be more specific based on the report text, infer location as specifically as you can using exam type:

- CT/MR Abdomen/Pelvis → body_region: "abdomen" or "pelvis"
- Chest XR/CT → body_region: "chest"
- Brain MR/CT → body_region: "head"
- MSK XR/MR shoulder → body_region: "upper extremity"

For specific_anatomy, extract the most specific location mentioned:
- "lower lobe of right lung", "left kidney interpolar region", "T9 vertebral body", "mitral annulus"

For laterality, use when stated or clearly implied:
- "left", "right", "bilateral", or None

## NON-FINDING TEXT CATEGORIES

The category MUST be one of: "metadata", "technique", "indication", "comparison", "clinical_history", "impression", "other"

- **metadata**: Report header, date, exam type
- **technique**: Technical details of how the exam was performed
- **indication**: Clinical indication for the exam
- **comparison**: Prior exams mentioned for comparison
- **clinical_history**: Patient history, symptoms
- **impression**: Impression/conclusion section (findings here are typically restated from above)
- **other**: Section headers, formatting, anything else without findings

## EXAMPLES

{examples}

## OUTPUT FORMAT

Return a ReportExtraction object with:
- exam_info: Exam metadata (study_description, study_date in YYYY-MM-DD format, modality, body_part)
- findings: List of ExtractedFinding objects
- non_finding_text: List of NonFindingText objects

Each ExtractedFinding must have:
- finding_name: Concise clinical term
- presence: One of "present", "absent", "indeterminate", "possible"
- location: FindingLocation with body_region, specific_anatomy, laterality (when applicable)
- attributes: List of FindingAttribute key-value pairs
- report_text: EXACT verbatim quote from the report

Remember: QUOTE MUST BE VERBATIM. Do not paraphrase or summarize the report text.\
"""


def _build_instructions() -> str:
    """Build the agent instructions with embedded few-shot examples."""
    examples = get_formatted_examples()
    return INSTRUCTIONS.format(examples=examples)


def _detect_provider(model: str) -> str | None:
    """Detect the provider from a model string prefix.

    Args:
        model: Model identifier (e.g., "openai:gpt-5-mini", "anthropic:claude-sonnet-4-5")

    Returns:
        Provider name ("openai", "anthropic", "google", "ollama") or None if unknown
    """
    if ":" not in model:
        return None

    prefix = model.split(":")[0]
    prefix_map = {
        "openai": "openai",
        "openai-chat": "openai",
        "openai-responses": "openai",
        "anthropic": "anthropic",
        "google-gla": "google",
        "google-vertex": "google",
        "ollama": "ollama",
    }
    return prefix_map.get(prefix)


def _build_openai_settings(reasoning_level: str) -> OpenAIChatModelSettings | None:
    """Build OpenAI model settings with reasoning effort."""
    if reasoning_level == "none":
        return None
    return OpenAIChatModelSettings(openai_reasoning_effort=reasoning_level)  # type: ignore[typeddict-item]


def _build_anthropic_settings(reasoning_level: str) -> AnthropicModelSettings | None:
    """Build Anthropic model settings with extended thinking."""
    if reasoning_level == "none":
        # Unlike OpenAI/Google, Anthropic needs an explicit disable — returning None
        # would leave agent-level defaults (thinking enabled) in effect.
        thinking: BetaThinkingConfigDisabledParam = {"type": "disabled"}
        return AnthropicModelSettings(
            anthropic_thinking=thinking,
        )
    budget_tokens, max_tokens = ANTHROPIC_THINKING_BUDGETS[reasoning_level]
    thinking: BetaThinkingConfigEnabledParam = {
        "type": "enabled",
        "budget_tokens": budget_tokens,
    }
    return AnthropicModelSettings(
        anthropic_thinking=thinking,
        max_tokens=max_tokens,
    )


def _build_google_settings(reasoning_level: str) -> GoogleModelSettings | None:
    """Build Google model settings with thinking level."""
    if reasoning_level == "none":
        return None
    level_map = {
        "minimal": "MINIMAL",
        "low": "LOW",
        "medium": "MEDIUM",
        "high": "HIGH",
    }
    return GoogleModelSettings(
        google_thinking_config={"thinking_level": level_map[reasoning_level]},
    )


def _get_model_settings(model: str, reasoning: str | None = None) -> ModelSettings | None:
    """Build provider-appropriate ModelSettings for the agent.

    Detects the provider from the model string and builds the corresponding
    settings with reasoning/thinking configuration.

    Args:
        model: The model identifier (e.g., "openai:gpt-5-mini")
        reasoning: Optional override for reasoning level

    Returns:
        Provider-specific ModelSettings, or None if no settings needed
    """
    provider = _detect_provider(model)
    if provider is None:
        return None

    # Resolve reasoning level: explicit param > env var > provider default
    level = (
        reasoning
        or os.getenv("FINDING_EXTRACTOR_REASONING")
        or PROVIDER_DEFAULT_REASONING.get(provider)
    )
    if level is None:
        return None

    builders = {
        "openai": _build_openai_settings,
        "anthropic": _build_anthropic_settings,
        "google": _build_google_settings,
    }

    builder = builders.get(provider)
    if builder is None:
        return None

    return builder(level)


def create_agent(model: str | None = None) -> Agent[ExtractorDeps, ReportExtraction]:
    """Create and configure the finding extraction agent.

    Args:
        model: Optional model override. Defaults to openai:gpt-5-mini or
               FINDING_EXTRACTOR_MODEL env var.

    Returns:
        Configured Agent instance with ReportExtraction output type
    """
    if model is None:
        model = os.getenv("FINDING_EXTRACTOR_MODEL", DEFAULT_MODEL)

    instructions = _build_instructions()
    model_settings = _get_model_settings(model)

    kwargs: dict = {
        "instructions": instructions,
        "output_type": ReportExtraction,
        "deps_type": ExtractorDeps,
        "output_retries": 3,
    }
    if model_settings is not None:
        kwargs["model_settings"] = model_settings

    agent = Agent[ExtractorDeps, ReportExtraction](model, **kwargs)

    @agent.output_validator
    def validate_verbatim(
        ctx: RunContext[ExtractorDeps], output: ReportExtraction
    ) -> ReportExtraction:
        errors = check_verbatim(ctx.deps.report_text, output)
        if errors:
            msg = "Verbatim check failed. " + errors[0]
            if len(errors) > 1:
                msg += f" (and {len(errors) - 1} more)"
            msg += ". Quote EXACTLY from the report text."
            raise ModelRetry(msg)
        return output

    return agent


def _normalize_ws(text: str) -> str:
    """Collapse runs of whitespace to single spaces and strip."""
    return " ".join(text.split())


def _verbatim_match(quote: str, report_text: str) -> bool:
    """Check if quote appears in report_text, tolerating whitespace differences."""
    if quote in report_text:
        return True
    return _normalize_ws(quote) in _normalize_ws(report_text)


def check_verbatim(report_text: str, output: ReportExtraction) -> list[str]:
    """Check that all extracted text segments appear verbatim in the report.

    Args:
        report_text: The original report text
        output: The extraction to validate

    Returns:
        List of error messages for non-verbatim quotes (empty if all pass)
    """
    errors = []
    for finding in output.findings:
        if not _verbatim_match(finding.report_text, report_text):
            errors.append(f"Finding '{finding.finding_name}': quote not found verbatim")
    for nft in output.non_finding_text:
        if not _verbatim_match(nft.text, report_text):
            errors.append(f"Non-finding ({nft.category}): text not found verbatim")
    return errors


def build_prompt(report_text: str, exam_description: str | None = None) -> str:
    """Build the user prompt for the extraction agent.

    Args:
        report_text: The full text of the radiology report
        exam_description: Optional exam description for context (e.g., modality, body part)

    Returns:
        Formatted prompt string
    """
    prompt_parts = []

    if exam_description:
        prompt_parts.append(f"Exam Description: {exam_description}")
        prompt_parts.append("")

    prompt_parts.append("RADIOLOGY REPORT:")
    prompt_parts.append("-" * 40)
    prompt_parts.append(report_text)
    prompt_parts.append("-" * 40)
    prompt_parts.append("")
    prompt_parts.append(
        "Extract all findings from this report into the structured format described above."
    )

    return "\n".join(prompt_parts)


async def extract_findings(
    report_text: str,
    exam_description: str | None = None,
    model: str | None = None,
    reasoning: str | None = None,
) -> ReportExtraction:
    """Run the extraction agent on a radiology report.

    Args:
        report_text: The full text of the radiology report
        exam_description: Optional exam description for context
        model: Optional model override
        reasoning: Optional reasoning effort override

    Returns:
        ReportExtraction containing all extracted findings
    """
    agent = create_agent(model)
    deps = ExtractorDeps(report_text=report_text)

    run_settings = None
    if reasoning:
        model_id = model or os.getenv("FINDING_EXTRACTOR_MODEL", DEFAULT_MODEL)
        run_settings = _get_model_settings(model_id, reasoning)

    prompt = build_prompt(report_text, exam_description)

    if run_settings:
        result = await agent.run(prompt, deps=deps, model_settings=run_settings)
    else:
        result = await agent.run(prompt, deps=deps)

    return result.output


def validate_extraction(
    report_text: str,
    extraction: ReportExtraction,
) -> ValidationResult:
    """Validate a ReportExtraction against the original report text.

    Performs:
    - Verbatim check: Verify each report_text is a substring of the original report
    - Coverage check: Identify any text segments that may have been skipped

    Args:
        report_text: The original report text
        extraction: The extracted findings to validate

    Returns:
        ValidationResult with errors and warnings
    """
    verbatim_errors = []
    coverage_warnings = []

    # Check verbatim quotes in findings
    for i, finding in enumerate(extraction.findings):
        if not _verbatim_match(finding.report_text, report_text):
            verbatim_errors.append(
                f"Finding {i} ({finding.finding_name}): report_text not found verbatim in report. "
                f"Quote: '{finding.report_text[:100]}...'"
            )

    # Check non-finding text verbatim
    for i, non_finding in enumerate(extraction.non_finding_text):
        if not _verbatim_match(non_finding.text, report_text):
            verbatim_errors.append(
                f"Non-finding {i} ({non_finding.category}): text not found verbatim in report. "
                f"Text: '{non_finding.text[:100]}...'"
            )

    # Coverage check (informational)
    extracted_texts = [f.report_text for f in extraction.findings]
    extracted_texts.extend(nf.text for nf in extraction.non_finding_text)

    report_lines = report_text.split("\n")
    unaccounted_lines = []

    for line in report_lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        found = any(line_stripped in extracted for extracted in extracted_texts)
        if not found:
            unaccounted_lines.append(line_stripped)

    if unaccounted_lines:
        coverage_warnings.append(
            f"Some report lines may not be fully accounted for: {len(unaccounted_lines)} lines. "
            f"Example: '{unaccounted_lines[0][:80]}...'"
        )

    return ValidationResult(
        is_valid=len(verbatim_errors) == 0,
        verbatim_errors=verbatim_errors,
        coverage_warnings=coverage_warnings,
    )
