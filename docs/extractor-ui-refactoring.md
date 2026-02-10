# Extractor UI Refactoring Plan (Cursory)

Captured from the skill restructuring work. This is a **preliminary list** based on what we already know — a detailed plan will require fresh context (reading the current `extractor-ui/index.html` and `extractor-ui/app.js` in full, checking the Playwright test suite, and verifying behavior in the browser).

## What's Already Good

The extractor UI is in better shape than the viewer:
- Alpine.js dark mode toggle (not vanilla JS)
- Proper `x-cloak` on multiple view sections
- Clean hash-based routing with `navigateFromHash()`
- Mock mode (`?mock` URL parameter) for development without backend
- 48 Playwright E2E tests in `tests/test_ui.py`

## Known Refactoring Items

### 1. Tailwind v3 to v4 CDN Migration

Same as viewer — see `docs/frontend-refactoring.md` § Tailwind v3 to v4 Migration for steps. The extractor UI uses `cdn.tailwindcss.com` with `tailwind.config = { darkMode: 'class' }`. Needs to move to `@tailwindcss/browser@4` with `@custom-variant dark`.

### 2. Flowbite 4.0.0 to Target Version

Currently loads `flowbite@4.0.0`. Skill documents `4.0.1`. Update both CSS and JS CDN references once the target version is decided (see `docs/frontend-refactoring.md` § Flowbite Version).

### 3. Dark Mode Toggle Pattern Alignment

The extractor uses `isDark` state + imperative `toggleDarkMode()` method:
```javascript
toggleDarkMode() {
    this.isDark = !this.isDark;
    document.documentElement.classList.toggle('dark', this.isDark);
    localStorage.setItem('color-theme', this.isDark ? 'dark' : 'light');
}
```

The skill documents `darkMode` state + reactive `$watch` pattern:
```javascript
darkMode: document.documentElement.classList.contains('dark'),
init() {
    this.$watch('darkMode', (enabled) => {
        document.documentElement.classList.toggle('dark', enabled);
        localStorage.setItem('color-theme', enabled ? 'dark' : 'light');
    });
}
```

Functionally equivalent, but naming and approach differ. Standardize to the skill's `darkMode` + `$watch` pattern for consistency.

### 4. Semantic Token Migration (Audit Needed)

The extractor UI likely uses raw Tailwind `dark:` prefix class pairs (e.g., `bg-white dark:bg-gray-800`, `text-gray-900 dark:text-white`) rather than Flowbite v4 semantic tokens (`bg-neutral-primary-soft`, `text-heading`). **This needs a full audit** — read through `extractor-ui/index.html` and catalog all raw `dark:` pairs that have semantic token equivalents. The mapping table in `skills/flowbite-tailwind-alpine/references/color-patterns.md` § Legacy Classic Tailwind to Semantic Token Mapping covers the conversions.

## Before Starting

A detailed plan should:
1. Read `extractor-ui/index.html` and `extractor-ui/app.js` with fresh context
2. Grep for `dark:` class usage to scope the semantic token migration
3. Check whether any Tailwind v3-specific utilities are used that might break on v4
4. Review the Playwright tests (`tests/test_ui.py`) to understand coverage — these should be run before and after each change
5. Decide whether to batch all items into one pass or do them incrementally (incremental is safer given the test suite)
