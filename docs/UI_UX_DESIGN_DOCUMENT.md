# UI/UX Design Document
## Product Connections Scheduler

**Document Version:** 1.0
**Last Updated:** 2026-02-04
**Application Type:** Internal Business Tool / Employee Scheduling SaaS

---

## Table of Contents

1. [Design Philosophy](#1-design-philosophy)
2. [Brand Identity](#2-brand-identity)
3. [Design Tokens](#3-design-tokens)
4. [Typography System](#4-typography-system)
5. [Color System](#5-color-system)
6. [Spacing System](#6-spacing-system)
7. [Component Library](#7-component-library)
8. [Layout Patterns](#8-layout-patterns)
9. [Navigation System](#9-navigation-system)
10. [Accessibility Standards](#10-accessibility-standards)
11. [Responsive Design](#11-responsive-design)
12. [Animation & Motion](#12-animation--motion)
13. [Iconography](#13-iconography)
14. [Forms & Inputs](#14-forms--inputs)
15. [Feedback & Notifications](#15-feedback--notifications)

---

## 1. Design Philosophy

### Core Principles

| Principle | Description |
|-----------|-------------|
| **Clarity First** | Information hierarchy should be immediately clear. Users (supervisors, managers) need to quickly scan schedules and identify issues. |
| **Efficiency** | Minimize clicks for common tasks. Scheduling operations should be fast and intuitive. |
| **Consistency** | Visual and interaction patterns remain consistent across all pages. |
| **Accessibility** | WCAG 2.1 Level AA compliance. The app must be usable by all employees regardless of ability. |
| **Professional Aesthetic** | Clean, business-appropriate design that builds trust and credibility. |

### Target Users

- **Primary:** Club Supervisors managing daily schedules
- **Secondary:** Lead Event Specialists, HR/Admin staff
- **Environment:** Desktop-first (office workstations), with mobile access for on-the-go viewing

### Design Style

**Classification:** Corporate Minimalism with Functional Focus

The design follows a **clean professional** aesthetic:
- White backgrounds with subtle shadows for depth
- Navy/blue accent colors reflecting corporate identity
- Clear visual hierarchy with ample whitespace
- Card-based layouts for scannable information
- Subtle animations for feedback (not decoration)

---

## 2. Brand Identity

### Logo

- **File:** `PC-Logo_Primary_Full-Color-1024x251.png`
- **Placement:** Top-left header, white background container with rounded corners
- **Minimum Height:** 40px mobile, 50px desktop

### Brand Voice

| Context | Voice |
|---------|-------|
| Headers | Professional, action-oriented ("Dashboard", "Schedule Verification") |
| Button labels | Imperative, concise ("Save", "Cancel", "Refresh Database") |
| Error messages | Helpful, non-technical ("Unable to save. Please try again.") |
| Success messages | Positive, brief ("Schedule updated successfully") |

---

## 3. Design Tokens

The application uses a **CSS Custom Properties** based design token system defined in `design-tokens.css`. All styles reference these tokens for consistency.

### Token Architecture

```
:root
├── Color Tokens (--color-*)
├── Typography Tokens (--font-*)
├── Spacing Tokens (--space-*, --spacing-*)
├── Component Tokens (--btn-*, --input-*, --modal-*)
├── Shadow Tokens (--shadow-*)
├── Border Tokens (--radius-*, --border-*)
├── Transition Tokens (--transition-*)
└── Z-Index Tokens (--z-*)
```

### Token Files

| File | Purpose |
|------|---------|
| `design-tokens.css` | Foundational design system values |
| `style.css` | Global styles referencing tokens |
| `responsive.css` | Breakpoint-specific token overrides |

---

## 4. Typography System

### Font Stack

```css
--font-primary: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
--font-monospace: 'SF Mono', Monaco, 'Cascadia Code', 'Courier New', monospace;
```

**Outfit** is the primary typeface - a geometric sans-serif with excellent readability at small sizes.

### Type Scale

| Token | Size | Usage |
|-------|------|-------|
| `--font-size-xs` | 12px (0.75rem) | Labels, badges, timestamps |
| `--font-size-sm` | 14px (0.875rem) | Body text minimum, table cells |
| `--font-size-base` | 16px (1rem) | Default body text |
| `--font-size-md` | 18px (1.125rem) | Large body text, subheadings |
| `--font-size-lg` | 20px (1.25rem) | Section headings (h3) |
| `--font-size-xl` | 24px (1.5rem) | Page section headings (h2) |
| `--font-size-2xl` | 30px (1.875rem) | Page titles (h1) |
| `--font-size-3xl` | 36px (2.25rem) | Hero/feature headings |

### Font Weights

| Token | Weight | Usage |
|-------|--------|-------|
| `--font-weight-normal` | 400 | Body text |
| `--font-weight-medium` | 500 | Emphasized text, labels |
| `--font-weight-semibold` | 600 | Buttons, headings |
| `--font-weight-bold` | 700 | Strong emphasis, stats |

### Line Heights

| Token | Value | Usage |
|-------|-------|-------|
| `--line-height-tight` | 1.25 | Headings, tight layouts |
| `--line-height-normal` | 1.5 | Body text (default) |
| `--line-height-relaxed` | 1.75 | Long-form content |

---

## 5. Color System

### Primary Brand Colors

| Name | Value | Usage |
|------|-------|-------|
| PC Navy | `#2E4C73` | Primary brand, headings, CTA buttons |
| PC Blue | `#1B9BD8` | Secondary accent, links, highlights |
| PC Light Blue | `#E8F4F9` | Background tints, hover states |

### Semantic Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--color-success` | `#28a745` | Success states, confirmations |
| `--color-warning` | `#FF8C00` | Warnings, caution states |
| `--color-danger` | `#dc3545` | Errors, destructive actions |
| `--color-info` | `#3B82F6` | Informational, neutral highlights |

### Event Type Colors

These colors are used to visually distinguish different event categories:

| Event Type | Color | Hex |
|------------|-------|-----|
| Juicer | Coral Red | `#FF6B6B` |
| Digital | Teal | `#4ECDC4` |
| Core | Mint Green | `#95E1D3` |
| Supervisor | Indigo | `#6366f1` |
| Freeosk | Yellow | `#FFD93D` |

### Neutral Scale

```css
--color-neutral-50:  #FFFFFF   /* White */
--color-neutral-100: #F9FAFB   /* Lightest gray - backgrounds */
--color-neutral-200: #E5E7EB   /* Light borders */
--color-neutral-300: #D1D5DB   /* Input borders */
--color-neutral-400: #9CA3AF   /* Muted text */
--color-neutral-500: #6B7280   /* Secondary text */
--color-neutral-600: #4B5563   /* Body text */
--color-neutral-700: #374151   /* Headings */
--color-neutral-800: #1F2937   /* Primary text */
--color-neutral-900: #111827   /* Emphasis */
```

### Color Usage Guidelines

1. **Primary navy** for CTAs, headers, brand elements
2. **Blue accent** for secondary buttons, links, interactive elements
3. **Light blue** for hover backgrounds, selected states
4. **Semantic colors** only for their intended purpose (success, warning, error)
5. **Neutral scale** for text, borders, backgrounds

---

## 6. Spacing System

### Base Unit

The spacing system uses a **4px base unit** following an 8-point grid system.

### Spacing Scale

| Token | Value | Pixels |
|-------|-------|--------|
| `--space-1` | 0.25rem | 4px |
| `--space-2` | 0.5rem | 8px |
| `--space-3` | 0.75rem | 12px |
| `--space-4` | 1rem | 16px |
| `--space-5` | 1.25rem | 20px |
| `--space-6` | 1.5rem | 24px |
| `--space-8` | 2rem | 32px |
| `--space-10` | 2.5rem | 40px |
| `--space-12` | 3rem | 48px |
| `--space-16` | 4rem | 64px |
| `--space-20` | 5rem | 80px |

### Semantic Spacing

| Token | Maps To | Usage |
|-------|---------|-------|
| `--spacing-xs` | --space-1 (4px) | Icon margins, tight spacing |
| `--spacing-sm` | --space-2 (8px) | Button padding, list gaps |
| `--spacing-md` | --space-4 (16px) | Card padding, section gaps |
| `--spacing-lg` | --space-6 (24px) | Section margins, large gaps |
| `--spacing-xl` | --space-8 (32px) | Page sections, major divisions |

---

## 7. Component Library

### Buttons

#### Variants

| Class | Background | Text | Usage |
|-------|------------|------|-------|
| `.btn-primary` | Navy gradient | White | Primary actions |
| `.btn-secondary` | Blue | White | Secondary actions |
| `.btn-outline` | Transparent | Navy | Tertiary actions |
| `.btn-danger` | Red | White | Destructive actions |
| `.btn-lock` | Orange | White | Toggle/lock states |

#### Specifications

```css
Height: 40px (2.5rem) - minimum touch target
Padding: 8px 12px
Border Radius: 6px
Font: 14px, semibold (600)
Transition: 200ms ease
```

#### States

- **Default:** Base styling
- **Hover:** Slight lift (-1px translateY), increased shadow
- **Active/Pressed:** Darker shade, no lift
- **Disabled:** 60% opacity, cursor: not-allowed
- **Loading:** Spinner replaces text, pointer-events: none

### Cards

#### Standard Card

```html
<div class="card">
  <div class="card-header">Title</div>
  <div class="card-body">Content</div>
  <div class="card-footer">Actions</div>
</div>
```

**Specifications:**
- Background: White
- Border: 1px solid rgba(46, 76, 115, 0.08)
- Border Radius: 8px
- Shadow: 0 1px 3px rgba(0, 0, 0, 0.1)
- Hover: Lift + increased shadow

#### Stat Card

Used on dashboard for key metrics.

```html
<div class="stat-card">
  <div class="stat-number">42</div>
  <p class="stat-label">Active Events</p>
</div>
```

- Number: 3rem, bold, gradient text
- Label: Uppercase, letter-spacing 1px

### Modals

#### Structure

```html
<div class="modal" role="dialog" aria-modal="true">
  <div class="modal-overlay"></div>
  <div class="modal-container [--small|--medium|--large]">
    <div class="modal-header">
      <h2 class="modal-title">Title</h2>
      <button class="modal-close">×</button>
    </div>
    <div class="modal-body">Content</div>
    <div class="modal-footer">
      <button class="btn btn-secondary">Cancel</button>
      <button class="btn btn-primary">Confirm</button>
    </div>
  </div>
</div>
```

#### Sizes

| Size | Max Width | Usage |
|------|-----------|-------|
| Small | 400px | Confirmations, simple forms |
| Medium | 600px | Standard forms, content |
| Large | 800px | Complex forms, data tables |

#### Behavior

- Backdrop: Fade in 200ms, rgba(0,0,0,0.5)
- Container: Scale 0.95 → 1, fade in
- Focus trapped within modal
- Escape key closes modal
- Click outside closes modal (configurable)

### Tables

#### Standard Table

```html
<table class="event-table">
  <thead>
    <tr><th>Column</th></tr>
  </thead>
  <tbody>
    <tr><td>Data</td></tr>
  </tbody>
</table>
```

**Specifications:**
- Header: #F8F9FA background, 600 weight, 2px bottom border
- Cells: 12px padding
- Rows: Hover state with subtle background
- Mobile: Horizontal scroll with touch momentum

### Badges

```html
<span class="badge badge-success">Active</span>
<span class="badge badge-warning">Pending</span>
<span class="badge badge-danger">Error</span>
```

**Specifications:**
- Padding: 4px 8px
- Border Radius: 12px (pill shape)
- Font: 11-12px, bold
- Colors match semantic palette

---

## 8. Layout Patterns

### Page Structure

```
┌─────────────────────────────────────────────┐
│                   Header                      │
│  [Logo]  [Title]  [Nav Links]  [User Menu]   │
├─────────────────────────────────────────────┤
│                                               │
│               Main Content                    │
│  ┌─────────────────────────────────────┐     │
│  │          .container                  │     │
│  │  ┌─────────────────────────────┐    │     │
│  │  │     .main-content            │    │     │
│  │  │                              │    │     │
│  │  │   Page-specific content      │    │     │
│  │  │                              │    │     │
│  │  └─────────────────────────────┘    │     │
│  └─────────────────────────────────────┘     │
│                                               │
├─────────────────────────────────────────────┤
│                   Footer                      │
└─────────────────────────────────────────────┘
```

### Container Widths

| Container | Max Width | Usage |
|-----------|-----------|-------|
| `.container` | 100% (fluid) | Main wrapper |
| `.main-content` | Full width | Content area |
| Modal containers | 400-800px | Overlay content |

### Grid Systems

#### Stats Grid
```css
grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
gap: var(--spacing-md);
```

#### Employee Card Grid
```css
grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
gap: 20px;
```

#### Daily Preview Grid
```css
grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
gap: 15px;
```

---

## 9. Navigation System

### Header Navigation

**Structure:**
- Logo (left)
- Centered title
- Navigation links (horizontal)
- User section (right): Refresh, AI, Notifications, Profile

### Navigation Links

| Pattern | Usage |
|---------|-------|
| Direct Link | Single destination (Home, Printing) |
| Dropdown | Multiple related items (Scheduling, Team) |

**Dropdown Behavior:**
- Click to toggle on desktop
- Full-width slide panel on mobile
- Submenu items indented on mobile

### Mobile Navigation

- Hamburger menu toggle (44x44px touch target)
- Slide-out panel from left
- Full-height, 85% width (max 320px)
- Dark navy background matching header
- Overlay backdrop when open

### Breadcrumbs

Used on detail pages (e.g., Daily View):
```html
<nav aria-label="Breadcrumb navigation">
  <a href="/calendar" class="btn-back">
    <span>←</span> Back to Calendar
  </a>
</nav>
```

---

## 10. Accessibility Standards

### Compliance Level

**WCAG 2.1 Level AA**

### Key Features

| Feature | Implementation |
|---------|----------------|
| **Skip to Content** | `.skip-to-content` link at document start |
| **Focus Management** | Focus trap in modals, visible focus rings |
| **ARIA Attributes** | role, aria-modal, aria-label, aria-expanded |
| **Color Contrast** | 4.5:1 minimum for text |
| **Touch Targets** | 44x44px minimum on touch devices |
| **Screen Reader** | `.sr-only` class for visual-only content |
| **Reduced Motion** | `prefers-reduced-motion` media query respected |
| **Keyboard Navigation** | Tab order, Escape to close, Enter to submit |

### Focus Indicators

```css
:focus-visible {
  outline: 2px solid var(--secondary-color);
  outline-offset: 2px;
}
```

### Screen Reader Only Content

```css
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}
```

---

## 11. Responsive Design

### Breakpoints

| Breakpoint | Width | Target |
|------------|-------|--------|
| Desktop | 1024px+ | Default styles |
| Tablet | 768px - 1024px | Larger tablets, small laptops |
| Mobile | < 768px | Phones, small tablets |
| Small Mobile | < 480px | Very small screens |

### Approach

**Desktop-first** with progressive enhancement for touch:
- Base styles optimized for 1024px+ screens
- Tablet adjustments at 1024px
- Mobile adjustments at 768px

### Safe Area Insets

Support for notched devices (iPhone X+):
```css
:root {
  --safe-area-top: env(safe-area-inset-top, 0px);
  --safe-area-bottom: env(safe-area-inset-bottom, 0px);
  /* ... */
}
```

### Touch Optimizations

- Minimum 44x44px touch targets on touch devices
- `-webkit-tap-highlight-color` for touch feedback
- `touch-action: manipulation` to prevent delays
- 16px minimum font size for inputs (prevents iOS zoom)

### Landscape Mode

Special handling for landscape orientation with limited vertical space:
- Header logo hidden at < 600px height
- Compact spacing and font sizes
- Footer hidden at < 500px height

---

## 12. Animation & Motion

### Duration Scale

| Token | Duration | Usage |
|-------|----------|-------|
| `--transition-fast` | 150ms | Micro-interactions (hover states) |
| `--transition-base` | 200ms | Standard transitions (dropdowns) |
| `--transition-slow` | 300ms | Complex animations (modals, mobile menu) |

### Easing

- **Standard:** `ease` for most transitions
- **Decelerate:** `cubic-bezier(0.4, 0, 0.2, 1)` for entering elements

### Common Animations

| Animation | Duration | Easing | Usage |
|-----------|----------|--------|-------|
| Hover lift | 200ms | ease | Cards, buttons |
| Dropdown fade | 200ms | ease | Navigation menus |
| Modal scale | 200ms | ease | Modal appearance |
| Mobile menu slide | 300ms | ease | Navigation panel |

### Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## 13. Iconography

### Icon System

**Primary:** Material Symbols Outlined (Google Fonts)
```html
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined" />
```

**Usage:**
```html
<span class="material-symbols-outlined">lock_open</span>
```

### Emoji Icons

Emojis are used for navigation and decorative purposes:

| Context | Examples |
|---------|----------|
| Navigation | 🏠 Home, 📅 Scheduling, 👥 Team, 🖨️ Printing |
| User Menu | ❓ Help, ⚙️ Settings, 🚪 Logout |
| Status | ✨ AI Assistant |

**Note:** This is a design flaw - see UI/UX Flaws document for recommendation.

### Icon Sizing

| Context | Size |
|---------|------|
| Navigation icons | 1.2rem |
| Inline icons | 1em (matches text) |
| Stat icons | 1.5rem |
| Feature icons | 2-3rem |

---

## 14. Forms & Inputs

### Input Fields

```css
Height: 40px (2.5rem) - touch target
Padding: 8px 12px
Border: 1px solid #D1D5DB
Border Radius: 6px
Font Size: 16px (prevents iOS zoom)
```

### States

| State | Border | Background |
|-------|--------|------------|
| Default | #D1D5DB | White |
| Focus | Primary color | White |
| Valid | Success color | Light green tint |
| Invalid | Danger color | Light red tint |
| Disabled | #E5E7EB | #F9FAFB |

### Form Groups

```html
<div class="form-group">
  <label for="field">Label <span class="required-indicator">*</span></label>
  <input type="text" id="field" class="form-control">
  <div class="invalid-feedback">Error message</div>
</div>
```

### Validation

- Real-time validation with `ValidationEngine` module
- Visual feedback: border color + icon
- Error messages appear below field
- ARIA attributes for accessibility

### Checkboxes

- Minimum 18x18px checkbox size
- 44x44px touch target area
- Label clickable with proper `for` association

---

## 15. Feedback & Notifications

### Toast Notifications

**Module:** `toast-notifications.js`

| Type | Color | Icon | Auto-dismiss |
|------|-------|------|--------------|
| Success | Green | ✓ | 5 seconds |
| Error | Red | ✗ | Manual |
| Warning | Orange | ⚠ | 5 seconds |
| Info | Blue | ℹ | 5 seconds |

**Position:** Top-right (configurable)
**Behavior:**
- Queue multiple toasts
- Pause on hover
- Screen reader announcement

### Loading States

| Type | Usage |
|------|-------|
| Spinner | Inline loading, button loading |
| Progress bar | Long operations |
| Skeleton | Content placeholders |

### Empty States

```html
<div class="no-events">
  <div class="no-events-icon">📭</div>
  <h3>No events found</h3>
  <p>There are no events matching your criteria.</p>
  <button class="btn btn-primary">Create Event</button>
</div>
```

---

## Appendix A: CSS File Structure

```
app/static/css/
├── design-tokens.css          # Design system foundation
├── style.css                  # Global styles
├── modals.css                 # Modal system
├── form-validation.css        # Form feedback
├── loading-states.css         # Loading indicators
├── keyboard-shortcuts.css     # Keyboard shortcuts UI
├── responsive.css             # Responsive overrides
├── login.css                  # Login page
├── help.css                   # Help pages
├── validation.css             # Validation UI
├── components/
│   ├── modal.css
│   ├── schedule-modal.css
│   ├── notification-modal.css
│   └── ai-chat.css
└── pages/
    ├── daily-view.css
    ├── dashboard.css
    ├── workload-dashboard.css
    └── attendance-calendar.css
```

---

## Appendix B: JavaScript Module Structure

```
app/static/js/
├── utils/
│   ├── api-client.js          # HTTP client
│   ├── focus-trap.js          # Keyboard navigation
│   └── loading-state.js       # Loading UI
├── modules/
│   ├── state-manager.js       # App state persistence
│   ├── validation-engine.js   # Form validation
│   ├── toast-notifications.js # Toast system
│   └── aria-announcer.js      # Screen reader
├── components/
│   ├── modal.js               # Base modal class
│   ├── schedule-modal.js      # Scheduling forms
│   └── conflict-validator.js  # Real-time validation
└── pages/
    ├── daily-view.js          # Daily schedule
    └── dashboard.js           # Overview dashboard
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-04 | Claude | Initial documentation |
