# Stage 1.5 Done: Agent-Internal Status Callback

Completed: 2026-02-11

## What Stage 1.5 does

Stage 1.5 exposed progress from inside the agent call itself, including retry visibility during validation retries.

## Delivered

1. Optional status callback in extractor dependencies.
2. Agent emits internal progress messages before/after model call and during retries.
3. Worker and CLI wire callback to DB updates and stderr output respectively.

## Main artifacts

1. `src/finding_extractor/models.py` (`ExtractorDeps` callback)
2. `src/finding_extractor/agent.py` (`_emit_status` and callback usage)
3. `src/finding_extractor/tasks.py`
4. `src/finding_extractor/cli.py`
