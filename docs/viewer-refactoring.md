# Viewer Refactoring Plan

Align `viewer/index.html` and `viewer/app.js` with the project's established CDN stack, matching the pattern proven in the extractor UI. The viewer predates the skill conventions and uses older patterns.

## What's Already Good

- Single-component pattern (`iplApp()` in `viewer/app.js`) — matches the skill's recommended architecture
- Three-level navigation (IPL → Exam → Report) is clean and well-structured
- Status computation and body region filtering work correctly
- Multi-patient support with URL parameter deep linking
- Classic `dark:` prefix color patterns throughout — no migration needed
- `x-cloak` on the shared popover element

## Changes Needed

### 1. CDN Stack Update

The viewer currently loads CDNs in the wrong order and uses Tailwind v3:

**Current (`viewer/index.html` lines 8–20):**
```html
<script src="https://cdn.tailwindcss.com"></script>
<script>
    tailwind.config = { darkMode: 'class', theme: { extend: {} } }
</script>
<link href="https://cdn.jsdelivr.net/npm/flowbite@4.0.0/dist/flowbite.min.css" rel="stylesheet" />
```

**Target (matches extractor UI and skill boilerplate):**
```html
<!-- 1. Flowbite CSS (includes Tailwind v4 + Flowbite plugin styles) -->
<link href="https://cdn.jsdelivr.net/npm/flowbite@4.0.1/dist/flowbite.min.css" rel="stylesheet" />

<!-- 2. Tailwind CSS v4 browser CDN (dynamic utility generation + class-based dark mode) -->
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
<style type="text/tailwindcss">
    @custom-variant dark (&:where(.dark, .dark *));
</style>
```

This removes the Tailwind v3 Play CDN (`cdn.tailwindcss.com`) and `tailwind.config` block entirely. Also bumps Flowbite JS from 4.0.0 → 4.0.1 (line 467).

### 2. FOUC Script — Dark by Default

The viewer currently defaults to system preference:

**Current (lines 29–37):**
```javascript
if (localStorage.getItem('color-theme') === 'dark' ||
    (!('color-theme' in localStorage) &&
     window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    document.documentElement.classList.add('dark');
} else {
    document.documentElement.classList.remove('dark');
}
```

**Target (dark by default, matching extractor UI):**
```javascript
if (localStorage.getItem('color-theme') === 'light') {
    document.documentElement.classList.remove('dark');
} else {
    document.documentElement.classList.add('dark');
}
```

### 3. Dark Mode Toggle — Vanilla JS to Alpine.js

The viewer uses ~40 lines of vanilla JS (lines 470–508) with `document.getElementById` to toggle dark mode icons and persist the theme. This should be replaced with the skill's Alpine.js pattern.

**Remove:**
- The entire `<script>` block at lines 470–508 (vanilla JS toggle logic)
- `id="theme-toggle"`, `id="theme-toggle-dark-icon"`, `id="theme-toggle-light-icon"` from the button/SVG elements

**Add to `iplApp()` in `viewer/app.js`:**
```javascript
darkMode: document.documentElement.classList.contains('dark'),

init() {
    this.$watch('darkMode', (enabled) => {
        document.documentElement.classList.toggle('dark', enabled);
        localStorage.setItem('color-theme', enabled ? 'dark' : 'light');
    });
    // ... existing init code (navigateFromHash, etc.)
}
```

**Replace toggle button HTML (line 155–162):**
```html
<button type="button" @click="darkMode = !darkMode"
        class="text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 focus:outline-none focus:ring-4 focus:ring-gray-200 dark:focus:ring-gray-700 rounded-lg text-sm p-2.5">
    <svg x-show="darkMode" class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
        <path d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" fill-rule="evenodd" clip-rule="evenodd"/>
    </svg>
    <svg x-show="!darkMode" class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
        <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z"></path>
    </svg>
    <span class="sr-only">Toggle dark mode</span>
</button>
```

### 4. Popover Positioning (DO NOT ATTEMPT CASUALLY)

The viewer's `getPopoverStyle()` method in `viewer/app.js` does manual `getBoundingClientRect()` math to position finding popovers. The Alpine.js Anchor plugin (`x-anchor`) could theoretically replace this, but popover/tooltip positioning has been repeatedly problematic in this project.

**Rules for any popover changes:**
- Do NOT attempt without real browser verification
- MUST include Playwright testing against the running app
- Test in both IPL view and exam view
- Test near viewport edges (top, bottom, sides)
- Consider this a separate, standalone task — never bundle with other refactoring

### 5. x-cloak Coverage (Minor)

The viewer currently uses `x-cloak` only on the shared popover element. Check whether other `x-show` elements that start hidden would benefit from `x-cloak` to prevent flash on initial load.

## What Is NOT Needed

- **Semantic token migration** — The project uses classic `dark:` prefix patterns for CDN compatibility. No migration to `text-heading`, `bg-neutral-primary`, etc.
- **Color class changes** — The viewer's existing `dark:` prefix pairs are correct and match the skill's `color-patterns.md`.

## Recommended Order

1. CDN stack update (item 1) + Flowbite version bump
2. FOUC script (item 2) + dark mode toggle (item 3) — these go together
3. x-cloak audit (item 5)
4. Popovers (item 4) — only if explicitly requested, as a separate task

## Verification

The viewer has no Playwright tests. After each change:
1. `python3 -m http.server 8000` from `viewer/`
2. Manual browser check at `http://localhost:8000`
3. Toggle light/dark mode on every view (IPL, Exam, Report)
4. Verify finding popovers still position correctly
5. Test with multiple patients via dropdown
