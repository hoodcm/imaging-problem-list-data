# Viewer Refactoring Plan (Cursory)

Captured from the skill restructuring work. This is a **preliminary list** based on what we already know — a detailed plan will require fresh context (reading the current `viewer/index.html` and `viewer/app.js` in full, running the app in a browser, and verifying behavior).

The viewer has more technical debt than the extractor UI. It predates the skill conventions and uses older patterns throughout.

## What's Already Good

- Single-component pattern (`iplApp()` in `viewer/app.js`) — matches the skill's recommended architecture
- Three-level navigation (IPL → Exam → Report) is clean and well-structured
- Status computation and body region filtering work correctly
- Multi-patient support with URL parameter deep linking
- `x-cloak` on the shared popover element

## Known Refactoring Items

### 1. Tailwind v3 to v4 CDN Migration

Same as extractor UI — see `docs/frontend-refactoring.md` § Tailwind v3 to v4 Migration for steps. The viewer uses `cdn.tailwindcss.com` with `tailwind.config = { darkMode: 'class' }`. Needs to move to `@tailwindcss/browser@4` with `@custom-variant dark`.

### 2. Flowbite 4.0.0 to Target Version

Currently loads `flowbite@4.0.0`. Skill documents `4.0.1`. Update both CSS and JS CDN references once the target version is decided (see `docs/frontend-refactoring.md` § Flowbite Version).

### 3. Dark Mode Toggle — Vanilla JS to Alpine.js

The viewer's dark mode toggle is ~40 lines of vanilla JS in `viewer/index.html` (around lines 470-508) using `document.getElementById` to toggle icon visibility and `classList` to switch themes. This should be replaced with the skill's `darkMode` state + `$watch` pattern.

**Current behavior to preserve:**
- The viewer defaults to system preference via `window.matchMedia('(prefers-color-scheme: dark)')`, falling back to dark mode. This is slightly different from the skill's "always default to dark" pattern. Decide whether to keep system-preference detection or standardize to always-dark default.

**Target pattern** (from the skill):
```javascript
darkMode: document.documentElement.classList.contains('dark'),
init() {
    this.$watch('darkMode', (enabled) => {
        document.documentElement.classList.toggle('dark', enabled);
        localStorage.setItem('color-theme', enabled ? 'dark' : 'light');
    });
}
```

The toggle button HTML would use `@click="darkMode = !darkMode"` with `x-show="darkMode"` / `x-show="!darkMode"` on the sun/moon SVGs, replacing the `getElementById` icon toggling.

### 4. Semantic Token Migration (Audit Needed)

The viewer predates the Flowbite v4 semantic token system and likely uses raw Tailwind `dark:` prefix class pairs extensively (e.g., `bg-white dark:bg-gray-800`, `text-gray-900 dark:text-white`). **This needs a full audit** — grep `viewer/index.html` for `dark:` class usage and map each pair to its semantic token equivalent using the table in `skills/flowbite-tailwind-alpine/references/color-patterns.md` § Legacy Classic Tailwind to Semantic Token Mapping.

This is likely the largest single item — the viewer has substantial markup with color classes.

### 5. Popover Positioning (DO NOT ATTEMPT CASUALLY)

The viewer's `getPopoverStyle()` method in `viewer/app.js` does manual `getBoundingClientRect()` math to position finding popovers:
- IPL view: above the finding (or below if near viewport top)
- Exam view: to the right of the finding

The Alpine.js Anchor plugin (`x-anchor`) could theoretically replace this, but **popover/tooltip positioning has been repeatedly problematic in this project**. Agents have proposed "simple" fixes that broke on implementation.

**Rules for any popover changes:**
- Do NOT attempt without `docker compose up` and real browser verification
- MUST include Playwright testing against the running app
- Test in both IPL view and exam view
- Test near viewport edges (top, bottom, sides)
- Consider this a separate, standalone task — never bundle with other refactoring

### 6. x-cloak Coverage (Minor)

The viewer currently uses `x-cloak` only on the shared popover element. The extractor UI uses it on multiple view sections. Check whether other `x-show` elements in the viewer that start hidden would benefit from `x-cloak` to prevent flash on initial load.

## Before Starting

A detailed plan should:
1. Read `viewer/index.html` and `viewer/app.js` with fresh context
2. Grep for `dark:` class usage to scope the semantic token migration (likely the largest task)
3. Catalog the vanilla JS dark mode toggle code to understand the full removal scope
4. Check whether any Tailwind v3-specific utilities are used that might break on v4
5. Run the app in a browser to verify current behavior as a baseline (the viewer has no Playwright tests — manual verification required)
6. Consider ordering: CDN migrations (items 1-2) first, then dark mode (item 3), then semantic tokens (item 4), popovers (item 5) last and only if explicitly requested
