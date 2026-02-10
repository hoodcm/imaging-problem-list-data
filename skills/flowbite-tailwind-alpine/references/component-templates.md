# Flowbite v4 Component Templates

Copy-paste ready templates using Flowbite v4 semantic design tokens. Dark mode is handled automatically by the tokens — no `dark:` prefixes needed for standard elements.

## Table of Contents

1. [Page Boilerplate](#page-boilerplate)
2. [Buttons](#buttons)
3. [Dropdowns](#dropdowns)
4. [Cards](#cards)
5. [Modals](#modals)
6. [Badges & Pills](#badges--pills)
7. [Alerts](#alerts)
8. [Tables](#tables)
9. [Tabs](#tabs)
10. [Forms](#forms)
11. [Tooltips](#tooltips)
12. [Accordions](#accordions)
13. [Breadcrumbs](#breadcrumbs)
14. [Spinners & Loading](#spinners--loading)
15. [Empty States](#empty-states)
16. [Popovers](#popovers)
17. [Toasts](#toasts)
18. [Pagination](#pagination)
19. [Navbars & Headers](#navbars--headers)
20. [Dark Mode Toggle](#dark-mode-toggle)
21. [Responsive Grid Layouts](#responsive-grid-layouts)

---

## Page Boilerplate

Complete HTML page with Tailwind v4 CDN, Flowbite v4, dark mode init, and Alpine.js app shell:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Page Title</title>

    <!-- Tailwind CSS v4 Play CDN -->
    <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>

    <!-- Tailwind v4 config: class-based dark mode -->
    <style type="text/tailwindcss">
        @custom-variant dark (&:where(.dark, .dark *));
    </style>

    <!-- Flowbite CSS -->
    <link href="https://cdn.jsdelivr.net/npm/flowbite@4.0.1/dist/flowbite.min.css" rel="stylesheet" />

    <!-- Alpine.js -->
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
</head>
<body class="bg-neutral-primary text-body min-h-screen">

    <div x-data="myApp()" x-init="init()" x-cloak>
        <!-- REQUIRED: Include a dark mode toggle button (see Dark Mode Toggle section) -->
        <!-- App content here -->
    </div>

    <!-- Flowbite JS (before app.js) -->
    <script src="https://cdn.jsdelivr.net/npm/flowbite@4.0.1/dist/flowbite.min.js"></script>
    <script src="app.js"></script>
</body>
</html>
```

---

## Buttons

### Primary Button
```html
<button type="button"
        class="text-white bg-brand box-border border border-transparent hover:bg-brand-strong focus:ring-4 focus:ring-brand-medium shadow-xs font-medium leading-5 rounded-base text-sm px-4 py-2.5 focus:outline-none">
    Primary Action
</button>
```

### Secondary/Alternative Button
```html
<button type="button"
        class="text-body bg-neutral-secondary-medium box-border border border-default-medium hover:bg-neutral-tertiary-medium hover:text-heading focus:ring-4 focus:ring-neutral-tertiary shadow-xs font-medium leading-5 rounded-base text-sm px-4 py-2.5 focus:outline-none">
    Secondary Action
</button>
```

### Danger Button
```html
<button type="button"
        class="text-white bg-danger box-border border border-transparent hover:bg-danger-strong focus:ring-4 focus:ring-danger-medium shadow-xs font-medium leading-5 rounded-base text-sm px-4 py-2.5 focus:outline-none">
    Delete
</button>
```

### Button with Icon (Left)
```html
<button type="button"
        class="text-white bg-brand box-border border border-transparent hover:bg-brand-strong focus:ring-4 focus:ring-brand-medium shadow-xs font-medium leading-5 rounded-base text-sm px-4 py-2.5 inline-flex items-center focus:outline-none">
    <svg class="w-4 h-4 me-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
    </svg>
    Add Item
</button>
```

### Small Button
```html
<button type="button"
        class="text-white bg-brand box-border border border-transparent hover:bg-brand-strong focus:ring-4 focus:ring-brand-medium shadow-xs font-medium leading-5 rounded-base text-xs px-3 py-2 focus:outline-none">
    Small
</button>
```

### Icon-Only Button (e.g., theme toggle, close)
```html
<button type="button"
        class="text-body hover:text-heading bg-transparent hover:bg-neutral-secondary-medium focus:outline-none focus:ring-4 focus:ring-neutral-tertiary rounded-base text-sm p-2.5 inline-flex items-center justify-center">
    <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
        <!-- icon path -->
    </svg>
    <span class="sr-only">Toggle theme</span>
</button>
```

### Link-Style Button (Breadcrumb/Back)
```html
<button @click="goBack()"
        class="inline-flex items-center text-sm font-medium text-fg-brand hover:underline">
    <svg class="w-4 h-4 me-2 rtl:rotate-180" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
    </svg>
    Back to List
</button>
```

---

## Dropdowns

### Standard Dropdown (Flowbite data attributes)
```html
<div>
    <button id="dropdownButton"
            data-dropdown-toggle="dropdownMenu"
            type="button"
            class="text-body bg-neutral-secondary-medium box-border border border-default-medium hover:bg-neutral-tertiary-medium hover:text-heading focus:ring-4 focus:ring-neutral-tertiary shadow-xs font-medium leading-5 rounded-base text-sm px-4 py-2.5 inline-flex items-center focus:outline-none">
        <span>Select Option</span>
        <svg class="w-2.5 h-2.5 ms-3" aria-hidden="true" fill="none" viewBox="0 0 10 6">
            <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m1 1 4 4 4-4"/>
        </svg>
    </button>

    <div id="dropdownMenu"
         class="z-10 hidden bg-neutral-primary-medium border border-default-medium rounded-base shadow-lg w-44">
        <ul class="p-2 text-sm text-body font-medium" aria-labelledby="dropdownButton">
            <li>
                <a href="#" class="inline-flex items-center w-full p-2 hover:bg-neutral-tertiary-medium hover:text-heading rounded">
                    Option 1
                </a>
            </li>
            <li>
                <a href="#" class="inline-flex items-center w-full p-2 hover:bg-neutral-tertiary-medium hover:text-heading rounded">
                    Option 2
                </a>
            </li>
        </ul>
    </div>
</div>
```

### Dropdown with Alpine.js Dynamic Content
```html
<div>
    <button id="dynamicDropdownBtn"
            data-dropdown-toggle="dynamicDropdown"
            type="button"
            class="text-body bg-neutral-secondary-medium box-border border border-default-medium hover:bg-neutral-tertiary-medium hover:text-heading focus:ring-4 focus:ring-neutral-tertiary shadow-xs font-medium leading-5 rounded-base text-sm px-4 py-2.5 inline-flex items-center focus:outline-none">
        <svg class="w-4 h-4 me-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
        <span x-text="selectedItem ? selectedItem.name : 'Select...'"></span>
        <svg class="w-2.5 h-2.5 ms-3" aria-hidden="true" fill="none" viewBox="0 0 10 6">
            <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m1 1 4 4 4-4"/>
        </svg>
    </button>

    <div id="dynamicDropdown"
         class="z-10 hidden bg-neutral-primary-medium border border-default-medium rounded-base shadow-lg w-80">
        <ul class="p-2 text-sm text-body font-medium">
            <template x-for="item in items" :key="item.id">
                <li>
                    <a @click.prevent="selectItem(item.id)"
                       href="#"
                       class="block px-4 py-3 hover:bg-neutral-tertiary-medium hover:text-heading rounded"
                       :class="selectedItem && selectedItem.id === item.id ? 'bg-brand-softer text-fg-brand' : ''">
                        <div class="font-medium text-heading" x-text="item.name"></div>
                        <div class="text-xs text-body-subtle" x-text="item.description"></div>
                    </a>
                </li>
            </template>
        </ul>
    </div>
</div>
```

### Dropdown with Header and Divider
```html
<div id="dropdownWithHeader"
     class="z-10 hidden bg-neutral-primary-medium border border-default-medium rounded-base shadow-lg w-44 divide-y divide-default">
    <div class="px-4 py-3 text-sm">
        <div class="font-medium text-heading">John Doe</div>
        <div class="truncate text-body-subtle">john@example.com</div>
    </div>
    <ul class="p-2 text-sm text-body font-medium">
        <li><a href="#" class="inline-flex items-center w-full p-2 hover:bg-neutral-tertiary-medium hover:text-heading rounded">Dashboard</a></li>
        <li><a href="#" class="inline-flex items-center w-full p-2 hover:bg-neutral-tertiary-medium hover:text-heading rounded">Settings</a></li>
    </ul>
    <div class="p-2">
        <a href="#" class="inline-flex items-center w-full p-2 text-sm text-body hover:bg-neutral-tertiary-medium hover:text-heading rounded">Sign out</a>
    </div>
</div>
```

---

## Cards

### Standard Card
```html
<div class="bg-neutral-primary-soft block p-6 border border-default rounded-base shadow-xs">
    <h5 class="mb-3 text-2xl font-semibold tracking-tight text-heading leading-8">
        Card Title
    </h5>
    <p class="text-body">
        Card description text goes here.
    </p>
</div>
```

### Card with Action Button
```html
<div class="bg-neutral-primary-soft block max-w-sm p-6 border border-default rounded-base shadow-xs">
    <h5 class="mb-3 text-2xl font-semibold tracking-tight text-heading leading-8">
        Card Title
    </h5>
    <p class="mb-3 text-body">
        Card content here.
    </p>
    <a href="#"
       class="inline-flex items-center text-white bg-brand box-border border border-transparent hover:bg-brand-strong focus:ring-4 focus:ring-brand-medium shadow-xs font-medium leading-5 rounded-base text-sm px-4 py-2.5 focus:outline-none">
        Read more
        <svg class="rtl:rotate-180 w-3.5 h-3.5 ms-2" aria-hidden="true" fill="none" viewBox="0 0 14 10">
            <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M1 5h12m0 0L9 1m4 4L9 9"/>
        </svg>
    </a>
</div>
```

### Interactive Card (Clickable with Hover)
```html
<div class="bg-neutral-primary-soft max-w-sm p-6 border border-default rounded-base shadow-xs cursor-pointer hover:bg-neutral-secondary-medium transition-colors"
     @click="handleCardClick(item)">
    <div class="flex justify-between items-start mb-3">
        <h5 class="text-lg font-bold tracking-tight text-heading pr-2"
            x-text="item.title"></h5>
        <!-- Status badge -->
        <span class="text-xs font-medium px-1.5 py-0.5 rounded"
              :class="getStatusClasses(item.status)"
              x-text="item.statusLabel"></span>
    </div>
    <p class="text-sm text-body" x-text="item.description"></p>
</div>
```

### Card with Metadata Grid
```html
<div class="bg-neutral-primary-soft p-6 border border-default rounded-base shadow-xs">
    <h2 class="mb-4 text-2xl font-bold tracking-tight text-heading"
        x-text="item.title"></h2>
    <div class="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
        <div>
            <div class="text-body-subtle">Label 1</div>
            <div class="font-medium text-heading" x-text="item.field1"></div>
        </div>
        <div>
            <div class="text-body-subtle">Label 2</div>
            <div class="font-medium text-heading" x-text="item.field2"></div>
        </div>
        <div>
            <div class="text-body-subtle">Label 3</div>
            <div class="font-medium text-heading" x-text="item.field3"></div>
        </div>
    </div>
</div>
```

---

## Modals

### Standard Modal (Flowbite data attributes)
```html
<!-- Trigger Button -->
<button data-modal-target="defaultModal" data-modal-toggle="defaultModal"
        type="button"
        class="text-white bg-brand box-border border border-transparent hover:bg-brand-strong focus:ring-4 focus:ring-brand-medium shadow-xs font-medium leading-5 rounded-base text-sm px-4 py-2.5 focus:outline-none">
    Open Modal
</button>

<!-- Modal -->
<div id="defaultModal" tabindex="-1" aria-hidden="true"
     class="hidden overflow-y-auto overflow-x-hidden fixed top-0 right-0 left-0 z-50 justify-center items-center w-full md:inset-0 h-[calc(100%-1rem)] max-h-full">
    <div class="relative p-4 w-full max-w-2xl max-h-full">
        <div class="relative bg-neutral-primary-soft border border-default rounded-base shadow-sm p-4 md:p-6">
            <!-- Header -->
            <div class="flex items-center justify-between border-b border-default pb-4 md:pb-5">
                <h3 class="text-lg font-medium text-heading">
                    Modal Title
                </h3>
                <button type="button"
                        class="text-body bg-transparent hover:bg-neutral-tertiary hover:text-heading rounded-base text-sm w-9 h-9 ms-auto inline-flex justify-center items-center"
                        data-modal-hide="defaultModal">
                    <svg class="w-3 h-3" aria-hidden="true" fill="none" viewBox="0 0 14 14">
                        <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m1 1 6 6m0 0 6 6M7 7l6-6M7 7l-6 6"/>
                    </svg>
                    <span class="sr-only">Close modal</span>
                </button>
            </div>
            <!-- Body -->
            <div class="space-y-4 md:space-y-6 py-4 md:py-6">
                <p class="leading-relaxed text-body">
                    Modal content goes here.
                </p>
            </div>
            <!-- Footer -->
            <div class="flex items-center border-t border-default space-x-4 pt-4 md:pt-5">
                <button data-modal-hide="defaultModal" type="button"
                        class="text-white bg-brand box-border border border-transparent hover:bg-brand-strong focus:ring-4 focus:ring-brand-medium shadow-xs font-medium leading-5 rounded-base text-sm px-4 py-2.5 focus:outline-none">
                    Confirm
                </button>
                <button data-modal-hide="defaultModal" type="button"
                        class="text-body bg-neutral-secondary-medium box-border border border-default-medium hover:bg-neutral-tertiary-medium hover:text-heading focus:ring-4 focus:ring-neutral-tertiary shadow-xs font-medium leading-5 rounded-base text-sm px-4 py-2.5 focus:outline-none">
                    Cancel
                </button>
            </div>
        </div>
    </div>
</div>
```

### Confirmation Modal (Small)
```html
<div id="confirmModal" tabindex="-1"
     class="hidden overflow-y-auto overflow-x-hidden fixed top-0 right-0 left-0 z-50 justify-center items-center w-full md:inset-0 h-[calc(100%-1rem)] max-h-full">
    <div class="relative p-4 w-full max-w-md max-h-full">
        <div class="relative bg-neutral-primary-soft border border-default rounded-base shadow-sm">
            <button type="button"
                    class="absolute top-3 end-2.5 text-body bg-transparent hover:bg-neutral-tertiary hover:text-heading rounded-base text-sm w-9 h-9 ms-auto inline-flex justify-center items-center"
                    data-modal-hide="confirmModal">
                <svg class="w-3 h-3" aria-hidden="true" fill="none" viewBox="0 0 14 14">
                    <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m1 1 6 6m0 0 6 6M7 7l6-6M7 7l-6 6"/>
                </svg>
                <span class="sr-only">Close modal</span>
            </button>
            <div class="p-4 md:p-5 text-center">
                <svg class="mx-auto mb-4 text-body w-12 h-12" aria-hidden="true" fill="none" viewBox="0 0 20 20">
                    <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 11V6m0 8h.01M19 10a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"/>
                </svg>
                <h3 class="mb-5 text-lg font-normal text-body">
                    Are you sure you want to delete this item?
                </h3>
                <button data-modal-hide="confirmModal" type="button"
                        class="text-white bg-danger box-border border border-transparent hover:bg-danger-strong focus:ring-4 focus:ring-danger-medium shadow-xs font-medium leading-5 rounded-base text-sm inline-flex items-center px-4 py-2.5 text-center focus:outline-none">
                    Yes, I'm sure
                </button>
                <button data-modal-hide="confirmModal" type="button"
                        class="text-body bg-neutral-secondary-medium box-border border border-default-medium hover:bg-neutral-tertiary-medium hover:text-heading focus:ring-4 focus:ring-neutral-tertiary shadow-xs font-medium leading-5 rounded-base text-sm px-4 py-2.5 ms-3 focus:outline-none">
                    No, cancel
                </button>
            </div>
        </div>
    </div>
</div>
```

---

## Badges & Pills

### Status Badges (Flowbite v4 Semantic Tokens)
```html
<!-- Brand / Info -->
<span class="bg-brand-softer text-fg-brand-strong text-xs font-medium px-1.5 py-0.5 rounded">
    Info
</span>

<!-- Success / Active / Present -->
<span class="bg-success-soft text-fg-success-strong text-xs font-medium px-1.5 py-0.5 rounded">
    Active
</span>

<!-- Warning / Resolved -->
<span class="bg-warning-soft text-fg-warning text-xs font-medium px-1.5 py-0.5 rounded">
    Resolved
</span>

<!-- Danger / Error -->
<span class="bg-danger-soft text-fg-danger-strong text-xs font-medium px-1.5 py-0.5 rounded">
    Error
</span>

<!-- Gray / Default / Unknown -->
<span class="bg-neutral-secondary-medium text-heading text-xs font-medium px-1.5 py-0.5 rounded">
    Unknown
</span>

<!-- Alternative (light) -->
<span class="bg-neutral-primary-soft text-heading text-xs font-medium px-1.5 py-0.5 rounded">
    Default
</span>
```

### Rounded Pill Badges
```html
<!-- Add rounded-full for pill shape -->
<span class="bg-success-soft text-fg-success-strong text-xs font-medium px-2.5 py-0.5 rounded-full">
    Active
</span>
```

### Dynamic Status Badge (Alpine.js)
```html
<span class="text-xs font-medium px-1.5 py-0.5 rounded"
      :class="{
          'bg-success-soft text-fg-success-strong': item.status === 'active',
          'bg-brand-softer text-fg-brand-strong': item.status === 'info',
          'bg-warning-soft text-fg-warning': item.status === 'warning',
          'bg-danger-soft text-fg-danger-strong': item.status === 'error',
          'bg-neutral-secondary-medium text-heading': item.status === 'default'
      }"
      x-text="item.statusLabel">
</span>
```

### Count Badge (Notification Dot)
```html
<span class="inline-flex items-center justify-center w-5 h-5 text-xs font-bold text-white bg-brand rounded-full">
    3
</span>
```

---

## Alerts

### Info Alert
```html
<div class="p-4 mb-4 text-sm text-fg-brand-strong rounded-base bg-brand-softer" role="alert">
    <span class="font-medium">Info alert!</span> This is an informational message.
</div>
```

### Success Alert
```html
<div class="p-4 mb-4 text-sm text-fg-success-strong rounded-base bg-success-soft" role="alert">
    <span class="font-medium">Success!</span> Operation completed successfully.
</div>
```

### Warning Alert
```html
<div class="p-4 mb-4 text-sm text-fg-warning rounded-base bg-warning-soft" role="alert">
    <span class="font-medium">Warning!</span> Please review before proceeding.
</div>
```

### Danger Alert
```html
<div class="p-4 mb-4 text-sm text-fg-danger-strong rounded-base bg-danger-soft" role="alert">
    <span class="font-medium">Error!</span> Something went wrong.
</div>
```

### Dark/Neutral Alert
```html
<div class="p-4 mb-4 text-sm text-heading rounded-base bg-neutral-secondary-medium" role="alert">
    <span class="font-medium">Note:</span> This is a neutral message.
</div>
```

### Alert with Icon
```html
<div class="flex items-center p-4 mb-4 text-sm text-fg-brand-strong rounded-base bg-brand-softer" role="alert">
    <svg class="shrink-0 inline w-4 h-4 me-3" aria-hidden="true" fill="currentColor" viewBox="0 0 20 20">
        <path d="M10 .5a9.5 9.5 0 1 0 9.5 9.5A9.51 9.51 0 0 0 10 .5ZM9.5 4a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3ZM12 15H8a1 1 0 0 1 0-2h1v-3H8a1 1 0 0 1 0-2h2a1 1 0 0 1 1 1v4h1a1 1 0 0 1 0 2Z"/>
    </svg>
    <span class="sr-only">Info</span>
    <div>
        <span class="font-medium">Info alert!</span> Change a few things up and try submitting again.
    </div>
</div>
```

### Dismissible Alert
```html
<div id="alert-1" class="flex items-center p-4 mb-4 text-fg-brand-strong rounded-base bg-brand-softer" role="alert">
    <svg class="shrink-0 w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
        <path d="M10 .5a9.5 9.5 0 1 0 9.5 9.5A9.51 9.51 0 0 0 10 .5ZM9.5 4a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3ZM12 15H8a1 1 0 0 1 0-2h1v-3H8a1 1 0 0 1 0-2h2a1 1 0 0 1 1 1v4h1a1 1 0 0 1 0 2Z"/>
    </svg>
    <span class="sr-only">Info</span>
    <div class="ms-3 text-sm font-medium">Dismissible info alert.</div>
    <button type="button"
            class="ms-auto -mx-1.5 -my-1.5 text-fg-brand-strong hover:text-heading bg-transparent hover:bg-neutral-tertiary-medium rounded-base focus:ring-2 focus:ring-brand p-1.5 inline-flex items-center justify-center h-8 w-8"
            data-dismiss-target="#alert-1" aria-label="Close">
        <span class="sr-only">Close</span>
        <svg class="w-3 h-3" aria-hidden="true" fill="none" viewBox="0 0 14 14">
            <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m1 1 6 6m0 0 6 6M7 7l6-6M7 7l-6 6"/>
        </svg>
    </button>
</div>
```

---

## Tables

### Standard Table with Hover
```html
<div class="relative overflow-x-auto bg-neutral-primary-soft shadow-xs rounded-base border border-default">
    <table class="w-full text-sm text-left rtl:text-right text-body">
        <thead class="text-sm text-body bg-neutral-secondary-soft border-b rounded-base border-default">
            <tr>
                <th scope="col" class="px-6 py-3 font-medium">Column 1</th>
                <th scope="col" class="px-6 py-3 font-medium">Column 2</th>
                <th scope="col" class="px-6 py-3 font-medium">Column 3</th>
                <th scope="col" class="px-6 py-3 font-medium"><span class="sr-only">Actions</span></th>
            </tr>
        </thead>
        <tbody>
            <template x-for="(row, index) in rows" :key="row.id">
                <tr class="bg-neutral-primary border-b border-default hover:bg-neutral-secondary-soft">
                    <th scope="row" class="px-6 py-4 font-medium text-heading whitespace-nowrap"
                        x-text="row.col1"></th>
                    <td class="px-6 py-4" x-text="row.col2"></td>
                    <td class="px-6 py-4" x-text="row.col3"></td>
                    <td class="px-6 py-4 text-right">
                        <a href="#" class="font-medium text-fg-brand hover:underline"
                           @click.prevent="editRow(row)">Edit</a>
                    </td>
                </tr>
            </template>
        </tbody>
    </table>
</div>
```

---

## Tabs

### Default Tabs
```html
<ul class="flex flex-wrap text-sm font-medium text-center text-body border-b border-default">
    <li class="me-2">
        <button @click="activeTab = 'tab1'"
                class="inline-block p-4 rounded-t-base"
                :class="activeTab === 'tab1'
                    ? 'text-fg-brand bg-neutral-secondary-soft active'
                    : 'hover:text-heading hover:bg-neutral-secondary-soft'">
            Tab 1
        </button>
    </li>
    <li class="me-2">
        <button @click="activeTab = 'tab2'"
                class="inline-block p-4 rounded-t-base"
                :class="activeTab === 'tab2'
                    ? 'text-fg-brand bg-neutral-secondary-soft active'
                    : 'hover:text-heading hover:bg-neutral-secondary-soft'">
            Tab 2
        </button>
    </li>
    <li>
        <span class="inline-block p-4 text-fg-disabled rounded-t-base cursor-not-allowed">
            Disabled
        </span>
    </li>
</ul>
<div>
    <div x-show="activeTab === 'tab1'">Tab 1 content</div>
    <div x-show="activeTab === 'tab2'">Tab 2 content</div>
</div>
```

### Pill Tabs
```html
<ul class="flex flex-wrap text-sm font-medium text-center text-body mb-4">
    <li class="me-2">
        <button @click="activeTab = 'tab1'"
                class="inline-block px-4 py-3 rounded-base"
                :class="activeTab === 'tab1'
                    ? 'text-white bg-brand'
                    : 'hover:text-heading hover:bg-neutral-secondary-medium'">
            Tab 1
        </button>
    </li>
    <li class="me-2">
        <button @click="activeTab = 'tab2'"
                class="inline-block px-4 py-3 rounded-base"
                :class="activeTab === 'tab2'
                    ? 'text-white bg-brand'
                    : 'hover:text-heading hover:bg-neutral-secondary-medium'">
            Tab 2
        </button>
    </li>
</ul>
```

---

## Forms

### Text Input with Label
```html
<div class="mb-6">
    <label for="input-field" class="block mb-2.5 text-sm font-medium text-heading">
        Field Label
    </label>
    <input type="text" id="input-field"
           x-model="fieldValue"
           class="bg-neutral-secondary-medium border border-default-medium text-heading text-sm rounded-base focus:ring-brand focus:border-brand block w-full px-3 py-2.5 shadow-xs placeholder:text-body"
           placeholder="Enter value...">
</div>
```

### Select Dropdown
```html
<div class="mb-6">
    <label for="select-field" class="block mb-2.5 text-sm font-medium text-heading">
        Select Option
    </label>
    <select id="select-field"
            x-model="selectedValue"
            class="block w-full px-3 py-2.5 bg-neutral-secondary-medium border border-default-medium text-heading text-sm rounded-base focus:ring-brand focus:border-brand shadow-xs placeholder:text-body">
        <option value="all">All Options</option>
        <option value="opt1">Option 1</option>
        <option value="opt2">Option 2</option>
    </select>
</div>
```

### Checkbox
```html
<div class="flex items-center mb-4">
    <input id="checkbox-1" type="checkbox"
           x-model="isChecked"
           class="w-4 h-4 text-brand bg-neutral-secondary-medium border-default-medium rounded focus:ring-brand focus:ring-2">
    <label for="checkbox-1" class="ms-2 text-sm font-medium text-heading">
        Checkbox label
    </label>
</div>
```

### Search Input
```html
<div class="relative">
    <div class="absolute inset-y-0 start-0 flex items-center ps-3 pointer-events-none">
        <svg class="w-4 h-4 text-body" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
        </svg>
    </div>
    <input type="search"
           x-model="searchQuery"
           class="block w-full p-4 ps-10 text-sm bg-neutral-secondary-medium border border-default-medium text-heading rounded-base focus:ring-brand focus:border-brand shadow-xs placeholder:text-body"
           placeholder="Search...">
</div>
```

---

## Tooltips

### Flowbite Tooltip (data attribute)
```html
<button data-tooltip-target="tooltip-default" type="button"
        class="text-white bg-brand box-border border border-transparent hover:bg-brand-strong focus:ring-4 focus:ring-brand-medium shadow-xs font-medium leading-5 rounded-base text-sm px-4 py-2.5 focus:outline-none">
    Hover me
</button>
<div id="tooltip-default" role="tooltip"
     class="absolute z-10 invisible inline-block px-3 py-2 text-sm font-medium text-white transition-opacity duration-300 bg-neutral-tertiary rounded-base shadow-sm opacity-0 tooltip">
    Tooltip content
    <div class="tooltip-arrow" data-popper-arrow></div>
</div>
```

### Alpine.js Tooltip (Inline Hover)
```html
<div class="relative" x-data="{ showTooltip: false }">
    <button @mouseenter="showTooltip = true"
            @mouseleave="showTooltip = false"
            class="text-sm font-medium text-heading">
        Hover me
    </button>
    <div x-show="showTooltip"
         x-transition
         role="tooltip"
         class="absolute z-10 bottom-full mb-2 w-64 px-3 py-2 text-xs text-body bg-neutral-primary-soft border border-default rounded-base shadow-sm"
         style="left: 50%; transform: translateX(-50%);">
        <p class="leading-relaxed" x-text="tooltipContent"></p>
    </div>
</div>
```

---

## Accordions

### Standard Accordion (Flowbite)
```html
<div id="accordion-collapse" data-accordion="collapse">
    <h2 id="accordion-heading-1">
        <button type="button"
                class="flex items-center justify-between w-full p-5 font-medium rtl:text-right text-body border border-b-0 border-default rounded-t-base focus:ring-4 focus:ring-neutral-tertiary hover:bg-neutral-secondary-soft gap-3"
                data-accordion-target="#accordion-body-1" aria-expanded="true" aria-controls="accordion-body-1">
            <span>Section Title 1</span>
            <svg data-accordion-icon class="w-3 h-3 rotate-180 shrink-0" fill="none" viewBox="0 0 10 6">
                <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5 5 1 1 5"/>
            </svg>
        </button>
    </h2>
    <div id="accordion-body-1" class="hidden" aria-labelledby="accordion-heading-1">
        <div class="p-5 border border-b-0 border-default bg-neutral-primary">
            <p class="mb-2 text-body">Section 1 content.</p>
        </div>
    </div>

    <h2 id="accordion-heading-2">
        <button type="button"
                class="flex items-center justify-between w-full p-5 font-medium rtl:text-right text-body border border-b-0 border-default focus:ring-4 focus:ring-neutral-tertiary hover:bg-neutral-secondary-soft gap-3"
                data-accordion-target="#accordion-body-2" aria-expanded="false" aria-controls="accordion-body-2">
            <span>Section Title 2</span>
            <svg data-accordion-icon class="w-3 h-3 shrink-0" fill="none" viewBox="0 0 10 6">
                <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5 5 1 1 5"/>
            </svg>
        </button>
    </h2>
    <div id="accordion-body-2" class="hidden" aria-labelledby="accordion-heading-2">
        <div class="p-5 border border-b-0 border-default bg-neutral-primary">
            <p class="mb-2 text-body">Section 2 content.</p>
        </div>
    </div>
</div>
```

---

## Breadcrumbs

```html
<nav class="flex mb-4" aria-label="Breadcrumb">
    <ol class="inline-flex items-center space-x-1 md:space-x-2 rtl:space-x-reverse">
        <li class="inline-flex items-center">
            <a href="#" @click.prevent="navigateTo('home')"
               class="inline-flex items-center text-sm font-medium text-body hover:text-fg-brand">
                <svg class="w-3 h-3 me-2.5" fill="currentColor" viewBox="0 0 20 20">
                    <path d="m19.707 9.293-2-2-7-7a1 1 0 0 0-1.414 0l-7 7-2 2a1 1 0 0 0 1.414 1.414L2 10.414V18a2 2 0 0 0 2 2h3a1 1 0 0 0 1-1v-4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v4a1 1 0 0 0 1 1h3a2 2 0 0 0 2-2v-7.586l.293.293a1 1 0 0 0 1.414-1.414Z"/>
                </svg>
                Home
            </a>
        </li>
        <li>
            <div class="flex items-center">
                <svg class="rtl:rotate-180 w-3 h-3 text-body mx-1" fill="none" viewBox="0 0 6 10">
                    <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m1 9 4-4-4-4"/>
                </svg>
                <span class="ms-1 text-sm font-medium text-body-subtle md:ms-2"
                      x-text="currentPage"></span>
            </div>
        </li>
    </ol>
</nav>
```

---

## Spinners & Loading

### Centered Loading Spinner
```html
<div x-show="loading" class="flex items-center justify-center h-64">
    <div class="text-center">
        <div role="status">
            <svg aria-hidden="true"
                 class="inline w-12 h-12 text-neutral-tertiary animate-spin fill-brand"
                 viewBox="0 0 100 101" fill="none">
                <path d="M100 50.5908C100 78.2051 77.6142 100.591 50 100.591C22.3858 100.591 0 78.2051 0 50.5908C0 22.9766 22.3858 0.59082 50 0.59082C77.6142 0.59082 100 22.9766 100 50.5908ZM9.08144 50.5908C9.08144 73.1895 27.4013 91.5094 50 91.5094C72.5987 91.5094 90.9186 73.1895 90.9186 50.5908C90.9186 27.9921 72.5987 9.67226 50 9.67226C27.4013 9.67226 9.08144 27.9921 9.08144 50.5908Z" fill="currentColor"/>
                <path d="M93.9676 39.0409C96.393 38.4038 97.8624 35.9116 97.0079 33.5539C95.2932 28.8227 92.871 24.3692 89.8167 20.348C85.8452 15.1192 80.8826 10.7238 75.2124 7.41289C69.5422 4.10194 63.2754 1.94025 56.7698 1.05124C51.7666 0.367541 46.6976 0.446843 41.7345 1.27873C39.2613 1.69328 37.813 4.19778 38.4501 6.62326C39.0873 9.04874 41.5694 10.4717 44.0505 10.1071C47.8511 9.54855 51.7191 9.52689 55.5402 10.0491C60.8642 10.7766 65.9928 12.5457 70.6331 15.2552C75.2735 17.9648 79.3347 21.5619 82.5849 25.841C84.9175 28.9121 86.7997 32.2913 88.1811 35.8758C89.083 38.2158 91.5421 39.6781 93.9676 39.0409Z" fill="currentFill"/>
            </svg>
            <span class="sr-only">Loading...</span>
        </div>
        <p class="mt-4 text-body">Loading data...</p>
    </div>
</div>
```

### Small Inline Spinner
```html
<div role="status" class="inline-flex items-center">
    <svg aria-hidden="true" class="w-4 h-4 text-neutral-tertiary animate-spin fill-brand" viewBox="0 0 100 101" fill="none">
        <path d="M100 50.5908C100 78.2051 77.6142 100.591 50 100.591C22.3858 100.591 0 78.2051 0 50.5908C0 22.9766 22.3858 0.59082 50 0.59082C77.6142 0.59082 100 22.9766 100 50.5908ZM9.08144 50.5908C9.08144 73.1895 27.4013 91.5094 50 91.5094C72.5987 91.5094 90.9186 73.1895 90.9186 50.5908C90.9186 27.9921 72.5987 9.67226 50 9.67226C27.4013 9.67226 9.08144 27.9921 9.08144 50.5908Z" fill="currentColor"/>
        <path d="M93.9676 39.0409C96.393 38.4038 97.8624 35.9116 97.0079 33.5539C95.2932 28.8227 92.871 24.3692 89.8167 20.348C85.8452 15.1192 80.8826 10.7238 75.2124 7.41289C69.5422 4.10194 63.2754 1.94025 56.7698 1.05124C51.7666 0.367541 46.6976 0.446843 41.7345 1.27873C39.2613 1.69328 37.813 4.19778 38.4501 6.62326C39.0873 9.04874 41.5694 10.4717 44.0505 10.1071C47.8511 9.54855 51.7191 9.52689 55.5402 10.0491C60.8642 10.7766 65.9928 12.5457 70.6331 15.2552C75.2735 17.9648 79.3347 21.5619 82.5849 25.841C84.9175 28.9121 86.7997 32.2913 88.1811 35.8758C89.083 38.2158 91.5421 39.6781 93.9676 39.0409Z" fill="currentFill"/>
    </svg>
    <span class="ms-2 text-sm text-body">Loading...</span>
</div>
```

---

## Empty States

```html
<div x-show="items.length === 0" class="text-center py-12">
    <svg class="mx-auto h-12 w-12 text-body" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
    <h3 class="mt-2 text-sm font-medium text-heading">No items found</h3>
    <p class="mt-1 text-sm text-body-subtle">Try adjusting your filters or search criteria.</p>
</div>
```

---

## Popovers

### Alpine.js Popover (Shared Instance Pattern)

This pattern renders a single popover that repositions based on whichever element triggered it:

```html
<!-- Popover container (position: fixed, pointer-events managed) -->
<div x-show="openPopover !== null"
     @click.outside="closePopover()"
     x-cloak
     x-transition:enter="transition ease-out duration-100"
     x-transition:enter-start="opacity-0 scale-95"
     x-transition:enter-end="opacity-100 scale-100"
     x-transition:leave="transition ease-in duration-75"
     x-transition:leave-start="opacity-100 scale-100"
     x-transition:leave-end="opacity-0 scale-95"
     role="tooltip"
     class="pointer-events-none"
     :style="getPopoverStyle()">
    <div class="w-96 max-h-96 overflow-y-auto bg-neutral-primary-soft border border-default rounded-base shadow-lg pointer-events-auto">
        <!-- Header -->
        <div class="px-4 py-3 border-b border-default flex justify-between items-start">
            <div>
                <h6 class="font-semibold text-heading" x-text="popoverTitle"></h6>
                <p class="text-xs font-mono text-body-subtle mt-1" x-text="popoverSubtitle"></p>
            </div>
            <button @click="closePopover()" class="text-body hover:text-heading">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
            </button>
        </div>
        <!-- Body -->
        <div class="px-4 py-3 text-sm text-body space-y-2">
            <p x-text="popoverContent"></p>
        </div>
    </div>
</div>
```

---

## Toasts

### Default Toast
```html
<div class="flex items-center w-full max-w-xs p-4 text-body bg-neutral-primary-soft rounded-base shadow-xs border border-default" role="alert">
    <svg class="w-6 h-6 text-fg-brand" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24">
        <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.122 17.645a7.185 7.185 0 0 1-2.656 2.495 7.06 7.06 0 0 1-3.52.853 6.617 6.617 0 0 1-3.306-.718 6.73 6.73 0 0 1-2.54-2.266c-2.672-4.57.287-8.846.887-9.668A4.448 4.448 0 0 0 8.07 6.31 4.49 4.49 0 0 0 7.997 4c1.284.965 6.43 3.258 5.525 10.631 1.496-1.136 2.7-3.046 2.846-6.216 1.43 1.061 3.985 5.462 1.754 9.23Z"/>
    </svg>
    <div class="ms-2.5 text-sm border-s border-default ps-3.5">Message text here.</div>
    <button type="button"
            class="ms-auto flex items-center justify-center text-body hover:text-heading bg-transparent box-border border border-transparent hover:bg-neutral-secondary-medium focus:ring-4 focus:ring-neutral-tertiary font-medium leading-5 rounded text-sm h-8 w-8 focus:outline-none"
            @click="showToast = false" aria-label="Close">
        <span class="sr-only">Close</span>
        <svg class="w-5 h-5" aria-hidden="true" fill="none" viewBox="0 0 24 24">
            <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18 17.94 6M18 18 6.06 6"/>
        </svg>
    </button>
</div>
```

### Success Toast
```html
<div class="flex items-center w-full max-w-xs p-4 text-body bg-neutral-primary-soft rounded-base shadow-xs border border-default" role="alert">
    <div class="inline-flex items-center justify-center shrink-0 w-8 h-8 text-fg-success-strong bg-success-soft rounded-base">
        <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 .5a9.5 9.5 0 1 0 9.5 9.5A9.51 9.51 0 0 0 10 .5Zm3.707 8.207-4 4a1 1 0 0 1-1.414 0l-2-2a1 1 0 0 1 1.414-1.414L9 10.586l3.293-3.293a1 1 0 0 1 1.414 1.414Z"/>
        </svg>
    </div>
    <div class="ms-3 text-sm font-normal">Item saved successfully.</div>
    <button type="button"
            class="ms-auto flex items-center justify-center text-body hover:text-heading bg-transparent hover:bg-neutral-secondary-medium focus:ring-4 focus:ring-neutral-tertiary rounded text-sm h-8 w-8 focus:outline-none"
            @click="showToast = false" aria-label="Close">
        <svg class="w-3 h-3" fill="none" viewBox="0 0 14 14">
            <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m1 1 6 6m0 0 6 6M7 7l6-6M7 7l-6 6"/>
        </svg>
    </button>
</div>
```

### Error Toast
```html
<div class="flex items-center w-full max-w-xs p-4 text-body bg-neutral-primary-soft rounded-base shadow-xs border border-default" role="alert">
    <div class="inline-flex items-center justify-center shrink-0 w-8 h-8 text-fg-danger-strong bg-danger-soft rounded-base">
        <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 .5a9.5 9.5 0 1 0 9.5 9.5A9.51 9.51 0 0 0 10 .5Zm3.707 8.207-4 4a1 1 0 0 1-1.414 0l-2-2a1 1 0 0 1 1.414-1.414L9 10.586l3.293-3.293a1 1 0 0 1 1.414 1.414Z"/>
        </svg>
    </div>
    <div class="ms-3 text-sm font-normal">An error occurred.</div>
    <button type="button"
            class="ms-auto flex items-center justify-center text-body hover:text-heading bg-transparent hover:bg-neutral-secondary-medium focus:ring-4 focus:ring-neutral-tertiary rounded text-sm h-8 w-8 focus:outline-none"
            @click="showErrorToast = false" aria-label="Close">
        <svg class="w-3 h-3" fill="none" viewBox="0 0 14 14">
            <path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m1 1 6 6m0 0 6 6M7 7l6-6M7 7l-6 6"/>
        </svg>
    </button>
</div>
```

---

## Pagination

```html
<nav aria-label="Page navigation">
    <ul class="inline-flex -space-x-px text-sm">
        <li>
            <button @click="prevPage()"
                    :disabled="currentPage === 1"
                    class="flex items-center justify-center px-3 h-8 ms-0 leading-tight text-body bg-neutral-primary-soft border border-e-0 border-default rounded-s-base hover:bg-neutral-secondary-medium hover:text-heading disabled:opacity-50 disabled:cursor-not-allowed">
                Previous
            </button>
        </li>
        <template x-for="page in totalPages" :key="page">
            <li>
                <button @click="goToPage(page)"
                        class="flex items-center justify-center px-3 h-8 leading-tight border border-default"
                        :class="page === currentPage
                            ? 'text-fg-brand bg-brand-softer hover:bg-brand-softer'
                            : 'text-body bg-neutral-primary-soft hover:bg-neutral-secondary-medium hover:text-heading'"
                        x-text="page">
                </button>
            </li>
        </template>
        <li>
            <button @click="nextPage()"
                    :disabled="currentPage === totalPages"
                    class="flex items-center justify-center px-3 h-8 leading-tight text-body bg-neutral-primary-soft border border-default rounded-e-base hover:bg-neutral-secondary-medium hover:text-heading disabled:opacity-50 disabled:cursor-not-allowed">
                Next
            </button>
        </li>
    </ul>
</nav>
```

---

## Navbars & Headers

### Sticky Header with Logo and Controls
```html
<header class="bg-neutral-primary-soft border-b border-default sticky top-0 z-40">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <div class="flex justify-between items-center">
            <div class="flex items-center space-x-4">
                <h1 class="text-2xl font-bold text-heading">
                    App Title
                </h1>
                <!-- Additional controls (dropdowns, etc.) -->
            </div>
            <div class="flex items-center space-x-2">
                <!-- Right-side controls (theme toggle, settings, etc.) -->
            </div>
        </div>
    </div>
</header>
```

---

## Dark Mode Toggle

### Icon Toggle Button (Alpine.js)

Every page must include a visible dark mode toggle. This button uses Alpine.js state with `$watch` for persistence.

**Required app state:**
```javascript
// Add to your app component function
darkMode: document.documentElement.classList.contains('dark'),

init() {
    this.$watch('darkMode', (enabled) => {
        document.documentElement.classList.toggle('dark', enabled);
        localStorage.setItem('color-theme', enabled ? 'dark' : 'light');
    });
    // ... other init code
}
```

**Toggle button:**
```html
<button type="button" @click="darkMode = !darkMode"
        class="text-body hover:text-heading bg-transparent hover:bg-neutral-secondary-medium focus:outline-none focus:ring-4 focus:ring-neutral-tertiary rounded-base text-sm p-2.5 inline-flex items-center justify-center">
    <!-- Sun icon (shown in dark mode — click to switch to light) -->
    <svg x-show="darkMode" class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
        <path d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" fill-rule="evenodd" clip-rule="evenodd"/>
    </svg>
    <!-- Moon icon (shown in light mode — click to switch to dark) -->
    <svg x-show="!darkMode" class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
        <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z"/>
    </svg>
    <span class="sr-only">Toggle dark mode</span>
</button>
```

### In a Header Bar
```html
<header class="bg-neutral-primary-soft border-b border-default sticky top-0 z-40">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <div class="flex justify-between items-center">
            <h1 class="text-2xl font-bold text-heading">App Title</h1>
            <div class="flex items-center space-x-2">
                <!-- Dark mode toggle -->
                <button type="button" @click="darkMode = !darkMode"
                        class="text-body hover:text-heading bg-transparent hover:bg-neutral-secondary-medium focus:outline-none focus:ring-4 focus:ring-neutral-tertiary rounded-base text-sm p-2.5 inline-flex items-center justify-center">
                    <svg x-show="darkMode" class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" fill-rule="evenodd" clip-rule="evenodd"/>
                    </svg>
                    <svg x-show="!darkMode" class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z"/>
                    </svg>
                    <span class="sr-only">Toggle dark mode</span>
                </button>
            </div>
        </div>
    </div>
</header>
```

---

## Responsive Grid Layouts

### 3-Column Responsive Grid
```html
<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
    <template x-for="item in items" :key="item.id">
        <div class="bg-neutral-primary-soft max-w-sm p-6 border border-default rounded-base shadow-xs">
            <!-- Card content -->
        </div>
    </template>
</div>
```

### Split Layout (1/3 + 2/3)
```html
<div class="grid grid-cols-3 gap-6">
    <!-- Left: Sidebar (1/3) -->
    <div class="col-span-1 space-y-4">
        <!-- Sidebar content -->
    </div>

    <!-- Right: Main Content (2/3) -->
    <div class="col-span-2">
        <div class="bg-neutral-primary-soft p-6 border border-default rounded-base shadow-xs sticky top-24">
            <!-- Main content -->
        </div>
    </div>
</div>
```

### Filters + Content Layout
```html
<!-- Filters Card -->
<div class="bg-neutral-primary-soft p-6 border border-default rounded-base shadow-xs mb-6">
    <div class="flex flex-wrap gap-6 items-center">
        <div>
            <!-- Filter controls -->
        </div>
        <div class="ml-auto text-sm text-body">
            Showing <span class="font-semibold" x-text="filteredItems.length"></span> of <span x-text="allItems.length"></span> items
        </div>
    </div>
</div>

<!-- Results Grid -->
<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
    <!-- Items -->
</div>
```

### Max-Width Content Container
```html
<main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
    <!-- Page content -->
</main>
```
