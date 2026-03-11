"""Tests for dedicated chunk extraction prompt/schema scaffolding."""

from finding_extractor.extractor.prompt import build_chunk_system_prompt, build_system_prompt
from finding_extractor.models import ChunkExtraction


def test_chunk_prompt_is_smaller_than_full_prompt():
    full_prompt = build_system_prompt()
    chunk_prompt = build_chunk_system_prompt()

    assert len(chunk_prompt) < len(full_prompt)
    assert len(chunk_prompt) < 6000


def test_chunk_prompt_excludes_full_report_dedup_and_output_format_blocks():
    prompt = build_chunk_system_prompt()

    assert "SECTION PRIORITY AND DEDUPLICATION" not in prompt
    assert "Return a ReportExtraction object" not in prompt
    assert "Return a ChunkExtraction response" not in prompt
    assert "TARGET CHUNK" in prompt


def test_chunk_prompt_includes_normal_structure_absent_mapping_rule():
    prompt = build_chunk_system_prompt()

    assert "clear lungs" in prompt
    assert "absent pulmonary parenchymal abnormality" in prompt
    assert "general finding and then names specific instances" in prompt


def test_chunk_prompt_examples_are_loaded_from_yaml():
    prompt = build_chunk_system_prompt()

    assert "ct_abdomen_20210826_findings_vascular_calcifications" in prompt
    assert "vascular calcification" in prompt
    assert "mitral annular calcification" in prompt
    assert "coronary artery calcification" in prompt
    assert "ct_abdomen_20221103_findings_6" in prompt
    assert "section=findings; chunk_label=findings_6" in prompt
    assert "Example C (context helps interpretation only)" not in prompt


def test_chunk_schema_allows_loose_attributes():
    payload = {
        "findings": [
            {
                "finding_name": "renal calculus",
                "presence": "present",
                "location": {"body_region": "abdomen", "specific_anatomy": "right kidney"},
                "attributes": [
                    {"key": "size", "value": "3 mm"},
                    {"key": "custom_observation", "value": "faint linear calcification"},
                ],
                "report_text": "Stable bilateral renal stones ... 3 mm.",
            }
        ],
    }

    parsed = ChunkExtraction.model_validate(payload)
    assert len(parsed.findings) == 1
    assert parsed.findings[0].attributes[1].key == "custom_observation"
