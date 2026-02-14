Workstream: Stream Provider Expansion (Stage 5)
Branch/worktree: feature/provider-expansion (/Users/talkasab/repos/imaging-problem-list-provider)

Read first:
1) docs/extractor-agent-roadmap.md
2) docs/extractor-agent-plans/stream-provider-expansion.md
3) src/finding_extractor/agent.py
4) src/finding_extractor/model_catalog.py
5) src/finding_extractor/model_policy.py
6) src/finding_extractor/config.py
7) tests/test_extraction.py, tests/test_model_catalog.py, tests/test_model_policy.py, tests/test_api.py

Goal:
Deliver the first provider-expansion slice by modularizing provider settings logic and improving capability/discovery structure without breaking existing API behavior.

Constraints:
1) Preserve existing model-policy validation behavior.
2) Preserve current API contracts unless changes are additive and documented.
3) Keep extraction behavior backward compatible.
4) Do NOT implement Stream Coding Bridge or Stream Reliability Contract scope in this branch.
5) Keep changes small, reviewable, and test-covered.

Implementation scope (v1):
1) Extract provider settings builders from `src/finding_extractor/agent.py` into a dedicated module (e.g., `src/finding_extractor/providers.py`).
2) Move provider-specific reasoning/thinking mappings into that module.
3) Keep `agent.py` as orchestrator using the new module APIs.
4) Add/expand tests around provider settings behavior and reasoning compatibility.
5) If feasible without contract risk, add clearer capability metadata scaffolding that can support future catalog expansion.

Out of scope (for this slice):
1) Completed-with-warnings lifecycle/status work.
2) Coding bridge output fields.
3) Chunking/sub-agent orchestration.

Testing:
1) Unit tests for provider settings mapping (OpenAI/Anthropic/Google/Ollama behavior unchanged).
2) Regression tests for reasoning compatibility (`validate_reasoning_for_model`).
3) Model catalog/policy tests for unchanged acceptance/rejection semantics.
4) Ensure full lint + test pass.

Validation commands:
- task lint
- task test

Deliverables:
1) Refactor code + tests
2) Short design note in commit/PR summary explaining module boundaries
3) Docs update in stream doc and/or DEV_LOG with shipped slice and follow-up items
