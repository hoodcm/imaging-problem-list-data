# Stream C: Coding Runtime Hardening

Last updated: 2026-02-14
Status: Implemented
Owner/worktree: `/Users/talkasab/repos/imaging-problem-list-provider` (`feature/coding-bridge-runtime-hardening`)

## Goal

Improve coding bridge runtime efficiency and mapping quality without changing extraction success semantics.

## Completed

1. Added lazy reusable index lifecycle in `src/finding_extractor/coding_bridge.py`:
   1. Shared `Index` + `AnatomicLocationIndex` instances are initialized once and reused across `apply_coding()` calls.
   2. Added guarded async initialization to avoid duplicate concurrent opens.
   3. Added `reset_coding_indexes_for_testing()` for test/lifecycle cleanup.
2. Added region-aware location coding:
   1. Mapped `FindingLocation.body_region` values to `AnatomicLocationIndex.search(..., region=...)`.
   2. Falls back to unfiltered search when no mapping is available.
3. Preserved non-fatal coding behavior in task execution.
4. Added tests for:
   1. Reusable index lifecycle across repeated calls.
   2. Region-aware location matching and fallback behavior.
