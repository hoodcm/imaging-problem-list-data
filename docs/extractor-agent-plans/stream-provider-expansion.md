# Stream Provider Expansion: Stage 5 Provider/Model Capability Work

Last updated: 2026-02-14
Status: Active

## Stage definition

Stage 5 means expanding provider/model support safely after earlier extraction/eval foundations are in place.

## Scope

1. Refactor provider settings builders out of `agent.py` into dedicated module.
2. Expand model capability/discovery path for local models.
3. Add safe profile presets and maintain model-policy validation.

## Focus areas

1. Keep provider behavior explicit for reasoning/thinking settings.
2. Prevent drift between discovery metadata and runtime policy validation.
3. Preserve existing API contracts while broadening supported model inventory.

## Out of scope

1. Stage 6 chunking/orchestration changes.
2. Coding bridge logic.

## Acceptance criteria

1. Provider settings code is modular and easier to extend/test.
2. Model catalog includes richer capability metadata for decision-making.
3. Existing tests remain green; add provider-focused regression tests.
