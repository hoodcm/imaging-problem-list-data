"""LLM configuration: defaults, policy, catalog, resilience, and provider settings.

Submodules
----------
- ``defaults`` — canonical model IDs and curated model list
- ``policy`` — model ID validation and SOTA selection
- ``catalog`` — multi-provider model discovery with Redis caching
- ``model_settings`` — reasoning resolution, preset configs, and provider-specific settings
- ``resilience`` — resilient model/agent construction with fallback and rate limiting

All consumers import from submodules directly (e.g.,
``from finding_extractor.llm.policy import validate_model_id``).
Eager re-exports are intentionally omitted to avoid circular imports
with ``finding_extractor.core.config``.
"""
