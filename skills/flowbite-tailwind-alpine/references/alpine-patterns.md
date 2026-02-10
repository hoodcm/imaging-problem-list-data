# Alpine.js Integration Patterns

Patterns for using Alpine.js with Flowbite components in a static SPA without a build step.

All code examples use classic Tailwind `dark:` prefix classes compatible with the CDN-only setup. See `color-patterns.md` for the complete mapping table.

## Table of Contents

1. [App Architecture](#app-architecture)
2. [State Management](#state-management)
3. [Data Binding](#data-binding)
4. [Event Handling](#event-handling)
5. [Conditional Rendering](#conditional-rendering)
6. [List Rendering](#list-rendering)
7. [Computed Properties (Getters)](#computed-properties-getters)
8. [Async Data Loading](#async-data-loading)
9. [View Management](#view-management)
10. [Form Integration](#form-integration)
11. [Popover & Tooltip Management](#popover--tooltip-management)
12. [Transitions](#transitions)
13. [URL State Sync](#url-state-sync)
14. [Nested Components](#nested-components)
15. [Flowbite + Alpine.js Interaction](#flowbite--alpinejs-interaction)
16. [x-cloak — Preventing FOUC (MANDATORY)](#x-cloak--preventing-fouc-mandatory)
17. [Dark Mode — Default Dark, Always Switchable (MANDATORY)](#dark-mode--default-dark-always-switchable-mandatory)
18. [Alpine.store() — Global Shared State](#alpinestore--global-shared-state)
19. [Alpine.data() — Reusable Named Components](#alpinedata--reusable-named-components)
20. [Alpine.bind() — Reusable Attribute Sets](#alpinebind--reusable-attribute-sets)
21. [$watch — Reactive Side Effects](#watch--reactive-side-effects)
22. [$dispatch — Cross-Component Communication](#dispatch--cross-component-communication)
23. [Lifecycle Events — alpine:init and alpine:initialized](#lifecycle-events--alpineinit-and-alpineinitialized)
24. [x-id and $id — Unique ID Generation](#x-id-and-id--unique-id-generation)
25. [x-modelable — Custom Two-Way Binding](#x-modelable--custom-two-way-binding)
26. [x-model Advanced Modifiers](#x-model-advanced-modifiers)
27. [Multi-Step Form Pattern](#multi-step-form-pattern)
28. [Alpine.js Plugins](#alpinejs-plugins)
29. [Error Handling Patterns](#error-handling-patterns)
30. [Performance — Large Lists](#performance--large-lists)

---

## App Architecture

### Single-Component Pattern (Recommended)

Use a single Alpine.js component function that manages all app state:

```javascript
// app.js
function myApp() {
    return {
        // === State Properties ===
        items: [],
        currentItem: null,
        currentView: 'list',  // 'list', 'detail', 'edit'
        loading: true,
        filterValue: 'all',

        // === Initialization ===
        async init() {
            await this.loadData();
            this.loading = false;
        },

        // === Data Methods ===
        async loadData() { /* ... */ },

        // === Computed Properties (getters) ===
        get filteredItems() {
            return this.items.filter(/* ... */);
        },

        // === Actions ===
        selectItem(id) { /* ... */ },
        deleteItem(id) { /* ... */ }
    };
}
```

```html
<!-- index.html -->
<div x-data="myApp()" x-init="init()" class="min-h-screen">
    <!-- All app markup here -->
</div>
```

### Key Principles

1. **One component function** contains all state and methods.
2. **State properties** are plain values (strings, arrays, objects, booleans).
3. **Getters** provide computed/derived values that auto-update.
4. **Methods** handle user actions and async operations.
5. **Never** add separate `<script>` blocks for minor features — extend the existing component. When the function exceeds ~400 lines or you need state shared across independent UI regions, see `Alpine.store()` and `Alpine.data()` sections below.

---

## State Management

### Declaring State
```javascript
function myApp() {
    return {
        // Simple values
        loading: true,
        currentView: 'list',
        searchQuery: '',

        // Arrays
        items: [],
        selectedIds: [],

        // Objects
        currentItem: null,
        filters: { region: 'all', status: 'all' },

        // Derived state (use getters, not stored values)
        get filteredItems() {
            return this.items.filter(item =>
                this.filters.region === 'all' || item.region === this.filters.region
            );
        }
    };
}
```

### Updating State

Alpine.js reactivity is automatic. Simply mutate properties:

```javascript
// Direct assignment (triggers reactivity)
this.loading = true;
this.currentItem = newItem;
this.items = [...this.items, newItem];

// Array mutations (reactive)
this.items.push(newItem);
this.selectedIds = this.selectedIds.filter(id => id !== removedId);

// Object mutations (reactive)
this.filters.region = 'chest';
this.currentItem = { ...this.currentItem, name: 'Updated' };
```

---

## Data Binding

### Text Content (`x-text`)
```html
<!-- Simple text -->
<span x-text="item.name"></span>

<!-- Computed text -->
<span x-text="items.length + ' items'"></span>

<!-- Conditional text -->
<span x-text="currentItem ? currentItem.name : 'None selected'"></span>
```

### HTML Content (`x-html`)
```html
<!-- Render HTML (use when content contains markup) -->
<div x-html="formatMarkdown(rawText)"></div>
```

### Attribute Binding (`:attr`)
```html
<!-- Dynamic class -->
<div :class="isActive ? 'bg-blue-500' : 'bg-gray-500'"></div>

<!-- Object syntax for multiple conditional classes -->
<span :class="{
    'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-300': status === 'active',
    'bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-300': status === 'error'
}"></span>

<!-- Dynamic style -->
<div :style="{ position: 'fixed', left: x + 'px', top: y + 'px' }"></div>

<!-- Dynamic src/href -->
<img :src="item.imageUrl" :alt="item.name">
<a :href="'/items/' + item.id">View</a>

<!-- Dynamic disabled -->
<button :disabled="loading || !isValid">Submit</button>
```

---

## Event Handling

### Click Events (`@click`)
```html
<!-- Simple click -->
<button @click="selectItem(item.id)">Select</button>

<!-- Prevent default (for <a> tags) -->
<a @click.prevent="navigateTo('home')" href="#">Home</a>

<!-- Stop propagation -->
<button @click.stop="toggleDropdown()">Toggle</button>

<!-- Click outside (for closing menus/popovers) -->
<div @click.outside="closeMenu()">
    <!-- Menu content -->
</div>
```

### Mouse Events
```html
<!-- Hover effects -->
<div @mouseenter="showTooltip = true; highlightText(item.text)"
     @mouseleave="showTooltip = false; clearHighlight()">
    Hover me
</div>
```

### Keyboard Events
```html
<!-- Key-specific handlers -->
<input @keyup.enter="submitSearch()"
       @keyup.escape="clearSearch()">

<!-- With modifiers -->
<input @keydown.ctrl.s.prevent="save()">
```

### Alpine Event Modifiers

| Modifier | Effect |
|----------|--------|
| `.prevent` | Calls `preventDefault()` |
| `.stop` | Calls `stopPropagation()` |
| `.outside` | Fires when click is outside element |
| `.window` | Listens on window instead of element |
| `.document` | Listens on document instead of element |
| `.once` | Only fires once |
| `.debounce.300ms` | Debounces the handler |
| `.throttle.500ms` | Throttles the handler |
| `.self` | Only fires if event target is the element itself |

---

## Conditional Rendering

### `x-show` (Toggle Visibility - Preferred)
```html
<!-- Show/hide with CSS display: none -->
<div x-show="currentView === 'list'">List view content</div>
<div x-show="currentView === 'detail'">Detail view content</div>

<!-- With loading state -->
<div x-show="loading">Loading spinner...</div>
<div x-show="!loading && items.length > 0">Items list...</div>
<div x-show="!loading && items.length === 0">Empty state...</div>
```

### `x-if` (Conditional DOM Insertion)

Use `x-if` only when the element shouldn't exist in DOM at all (performance for heavy content):

```html
<!-- x-if MUST be on a <template> tag -->
<template x-if="currentItem">
    <div>
        <!-- Heavy content that shouldn't be in DOM when not needed -->
    </div>
</template>
```

### When to Use `x-show` vs `x-if`

| Use `x-show` when... | Use `x-if` when... |
|---|---|
| Toggling frequently | Content is rarely shown |
| Content is lightweight | Content is very heavy (tables, grids) |
| Want CSS transitions | Need to destroy/recreate DOM |
| Default choice | Only when x-show is insufficient |

### `x-cloak` (Hide Until Alpine Initializes)
```html
<!-- Prevent flash of unstyled content -->
<div x-cloak x-show="someCondition">
    This won't flash before Alpine loads
</div>
```

Required CSS:
```css
[x-cloak] { display: none !important; }
```

---

## List Rendering

### Basic Loop (`x-for`)
```html
<template x-for="item in items" :key="item.id">
    <div class="p-4 bg-white dark:bg-gray-800 rounded-lg">
        <span x-text="item.name"></span>
    </div>
</template>
```

### Loop with Index
```html
<template x-for="(item, index) in items" :key="item.id">
    <div :class="index % 2 === 0 ? 'bg-white dark:bg-gray-800' : 'bg-gray-50 dark:bg-gray-900'">
        <span x-text="(index + 1) + '. ' + item.name"></span>
    </div>
</template>
```

### Nested Loops
```html
<template x-for="section in sections" :key="section.key">
    <div class="mb-8">
        <h2 x-text="section.title" class="text-2xl font-bold text-gray-900 dark:text-white mb-4"></h2>
        <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            <template x-for="(item, index) in section.items" :key="section.key + '-' + index">
                <div class="p-6 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow">
                    <span x-text="item.name"></span>
                </div>
            </template>
        </div>
    </div>
</template>
```

### Filtered Loop
```html
<!-- Use a getter that returns filtered results -->
<template x-for="item in filteredItems" :key="item.id">
    <div x-text="item.name"></div>
</template>
```

---

## Computed Properties (Getters)

Getters automatically recompute when their dependencies change:

```javascript
function myApp() {
    return {
        items: [],
        filterRegion: 'all',
        filterStatus: 'all',

        // Single-level filtering
        get filteredItems() {
            let result = this.items;

            if (this.filterRegion !== 'all') {
                result = result.filter(item =>
                    item.regions.includes(this.filterRegion)
                );
            }

            return result;
        },

        // Multi-level grouping (getter calling getter)
        get groupedItems() {
            const items = this.filteredItems; // uses the getter above
            return {
                active: items.filter(i => i.status === 'active'),
                inactive: items.filter(i => i.status === 'inactive')
            };
        },

        // Sections for rendering (filters empty groups)
        get sections() {
            return [
                { title: 'Active', key: 'active', items: this.groupedItems.active },
                { title: 'Inactive', key: 'inactive', items: this.groupedItems.inactive }
            ].filter(section => section.items.length > 0);
        }
    };
}
```

---

## Async Data Loading

### Pattern: Load with Loading State
```javascript
async loadData() {
    this.loading = true;
    try {
        const response = await fetch('data/items.json');
        const data = await response.json();
        this.items = data.items;
    } catch (error) {
        console.error('Error loading data:', error);
    }
    this.loading = false;
},
```

### Pattern: Load Multiple Resources in Parallel
```javascript
async init() {
    // Load configuration files in parallel
    await Promise.all([
        this.loadConfig(),
        this.loadMappings(),
        this.loadMetadata()
    ]);

    // Then load main data (depends on config)
    await this.loadItems();

    this.loading = false;
},
```

### Pattern: Load on Selection
```javascript
async selectItem(itemId) {
    this.loading = true;
    try {
        const [metaResponse, dataResponse] = await Promise.all([
            fetch(`data/items/${itemId}/meta.json`),
            fetch(`data/items/${itemId}/data.json`)
        ]);

        this.currentMeta = await metaResponse.json();
        this.currentData = await dataResponse.json();
        this.currentView = 'detail';
    } catch (error) {
        console.error('Error loading item:', error);
    }
    this.loading = false;
},
```

---

## View Management

### Multi-View Pattern
```javascript
// State
currentView: 'list',  // 'list', 'detail', 'edit'

// Navigation methods
showList() {
    this.currentView = 'list';
    this.currentItem = null;
},

showDetail(item) {
    this.currentItem = item;
    this.currentView = 'detail';
},

showEdit(item) {
    this.currentItem = { ...item }; // clone for editing
    this.currentView = 'edit';
}
```

```html
<!-- View: List -->
<div x-show="currentView === 'list'">
    <!-- list content -->
</div>

<!-- View: Detail -->
<div x-show="currentView === 'detail'">
    <template x-if="currentItem">
        <div>
            <button @click="showList()">Back</button>
            <!-- detail content -->
        </div>
    </template>
</div>

<!-- View: Edit -->
<div x-show="currentView === 'edit'">
    <template x-if="currentItem">
        <div>
            <!-- edit form -->
        </div>
    </template>
</div>
```

---

## Form Integration

### Two-Way Binding with `x-model`
```html
<!-- Text input -->
<input type="text" x-model="searchQuery"
       class="bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:placeholder-gray-400">

<!-- Select -->
<select x-model="filterRegion"
        class="block w-full p-2.5 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 dark:placeholder-gray-400">
    <option value="all">All</option>
    <option value="option1">Option 1</option>
</select>

<!-- Checkbox -->
<input type="checkbox" x-model="isEnabled"
       class="w-4 h-4 text-blue-600 bg-gray-50 dark:bg-gray-700 border-gray-300 dark:border-gray-600 rounded focus:ring-blue-500 focus:ring-2">
```

### x-model Modifiers

| Modifier | Effect |
|----------|--------|
| `.lazy` | Syncs on `change` instead of `input` |
| `.number` | Casts value to number |
| `.debounce.300ms` | Debounces input |
| `.throttle.500ms` | Throttles input |

---

## Popover & Tooltip Management

### Shared Popover Pattern

When you have many trigger elements but only one popover should be visible at a time:

```javascript
// State for shared popover
openPopover: null,        // ID of currently open popover
popoverData: null,        // Data to display in popover
popoverAnchorRect: null,  // Position reference

// Toggle popover
togglePopover(id, event) {
    if (this.openPopover === id) {
        this.closePopover();
    } else {
        this.openPopover = id;
        this.popoverData = this.getDataForId(id);
        const anchor = event.target.closest('.relative') || event.target;
        this.popoverAnchorRect = anchor.getBoundingClientRect();
    }
},

closePopover() {
    this.openPopover = null;
    this.popoverData = null;
    this.popoverAnchorRect = null;
},

// Calculate position based on current context
getPopoverStyle() {
    if (!this.popoverAnchorRect) return { display: 'none' };
    const rect = this.popoverAnchorRect;
    const popoverHeight = 384;
    const hasRoomAbove = rect.top > popoverHeight + 8;

    if (hasRoomAbove) {
        return {
            position: 'fixed',
            left: rect.left + 'px',
            top: (rect.top - 8) + 'px',
            transform: 'translateY(-100%)',
            zIndex: 100
        };
    } else {
        return {
            position: 'fixed',
            left: rect.left + 'px',
            top: (rect.bottom + 8) + 'px',
            zIndex: 100
        };
    }
}
```

---

## Transitions

### Standard Fade + Scale
```html
<div x-show="isVisible"
     x-transition:enter="transition ease-out duration-100"
     x-transition:enter-start="opacity-0 scale-95"
     x-transition:enter-end="opacity-100 scale-100"
     x-transition:leave="transition ease-in duration-75"
     x-transition:leave-start="opacity-100 scale-100"
     x-transition:leave-end="opacity-0 scale-95">
    Content
</div>
```

### Simple Fade
```html
<div x-show="isVisible" x-transition>
    Content with default fade transition
</div>
```

### Slide Down
```html
<div x-show="isOpen"
     x-transition:enter="transition ease-out duration-200"
     x-transition:enter-start="opacity-0 -translate-y-2"
     x-transition:enter-end="opacity-100 translate-y-0"
     x-transition:leave="transition ease-in duration-150"
     x-transition:leave-start="opacity-100 translate-y-0"
     x-transition:leave-end="opacity-0 -translate-y-2">
    Dropdown content
</div>
```

---

## URL State Sync

### Push State on Navigation
```javascript
// Update URL when state changes
selectItem(itemId) {
    this.currentItem = this.items.find(i => i.id === itemId);

    const url = new URL(window.location);
    url.searchParams.set('item', itemId);
    window.history.pushState({}, '', url);
},

// Read URL on init
async init() {
    const urlParams = new URLSearchParams(window.location.search);
    const itemId = urlParams.get('item');

    if (itemId) {
        await this.selectItem(itemId);
    }
}
```

---

## Nested Components

### Inline `x-data` for Local State

Use nested `x-data` for isolated behavior like tooltips or hover states:

```html
<div x-data="{ hover: false, showTooltip: false }"
     @mouseenter="hover = true"
     @mouseleave="hover = false; showTooltip = false">

    <div class="p-3 bg-white dark:bg-gray-800 border rounded-lg transition-colors"
         :class="hover ? 'bg-blue-100 dark:bg-blue-900 border-blue-600 dark:border-blue-500' : 'border-gray-200 dark:border-gray-700'">
        <!-- Content -->
    </div>

    <div x-show="showTooltip" class="absolute z-10 ...">
        <!-- Tooltip -->
    </div>
</div>
```

### Accessing Parent State from Nested Components

Nested `x-data` can access parent scope naturally:

```html
<div x-data="myApp()">
    <!-- Parent state: items, currentView, etc. are available -->

    <template x-for="item in items" :key="item.id">
        <div x-data="{ isExpanded: false }">
            <!-- Local state: isExpanded -->
            <!-- Parent state: still accessible -->
            <button @click="isExpanded = !isExpanded">Toggle</button>
            <button @click="selectItem(item.id)">Select (parent method)</button>

            <div x-show="isExpanded">
                Expanded content for <span x-text="item.name"></span>
            </div>
        </div>
    </template>
</div>
```

---

## Flowbite + Alpine.js Interaction

### Re-initializing Flowbite After Alpine Renders

Flowbite's JS scans for `data-*` attributes on page load. If Alpine dynamically adds Flowbite-attributed elements, you may need to re-initialize:

```javascript
// After dynamically adding Flowbite elements
this.$nextTick(() => {
    if (window.initFlowbite) {
        window.initFlowbite();
    }
});
```

### Flowbite Dropdown with Alpine Dynamic Content

Flowbite handles open/close via `data-dropdown-toggle`. Alpine handles the content via `x-for`:

```html
<!-- Flowbite controls the dropdown mechanics -->
<button data-dropdown-toggle="myDropdown">Open</button>
<div id="myDropdown" class="z-10 hidden ...">
    <!-- Alpine controls the list content -->
    <template x-for="item in items" :key="item.id">
        <a @click.prevent="selectItem(item.id)" x-text="item.name"></a>
    </template>
</div>
```

### When to Use Flowbite vs Alpine for Interactivity

| Component | Use Flowbite | Use Alpine |
|-----------|-------------|-----------|
| Dropdown open/close | `data-dropdown-toggle` | - |
| Dropdown content | - | `x-for`, `x-text`, `@click` |
| Modal open/close | `data-modal-toggle` | - |
| Modal dynamic content | - | `x-text`, `x-show` |
| Tooltip positioning | `data-tooltip-target` | - |
| Custom hover tooltip | - | `x-show` with `@mouseenter/@mouseleave` |
| Accordion expand | `data-accordion` | - |
| Tab switching | - | `@click` + `:class` + `x-show` |
| Form binding | - | `x-model` |
| View switching | - | `x-show` + state |
| Loading states | - | `x-show="loading"` |

---

## x-cloak — Preventing FOUC (MANDATORY)

**Every page MUST include both pieces.** Without them, `x-show` elements flash visible before Alpine initializes.

**1. CSS rule** (in `<head>`):
```html
<style>
    [x-cloak] { display: none !important; }
</style>
```

**2. Attribute** on any `x-show` element that starts hidden, or on the root `x-data` element:
```html
<div x-data="myApp()" x-init="init()" x-cloak>
    <!-- Entire app hidden until Alpine initializes -->
</div>

<div x-cloak x-show="isModalOpen">
    Modal content won't flash before Alpine loads
</div>
```

Both are required — the CSS rule without the attribute (or vice versa) has no effect.

---

## Dark Mode — Default Dark, Always Switchable (MANDATORY)

**Every page ships with dark mode active by default. Every page must include a visible toggle button.**

### FOUC-Prevention Script (in `<head>`, before body renders)

```html
<script>
    if (localStorage.getItem('color-theme') === 'light') {
        document.documentElement.classList.remove('dark');
    } else {
        document.documentElement.classList.add('dark');
    }
</script>
```

This script defaults to dark. Only an explicit `'light'` preference in localStorage switches to light mode.

### Alpine.js State + $watch Pattern

Add `darkMode` to your app component. Use `$watch` to sync changes to the DOM and localStorage:

```javascript
function myApp() {
    return {
        darkMode: document.documentElement.classList.contains('dark'),

        init() {
            this.$watch('darkMode', (enabled) => {
                document.documentElement.classList.toggle('dark', enabled);
                localStorage.setItem('color-theme', enabled ? 'dark' : 'light');
            });
        }
        // ... other state
    };
}
```

See `references/component-templates.md` § Dark Mode Toggle for the toggle button component and header integration example.

The `dark:` prefix classes automatically apply when the `dark` class is present on `<html>` — no additional CSS needed.

---

## When to Decompose — Architecture Progression

> **Start with a single component function** (`x-data="myApp()"`). This is the right default for most pages. When your app function exceeds ~400 lines or you need state shared between independent UI regions, introduce `Alpine.store()` for global state and `Alpine.data()` for reusable sub-components. The sections below cover these patterns.

---

## Alpine.store() — Global Shared State

Global reactive stores accessible from any component via `$store.name`. Unlike `x-data` (scoped to a DOM subtree), stores are application-wide singletons.

### Registering Stores

Register in the `alpine:init` event (fires before Alpine processes the DOM):

```javascript
document.addEventListener('alpine:init', () => {
    // Object store with init() lifecycle hook
    Alpine.store('app', {
        init() {
            // Runs automatically after registration
        },
        darkMode: false,
        sidebarOpen: true,
        currentUserId: null,

        toggleDarkMode() {
            this.darkMode = !this.darkMode;
            document.documentElement.classList.toggle('dark', this.darkMode);
        }
    });

    // Simple value store
    Alpine.store('loading', false);
});
```

### Accessing Stores

```html
<!-- From any component (x-data can be empty) -->
<button x-data @click="$store.app.toggleDarkMode()"
        class="p-2 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
    <span x-text="$store.app.darkMode ? 'Light Mode' : 'Dark Mode'"></span>
</button>

<!-- Reactive binding -->
<div x-data :class="$store.app.sidebarOpen ? 'ml-64' : 'ml-0'"
     class="transition-all duration-300">
    Main content area
</div>

<!-- Simple value store -->
<div x-data x-show="$store.loading" class="fixed inset-0 bg-black/50 z-50">
    Loading overlay...
</div>
```

### When to Use `Alpine.store()` vs `x-data`

| Scenario | Use |
|----------|-----|
| State shared across unrelated components | `Alpine.store()` |
| App-wide preferences (dark mode, locale) | `Alpine.store()` |
| Component-specific UI state (open/closed) | `x-data` |
| Form data for a single form | `x-data` |
| Data needed only within a DOM subtree | `x-data` |

**Gotchas:**
- Register stores in `alpine:init` event, not at page load.
- The `init()` method on a store runs automatically after registration.
- Access outside Alpine expressions via `Alpine.store('name')`.
- Stores are reactive — any component reading `$store.x` re-renders when `x` changes.

---

## Alpine.data() — Reusable Named Components

Register named component definitions that can be referenced in `x-data` by name. Eliminates duplicate inline data objects.

### Basic Registration

```javascript
document.addEventListener('alpine:init', () => {
    Alpine.data('expandableCard', () => ({
        expanded: false,

        toggle() {
            this.expanded = !this.expanded;
        },

        init() {
            // Runs when component mounts
        },

        destroy() {
            // Runs when component is removed from DOM (e.g., by x-if)
        }
    }));

    // Parameterized component
    Alpine.data('accordion', (initialOpen = false) => ({
        open: initialOpen,

        toggle() {
            this.open = !this.open;
        }
    }));
});
```

### Usage

```html
<!-- Use by name -->
<div x-data="expandableCard">
    <button @click="toggle()" class="text-gray-900 dark:text-white">Toggle</button>
    <div x-show="expanded">Details...</div>
</div>

<!-- Parameterized -->
<div x-data="accordion(true)">
    <button @click="toggle()">Section 1 (starts open)</button>
    <div x-show="open" x-collapse>Content</div>
</div>

<div x-data="accordion(false)">
    <button @click="toggle()">Section 2 (starts closed)</button>
    <div x-show="open" x-collapse>Content</div>
</div>
```

**Gotchas:**
- Use regular `function` (not arrow functions) when you need `this` to access Alpine magics (`this.$watch`, `this.$dispatch`, `this.$persist`).
- The `destroy()` hook fires when the element is removed from the DOM (e.g., by `x-if`).

---

## Alpine.bind() — Reusable Attribute Sets

Define reusable sets of attributes and directives applied via `x-bind="name"`. Reduces repetition across elements sharing the same behavior.

```javascript
document.addEventListener('alpine:init', () => {
    Alpine.bind('ActionButton', () => ({
        type: 'button',
        ':disabled'() { return this.loading; },
        ':class'() {
            return this.loading ? 'opacity-50 cursor-not-allowed' : 'hover:bg-blue-800 dark:hover:bg-blue-700';
        },
        '@click'() { this.handleAction(); },
    }));

    Alpine.bind('SortableHeader', () => ({
        '@click'() { this.sortBy(this.$el.dataset.field); },
        ':class'() {
            return this.sortField === this.$el.dataset.field
                ? 'text-blue-600 dark:text-blue-500 font-semibold'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white cursor-pointer';
        },
    }));
});
```

```html
<div x-data="{ loading: false, handleAction() { /* ... */ } }">
    <button x-bind="ActionButton" class="px-4 py-2 bg-blue-700 dark:bg-blue-600 text-white rounded-lg">
        Save
    </button>
    <button x-bind="ActionButton" class="px-4 py-2 bg-blue-700 dark:bg-blue-600 text-white rounded-lg">
        Submit
    </button>
</div>
```

**Gotchas:**
- Bound attributes merge with existing attributes (classes are additive).
- Keys use Alpine shorthand: `'@click'`, `':class'`, `':disabled'`.
- Functions receive `this` as the component context.

---

## $watch — Reactive Side Effects

Monitor a specific property and execute a callback when it changes. Receives both old and new values.

### Syntax

```javascript
init() {
    this.$watch('propertyName', (newValue, oldValue) => {
        // React to change
    });
}
```

### Patterns

```javascript
init() {
    // Watch with old/new comparison
    this.$watch('selectedItem', (newId, oldId) => {
        if (newId !== oldId) {
            this.loadItemData(newId);
        }
    });

    // Watch nested property (dot notation)
    this.$watch('filters.region', (newRegion) => {
        this.updateUrlParams();
    });

    // Sync dark mode to DOM
    this.$watch('darkMode', (enabled) => {
        document.documentElement.classList.toggle('dark', enabled);
        localStorage.setItem('color-theme', enabled ? 'dark' : 'light');
    });
}
```

### $watch vs x-effect

| Feature | `$watch` | `x-effect` |
|---------|----------|------------|
| Targets specific property | Yes | No (auto-detects all deps) |
| Provides old value | Yes | No |
| Declared in | `init()` method | HTML attribute |
| Use when | Need old/new comparison or explicit target | Just need "re-run when deps change" |

**Gotchas:**
- **Infinite loop danger:** Never modify the watched property inside its own callback.
- Dot notation (`'foo.bar'`) works for nested properties.
- Deep changes to objects/arrays are detected automatically.

---

## $dispatch — Cross-Component Communication

Dispatch custom DOM events. Data is passed via `$event.detail`.

### Basic Usage (Bubbles Up)

```html
<div x-data @custom-event="handleEvent($event.detail)">
    <button @click="$dispatch('custom-event', { id: 123 })">
        Fire Event
    </button>
</div>
```

### Critical Pattern: `.window` for Sibling Communication

Events only bubble up the DOM. To communicate between sibling or unrelated components, the **listener** must use `.window`:

```html
<!-- Notification system (listens globally) -->
<div x-data="{ messages: [] }"
     @notify.window="messages.push($event.detail)"
     class="fixed top-4 right-4 z-50 space-y-2">
    <template x-for="(msg, i) in messages" :key="i">
        <div class="p-4 bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-300 rounded-lg shadow-lg"
             x-text="msg.text"
             x-init="setTimeout(() => messages.splice(i, 1), 3000)">
        </div>
    </template>
</div>

<!-- Any other component can dispatch -->
<div x-data>
    <button @click="$dispatch('notify', { text: 'Saved successfully' })"
            class="px-4 py-2 bg-blue-700 dark:bg-blue-600 text-white rounded-lg">
        Save
    </button>
</div>
```

**Gotchas:**
- Without `.window`, sibling components never see the event.
- Event names must be lowercase kebab-case (`my-event`, not `myEvent`).
- Access data via `$event.detail`, not `$event.data`.

---

## Lifecycle Events — alpine:init and alpine:initialized

### alpine:init

Fires **before** Alpine initializes components. Register stores, data, binds, and plugins here:

```javascript
document.addEventListener('alpine:init', () => {
    Alpine.store('app', { /* ... */ });
    Alpine.data('myComponent', () => ({ /* ... */ }));
    Alpine.bind('MyBind', () => ({ /* ... */ }));
});
```

### alpine:initialized

Fires **after** all Alpine components are initialized:

```javascript
document.addEventListener('alpine:initialized', () => {
    console.log('All Alpine components ready');
    // Safe to interact with Alpine components programmatically
});
```

**Registration timing rule:** `Alpine.store()`, `Alpine.data()`, `Alpine.bind()`, and `Alpine.plugin()` must all be called inside `alpine:init` when using CDN.

---

## x-id and $id — Unique ID Generation

Generate unique IDs for accessibility (`for`/`id` pairs, `aria-labelledby`). Essential for reusable components that appear multiple times on a page.

### Reusable Form Field

```html
<template x-for="field in formFields" :key="field.name">
    <div x-id="['input']" class="mb-4">
        <label :for="$id('input')"
               class="block mb-2 text-sm font-medium text-gray-900 dark:text-white"
               x-text="field.label"></label>
        <input :id="$id('input')" type="text" x-model="field.value"
               class="bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:placeholder-gray-400">
    </div>
</template>
<!-- Renders: input-1, input-2, etc. -->
```

### Keyed IDs for Lists

```html
<div x-id="['list']">
    <ul :id="$id('list')" role="listbox"
        :aria-activedescendant="$id('list', activeIndex)">
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

**Gotchas:**
- `x-id` requires a parent element with `x-data`.
- `$id('name', suffix)` appends a custom suffix for loop-specific IDs.
- Nested `x-id` scopes each get their own unique counter.

---

## x-modelable — Custom Two-Way Binding

Expose a child component's internal state to a parent via `x-model`. Creates true two-way binding between scopes.

```html
<!-- Parent controls rating, child manages stars -->
<div x-data="{ rating: 3 }">
    <p class="text-gray-500 dark:text-gray-400 mb-2">Rating: <span x-text="rating"></span></p>

    <div x-data="{ stars: 0 }" x-modelable="stars" x-model="rating"
         class="flex gap-1">
        <template x-for="i in 5" :key="i">
            <button @click="stars = i"
                    :class="i <= stars ? 'text-yellow-400' : 'text-gray-300 dark:text-gray-600'"
                    class="text-2xl">&#9733;</button>
        </template>
    </div>
</div>
```

Changing `stars` inside the child updates `rating` in the parent, and vice versa.

---

## x-model Advanced Modifiers

| Modifier | Behavior |
|----------|----------|
| `.lazy` | Syncs on `change` instead of `input` |
| `.number` | Casts value to number |
| `.boolean` | Casts value to boolean |
| `.debounce.300ms` | Debounces input |
| `.throttle.500ms` | Throttles input |
| `.blur` | Syncs on focus loss |
| `.enter` | Syncs only when Enter is pressed |
| `.fill` | Populates empty bound property from `value` attribute |

---

## Multi-Step Form Pattern

### Step State with Validation

```javascript
function multiStepForm() {
    return {
        step: 1,
        totalSteps: 3,
        errors: {},
        formData: { fullName: '', email: '', category: '' },

        get progress() {
            return Math.round((this.step / this.totalSteps) * 100);
        },

        validateStep() {
            this.errors = {};
            if (this.step === 1) {
                if (!this.formData.fullName) this.errors.fullName = 'Required';
                if (!this.formData.email) this.errors.email = 'Required';
            }
            return Object.keys(this.errors).length === 0;
        },

        nextStep() {
            if (this.validateStep()) this.step = Math.min(this.step + 1, this.totalSteps);
        },
        prevStep() {
            this.step = Math.max(this.step - 1, 1);
        }
    };
}
```

Use `x-show="step === N"` for each step, with Previous/Next/Submit buttons controlled by step position. See `references/component-templates.md` for button styling patterns.

---

## Alpine.js Plugins

Official plugins extend Alpine with new directives and magics. Load plugin scripts via CDN **before** the Alpine core script.

```html
<script defer src="https://cdn.jsdelivr.net/npm/@alpinejs/PLUGIN@3.x.x/dist/cdn.min.js"></script>
<!-- Alpine.js core AFTER plugins -->
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
```

### Plugin Reference

| Plugin | Directive/Magic | Purpose | Key Modifiers |
|--------|----------------|---------|---------------|
| **Persist** | `$persist(value)` | Save/restore state via localStorage | `.as('key')`, `.using(sessionStorage)` |
| **Focus** | `x-trap="condition"` | Trap keyboard focus in modals | `.inert`, `.noscroll`, `.noautofocus` |
| **Collapse** | `x-collapse` | Smooth height animation on show/hide | `.duration.500ms`, `.min.80px` |
| **Intersect** | `x-intersect` | Viewport enter/leave triggers | `.once`, `.half`, `.full` |
| **Anchor** | `x-anchor="$refs.el"` | Auto-position popovers/dropdowns | `.bottom-start`, `.offset.8`, `.top-end` |
| **Mask** | `x-mask="99/99/9999"` | Format input as user types | Wildcards: `9` (num), `a` (letter), `*` (any) |

### Persist Example

```javascript
function myApp() {
    return {
        darkMode: this.$persist(true),
        selectedItem: this.$persist('').as('app_selected'),
        tempFilter: this.$persist('all').using(sessionStorage),
    };
}
```

### Focus Example (Modal)

```html
<div x-show="isModalOpen"
     x-trap.noscroll.inert="isModalOpen"
     @keydown.escape.window="isModalOpen = false"
     class="fixed inset-0 z-50 flex items-center justify-center">
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
        <!-- Tab key stays inside -->
    </div>
</div>
```

---

## Error Handling Patterns

### Loading + Error + Success State Trio

```javascript
async loadData(id) {
    this.loading = true;
    this.error = null;

    try {
        const response = await fetch(`data/items/${id}/data.json`);
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        this.data = await response.json();
    } catch (err) {
        this.error = err.message;
        console.error('Load failed:', err);
    } finally {
        this.loading = false;
    }
}
```

### Template Pattern

Use three mutually exclusive `x-show` blocks: `x-show="error"` (with retry button), `x-show="loading"` (spinner), `x-show="!loading && !error && data"` (content). See `references/component-templates.md` for spinner and alert component markup.

**Key rules:**
- Always use `finally` to reset `loading` — even on error.
- Always clear `error` before starting a new request.
- Show a retry button on error states.

---

## Performance — Large Lists

### "Load More" Pattern with Computed Getter

```javascript
function largeListApp() {
    return {
        allItems: [],
        displayCount: 50,

        get visibleItems() {
            return this.allItems.slice(0, this.displayCount);
        },

        get hasMore() {
            return this.displayCount < this.allItems.length;
        },

        loadMore() {
            this.displayCount = Math.min(this.displayCount + 50, this.allItems.length);
        }
    };
}
```

Render `visibleItems` with `x-for`, then add either a "Load More" button (`@click="loadMore()"`) or an Intersect plugin sentinel (`x-intersect:enter="loadMore()"`) for infinite scroll.
