# Stream D: Coding API/UI Contract

Last updated: 2026-02-17
Status: Superseded by inline coding contract
Owner/worktree: `/Users/talkasab/repos/imaging-problem-list-ui` (`feature/coding-progress-ui-api-contract`)

## Supersession Note (2026-02-17)

This document describes the earlier detached coding payload contract (`coding_result` / `_coding`).
The runtime now uses inline coding attached to each finding and this is the active source of truth:

1. `extraction.findings[].coding.finding_code`
2. `extraction.findings[].coding.location_code`
3. extraction summary counts are derived from inline coding

Detached API fields (`coding_result`) and CLI `_coding` output are no longer emitted.

This file is retained only as historical planning context and should not be used as implementation guidance.
