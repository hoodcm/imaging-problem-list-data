# Accessibility Patterns

ARIA attributes, keyboard navigation, and screen reader patterns for Flowbite + Alpine.js components.

---

## Core Principles

1. **Semantic HTML first.** Use `<button>`, `<a>`, `<nav>`, `<main>`, `<header>` instead of `<div>` with click handlers.
2. **Every interactive element must be keyboard accessible.** Use native elements (`<button>`, `<a>`, `<input>`) that get focus for free.
3. **ARIA attributes supplement, not replace, semantics.** Add `role`, `aria-*` only when native elements aren't sufficient.
4. **Visible focus indicators.** Never remove `focus:ring-*` classes. They're essential for keyboard users.
5. **Screen reader text.** Use `sr-only` class for icon-only buttons and visual-only content.

---

## ARIA Attributes by Component

### Buttons

```html
<!-- Standard button (no extra ARIA needed) -->
<button type="button" class="...">Click me</button>

<!-- Icon-only button (needs sr-only label) -->
<button type="button" class="..." aria-label="Toggle theme">
    <svg class="w-5 h-5" aria-hidden="true"><!-- icon --></svg>
    <span class="sr-only">Toggle theme</span>
</button>

<!-- Toggle button (has state) -->
<button type="button" aria-pressed="false"
        @click="isActive = !isActive"
        :aria-pressed="isActive.toString()">
    Toggle
</button>
```

### Dropdowns

```html
<!-- Trigger button -->
<button id="dropdownBtn"
        data-dropdown-toggle="dropdownMenu"
        aria-expanded="false"
        aria-haspopup="true">
    Menu
    <svg class="w-2.5 h-2.5 ms-3" aria-hidden="true"><!-- chevron --></svg>
</button>

<!-- Dropdown menu -->
<div id="dropdownMenu" role="menu" aria-labelledby="dropdownBtn" class="hidden ...">
    <ul role="none">
        <li role="none">
            <a role="menuitem" href="#" class="...">Option 1</a>
        </li>
        <li role="none">
            <a role="menuitem" href="#" class="...">Option 2</a>
        </li>
    </ul>
</div>
```

### Modals

```html
<!-- Modal container -->
<div id="myModal" tabindex="-1" aria-hidden="true" aria-labelledby="myModalTitle" role="dialog"
     class="hidden overflow-y-auto overflow-x-hidden fixed ...">
    <div class="relative p-4 w-full max-w-2xl max-h-full">
        <div class="relative bg-white rounded-lg shadow dark:bg-gray-700">
            <!-- Header -->
            <div class="flex items-center justify-between p-4 border-b ...">
                <h3 id="myModalTitle" class="text-xl font-semibold ...">Modal Title</h3>
                <button type="button" data-modal-hide="myModal" aria-label="Close modal"
                        class="text-gray-400 bg-transparent ...">
                    <svg class="w-3 h-3" aria-hidden="true"><!-- close icon --></svg>
                    <span class="sr-only">Close modal</span>
                </button>
            </div>
            <!-- Body -->
            <div class="p-4 md:p-5" role="document">
                <!-- Modal content -->
            </div>
        </div>
    </div>
</div>
```

### Alerts

```html
<div role="alert" class="flex items-center p-4 mb-4 ...">
    <svg class="shrink-0 w-4 h-4 me-3" aria-hidden="true"><!-- icon --></svg>
    <span class="sr-only">Info</span>
    <div>Alert message here.</div>
</div>
```

### Loading States

```html
<div role="status" class="text-center">
    <svg aria-hidden="true" class="inline w-12 h-12 ... animate-spin"><!-- spinner --></svg>
    <span class="sr-only">Loading...</span>
    <p class="mt-4 text-gray-600 dark:text-gray-400" aria-live="polite">Loading data...</p>
</div>
```

### Tooltips

```html
<!-- Flowbite tooltip -->
<button data-tooltip-target="tooltip-1" type="button">Hover me</button>
<div id="tooltip-1" role="tooltip" class="absolute z-10 invisible ...">
    Tooltip content
    <div class="tooltip-arrow" data-popper-arrow></div>
</div>

<!-- Alpine tooltip -->
<div class="relative">
    <button @mouseenter="showTooltip = true" @mouseleave="showTooltip = false"
            aria-describedby="tooltip-2">
        Hover me
    </button>
    <div x-show="showTooltip" id="tooltip-2" role="tooltip" class="absolute z-10 ...">
        Tooltip content
    </div>
</div>
```

### Tables

```html
<div class="relative overflow-x-auto">
    <table class="w-full text-sm text-left ...">
        <thead>
            <tr>
                <th scope="col" class="px-6 py-3">Name</th>
                <th scope="col" class="px-6 py-3">Status</th>
                <th scope="col" class="px-6 py-3">
                    <span class="sr-only">Actions</span>
                </th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <th scope="row" class="px-6 py-4 font-medium ...">Item name</th>
                <td class="px-6 py-4">Active</td>
                <td class="px-6 py-4 text-right">
                    <a href="#" class="font-medium text-blue-600 ...">Edit</a>
                </td>
            </tr>
        </tbody>
    </table>
</div>
```

### Breadcrumbs

```html
<nav class="flex mb-4" aria-label="Breadcrumb">
    <ol class="inline-flex items-center space-x-1 ...">
        <li class="inline-flex items-center" aria-current="page">
            <span class="...">Current Page</span>
        </li>
    </ol>
</nav>
```

### Tabs

```html
<div role="tablist" class="flex flex-wrap -mb-px ...">
    <button role="tab"
            :aria-selected="activeTab === 'tab1'"
            :tabindex="activeTab === 'tab1' ? 0 : -1"
            @click="activeTab = 'tab1'"
            class="inline-flex items-center justify-center p-4 ...">
        Tab 1
    </button>
    <button role="tab"
            :aria-selected="activeTab === 'tab2'"
            :tabindex="activeTab === 'tab2' ? 0 : -1"
            @click="activeTab = 'tab2'"
            class="...">
        Tab 2
    </button>
</div>
<div role="tabpanel" x-show="activeTab === 'tab1'" :hidden="activeTab !== 'tab1'">
    Tab 1 content
</div>
<div role="tabpanel" x-show="activeTab === 'tab2'" :hidden="activeTab !== 'tab2'">
    Tab 2 content
</div>
```

### Accordion

```html
<div data-accordion="collapse">
    <h2>
        <button type="button"
                data-accordion-target="#body-1"
                aria-expanded="true"
                aria-controls="body-1"
                class="flex items-center justify-between w-full p-5 ...">
            <span>Section 1</span>
            <svg data-accordion-icon class="w-3 h-3 rotate-180 shrink-0" aria-hidden="true">
                <!-- chevron -->
            </svg>
        </button>
    </h2>
    <div id="body-1" aria-labelledby="heading-1">
        <div class="p-5 ...">Content</div>
    </div>
</div>
```

---

## Screen Reader Utilities

### `sr-only` Class (Visually Hidden, Screen Reader Accessible)
```html
<!-- For icon-only buttons -->
<button>
    <svg aria-hidden="true"><!-- icon --></svg>
    <span class="sr-only">Delete item</span>
</button>

<!-- For visual indicators that need text alternative -->
<span class="w-3 h-3 bg-green-500 rounded-full" aria-hidden="true"></span>
<span class="sr-only">Status: Active</span>
```

### `aria-hidden="true"` (Hide Decorative Elements)
```html
<!-- Decorative icons -->
<svg aria-hidden="true" class="w-4 h-4"><!-- purely decorative icon --></svg>

<!-- Decorative separators -->
<span aria-hidden="true" class="text-gray-400">|</span>
```

### `aria-live` (Dynamic Content Updates)
```html
<!-- Announce loading state changes -->
<div aria-live="polite">
    <span x-show="loading">Loading...</span>
    <span x-show="!loading" x-text="items.length + ' items loaded'"></span>
</div>

<!-- Announce errors immediately -->
<div aria-live="assertive" x-show="error" x-text="errorMessage"></div>
```

---

## Focus Management

### Focus Ring Classes (Never Remove These)
```html
<!-- Button focus ring (Flowbite v4 tokens) -->
focus:ring-4 focus:ring-brand-medium focus:outline-none

<!-- Input focus -->
focus:ring-brand focus:border-brand

<!-- Icon button focus -->
focus:ring-4 focus:ring-neutral-tertiary focus:outline-none

<!-- Legacy (Tailwind v3 style, used in existing viewer) -->
<!-- focus:ring-4 focus:ring-blue-300 dark:focus:ring-blue-800 focus:outline-none -->
<!-- focus:ring-blue-500 focus:border-blue-500 -->
<!-- focus:ring-4 focus:ring-gray-200 dark:focus:ring-gray-700 focus:outline-none -->
```

### Keyboard Navigation Patterns

| Key | Action |
|-----|--------|
| `Tab` | Move focus to next focusable element |
| `Shift+Tab` | Move focus to previous focusable element |
| `Enter` / `Space` | Activate button/link |
| `Escape` | Close modal/dropdown/popover |
| `Arrow keys` | Navigate within dropdown/menu/tabs |

### Trapping Focus in Modals

Flowbite handles focus trapping automatically when using `data-modal-*` attributes. If using Alpine.js for modals, consider the `@keydown.escape` handler:

```html
<div x-show="isModalOpen"
     @keydown.escape.window="isModalOpen = false"
     role="dialog"
     aria-modal="true">
    <!-- Modal content -->
</div>
```

---

## Dynamic ID Generation

### `x-id` and `$id` — Unique IDs for Accessibility

When building reusable components that need `for`/`id` pairs or `aria-labelledby` attributes, use `x-id` to create a scope and `$id()` to generate unique IDs. This ensures each instance gets its own IDs even when the same component appears multiple times on a page.

### Reusable Form Field Pattern

```html
<template x-for="field in formFields" :key="field.name">
    <div x-id="['input']" class="mb-4">
        <label :for="$id('input')" class="block mb-2.5 text-sm font-medium text-heading"
               x-text="field.label"></label>
        <input :id="$id('input')" type="text" x-model="field.value"
               class="bg-neutral-secondary-medium border border-default-medium text-heading text-sm rounded-base focus:ring-brand focus:border-brand block w-full px-3 py-2.5">
    </div>
</template>
```

Each iteration produces unique IDs (e.g., `input-1`, `input-2`) so `label[for]` always matches the correct `input[id]`.

### Keyed IDs for List Items

```html
<div x-id="['list']">
    <ul :id="$id('list')" role="listbox" :aria-activedescendant="$id('list', activeIndex)">
        <template x-for="(item, index) in items" :key="index">
            <li :id="$id('list', index)" role="option"
                :aria-selected="index === activeIndex"
                @click="activeIndex = index">
                <span x-text="item.name"></span>
            </li>
        </template>
    </ul>
</div>
```

Pass a second argument to `$id('name', suffix)` for loop-specific unique IDs.

---

## Flowbite Data Attributes Reference

Flowbite uses data attributes for interactive behavior. These are processed by `flowbite.min.js`:

| Attribute | Purpose | Example |
|-----------|---------|---------|
| `data-dropdown-toggle="id"` | Toggle a dropdown | `<button data-dropdown-toggle="menu1">` |
| `data-modal-target="id"` | Target a modal | `<button data-modal-target="modal1">` |
| `data-modal-toggle="id"` | Toggle a modal | `<button data-modal-toggle="modal1">` |
| `data-modal-show="id"` | Show a modal | `<button data-modal-show="modal1">` |
| `data-modal-hide="id"` | Hide a modal | `<button data-modal-hide="modal1">` |
| `data-tooltip-target="id"` | Show tooltip on hover | `<button data-tooltip-target="tip1">` |
| `data-accordion="collapse"` | Collapse others on expand | `<div data-accordion="collapse">` |
| `data-accordion="open"` | Keep all open | `<div data-accordion="open">` |
| `data-accordion-target="id"` | Target accordion body | `<button data-accordion-target="#body1">` |
| `data-dismiss-target="id"` | Dismiss/close element | `<button data-dismiss-target="#alert1">` |
| `data-collapse-toggle="id"` | Toggle collapse | `<button data-collapse-toggle="nav1">` |

### Re-initializing After Dynamic Content

When Alpine.js dynamically adds elements with Flowbite data attributes, call:

```javascript
this.$nextTick(() => {
    if (window.initFlowbite) {
        window.initFlowbite();
    }
});
```
