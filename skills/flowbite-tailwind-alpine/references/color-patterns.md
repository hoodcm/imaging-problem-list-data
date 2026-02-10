# Color & Design Token System

This project uses **classic Tailwind `dark:` prefix patterns** for dark mode. All pages are CDN-only (no build step), so Flowbite's semantic design tokens (`text-heading`, `bg-brand`, etc.) are **not available** — they require the Flowbite Tailwind plugin to define CSS custom properties.

## Quick Rule

Use standard Tailwind color classes with `dark:` prefixes for all dark mode styling. Semantic tokens will become available if/when the project adopts a build step.

---

## Standard Color Patterns (CDN-Compatible)

### Background Patterns

| Purpose | Classes |
|---------|---------|
| Page background | `bg-gray-50 dark:bg-gray-900` |
| Card, panel, header | `bg-white dark:bg-gray-800` |
| Dropdown menu | `bg-white dark:bg-gray-700` |
| Table header, inner panel | `bg-gray-50 dark:bg-gray-800` |
| Form inputs, gray badges | `bg-gray-50 dark:bg-gray-700` |
| Hover states | `hover:bg-gray-100 dark:hover:bg-gray-700` |
| Primary button | `bg-blue-700 dark:bg-blue-600 hover:bg-blue-800 dark:hover:bg-blue-700` |
| Info alert, brand badge | `bg-blue-50 dark:bg-blue-900/30` |
| Success alert/badge | `bg-green-50 dark:bg-green-900/30` |
| Danger alert/badge | `bg-red-50 dark:bg-red-900/30` |
| Warning alert/badge | `bg-yellow-50 dark:bg-yellow-900/20` |

### Text Patterns

| Purpose | Classes |
|---------|---------|
| Headings, titles, labels | `text-gray-900 dark:text-white` |
| Body text, secondary text | `text-gray-500 dark:text-gray-400` |
| Link/action text | `text-blue-600 dark:text-blue-500` |
| Info badge/alert text | `text-blue-800 dark:text-blue-400` |
| Success badge/alert text | `text-green-800 dark:text-green-400` |
| Danger badge/alert text | `text-red-800 dark:text-red-400` |
| Warning badge/alert text | `text-yellow-800 dark:text-yellow-300` |

### Border Patterns

| Purpose | Classes |
|---------|---------|
| Card, section, table borders | `border-gray-200 dark:border-gray-700` |
| Input, select, button borders | `border-gray-300 dark:border-gray-600` |

### Focus Ring Patterns

| Purpose | Classes |
|---------|---------|
| Primary button focus | `focus:ring-4 focus:ring-blue-300 dark:focus:ring-blue-800` |
| Input focus | `focus:ring-blue-500 focus:border-blue-500` |
| Secondary/icon button focus | `focus:ring-4 focus:ring-gray-200 dark:focus:ring-gray-700` |

---

## Complete Component Class Strings

### Card
```
bg-white dark:bg-gray-800 p-6 border border-gray-200 dark:border-gray-700 rounded-lg shadow
```

### Primary Button
```
text-white bg-blue-700 dark:bg-blue-600 hover:bg-blue-800 dark:hover:bg-blue-700 focus:ring-4 focus:ring-blue-300 dark:focus:ring-blue-800 font-medium rounded-lg text-sm px-5 py-2.5 focus:outline-none
```

### Secondary Button
```
text-gray-900 dark:text-white bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 focus:ring-4 focus:ring-gray-200 dark:focus:ring-gray-700 font-medium rounded-lg text-sm px-5 py-2.5 focus:outline-none
```

### Text Input
```
bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:placeholder-gray-400
```

### Select
```
block w-full p-2.5 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 dark:placeholder-gray-400
```

### Label
```
block mb-2 text-sm font-medium text-gray-900 dark:text-white
```

---

## Status Badge Patterns

| Status | Classes |
|--------|---------|
| Brand/Info | `bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-300` |
| Success/Active | `bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-300` |
| Warning/Resolved | `bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-300` |
| Danger/Error | `bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-300` |
| Gray/Default | `bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300` |

### Alert Patterns

| Type | Classes |
|------|---------|
| Info | `text-blue-800 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30` |
| Success | `text-green-800 dark:text-green-400 bg-green-50 dark:bg-green-900/30` |
| Warning | `text-yellow-800 dark:text-yellow-300 bg-yellow-50 dark:bg-yellow-900/20` |
| Danger | `text-red-800 dark:text-red-400 bg-red-50 dark:bg-red-900/30` |

---

## Dark Mode Toggle Implementation

> **Dark mode is the default.** When no localStorage preference exists, pages render in dark mode. Every page must include a visible toggle.

### FOUC-Prevention Script (In `<head>` — Required)

This script runs before the page renders. It defaults to dark mode unless the user has explicitly chosen light.

```html
<script>
    if (localStorage.getItem('color-theme') === 'light') {
        document.documentElement.classList.remove('dark');
    } else {
        document.documentElement.classList.add('dark');
    }
</script>
```

### Toggle Implementation

See `references/component-templates.md` for the complete dark mode toggle button component, app state, and header integration example. The key pattern: Alpine.js `darkMode` state + `$watch` to sync DOM class and localStorage.

---

## Custom Color Patterns (Beyond Standard Grays/Blues)

For elements that need non-standard colors (purple, indigo, etc.), use raw Tailwind classes with `dark:` prefix:

### Custom Status Colors
```html
<!-- Purple: Inactive / Never -->
<span class="bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300 text-xs font-medium px-1.5 py-0.5 rounded">
    Inactive
</span>
```

### Text Highlight
```html
<mark class="bg-yellow-300 dark:bg-yellow-600 px-1">highlighted text</mark>
```

### Scrollbar Colors (Custom CSS)

```css
/* Light mode */
::-webkit-scrollbar-track {
    background-color: rgb(243 244 246);  /* gray-100 */
}
::-webkit-scrollbar-thumb {
    background-color: rgb(209 213 219);  /* gray-300 */
}
::-webkit-scrollbar-thumb:hover {
    background-color: rgb(156 163 175);  /* gray-400 */
}

/* Dark mode */
.dark ::-webkit-scrollbar-track {
    background-color: rgb(17 24 39);     /* gray-900 */
}
.dark ::-webkit-scrollbar-thumb {
    background-color: rgb(55 65 81);     /* gray-700 */
}
.dark ::-webkit-scrollbar-thumb:hover {
    background-color: rgb(75 85 99);     /* gray-600 */
}
```

---

## Tailwind Dark Mode Configuration (CDN)

### CDN Setup
```html
<!-- Flowbite CSS first (includes Tailwind v4) -->
<link href="https://cdn.jsdelivr.net/npm/flowbite@4.0.1/dist/flowbite.min.css" rel="stylesheet" />

<!-- Tailwind v4 browser CDN after (adds dynamic utilities + class-based dark mode) -->
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
<style type="text/tailwindcss">
    @custom-variant dark (&:where(.dark, .dark *));
</style>
```

The `@custom-variant dark` directive makes `dark:` prefixes respond to the `.dark` class on `<html>` instead of the default `prefers-color-scheme` media query.

---

## Flowbite v4 Semantic Tokens (Build Step Only)

> **These tokens do NOT work in CDN-only setups.** They require the Flowbite Tailwind plugin (`flowbite/plugin`) in a build step to define CSS custom properties (`--color-brand`, `--color-heading`, etc.). The `@tailwindcss/browser@4` CDN does not load these properties.
>
> This section is preserved as reference for future adoption if a build step is introduced.

### Mapping: Classic → Semantic Token

| Classic Tailwind (light + dark) | Semantic Token |
|---------------------------------|----------------|
| `bg-white dark:bg-gray-900` | `bg-neutral-primary` |
| `bg-white dark:bg-gray-800` | `bg-neutral-primary-soft` |
| `bg-gray-50 dark:bg-gray-700` | `bg-neutral-secondary-medium` |
| `bg-blue-700 dark:bg-blue-600` | `bg-brand` |
| `text-gray-900 dark:text-white` | `text-heading` |
| `text-gray-500 dark:text-gray-400` | `text-body` |
| `text-blue-600 dark:text-blue-500` | `text-fg-brand` |
| `border-gray-200 dark:border-gray-700` | `border-default` |
| `border-gray-300 dark:border-gray-600` | `border-default-medium` |
| `rounded-lg` | `rounded-base` |
| `shadow` | `shadow-xs` |
