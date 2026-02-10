# IPL Project Frontend Guide

Project-specific frontend conventions for the imaging problem list viewer and extractor UI. For general stack conventions (Flowbite + Tailwind + Alpine.js), see the `flowbite-tailwind-alpine` skill.

## Overview

Two frontends share the same stack:

| App | Location | Entry Point | Component Function |
|-----|----------|-------------|-------------------|
| IPL Viewer | `viewer/` | `viewer/index.html` + `viewer/app.js` | `iplApp()` |
| Extractor UI | `extractor-ui/` | `extractor-ui/index.html` + `extractor-ui/app.js` | `extractorApp()` |

Both use: Alpine.js 3.x, Tailwind CSS (currently v3 CDN — see `docs/frontend-refactoring.md`), Flowbite 4.0.0, no build step.

## Viewer Architecture

The viewer is a static SPA that visualizes imaging problem lists from JSON data files.

**Component:** `iplApp()` in `viewer/app.js` — single function containing all state and methods.

**Key features:**
- **Three-level navigation:** IPL view (aggregated findings) → Exam view (single exam findings) → Report view (raw text)
- **Status computation:** Sorts observations by date and checks most recent presence status to derive current/resolved/never-present (`viewer/app.js:101-124`)
- **Body region filtering:** Uses keyword matching on finding descriptions to categorize findings by body region
- **Finding popover system:** Shared-instance popover with manual `getBoundingClientRect()` positioning (`getPopoverStyle()` method)
- **Multi-patient support:** Patient selector dropdown, URL parameter `?patient=<id>` for deep linking

**Data source:** Static JSON files under `data/` directory:
```
data/
  patients.json                    # Patient manifest
  patients/<patient-id>/
    patient.json                   # Demographics
    ipl.json                       # Imaging Problem List
    exams/<report-id>/
      efl.json                     # Exam Finding List
      report.txt                   # Raw report text
```

## Extractor UI Architecture

The extractor UI provides a frontend for the extraction service API.

**Component:** `extractorApp()` in `extractor-ui/app.js` — single function containing all state and methods.

**Key features:**
- **Hash-based routing:** `navigateFromHash()` parses `window.location.hash` with regex patterns
- **API client:** `apiFetch()` wraps `fetch()` with `/api` prefix, error extraction, and mock mode (`?mock` URL parameter)
- **Job polling:** `setTimeout`-based polling with `retry_after` support and in-flight guard
- **Corrections system:** Submit corrections for extraction results
- **Mock mode:** URL parameter `?mock` enables client-side mock data for development

**Routes:** `#/` (submit), `#/reports` (list), `#/reports/{id}` (detail), `#/reports/{id}/extracting/{job_id}` (polling), `#/extractions/{id}` (results)

For detailed specs see `docs/extractor-frontend.md` and `docs/frontend-internals.md`.

## Shared Conventions

Both apps follow these patterns:

1. **Single-component pattern:** One function (`iplApp()` / `extractorApp()`) holds all state, methods, and getters. No separate JS modules.
2. **Dark mode toggle in header:** Both apps have a dark mode toggle button in the sticky header.
3. **x-cloak on root element:** Both use `x-cloak` to prevent flash of unstyled content.
4. **Same CDN stack:** Both load Tailwind, Flowbite CSS, Alpine.js, and Flowbite JS from CDN (currently both on Tailwind v3 and Flowbite 4.0.0).
5. **FOUC-prevention script:** Both include a `<head>` script that reads `localStorage('color-theme')` and sets the `dark` class before render.

## When to Decompose

Start with the single component function pattern — it is the right default for most pages in this project.

Consider decomposition when:
- The component function exceeds ~400 lines
- You need shared state across independent UI regions (use `Alpine.store()` for global state)
- You have reusable sub-components appearing in multiple places (use `Alpine.data()`)

See the `flowbite-tailwind-alpine` skill's Alpine patterns reference for `Alpine.store()` and `Alpine.data()` details.

## Project-Specific Anti-Patterns

1. **Don't create separate JS files for minor features.** Extend the existing app function (`iplApp()` or `extractorApp()`).
2. **Don't add build steps.** Both apps are zero-build static SPAs.
3. **Don't replace existing vanilla JS patterns with Alpine unless explicitly asked.** The viewer's dark mode toggle (vanilla JS, `document.getElementById`) and popover positioning (`getBoundingClientRect()`) are known-fragile areas. See `docs/frontend-refactoring.md` for migration plans.
4. **Don't attempt "simple" popover fixes.** Popover/tooltip positioning has been repeatedly problematic — agents have proposed fixes that broke on implementation. Any changes to popover behavior MUST include Playwright testing with the running app.
