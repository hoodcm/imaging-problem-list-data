"""Extraction pipeline: orchestration, chunk agents, validator review, exam-info.

Submodules
----------
- ``orchestrator`` — chunk-scoped parallel extraction pipeline
- ``agent`` — PydanticAI extraction agent and prompt building
- ``runtime`` — shared orchestrated extraction runtime (worker + CLI)
- ``review`` — validator review sub-agent for re-extraction decisions
- ``exam_info_agent`` — exam-info extraction sub-agent

All consumers import from submodules directly (e.g.,
``from finding_extractor.extractor.runtime import run_extraction_runtime``).
"""
