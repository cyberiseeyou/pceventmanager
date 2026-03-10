# Mobile Optimization Audit Report

> Phase 1 Reconnaissance - Generated 2026-03-09
> App was not running during audit, so Playwright viewport testing is deferred.

---

## Quick Summary

| Check | Status | Notes |
|-------|--------|-------|
| Viewport meta tag | PASS | Proper `width=device-width, initial-scale=1.0, viewport-fit=cover` |
| apple-mobile-web-app meta tags | PASS | `capable`, `status-bar-style` present |
| theme-color meta tag | FAIL | Missing entirely |
| manifest.json | FAIL | Does not exist |
| Service worker | FAIL | Does not exist, no registration code |
| Responsive CSS framework | PASS | Custom design system with breakpoints at 768px, 1024px |
| Safe area insets (notch support) | PASS | `env(safe-area-inset-*)` implemented |
| Touch target sizing (48px+) | PARTIAL | Global rules exist but several elements fall below 44px |
| CSS framework consistency | FAIL | Mix of Bootstrap 4.6.2 and 5.1.3 in some templates |
| Mobile-first CSS approach | FAIL | Desktop-first with mobile overrides |
| Offline fallback page | FAIL | Does not exist |
| PWA icons (192x192, 512x512) | FAIL | Only small favicons (16, 32, 48px) |

---

## 1. Template Responsiveness Assessment

### CRITICAL (4 templates) — Broken on 360px screens

| Template | Issues |
|----------|--------|
| `employee_analytics.html` | Hardcoded inline styles, non-responsive data table, no mobile stacking |
| `printing.html` | Bootstrap 5 col-md-6 patterns, hardcoded max-width 1200px, tables without responsive wrappers |
| `settings.html` | Form sections stack poorly, select boxes not mobile-optimized, hardcoded padding |
| `calendar.html` | 7-column grid won't fit 360px, hardcoded min-height 140px on cells |

### NEEDS WORK (43 templates) — Desktop-first, no explicit mobile layout

| Category | Templates | Common Issues |
|----------|-----------|---------------|
| Dashboard | `command_center`, `daily_validation`, `weekly_validation`, `fix_wizard`, `approved_events`, `employee_availability`, `available_blocks`, `scan_out_checklist` | Flex layouts without wrapping, hardcoded max-widths, Bootstrap 4 in validation pages |
| Scheduling | `schedule`, `daily_view`, `auto_scheduler_main`, `auto_schedule_review`, `scheduler_history`, `schedule_verification` | Modal widths not responsive, sticky toolbars consuming screen space |
| Events | `unscheduled`, `unreported_events`, `lost_demos`, `event_times` | Tables not horizontally scrollable, filter bars with min-width constraints |
| Employees | `employees`, `employees/add`, `employees/import_selection`, `time_off_requests` | 2-column grids with no mobile breakpoint, min-width 200px inputs |
| Reports | `attendance`, `employee_schedules`, `employee_workload`, `event_statistics`, `event_type_breakdown`, `scheduling_coverage`, `time_off` | Fixed-width tables, date range forms not wrapping, Bootstrap 4 |
| Inventory | `inventory/index`, `inventory/orders`, `inventory/order_detail` | Bootstrap 5 column layouts don't stack, modals not mobile-optimized |
| Other | `rotations`, `shift_blocks`, `api_tester`, `workload_dashboard` | Grid minmax constraints too wide, form layouts not responsive |

### GOOD (16 templates) — Already responsive or minimal layout

| Template | Notes |
|----------|-------|
| `base.html` | Proper viewport meta, CSS variables, hamburger menu |
| `login.html` | Standalone responsive form |
| `auth/loading.html` | Simple loading state, responsive |
| `attendance.html` | Calendar grid responsive, flex-wrap on legend |
| `index.html` | Responsive stat-grid and dashboard sections |
| `reports/index.html` | Grid-based report cards with gap |
| `sync_admin.html` | CSS variables, auto-fit grid |
| All `help/*.html` (10 files) | Text-heavy content, inherits base responsive styles |
| All `components/*.html` (5 files) | Included fragments, not standalone |

---

## 2. CSS Framework Analysis

### Base Template: Custom CSS (No Bootstrap)
The app uses a custom design system built on CSS custom properties:
- `design-tokens.css` — spacing, colors, typography variables
- `style.css` — component styles
- `responsive.css` — breakpoints and mobile overrides
- Page-specific CSS in `static/css/pages/`

### Bootstrap Conflicts (Version Mismatch)

| Template | Bootstrap Version | Issue |
|----------|------------------|-------|
| `dashboard/daily_validation.html` | 4.6.2 | Deprecated version, jQuery dependency |
| `dashboard/weekly_validation.html` | 4.6.2 | Same as above |
| `inventory/index.html` | 5.1.3 | Overrides custom modal styles |
| `inventory/orders.html` | 5.1.3 | Same |
| `inventory/order_detail.html` | 5.1.3 | Same |
| `printing.html` | 5.1.3 | Conflicts with custom form styles |

**Recommendation:** Standardize all templates to either Bootstrap 5.3+ or fully commit to the custom CSS design system. Mixing frameworks creates unpredictable mobile behavior.

---

## 3. Hardcoded Width Issues

### CSS Files with Width Problems

| File | Line | Issue |
|------|------|-------|
| `css/components/ai-chat.css` | 10 | `.ai-chat-widget { width: 380px }` — exceeds 360px viewport |
| `css/pages/employees.css` | 9 | `grid minmax(350px, 1fr)` — breaks on 375px screens |
| `css/pages/daily-view.css` | 448 | `.daily-view-role-selector { min-width: 150px }` |
| `css/pages/daily-view.css` | 1333 | `.time-slot-actions { min-width: 200px }` |
| `css/pages/attendance-calendar.css` | 64 | `.employee-selector { min-width: 200px }` |
| `css/pages/attendance-calendar.css` | 92 | `.current-month { min-width: 200px }` |
| `css/pages/reports.css` | 48 | `.stat-card { min-width: 150px }` |
| `css/pages/index.css` | 601 | `.verification-date-group { min-width: 200px }` |
| `css/style.css` | 256 | `.nav-dropdown-menu { min-width: 200px }` |
| `css/style.css` | 387 | `.user-dropdown-menu { min-width: 200px }` |

### Templates with Inline Style Issues

| Template | Issue |
|----------|-------|
| `employee_analytics.html` | `width: 100%` with `padding: 20px` inline, table not responsive |
| `employees/add.html` | `grid: 1fr 1fr` (2 columns) with no mobile breakpoint, `max-width: 800px` |
| `schedule_verification.html` | `max-width: 1200px`, `max-width: 300px` on form groups |
| `command_center.html` | `max-width: 1400px` hardcoded |

---

## 4. Touch Target Audit

### Passing (Global Rules)
`responsive.css` defines good touch rules via `@media (hover: none) and (pointer: coarse)`:
- Form inputs: `min-height: 48px`, `font-size: 16px`
- Modal buttons: `100% width`, `min-height: 48px`
- Links: `min-height: 44px`, `padding: 12px`

### Failing Elements

| File | Line | Element | Size | Required |
|------|------|---------|------|----------|
| `responsive.css` | 307 | `.nav-arrow` | `padding: 4px` | 44px+ |
| `responsive.css` | 663 | `.calendar-day` | `padding: 4px` | 44px+ |
| `responsive.css` | 783 | `.hamburger-menu` | `36x36px` | 44px+ |
| `pages/employees.css` | 291 | Checkboxes | `18x18px` | 44px+ |
| `components/modal.css` | 548 | `.form-help` | `font-size: 12px` | 14px+ |
| `pages/employees.css` | 104 | `.day-cell` | `font-size: 11px` | 14px+ |
| `pages/attendance-calendar.css` | 364 | `.calendar-day-no-data` | `font-size: 11px` | 14px+ |

---

## 5. PWA Readiness

| Requirement | Status | Action Needed |
|-------------|--------|---------------|
| `manifest.json` | MISSING | Create with app name, icons, theme, display: standalone |
| Service worker | MISSING | Create with cache-first for static assets |
| SW registration | MISSING | Add to base.html |
| `<link rel="manifest">` | MISSING | Add to base.html `<head>` |
| `<meta name="theme-color">` | MISSING | Add to base.html (Sam's Club blue `#0067a0`) |
| `<link rel="apple-touch-icon">` | MISSING | Generate 180x180 icon |
| PWA icons (192, 512) | MISSING | Generate from logo |
| Offline fallback | MISSING | Create `offline.html` |
| HTTPS | PASS | Cloudflare tunnel provides this |
| Viewport meta | PASS | Already configured correctly |
| Mobile-web-app-capable | PASS | Already set |

---

## 6. Font Size Violations (< 14px)

15+ instances across CSS files where font sizes fall below the WCAG-recommended 14px minimum for body text:

| File | Count | Examples |
|------|-------|----------|
| `pages/employees.css` | 4 | 11px day cells, 12px IDs and labels |
| `pages/attendance-calendar.css` | 3 | 11-12px calendar labels |
| `components/modal.css` | 3 | 12-13px help text and roles |
| `components/ai-chat.css` | 2 | 11-12px status and meta text |
| `pages/daily-view.css` | 3+ | Various small labels |

---

## 7. Recommended Conversion Priority

Based on the requirements review (Tier 1 = must be perfect on mobile):

### Phase 2A: Foundation (do first)
1. `base.html` — bottom nav bar, standardize responsive foundation
2. `responsive.css` — fix touch target violations, add 360px breakpoint

### Phase 2B: Tier 1 Pages (daily use)
3. `daily_view.html` — daily schedule, most-used page
4. `dashboard/command_center.html` — morning command center
5. `dashboard/daily_validation.html` — remove Bootstrap 4, use custom CSS
6. `dashboard/scan_out_checklist.html` — end-of-day workflow

### Phase 2C: Tier 2 Pages (frequent use)
7. `unscheduled.html` — event browsing and assignment
8. `schedule.html` — event scheduling form
9. `calendar.html` — fix 7-column grid for mobile
10. `attendance.html` — already responsive, minor fixes
11. `employees.html` — fix min-width constraints

### Phase 2D: Tier 3 Pages (weekly use)
12. `auto_scheduler_main.html` + `auto_schedule_review.html`
13. `reports/*.html` — standardize on custom CSS, remove Bootstrap 4
14. `printing.html` — standardize on custom CSS, remove Bootstrap 5
15. `inventory/*.html` — standardize on custom CSS, remove Bootstrap 5
16. `settings.html` — fix form layout
17. `employee_analytics.html` — rewrite inline styles

### Phase 3: PWA Layer
18. Create `manifest.json`
19. Create service worker
20. Add offline fallback
21. Generate PWA icons

---

## 8. Playwright Viewport Testing

**Status: DEFERRED** — App was not running during audit.

**Test plan for when app is running:**
1. Navigate to login page at 360x640 (budget Android)
2. Navigate to daily view at 375x667 (iPhone SE)
3. Navigate to command center at 390x844 (iPhone 14)
4. Check for horizontal overflow on all Tier 1 pages
5. Verify touch targets meet 44px minimum
6. Test bottom nav bar interaction
7. Verify no content is clipped or hidden

**To run:** Start the app with `python app.py` or `flask run`, then re-run this audit.
