---
name: flowbite-tailwind-alpine
description: Build and maintain UI components using Flowbite, Tailwind CSS, and Alpine.js. Use when creating pages, adding components, styling elements, implementing dark mode, or working with interactive UI in static SPA setups.
---

# Flowbite + Tailwind CSS + Alpine.js UI Development

Use this skill when implementing or modifying UI components in static HTML applications that use Flowbite, Tailwind CSS, and Alpine.js without a build step.

## Version Matrix

| Library | Version | CDN |
|---------|---------|-----|
| Flowbite CSS | 4.0.1 | `cdn.jsdelivr.net/npm/flowbite@4.0.1/dist/flowbite.min.css` |
| Tailwind CSS | 4.x (browser CDN) | `cdn.jsdelivr.net/npm/@tailwindcss/browser@4` |
| Flowbite JS | 4.0.1 | `cdn.jsdelivr.net/npm/flowbite@4.0.1/dist/flowbite.min.js` |
| Alpine.js | 3.x | `cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js` |

> **Flowbite CSS includes a complete Tailwind v4 build** (utilities, theme, base resets, plus Flowbite plugin styles). The Tailwind browser CDN is loaded *after* Flowbite CSS to add dynamic utility generation and class-based dark mode via `@custom-variant dark`.

## Core Rules

1. **No build step.** All UI is vanilla HTML/JS/CSS loaded via CDN. Never introduce bundlers, compilers, or frameworks.
2. **Flowbite components first.** Use Flowbite's documented markup and data attributes before writing custom Tailwind. Check `references/component-templates.md` for ready-to-use patterns.
3. **Alpine.js for all interactivity.** Use `x-data`, `x-show`, `x-for`, `x-on`, `x-model`, `x-text`, `x-html`, and `x-cloak`. Never add standalone DOM-manipulating JS when Alpine can handle it.
4. **Classic `dark:` prefix for colors.** Use standard Tailwind color classes with `dark:` prefixes for dark mode (e.g., `bg-white dark:bg-gray-800`, `text-gray-900 dark:text-white`). Flowbite's semantic tokens (`text-heading`, `bg-neutral-primary-soft`, etc.) require a build step with the Flowbite Tailwind plugin and **do not work** with the CDN-only setup.
5. **Class-based dark mode.** We use the `dark` class on `<html>`. Standard Tailwind `dark:` prefixes handle color switching.
6. **Consistent color patterns.** Follow the classic color patterns documented in `references/color-patterns.md`.
7. **x-cloak is mandatory.** Every page must include `[x-cloak] { display: none !important; }` in the `<head>` and `x-cloak` on any element using `x-show` that should start hidden. This prevents flash of unstyled content before Alpine initializes.
8. **Dark mode default, always switchable.** Every page ships with dark mode active by default. Every page must include the FOUC-prevention script in `<head>` and a visible dark mode toggle button. Never ship a page without a toggle.

## CDN Stack

```html
<!-- 1. Flowbite CSS (includes Tailwind v4 + Flowbite plugin styles) -->
<link href="https://cdn.jsdelivr.net/npm/flowbite@4.0.1/dist/flowbite.min.css" rel="stylesheet" />

<!-- 2. Tailwind CSS v4 browser CDN (dynamic utility generation + class-based dark mode) -->
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
<style type="text/tailwindcss">
    @custom-variant dark (&:where(.dark, .dark *));
</style>

<!-- 3. Alpine.js (defer so it loads after DOM) -->
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

<!-- 4. Flowbite JS (at end of body, before app.js) -->
<script src="https://cdn.jsdelivr.net/npm/flowbite@4.0.1/dist/flowbite.min.js"></script>

<!-- 5. App logic (after Flowbite JS) -->
<script src="app.js"></script>
```

**Load order matters:** Flowbite CSS -> Tailwind v4 browser CDN -> `@custom-variant dark` -> Alpine.js (deferred) -> Dark mode init script -> x-cloak CSS -> ... body ... -> Flowbite JS -> App JS.

## Workflow

1. **Read existing code** before modifying.
2. **Check `references/component-templates.md`** for the correct Flowbite v4 markup for the component you need.
3. **Check `references/alpine-patterns.md`** for the correct Alpine.js integration pattern.
4. **Check `references/color-patterns.md`** for the classic `dark:` prefix color patterns.
5. **Implement** using the established patterns. Extend your app's component function for new state/methods.
6. **Verify theming** by confirming all color classes have proper `dark:` prefix counterparts for dark mode support.

## Quick Decision Guide

| Need | Use | Reference |
|------|-----|-----------|
| Dropdown, modal, tooltip, accordion | Flowbite data attributes | `references/component-templates.md` |
| Show/hide, loops, conditionals | Alpine.js directives | `references/alpine-patterns.md` |
| Color for text, bg, border | Classic Tailwind + `dark:` prefix | `references/color-patterns.md` |
| New page state or data | Extend your app component function | `references/alpine-patterns.md` |
| Responsive layout | Tailwind grid/flex utilities | `references/component-templates.md` |
| Loading/empty states | Flowbite spinner + text | `references/component-templates.md` |

## Anti-Patterns

1. **Never** use `document.querySelector` for show/hide when `x-show` works.
2. **Never** add inline `onclick` handlers — use `@click` (Alpine).
3. **Never** use Flowbite semantic tokens (`text-heading`, `bg-brand`, `bg-neutral-primary`, etc.) in CDN-only pages — they require a build step and resolve to nothing without it. Use classic `dark:` prefix pairs instead (e.g., `text-gray-900 dark:text-white`).
4. **Never** add `<style>` blocks for things Tailwind utilities can handle.
5. **Never** create separate JS files for minor features — extend your app's component function. For larger apps, see `Alpine.store()` and `Alpine.data()` patterns in the Alpine reference.
6. **Never** use `x-if` when `x-show` suffices (x-if removes from DOM, x-show just hides).
7. **Never** omit the `@custom-variant dark (&:where(.dark, .dark *));` directive — without it, `dark:` prefixes use `prefers-color-scheme` media queries instead of responding to the `.dark` class on `<html>`.
8. **Never** load the Tailwind browser CDN *before* Flowbite CSS — Flowbite CSS must load first so the browser CDN's class-based dark variants take precedence.
9. **Never** omit `x-cloak` from `x-show` elements that start hidden — it causes flash of unstyled content before Alpine initializes.
10. **Never** ship a page without a dark mode toggle — users must always be able to switch between light and dark mode.

## References

Read these files as needed:

- `references/component-templates.md` for complete HTML templates of common Flowbite v4 components.
- `references/alpine-patterns.md` for Alpine.js integration patterns, state management, event handling, global stores, reusable components, plugins, and cross-component communication.
- `references/color-patterns.md` for classic `dark:` prefix color patterns, component class strings, and badge/alert patterns.
- `references/accessibility.md` for ARIA attributes, keyboard navigation, and screen reader patterns.
