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

## Viewer

**Status:** More technical debt than extractor UI. Higher priority.

The viewer predates the skill conventions — it uses vanilla JS dark mode toggle, manual popover positioning, and likely extensive raw `dark:` class pairs instead of semantic tokens. It also has no Playwright tests (manual verification required).

See `docs/viewer-refactoring.md` for the full cursory plan.

## Extractor UI

**Status:** Already follows better patterns. Lower priority than viewer.

The extractor UI is in better shape (Alpine.js dark mode, proper x-cloak, clean routing, mock mode). It still needs the Tailwind v3→v4 and Flowbite version changes listed above, plus dark mode naming alignment and a semantic token audit.

See `docs/extractor-ui-refactoring.md` for the full cursory plan.
