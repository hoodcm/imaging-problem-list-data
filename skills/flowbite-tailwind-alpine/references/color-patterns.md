# Color & Design Token System

Flowbite v4 uses semantic design tokens powered by CSS custom properties. Dark mode is handled automatically — no `dark:` prefix needed for standard token classes.

## Quick Rule

Use Flowbite v4 semantic tokens for all colors. The tokens automatically adapt to light/dark mode. Only use raw Tailwind color classes with `dark:` prefixes for custom elements not covered by tokens.

---

## Flowbite v4 Semantic Token Reference

### Background Tokens

| Token | Purpose | Light Equivalent | Dark Equivalent |
|-------|---------|-----------------|-----------------|
| `bg-neutral-primary` | Page background | `bg-white` | `bg-gray-900` |
| `bg-neutral-primary-soft` | Card, panel, header | `bg-white` | `bg-gray-800` |
| `bg-neutral-primary-medium` | Dropdown menu | `bg-white` | `bg-gray-700` |
| `bg-neutral-secondary-soft` | Table header, hover tab | `bg-gray-50` | `bg-gray-800` |
| `bg-neutral-secondary-medium` | Form inputs, gray badges | `bg-gray-50` | `bg-gray-700` |
| `bg-neutral-tertiary` | Close button hover | `bg-gray-200` | `bg-gray-600` |
| `bg-neutral-tertiary-medium` | Dropdown item hover | `bg-gray-100` | `bg-gray-600` |
| `bg-brand` | Primary button | `bg-blue-700` | `bg-blue-600` |
| `bg-brand-strong` | Primary button hover | `bg-blue-800` | `bg-blue-700` |
| `bg-brand-softer` | Info alert, brand badge | `bg-blue-50` | `bg-blue-900` |
| `bg-success-soft` | Success alert/badge | `bg-green-100` | `bg-green-800` |
| `bg-danger-soft` | Danger alert/badge | `bg-red-100` | `bg-red-900` |
| `bg-danger` | Danger button | `bg-red-700` | `bg-red-600` |
| `bg-danger-strong` | Danger button hover | `bg-red-800` | `bg-red-700` |
| `bg-warning-soft` | Warning alert/badge | `bg-yellow-100` | `bg-yellow-800` |

### Hover Background Tokens

| Token | Purpose |
|-------|---------|
| `hover:bg-brand-strong` | Primary button hover |
| `hover:bg-neutral-secondary-medium` | Card hover, interactive element |
| `hover:bg-neutral-secondary-soft` | Table row hover, tab hover |
| `hover:bg-neutral-tertiary` | Close button hover |
| `hover:bg-neutral-tertiary-medium` | Dropdown item hover |

### Text/Foreground Tokens

| Token | Purpose | Light Equivalent | Dark Equivalent |
|-------|---------|-----------------|-----------------|
| `text-heading` | Headings, titles, labels | `text-gray-900` | `text-white` |
| `text-body` | Body text, secondary text | `text-gray-500` | `text-gray-400` |
| `text-body-subtle` | Muted/tertiary text | `text-gray-500` | `text-gray-500` |
| `text-fg-brand` | Link/action text, active tab | `text-blue-600` | `text-blue-500` |
| `text-fg-brand-strong` | Info badge/alert text | `text-blue-800` | `text-blue-400` |
| `text-fg-success-strong` | Success badge/alert text | `text-green-800` | `text-green-400` |
| `text-fg-danger-strong` | Danger badge/alert text | `text-red-800` | `text-red-400` |
| `text-fg-warning` | Warning badge/alert text | `text-yellow-800` | `text-yellow-300` |
| `text-fg-disabled` | Disabled tab/element text | `text-gray-400` | `text-gray-500` |

### Hover Text Tokens

| Token | Purpose |
|-------|---------|
| `hover:text-heading` | Text darkening on hover |
| `hover:text-fg-brand` | Link hover |

### Border Tokens

| Token | Purpose | Light Equivalent | Dark Equivalent |
|-------|---------|-----------------|-----------------|
| `border-default` | Card, section, table borders | `border-gray-200` | `border-gray-700` |
| `border-default-medium` | Input, select, button borders | `border-gray-300` | `border-gray-600` |
| `divide-default` | List dividers | `divide-gray-100` | `divide-gray-600` |

### Focus Ring Tokens

| Token | Purpose |
|-------|---------|
| `focus:ring-brand` | Input focus ring |
| `focus:ring-brand-medium` | Primary button focus ring |
| `focus:ring-neutral-tertiary` | Secondary/icon button focus ring |
| `focus:ring-danger-medium` | Danger button focus ring |
| `focus:border-brand` | Input focus border |

### Shape Tokens

| Token | Classic Equivalent |
|-------|--------------------|
| `rounded-base` | `rounded-lg` |
| `rounded-t-base` | `rounded-t-lg` |
| `shadow-xs` | `shadow` |
| `shadow-sm` | `shadow-md` |

---

## Complete Component Class Strings (Flowbite v4)

### Card
```
bg-neutral-primary-soft p-6 border border-default rounded-base shadow-xs
```

### Primary Button
```
text-white bg-brand box-border border border-transparent hover:bg-brand-strong focus:ring-4 focus:ring-brand-medium shadow-xs font-medium leading-5 rounded-base text-sm px-4 py-2.5 focus:outline-none
```

### Secondary Button
```
text-body bg-neutral-secondary-medium box-border border border-default-medium hover:bg-neutral-tertiary-medium hover:text-heading focus:ring-4 focus:ring-neutral-tertiary shadow-xs font-medium leading-5 rounded-base text-sm px-4 py-2.5 focus:outline-none
```

### Text Input
```
bg-neutral-secondary-medium border border-default-medium text-heading text-sm rounded-base focus:ring-brand focus:border-brand block w-full px-3 py-2.5 shadow-xs placeholder:text-body
```

### Select
```
block w-full px-3 py-2.5 bg-neutral-secondary-medium border border-default-medium text-heading text-sm rounded-base focus:ring-brand focus:border-brand shadow-xs placeholder:text-body
```

### Label
```
block mb-2.5 text-sm font-medium text-heading
```

### Badge (base, add status colors)
```
text-xs font-medium px-1.5 py-0.5 rounded
```

### Rounded Pill Badge (base)
```
text-xs font-medium px-2.5 py-0.5 rounded-full
```

### Table Header Row
```
text-sm text-body bg-neutral-secondary-soft border-b border-default
```

### Table Body Row
```
bg-neutral-primary border-b border-default hover:bg-neutral-secondary-soft
```

### Sticky Header
```
bg-neutral-primary-soft border-b border-default sticky top-0 z-40
```

### Content Container
```
max-w-7xl mx-auto px-4 sm:px-6 lg:px-8
```

---

## Status Badge Patterns

### With Semantic Tokens (Flowbite v4)

| Status | Classes |
|--------|---------|
| Brand/Info | `bg-brand-softer text-fg-brand-strong` |
| Success/Active | `bg-success-soft text-fg-success-strong` |
| Warning/Resolved | `bg-warning-soft text-fg-warning` |
| Danger/Error | `bg-danger-soft text-fg-danger-strong` |
| Gray/Default | `bg-neutral-secondary-medium text-heading` |
| Light/Alternative | `bg-neutral-primary-soft text-heading` |

### Alert Patterns

| Type | Classes |
|------|---------|
| Info | `text-fg-brand-strong bg-brand-softer` |
| Success | `text-fg-success-strong bg-success-soft` |
| Warning | `text-fg-warning bg-warning-soft` |
| Danger | `text-fg-danger-strong bg-danger-soft` |
| Neutral | `text-heading bg-neutral-secondary-medium` |

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

See `references/component-templates.md` § Dark Mode Toggle for the complete button component, app state, and header integration example. The key integration point: Flowbite v4 semantic tokens automatically switch values when the `dark` class is toggled on `<html>` — no additional CSS needed.

---

## Custom Color Patterns (Outside Flowbite Tokens)

For elements that need colors NOT covered by Flowbite's semantic tokens (e.g., custom status colors like purple, or highlighting), use raw Tailwind classes with `dark:` prefix:

### Custom Status Colors (No Token Equivalent)
```html
<!-- Purple: Inactive / Never (no Flowbite token for purple) -->
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

## Legacy Classic Tailwind to Semantic Token Mapping

Use this table when migrating existing code from classic `dark:` prefix patterns to Flowbite v4 semantic tokens.

### Background Mappings

| Classic Tailwind (light + dark) | Flowbite v4 Token |
|---------------------------------|-------------------|
| `bg-white dark:bg-gray-900` | `bg-neutral-primary` |
| `bg-white dark:bg-gray-800` | `bg-neutral-primary-soft` |
| `bg-white dark:bg-gray-700` | `bg-neutral-primary-medium` |
| `bg-gray-50 dark:bg-gray-800` | `bg-neutral-secondary-soft` |
| `bg-gray-50 dark:bg-gray-700` | `bg-neutral-secondary-medium` |
| `bg-gray-100 dark:bg-gray-700` | `bg-neutral-secondary-medium` |
| `bg-gray-200 dark:bg-gray-600` | `bg-neutral-tertiary` |
| `bg-gray-100 dark:bg-gray-600` | `bg-neutral-tertiary-medium` |
| `bg-blue-700 dark:bg-blue-600` | `bg-brand` |
| `bg-blue-50 dark:bg-blue-900` | `bg-brand-softer` |
| `bg-green-100 dark:bg-green-800` | `bg-success-soft` |
| `bg-red-100 dark:bg-red-900` | `bg-danger-soft` |
| `bg-yellow-100 dark:bg-yellow-800` | `bg-warning-soft` |

### Text Mappings

| Classic Tailwind (light + dark) | Flowbite v4 Token |
|---------------------------------|-------------------|
| `text-gray-900 dark:text-white` | `text-heading` |
| `text-gray-500 dark:text-gray-400` | `text-body` |
| `text-gray-500 dark:text-gray-500` | `text-body-subtle` |
| `text-blue-600 dark:text-blue-500` | `text-fg-brand` |
| `text-blue-800 dark:text-blue-400` | `text-fg-brand-strong` |
| `text-green-800 dark:text-green-400` | `text-fg-success-strong` |
| `text-red-800 dark:text-red-400` | `text-fg-danger-strong` |
| `text-yellow-800 dark:text-yellow-300` | `text-fg-warning` |
| `text-gray-400 dark:text-gray-500` | `text-fg-disabled` |

### Border Mappings

| Classic Tailwind (light + dark) | Flowbite v4 Token |
|---------------------------------|-------------------|
| `border-gray-200 dark:border-gray-700` | `border-default` |
| `border-gray-300 dark:border-gray-600` | `border-default-medium` |

### Shape Mappings

| Classic Tailwind | Flowbite v4 Token |
|------------------|-------------------|
| `rounded-lg` | `rounded-base` |
| `rounded-t-lg` | `rounded-t-base` |
| `shadow` | `shadow-xs` |

### Focus Ring Mappings

| Classic Tailwind (light + dark) | Flowbite v4 Token |
|---------------------------------|-------------------|
| `focus:ring-blue-300 dark:focus:ring-blue-800` | `focus:ring-brand-medium` |
| `focus:ring-gray-200 dark:focus:ring-gray-700` | `focus:ring-neutral-tertiary` |
| `focus:ring-red-300 dark:focus:ring-red-900` | `focus:ring-danger-medium` |
| `focus:ring-blue-500` | `focus:ring-brand` |
| `focus:border-blue-500` | `focus:border-brand` |

---

## Neutral Background Tier System

Flowbite v4 uses a three-tier neutral background system, each with `-soft` and `-medium` variants:

| Tier | Soft Variant | Medium Variant | Use Case |
|------|-------------|----------------|----------|
| Primary | `bg-neutral-primary-soft` (white/gray-800) | `bg-neutral-primary-medium` (white/gray-700) | Cards, panels, dropdowns |
| Secondary | `bg-neutral-secondary-soft` (gray-50/gray-800) | `bg-neutral-secondary-medium` (gray-50/gray-700) | Table headers, form inputs |
| Tertiary | `bg-neutral-tertiary` (gray-200/gray-600) | `bg-neutral-tertiary-medium` (gray-100/gray-600) | Hover states, emphasis |

`bg-neutral-primary` (no suffix) is the deepest level — used for page background (white/gray-900).

---

## Tailwind v4 Dark Mode Configuration

### CDN Setup
```html
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
<style type="text/tailwindcss">
    @custom-variant dark (&:where(.dark, .dark *));
</style>
```

### Key Differences from Tailwind v3

| Feature | Tailwind v3 | Tailwind v4 |
|---------|------------|------------|
| CDN URL | `cdn.tailwindcss.com` | `cdn.jsdelivr.net/npm/@tailwindcss/browser@4` |
| Config format | JS: `tailwind.config = { ... }` | CSS: `<style type="text/tailwindcss">` |
| Dark mode | `darkMode: 'class'` in JS config | `@custom-variant dark (...)` in CSS |
| Theme extension | `theme: { extend: { ... } }` in JS | `@theme { ... }` in CSS |
| Default dark mode | Media query | Media query (same) |

**Important:** `@custom-variant` **defines** a variant override. There is also `@variant` which **applies** an existing variant to a CSS block — different purposes. Use `@custom-variant` for dark mode configuration.
