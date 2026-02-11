# Design System Guide

All visual styling in the Flask Schedule Webapp must use design tokens defined in
`app/static/css/design-tokens.css`. Never hardcode colors, spacing, font sizes, or
other visual values. This guide documents every available token and how to use it.

---

## Color Palette

### Primary Brand Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--color-primary` | `#2E4C73` | PC Navy. Primary buttons, headings, nav backgrounds |
| `--color-primary-light` | `#1B9BD8` | PC Blue. Links, hover accents, secondary actions |
| `--color-primary-dark` | `#1E3A5F` | Pressed/active states for primary elements |

Aliases (for backward compatibility):
- `--pc-navy` = `--color-primary`
- `--pc-blue` = `--color-primary-light`
- `--pc-light-blue` = `#E8F4F9` (light blue backgrounds)
- `--primary-color` = `--color-primary`

### Secondary Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--color-secondary` | `#FF8C00` | Orange. Highlights, attention-drawing elements |
| `--color-secondary-light` | `#FFA500` | Hover state for secondary elements |
| `--color-secondary-dark` | `#CC7000` | Pressed state for secondary elements |

### Semantic / Status Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--color-success` | `#28a745` | Confirmations, approved states, positive actions |
| `--color-success-light` | `#34CE57` | Hover for success elements |
| `--color-success-dark` | `#1E7E34` | Pressed for success elements |
| `--color-warning` | `#FF8C00` | Warnings, alerts requiring attention |
| `--color-warning-light` | `#FFA500` | Hover for warning elements |
| `--color-warning-dark` | `#CC7000` | Pressed for warning elements |
| `--color-danger` | `#dc3545` | Errors, destructive actions, delete buttons |
| `--color-danger-light` | `#E74C5C` | Hover for danger elements |
| `--color-danger-dark` | `#BD2130` | Pressed for danger elements |
| `--color-info` | `#3B82F6` | Informational messages, help text |
| `--color-info-light` | `#60A5FA` | Hover for info elements |
| `--color-info-dark` | `#2563EB` | Pressed for info elements |

### Neutral / Gray Scale

Use neutrals for text, borders, backgrounds, and dividers.

| Token | Value | Typical Usage |
|-------|-------|---------------|
| `--color-neutral-50` | `#FFFFFF` | Page background, card backgrounds |
| `--color-neutral-100` | `#F9FAFB` | Alternate row backgrounds, subtle fills |
| `--color-neutral-200` | `#E5E7EB` | Default borders, dividers |
| `--color-neutral-300` | `#D1D5DB` | Input borders, heavier dividers |
| `--color-neutral-400` | `#9CA3AF` | Placeholder text, disabled text |
| `--color-neutral-500` | `#6B7280` | Secondary/muted text |
| `--color-neutral-600` | `#4B5563` | Body text (lighter) |
| `--color-neutral-700` | `#374151` | Body text (standard) |
| `--color-neutral-800` | `#1F2937` | Headings, high-emphasis text |
| `--color-neutral-900` | `#111827` | Maximum contrast text |
| `--color-neutral-950` | `#030712` | Near-black, rare usage |

### Event Type Colors

Used to visually distinguish event types on the calendar and in lists.

| Token | Value | Event Type |
|-------|-------|------------|
| `--color-juicer` | `#FF6B6B` | Juicer events |
| `--color-digital` | `#4ECDC4` | Digital events (Setup, Refresh, Teardown) |
| `--color-core` | `#95E1D3` | Core events |
| `--color-supervisor` | `#6366f1` | Supervisor events |
| `--color-freeosk` | `#FFD93D` | Freeosk events |

### Role Badge Colors

Used for employee role badges and tags.

| Token | Value | Role |
|-------|-------|------|
| `--color-badge-lead` | `#FF69B4` | Lead Event Specialist |
| `--color-badge-supervisor` | `#00CED1` | Club Supervisor |
| `--color-badge-juicer` | `var(--color-secondary)` | Juicer Barista |
| `--color-badge-specialist` | `var(--color-success)` | Event Specialist |
| `--color-badge-ab-trained` | `#007bff` | A&B Trained |
| `--color-badge-juicer-trained` | `#17a2b8` | Juicer Trained |
| `--color-badge-inactive` | `var(--color-danger)` | Inactive |

### Schedule Status Colors

| Token | Value | Status |
|-------|-------|--------|
| `--color-scheduled` | `#3B82F6` | Scheduled |
| `--color-unscheduled` | `#9CA3AF` | Unscheduled |
| `--color-completed` | `#28a745` | Completed |
| `--color-overdue` | `#dc3545` | Overdue |

---

## Typography

### Font Families

| Token | Value | Usage |
|-------|-------|-------|
| `--font-primary` | `'Outfit', -apple-system, ...` | All UI text |
| `--font-monospace` | `'SF Mono', Monaco, ...` | Code, IDs, timestamps |

### Font Sizes

Minimum body text size is 14px for accessibility compliance.

| Token | Value | Usage |
|-------|-------|-------|
| `--font-size-xs` | `0.75rem` (12px) | Badges, labels only. Use sparingly. |
| `--font-size-sm` | `0.875rem` (14px) | Minimum body text, table cells, buttons |
| `--font-size-base` | `1rem` (16px) | Default body text, inputs |
| `--font-size-md` | `1.125rem` (18px) | Emphasized body text |
| `--font-size-lg` | `1.25rem` (20px) | h4, small section headings |
| `--font-size-xl` | `1.5rem` (24px) | h3, medium headings |
| `--font-size-2xl` | `1.875rem` (30px) | h2, large headings |
| `--font-size-3xl` | `2.25rem` (36px) | h1, page titles |

### Font Weights

| Token | Value | Usage |
|-------|-------|-------|
| `--font-weight-normal` | `400` | Body text |
| `--font-weight-medium` | `500` | Slightly emphasized text, labels |
| `--font-weight-semibold` | `600` | Buttons, table headers, sub-headings |
| `--font-weight-bold` | `700` | Headings, strong emphasis |

### Line Heights

| Token | Value | Usage |
|-------|-------|-------|
| `--line-height-tight` | `1.25` | Headings, compact UI |
| `--line-height-normal` | `1.5` | Body text (default) |
| `--line-height-relaxed` | `1.75` | Long-form content, help text |

---

## Spacing

All spacing follows a **4px base grid**. Use spacing tokens for margins, padding, and gaps.

### Numeric Scale

| Token | Value | Pixels |
|-------|-------|--------|
| `--space-0` | `0` | 0 |
| `--space-1` | `0.25rem` | 4px |
| `--space-2` | `0.5rem` | 8px |
| `--space-3` | `0.75rem` | 12px |
| `--space-4` | `1rem` | 16px |
| `--space-5` | `1.25rem` | 20px |
| `--space-6` | `1.5rem` | 24px |
| `--space-8` | `2rem` | 32px |
| `--space-10` | `2.5rem` | 40px |
| `--space-12` | `3rem` | 48px |
| `--space-16` | `4rem` | 64px |
| `--space-20` | `5rem` | 80px |

### Semantic Aliases

| Token | Maps To | Usage |
|-------|---------|-------|
| `--spacing-xs` | `--space-1` (4px) | Tight gaps, icon padding |
| `--spacing-sm` | `--space-2` (8px) | Small gaps, compact padding |
| `--spacing-md` | `--space-4` (16px) | Standard padding, form gaps |
| `--spacing-lg` | `--space-6` (24px) | Section padding, card padding |
| `--spacing-xl` | `--space-8` (32px) | Large section margins |

---

## Borders

### Border Width and Color

| Token | Value | Usage |
|-------|-------|-------|
| `--border-width` | `1px` | Default border |
| `--border-width-thick` | `2px` | Emphasized borders, focus rings |
| `--border-color` | `var(--color-neutral-200)` | Default borders, dividers |
| `--border-color-dark` | `var(--color-neutral-300)` | Higher-contrast borders |

### Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| `--radius-sm` | `4px` | Small elements, badges, chips |
| `--radius-md` | `6px` | Buttons, inputs, event cards |
| `--radius-lg` | `8px` | Cards, modals |
| `--radius-xl` | `12px` | Large containers, panels |
| `--radius-full` | `9999px` | Circles, pill shapes |

---

## Shadows

| Token | Value | Usage |
|-------|-------|-------|
| `--shadow-xs` | `0 1px 2px rgba(0,0,0,0.05)` | Subtle lift (table rows on hover) |
| `--shadow-sm` | `0 1px 3px rgba(0,0,0,0.1)` | Cards at rest |
| `--shadow-md` | `0 4px 6px rgba(0,0,0,0.1)` | Dropdowns, popovers |
| `--shadow-lg` | `0 10px 15px rgba(0,0,0,0.1)` | Modals, floating panels |
| `--shadow-xl` | `0 20px 25px rgba(0,0,0,0.15)` | Elevated overlays |

---

## Transitions

| Token | Value | Usage |
|-------|-------|-------|
| `--transition-fast` | `150ms ease` | Hover color changes, small transforms |
| `--transition-base` | `200ms ease` | General interactions, button presses |
| `--transition-slow` | `300ms ease` | Panel expand/collapse, page transitions |

---

## Z-Index Layers

Use these tokens to maintain a consistent stacking order. Never use arbitrary z-index values.

| Token | Value | Usage |
|-------|-------|-------|
| `--z-base` | `1` | Slightly above normal flow |
| `--z-dropdown` | `1000` | Dropdown menus |
| `--z-sticky` | `1020` | Sticky headers, sticky columns |
| `--z-fixed` | `1030` | Fixed navigation bars |
| `--z-modal-backdrop` | `1040` | Modal backdrop overlay |
| `--z-modal` | `1050` | Modal dialogs |
| `--z-popover` | `1060` | Popovers, tooltips with interaction |
| `--z-tooltip` | `1070` | Tooltips |
| `--z-notification` | `1080` | Toast notifications |
| `--z-loading-overlay` | `10000` | Full-page loading overlays |

---

## Component Tokens

### Event Cards

| Token | Value | Usage |
|-------|-------|-------|
| `--event-card-padding` | `var(--space-3)` (12px) | Internal padding |
| `--event-card-border-radius` | `6px` | Corner rounding |
| `--event-card-font-size` | `var(--font-size-sm)` (14px) | Card text size |
| `--event-card-min-height` | `56px` | Touch target compliance |
| `--event-card-gap` | `var(--space-2)` (8px) | Gap between card elements |

### Buttons

| Token | Value | Usage |
|-------|-------|-------|
| `--btn-padding-y` | `var(--space-2)` (8px) | Vertical padding |
| `--btn-padding-x` | `var(--space-3)` (12px) | Horizontal padding |
| `--btn-height` | `2.5rem` (40px) | Minimum button height |
| `--btn-font-size` | `var(--font-size-sm)` (14px) | Button text size |
| `--btn-border-radius` | `6px` | Corner rounding |
| `--btn-font-weight` | `var(--font-weight-semibold)` (600) | Text weight |

### Input Fields

| Token | Value | Usage |
|-------|-------|-------|
| `--input-padding-y` | `var(--space-2)` (8px) | Vertical padding |
| `--input-padding-x` | `var(--space-3)` (12px) | Horizontal padding |
| `--input-height` | `2.5rem` (40px) | Minimum input height |
| `--input-font-size` | `var(--font-size-base)` (16px) | Input text size |
| `--input-border-radius` | `6px` | Corner rounding |
| `--input-border-color` | `var(--color-neutral-300)` | Default border |
| `--input-focus-border-color` | `var(--color-primary)` | Focused border |

### Modals

| Token | Value | Usage |
|-------|-------|-------|
| `--modal-padding` | `var(--space-6)` (24px) | Internal padding |
| `--modal-border-radius` | `8px` | Corner rounding |
| `--modal-backdrop` | `rgba(0, 0, 0, 0.5)` | Backdrop overlay color |
| `--modal-max-width` | `600px` | Maximum modal width |

### Navigation

| Token | Value | Usage |
|-------|-------|-------|
| `--nav-height` | `60px` | Navigation bar height |
| `--nav-padding` | `var(--space-4)` (16px) | Navigation internal padding |
| `--nav-link-padding` | `var(--space-3)` (12px) | Padding around nav links |

---

## Breakpoints

CSS custom properties cannot be used in `@media` queries. Use these pixel values directly.

| Name | Value | Usage |
|------|-------|-------|
| sm | `640px` | Small phones (landscape) |
| md | `768px` | Tablets |
| lg | `1024px` | Laptops, small desktops |
| xl | `1280px` | Desktops |
| 2xl | `1536px` | Large desktops |

```css
@media (max-width: 768px) {
  /* Tablet and below */
}
```

---

## Usage Examples

### Correct vs. Incorrect

Always use tokens. Never hardcode visual values.

```css
/* CORRECT */
.card {
  background: var(--color-neutral-50);
  color: var(--color-neutral-700);
  border: var(--border-width) solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  box-shadow: var(--shadow-sm);
  font-size: var(--font-size-base);
  transition: box-shadow var(--transition-base);
}

/* WRONG - hardcoded values */
.card {
  background: #fff;
  color: #374151;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  font-size: 16px;
  transition: box-shadow 200ms ease;
}
```

### Status Badge

```css
/* CORRECT */
.badge-success {
  background-color: var(--color-success);
  color: var(--color-neutral-50);
  font-size: var(--font-size-xs);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  font-weight: var(--font-weight-semibold);
}

/* WRONG */
.badge-success {
  background-color: #28a745;
  color: white;
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 600;
}
```

### Event Card

```css
/* CORRECT */
.event-card {
  padding: var(--event-card-padding);
  border-radius: var(--event-card-border-radius);
  font-size: var(--event-card-font-size);
  min-height: var(--event-card-min-height);
  gap: var(--event-card-gap);
}

.event-card--juicer {
  border-left: 3px solid var(--color-juicer);
}
```

### Button

```css
/* CORRECT */
.btn-primary {
  background-color: var(--color-primary);
  color: var(--color-neutral-50);
  padding: var(--btn-padding-y) var(--btn-padding-x);
  min-height: var(--btn-height);
  font-size: var(--btn-font-size);
  font-weight: var(--btn-font-weight);
  border-radius: var(--btn-border-radius);
  transition: background-color var(--transition-fast);
}

.btn-primary:hover {
  background-color: var(--color-primary-light);
}

.btn-primary:active {
  background-color: var(--color-primary-dark);
}
```

### Modal

```css
/* CORRECT */
.modal-overlay {
  background: var(--modal-backdrop);
  z-index: var(--z-modal-backdrop);
}

.modal-dialog {
  max-width: var(--modal-max-width);
  padding: var(--modal-padding);
  border-radius: var(--modal-border-radius);
  background: var(--color-neutral-50);
  box-shadow: var(--shadow-lg);
  z-index: var(--z-modal);
}
```

### Z-Index Layering

```css
/* CORRECT - predictable stacking */
.dropdown-menu   { z-index: var(--z-dropdown); }
.sticky-header   { z-index: var(--z-sticky); }
.modal           { z-index: var(--z-modal); }
.toast           { z-index: var(--z-notification); }

/* WRONG - arbitrary values lead to stacking bugs */
.dropdown-menu   { z-index: 999; }
.sticky-header   { z-index: 100; }
.modal           { z-index: 9999; }
.toast           { z-index: 99999; }
```

---

## Common Hardcoded-to-Token Mappings

When refactoring existing CSS, replace hardcoded values with these tokens.

### Colors

| Hardcoded Value | Replace With |
|-----------------|-------------|
| `#fff`, `#ffffff`, `white` | `var(--color-neutral-50)` |
| `#f9fafb`, `#f8f9fa` | `var(--color-neutral-100)` |
| `#e5e7eb`, `#eee`, `#efefef` | `var(--color-neutral-200)` |
| `#d1d5db`, `#ddd`, `#ccc` | `var(--color-neutral-300)` |
| `#9ca3af`, `#999`, `#aaa` | `var(--color-neutral-400)` |
| `#6b7280`, `#666`, `#777` | `var(--color-neutral-500)` |
| `#4b5563`, `#555` | `var(--color-neutral-600)` |
| `#374151`, `#333`, `#444` | `var(--color-neutral-700)` |
| `#1f2937`, `#222` | `var(--color-neutral-800)` |
| `#111827`, `#111` | `var(--color-neutral-900)` |
| `#2E4C73` | `var(--color-primary)` |
| `#1B9BD8` | `var(--color-primary-light)` |
| `#28a745` | `var(--color-success)` |
| `#dc3545` | `var(--color-danger)` |
| `#FF8C00` | `var(--color-warning)` or `var(--color-secondary)` |
| `#007bff`, `#3B82F6` | `var(--color-info)` |

### Spacing

| Hardcoded Value | Replace With |
|-----------------|-------------|
| `4px`, `0.25rem` | `var(--space-1)` |
| `8px`, `0.5rem` | `var(--space-2)` |
| `12px`, `0.75rem` | `var(--space-3)` |
| `16px`, `1rem` | `var(--space-4)` |
| `20px`, `1.25rem` | `var(--space-5)` |
| `24px`, `1.5rem` | `var(--space-6)` |
| `32px`, `2rem` | `var(--space-8)` |
| `40px`, `2.5rem` | `var(--space-10)` |
| `48px`, `3rem` | `var(--space-12)` |

### Font Sizes

| Hardcoded Value | Replace With |
|-----------------|-------------|
| `12px`, `0.75rem` | `var(--font-size-xs)` |
| `14px`, `0.875rem` | `var(--font-size-sm)` |
| `16px`, `1rem` | `var(--font-size-base)` |
| `18px`, `1.125rem` | `var(--font-size-md)` |
| `20px`, `1.25rem` | `var(--font-size-lg)` |
| `24px`, `1.5rem` | `var(--font-size-xl)` |
| `30px`, `1.875rem` | `var(--font-size-2xl)` |
| `36px`, `2.25rem` | `var(--font-size-3xl)` |

### Border Radius

| Hardcoded Value | Replace With |
|-----------------|-------------|
| `4px` | `var(--radius-sm)` |
| `6px` | `var(--radius-md)` |
| `8px` | `var(--radius-lg)` |
| `12px` | `var(--radius-xl)` |
| `50%`, `9999px` | `var(--radius-full)` |

---

## Accessibility Notes

- **Minimum body text**: Use `--font-size-sm` (14px) as the floor. Only use `--font-size-xs` for non-essential labels.
- **Touch targets**: Buttons and inputs use `--btn-height` / `--input-height` (40px) to meet minimum 44px touch targets with padding.
- **Reduced motion**: The design tokens file includes `@media (prefers-reduced-motion: reduce)` which disables all animations automatically.
- **Screen reader**: Use the `.sr-only` utility class for visually hidden but screen-reader-accessible text.
- **Skip navigation**: Use the `.skip-to-content` class on a link at the top of the page.
