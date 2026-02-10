---
name: flowbite-tailwind-alpine
description: Build and maintain UI components using Flowbite, Tailwind CSS, and Alpine.js. Use when creating pages, adding components, styling elements, implementing dark mode, or working with interactive UI in static SPA setups.
---

# Flowbite + Tailwind CSS + Alpine.js UI Development

Use this skill when implementing or modifying UI components in static HTML applications that use Flowbite, Tailwind CSS, and Alpine.js without a build step.

## Version Matrix

| Library | Version | CDN |
|---------|---------|-----|
| Tailwind CSS | 4.x | `@tailwindcss/browser@4` |
| Flowbite | 4.0.1 | `cdn.jsdelivr.net/npm/flowbite@4.0.1` |
| Alpine.js | 3.x | `cdn.jsdelivr.net/npm/alpinejs@3.x.x` |

## Core Rules

1. **No build step.** All UI is vanilla HTML/JS/CSS loaded via CDN. Never introduce bundlers, compilers, or frameworks.
2. **Flowbite components first.** Use Flowbite's documented markup and data attributes before writing custom Tailwind. Check `references/component-templates.md` for ready-to-use patterns.
3. **Alpine.js for all interactivity.** Use `x-data`, `x-show`, `x-for`, `x-on`, `x-model`, `x-text`, `x-html`, and `x-cloak`. Never add standalone DOM-manipulating JS when Alpine can handle it.
4. **Flowbite v4 semantic tokens.** Use Flowbite's semantic design tokens (`text-heading`, `bg-neutral-primary-soft`, `border-default`, etc.) instead of raw Tailwind color classes with `dark:` prefixes. The semantic tokens automatically handle dark mode via CSS variables — no `dark:` prefix needed for most elements.
5. **Class-based dark mode.** We use the `dark` class on `<html>`. Flowbite's CSS variables automatically switch values when this class is present.
6. **Consistent token usage.** Follow the semantic token system exactly (see `references/color-patterns.md`).
7. **x-cloak is mandatory.** Every page must include `[x-cloak] { display: none !important; }` in the `<head>` and `x-cloak` on any element using `x-show` that should start hidden. This prevents flash of unstyled content before Alpine initializes.
8. **Dark mode default, always switchable.** Every page ships with dark mode active by default. Every page must include the FOUC-prevention script in `<head>` and a visible dark mode toggle button. Never ship a page without a toggle.

## CDN Stack (Tailwind v4 + Flowbite v4)

```html
<!-- 1. Tailwind CSS v4 Play CDN -->
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>

<!-- 2. Tailwind v4 config: class-based dark mode -->
<style type="text/tailwindcss">
    @custom-variant dark (&:where(.dark, .dark *));
</style>

<!-- 3. Flowbite CSS -->
<link href="https://cdn.jsdelivr.net/npm/flowbite@4.0.1/dist/flowbite.min.css" rel="stylesheet" />

<!-- 4. Alpine.js (defer so it loads after DOM) -->
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>

<!-- REQUIRED: Dark mode init — defaults to dark, prevents FOUC -->
<script>
    if (localStorage.getItem('color-theme') === 'light') {
        document.documentElement.classList.remove('dark');
    } else {
        document.documentElement.classList.add('dark');
    }
</script>

<!-- REQUIRED: x-cloak CSS — prevents flash of unstyled content -->
<style>
    [x-cloak] { display: none !important; }
</style>

<!-- 5. Flowbite JS (at end of body, before app.js) -->
<script src="https://cdn.jsdelivr.net/npm/flowbite@4.0.1/dist/flowbite.min.js"></script>

<!-- 6. App logic (after Flowbite JS) -->
<script src="app.js"></script>
```

**Load order matters:** Tailwind CDN -> Tailwind config style -> Flowbite CSS -> Alpine.js (deferred) -> Dark mode init script -> x-cloak CSS -> ... body ... -> Flowbite JS -> App JS.

**Key Tailwind v4 change:** Dark mode config is now CSS-based via `@custom-variant` in a `<style type="text/tailwindcss">` block. The old `tailwind.config = { darkMode: 'class' }` JS pattern is Tailwind v3 only.

## Workflow

1. **Read existing code** before modifying.
2. **Check `references/component-templates.md`** for the correct Flowbite v4 markup for the component you need.
3. **Check `references/alpine-patterns.md`** for the correct Alpine.js integration pattern.
4. **Check `references/color-patterns.md`** for the semantic token system and legacy class mappings.
5. **Implement** using the established patterns. Extend your app's component function for new state/methods.
6. **Verify theming** by confirming semantic tokens are used (no manual `dark:` prefixes needed for Flowbite token classes).

## Quick Decision Guide

| Need | Use | Reference |
|------|-----|-----------|
| Dropdown, modal, tooltip, accordion | Flowbite data attributes | `references/component-templates.md` |
| Show/hide, loops, conditionals | Alpine.js directives | `references/alpine-patterns.md` |
| Color for text, bg, border | Flowbite semantic tokens | `references/color-patterns.md` |
| New page state or data | Extend your app component function | `references/alpine-patterns.md` |
| Responsive layout | Tailwind grid/flex utilities | `references/component-templates.md` |
| Loading/empty states | Flowbite spinner + text | `references/component-templates.md` |

## Anti-Patterns

1. **Never** use `document.querySelector` for show/hide when `x-show` works.
2. **Never** add inline `onclick` handlers — use `@click` (Alpine).
3. **Never** use raw `dark:` prefix color pairs when a Flowbite semantic token exists (e.g., use `text-heading` not `text-gray-900 dark:text-white`).
4. **Never** add `<style>` blocks for things Tailwind utilities can handle.
5. **Never** create separate JS files for minor features — extend your app's component function. For larger apps, see `Alpine.store()` and `Alpine.data()` patterns in the Alpine reference.
6. **Never** use `x-if` when `x-show` suffices (x-if removes from DOM, x-show just hides).
7. **Never** use `cdn.tailwindcss.com` in new pages — that is the Tailwind v3 CDN.
8. **Never** use `tailwind.config = { ... }` JS config — Tailwind v4 uses CSS-based config with `@custom-variant`.
9. **Never** omit `x-cloak` from `x-show` elements that start hidden — it causes flash of unstyled content before Alpine initializes.
10. **Never** ship a page without a dark mode toggle — users must always be able to switch between light and dark mode.

## References

Read these files as needed:

- `references/component-templates.md` for complete HTML templates of every common Flowbite v4 component with semantic tokens.
- `references/alpine-patterns.md` for Alpine.js integration patterns, state management, event handling, global stores, reusable components, plugins, and cross-component communication.
- `references/color-patterns.md` for the semantic token system, legacy class mappings, and custom color patterns.
- `references/accessibility.md` for ARIA attributes, keyboard navigation, and screen reader patterns.
