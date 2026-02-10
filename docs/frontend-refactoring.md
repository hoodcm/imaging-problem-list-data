# Frontend Refactoring Notes

Known technical debt and future refactoring opportunities for the viewer and extractor UI. These are captured for planning purposes — not actions to take now.

## Tailwind v3 to v4 Migration

**Status:** Extractor UI migrated to Tailwind v4. Viewer still on Tailwind v3.

The extractor UI (`extractor-ui/index.html`) uses `@tailwindcss/browser@4` with CSS-based dark mode configuration:
```html
<style type="text/tailwindcss">
    @custom-variant dark (&:where(.dark, .dark *));
</style>
```

The viewer (`viewer/index.html`) still uses `cdn.tailwindcss.com` (Tailwind v3 Play CDN) with:
```javascript
tailwind.config = { darkMode: 'class' }
```

**Remaining migration (viewer only):**
1. Replace `<script src="https://cdn.tailwindcss.com"></script>` with `<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>`
2. Replace `<script> tailwind.config = { darkMode: 'class' } </script>` with `<style type="text/tailwindcss"> @custom-variant dark (&:where(.dark, .dark *)); </style>`
3. Verify all `dark:` utility classes still work correctly
4. Test both light and dark mode thoroughly

## Flowbite Version

**Status:** Extractor UI uses Flowbite 4.0.1. Viewer uses Flowbite 4.0.0.

The viewer (`viewer/index.html`) references `flowbite@4.0.0`. The extractor UI (`extractor-ui/index.html`) has been updated to `flowbite@4.0.1`. The viewer should be bumped to 4.0.1 when it undergoes its Tailwind v4 migration.

## Viewer

**Status:** More technical debt than extractor UI. Higher priority.

The viewer predates the skill conventions — it uses vanilla JS dark mode toggle, manual popover positioning, and likely extensive raw `dark:` class pairs instead of semantic tokens. It also has no Playwright tests (manual verification required).

See `docs/viewer-refactoring.md` for the full cursory plan.

## Extractor UI

**Status:** Already follows better patterns. Lower priority than viewer.

The extractor UI is in better shape (Alpine.js dark mode, proper x-cloak, clean routing, mock mode). Its Tailwind v3→v4 and Flowbite 4.0.1 migration is complete. Remaining work: dark mode naming alignment and a semantic token audit.

See `docs/extractor-ui-refactoring.md` for the full cursory plan.
