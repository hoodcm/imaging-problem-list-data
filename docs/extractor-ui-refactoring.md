# Extractor UI Refactoring — Completed

Refactoring of `extractor-ui/index.html` and `extractor-ui/app.js` to align with the project's Flowbite/Tailwind/Alpine CDN stack.

## What Was Done

### Phase 1: CDN Infrastructure
- **Flowbite 4.0.0 → 4.0.1**: Updated both CSS and JS CDN references
- **Tailwind v4 browser CDN**: Added `@tailwindcss/browser@4` with `@custom-variant dark` for class-based dark mode and dynamic utility generation. Flowbite CSS loads first (it includes a complete Tailwind v4 build), then the browser CDN loads after to add class-based dark mode support.
- **FOUC script**: Changed from system-preference-based to dark-by-default (`localStorage 'light'` opts out)

### Phase 2: Dark Mode Pattern Alignment
- Renamed `isDark` → `darkMode` in `app.js`
- Added reactive `$watch('darkMode', ...)` in `init()` to sync DOM + localStorage
- Removed imperative `toggleDarkMode()` method
- Updated HTML: `@click="darkMode = !darkMode"`, `x-show="!darkMode"` / `x-show="darkMode"`

## What Was NOT Done (and Why)

### Semantic Token Migration — Rejected

The original plan included migrating ~120 `dark:` class pairs to Flowbite v4 semantic tokens (`text-heading`, `bg-neutral-primary`, `bg-brand`, etc.).

**Root cause for rejection:** Flowbite's semantic tokens require the Flowbite Tailwind plugin (a build step) to define CSS custom properties (`--color-brand`, `--color-heading`, etc.). These properties are not available in CDN-only setups.

**Decision:** Stick with the classic `dark:` prefix approach (`bg-white dark:bg-gray-800`, `text-gray-900 dark:text-white`, etc.) which works reliably with CDN. No build step will be introduced at this time.

**Lesson learned:** E2E tests that check DOM structure can all pass while the UI is visually broken. Visual regression testing (screenshots) is essential when changing styling infrastructure.

## Verification

All 48 Playwright tests pass: `uv run pytest tests/test_ui.py -v`
