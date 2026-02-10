# Frontend Refactoring Notes

Known technical debt and future refactoring opportunities for the viewer and extractor UI. These are captured for planning purposes — not actions to take now.

## Tailwind v3 to v4 Migration

**Status:** Both UIs use Tailwind v3. The skill documents Tailwind v4.

Both `viewer/index.html` and `extractor-ui/index.html` use `cdn.tailwindcss.com` (Tailwind v3 Play CDN) with:
```javascript
tailwind.config = { darkMode: 'class' }
```

The skill documents Tailwind v4 (`@tailwindcss/browser@4`) with CSS-based configuration:
```html
<style type="text/tailwindcss">
    @custom-variant dark (&:where(.dark, .dark *));
</style>
```

**Migration steps (for both UIs):**
1. Replace `<script src="https://cdn.tailwindcss.com"></script>` with `<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>`
2. Replace `<script> tailwind.config = { darkMode: 'class' } </script>` with `<style type="text/tailwindcss"> @custom-variant dark (&:where(.dark, .dark *)); </style>`
3. Verify all `dark:` utility classes still work correctly
4. Test both light and dark mode thoroughly

## Flowbite Version

**Status:** Both UIs load Flowbite 4.0.0. Skill references 4.0.1.

Both `viewer/index.html` and `extractor-ui/index.html` reference:
```
flowbite@4.0.0/dist/flowbite.min.css
flowbite@4.0.0/dist/flowbite.min.js
```

The skill documents `flowbite@4.0.1`. Decide which version to standardize on, then update both UIs and the skill to match.

## Viewer Dark Mode Toggle

**Status:** Viewer uses vanilla JS. Extractor UI already uses Alpine.js pattern.

The viewer's dark mode toggle is ~40 lines of vanilla JS using `document.getElementById` (in `viewer/index.html`). It defaults to system preference detection, then falls back to dark mode.

The extractor UI already uses the better Alpine.js pattern: `isDark` state property + `toggleDarkMode()` method in `extractorApp()`.

**Migration plan:** Refactor the viewer to use Alpine.js `darkMode` state with `$watch`, matching the extractor UI and the skill's documented pattern. Note: the viewer's dark mode init logic is slightly different (defaults to system preference, not unconditionally dark) — preserve this behavior during migration.

## Viewer Popover Positioning

**Status:** Manual `getBoundingClientRect()` math. Fragile.

The viewer's `getPopoverStyle()` method does manual viewport math to position finding popovers above or below trigger elements (IPL view), or to the right (exam view).

The Alpine.js Anchor plugin (`x-anchor`) could theoretically replace this, but **popover/tooltip positioning has been repeatedly problematic in this project**. Agents have proposed "simple" fixes that broke on implementation.

**Rules for any popover changes:**
- Do NOT attempt changes without `docker compose up` and real browser verification
- MUST include Playwright testing against the running app
- Test in both IPL view and exam view
- Test near viewport edges (top, bottom, sides)

## Extractor UI

**Status:** Already follows better patterns. Lower priority than viewer.

The extractor UI is in better shape (Alpine.js dark mode, proper x-cloak, clean routing, mock mode). It still needs the Tailwind v3→v4 and Flowbite version changes listed above, plus dark mode naming alignment and a semantic token audit.

See `docs/extractor-ui-refactoring.md` for the full cursory plan.
