Workstream: Parallel Agent Restructuring Equilibration
Branch/worktree: dev (/Users/talkasab/repos/imaging-problem-list)

Read first:
1) docs/extractor-agent-roadmap.md
2) docs/agent_restructuring.md
3) docs/extractor-agent-plans/stream-restructure-orchestrator-core.md
4) docs/extractor-agent-plans/stream-provider-failfast-hardening.md
5) docs/extractor-agent-plans/stream-coding-runtime-hardening.md
6) docs/extractor-agent-plans/stream-coding-api-ui-contract.md

Goal:
Coordinate four parallel worktree streams so we can start restructuring from a safe baseline:
1) fail-fast provider/runtime contract
2) modular orchestrator + progress contract
3) coding bridge runtime hardening
4) coding API/UI exposure

Execution mode:
1) Run each stream in its own branch/worktree.
2) Keep ownership boundaries strict to minimize conflicts.
3) Merge in planned order: B (provider) -> C (coding runtime) -> A (orchestrator) -> D (API/UI).

Streams and owners:
1) Stream A (this worktree): `docs/extractor-agent-plans/stream-restructure-orchestrator-core.md`
2) Stream B (`-agent`): `docs/extractor-agent-plans/stream-provider-failfast-hardening.md`
3) Stream C (`-provider`): `docs/extractor-agent-plans/stream-coding-runtime-hardening.md`
4) Stream D (`-ui`): `docs/extractor-agent-plans/stream-coding-api-ui-contract.md`

Required outputs:
1) Each stream lands with tests green for its scope.
2) Roadmap + stream docs updated with status and commit refs.
3) Final integration pass on `dev` with:
   - task lint
   - task test

Out of scope for this cycle:
1) LangGraph/CrewAI adoption
2) Agent-based coding resolution
3) Strict numeric SLO commitments
