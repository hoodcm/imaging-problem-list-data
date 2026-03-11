"""Dedicated sub-agent for extracting exam metadata from radiology reports."""

from __future__ import annotations

import json
from datetime import date
from typing import Literal, cast

from pydantic import Field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from finding_extractor.core.base_model import StrictBaseModel
from finding_extractor.llm.resilience import create_resilient_agent
from finding_extractor.models import BodyRegion, Contrast, ExamInfo, Modality


class ExamInfoExtraction(StrictBaseModel):
    """Structured exam metadata extracted by the sub-agent."""

    study_description: str | None = Field(
        default=None,
        description=(
            'Concise study description in format "MODALITY BODY_PART [+/- details]". '
            'Examples: "CT Abdomen and Pelvis With IV Contrast", "XR Chest PA and Lateral", '
            '"MR Brain Without and With Contrast".'
        ),
    )
    study_date: date | None = Field(
        default=None,
        description="Exam date in ISO format (YYYY-MM-DD), if stated in the report.",
    )
    modality: Modality | None = Field(
        default=None,
        description=(
            "Imaging modality code. Must be one of: "
            "CT, XR, MR, US, NM, PET, FLUORO, MG, DXA, IR."
        ),
    )
    body_region: BodyRegion | None = Field(
        default=None,
        description=(
            "Constrained body region category. Must be one of: "
            "chest, abdomen, pelvis, head, neck, spine, upper extremity, "
            "lower extremity, breast. For multi-region exams, use the primary/first region."
        ),
    )
    body_part: str | None = Field(
        default=None,
        description=(
            "Specific anatomic term(s) from the report, comma-separated if multiple. "
            'Examples: "abdomen, pelvis", "brain", "shoulder", "chest".'
        ),
    )
    contrast: Contrast | None = Field(
        default=None,
        description=(
            'Contrast status: "with" (IV contrast), "without" (no contrast), '
            '"without and with" (dual-phase), or null if not applicable (e.g., XR).'
        ),
    )
    laterality: Literal["left", "right", "bilateral"] | None = Field(
        default=None,
        description="Laterality of the examined body part, if applicable.",
    )


_INSTRUCTIONS = """\
You are a radiology exam metadata extractor. Extract structured exam metadata \
from the provided radiology report context.

## Priority of evidence (highest to lowest)
1. exam_description_hint (if provided) — most reliable, from ordering system
2. source_ref / filename — often encodes modality and body part
3. Report header lines (title, technique, indication)
4. Report body content

## Modality codes
Map the imaging modality to one of these standard codes:
- CT = computed tomography
- XR = radiograph / X-ray / plain film
- MR = MRI / magnetic resonance
- US = ultrasound / sonography
- NM = nuclear medicine / scintigraphy
- PET = PET or PET/CT
- FLUORO = fluoroscopy
- MG = mammography
- DXA = DEXA / bone densitometry
- IR = interventional radiology

## body_region mapping
Map the anatomic area to one of these constrained categories:
- chest — lungs, heart, thorax
- abdomen — liver, kidneys, pancreas, GI
- pelvis — bladder, uterus, prostate, pelvic organs
- head — brain, orbits, sinuses, skull
- neck — cervical soft tissues, thyroid, carotid
- spine — cervical/thoracic/lumbar/sacral spine
- upper extremity — shoulder, arm, elbow, wrist, hand
- lower extremity — hip, knee, ankle, foot, femur, tibia
- breast — mammography targets

For multi-region exams (e.g., "CT Abdomen and Pelvis"), use the primary/first region.

## body_part vs body_region
- body_region: constrained category from the list above
- body_part: specific anatomic term(s) from the report, comma-separated if multiple
  - "abdomen, pelvis" for CT A/P; "brain" for MR Brain; "shoulder" for XR Shoulder

## contrast
- "with" = IV contrast administered
- "without" = explicitly no contrast
- "without and with" = dual-phase (pre- and post-contrast)
- null = not applicable (e.g., plain radiographs, ultrasound)

## study_description format
Use format: "MODALITY BODY_PART [+/- contrast details]"
- "CT Abdomen and Pelvis With IV Contrast"
- "XR Chest PA and Lateral"
- "MR Brain Without and With Contrast"
- "XR Left Shoulder"
- "US Abdomen"

## Anti-patterns
Do NOT return vague descriptions like "Radiological Study" or "Imaging Exam". \
Always extract specific modality and body part from the available evidence.

## Examples

### Example A — CT with contrast, multi-region
Input context: filename "ct_abdomen_20230118.md", title "CT Abdomen and Pelvis With Intravenous Contrast", date line "Date of Exam: January 18, 2023"
Output:
- study_description: "CT Abdomen and Pelvis With IV Contrast"
- study_date: "2023-01-18"
- modality: "CT"
- body_region: "abdomen"
- body_part: "abdomen, pelvis"
- contrast: "with"
- laterality: null

### Example B — Plain radiograph, no contrast
Input context: filename "xr_chest_20210614.md", title "Chest Radiograph (PA and Lateral)", date line "Date of Exam: June 14, 2021"
Output:
- study_description: "XR Chest PA and Lateral"
- study_date: "2021-06-14"
- modality: "XR"
- body_region: "chest"
- body_part: "chest"
- contrast: null
- laterality: null

### Example C — MR with body_region mapping, dual-phase contrast
Input context: filename "mr_brain_20230125.md", title "MRI Brain Without and With Contrast", date line "Date of Exam: January 25, 2023"
Output:
- study_description: "MR Brain Without and With Contrast"
- study_date: "2023-01-25"
- modality: "MR"
- body_region: "head"
- body_part: "brain"
- contrast: "without and with"
- laterality: null

### Example D — XR with laterality
Input context: filename "xr_shoulder_20210522.md", title "Left Shoulder Radiograph", date line "Date of Exam: May 22, 2021"
Output:
- study_description: "XR Left Shoulder"
- study_date: "2021-05-22"
- modality: "XR"
- body_region: "upper extremity"
- body_part: "shoulder"
- contrast: null
- laterality: "left"

### Example E — Ultrasound, no date in report
Input context: filename "us_abdomen_20220208.md", title "Abdominal Ultrasound", no date line present
Output:
- study_description: "US Abdomen"
- study_date: null
- modality: "US"
- body_region: "abdomen"
- body_part: "abdomen"
- contrast: null
- laterality: null
"""


def _build_exam_info_prompt(
    report_text: str,
    *,
    exam_description: str | None = None,
    source_ref: str | None = None,
    external_metadata: dict[str, str] | None = None,
) -> str:
    payload: dict[str, object] = {}
    if exam_description:
        payload["exam_description_hint"] = exam_description
    if source_ref:
        payload["source_ref"] = source_ref
    if external_metadata:
        payload["external_metadata"] = external_metadata
    # First 20 lines of report text as context
    report_context = "\n".join(report_text.split("\n")[:20])
    payload["report_context"] = report_context
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
    return ExamInfo(
        study_description=description,
        study_date=result.study_date,
        modality=result.modality,
        body_region=result.body_region,
        body_part=result.body_part,
        contrast=result.contrast,
        laterality=result.laterality,
    )


async def extract_exam_info(
    report_text: str,
    *,
    exam_description: str | None = None,
    source_ref: str | None = None,
    external_metadata: dict[str, str] | None = None,
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
    )
    usage_limits = UsageLimits(request_limit=4)
    result = await agent.run(prompt, usage_limits=usage_limits)
    return _to_exam_info(result.output, fallback_description=fallback)
