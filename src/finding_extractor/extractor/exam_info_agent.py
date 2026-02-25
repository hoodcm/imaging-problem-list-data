"""Dedicated sub-agent for extracting exam metadata from radiology reports."""

from __future__ import annotations

import json
from typing import Literal, cast

from pydantic import Field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from finding_extractor.base import StrictBaseModel
from finding_extractor.llm_config.resilience import create_resilient_agent
from finding_extractor.models import ExamInfo


class ExamInfoExtraction(StrictBaseModel):
    """Structured exam metadata extracted by the sub-agent."""

    study_description: str | None = Field(
        default=None,
        description="Concise study description inferred from the report.",
    )
    modality: Literal["CT", "XR", "MR", "US", "NM", "PET", "FLUORO"] | None = Field(
        default=None,
        description="Imaging modality code.",
    )
    body_part: str | None = Field(
        default=None,
        description='Primary body part examined: "abdomen", "chest", "brain", etc.',
    )
    laterality: Literal["left", "right", "bilateral"] | None = Field(
        default=None,
        description="Laterality of the examined body part, if applicable.",
    )


_INSTRUCTIONS = (
    "You are a radiology exam metadata extractor. "
    "Given a radiology report (and optional exam description hint), extract the "
    "imaging modality, primary body part examined, and laterality. "
    "Use standard modality codes: CT, XR, MR, US, NM, PET, FLUORO. "
    "For body_part, use lowercase anatomic terms like 'abdomen', 'chest', 'brain', 'shoulder'. "
    "Only set laterality when the exam is specifically for one side (e.g., 'left shoulder MR'). "
    "If information cannot be determined, leave the field null."
)


def _build_exam_info_prompt(
    report_text: str,
    *,
    exam_description: str | None = None,
    source_ref: str | None = None,
    external_metadata: dict[str, str] | None = None,
    report_headers: str | None = None,
) -> str:
    payload: dict[str, object] = {}
    if exam_description:
        payload["exam_description_hint"] = exam_description
    if source_ref:
        payload["source_ref"] = source_ref
    if external_metadata:
        payload["external_metadata"] = external_metadata
    if report_headers:
        payload["report_headers"] = report_headers
    # Fallback preview when headers are unavailable.
    if not report_headers:
        preview = report_text[:600]
        if len(report_text) > 600:
            preview += "..."
        payload["report_preview"] = preview
    return (
        "Extract exam metadata from this radiology report.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _create_exam_info_agent(
    model_name: str,
    reasoning: str | None,
) -> Agent[None, ExamInfoExtraction]:
    agent = create_resilient_agent(
        model_name=model_name,
        reasoning=reasoning,
        instructions=_INSTRUCTIONS,
        output_type=ExamInfoExtraction,
        output_retries=2,
    )
    return cast(Agent[None, ExamInfoExtraction], agent)


def _to_exam_info(result: ExamInfoExtraction, *, fallback_description: str) -> ExamInfo:
    """Convert agent output to the canonical ExamInfo model."""
    description = (result.study_description or "").strip() or fallback_description
    modality = result.modality.upper() if result.modality else None
    return ExamInfo(
        study_description=description,
        modality=modality,
        body_part=result.body_part,
        laterality=result.laterality,
    )


async def extract_exam_info(
    report_text: str,
    *,
    exam_description: str | None = None,
    source_ref: str | None = None,
    external_metadata: dict[str, str] | None = None,
    report_headers: str | None = None,
    model_name: str,
    reasoning: str | None = None,
) -> ExamInfo:
    """Run the exam-info sub-agent and return an ExamInfo."""
    fallback = (exam_description or "").strip() or "Radiology study"
    agent = _create_exam_info_agent(model_name, reasoning)
    prompt = _build_exam_info_prompt(
        report_text,
        exam_description=exam_description,
        source_ref=source_ref,
        external_metadata=external_metadata,
        report_headers=report_headers,
    )
    usage_limits = UsageLimits(request_limit=4)
    result = await agent.run(prompt, usage_limits=usage_limits)
    return _to_exam_info(result.output, fallback_description=fallback)
