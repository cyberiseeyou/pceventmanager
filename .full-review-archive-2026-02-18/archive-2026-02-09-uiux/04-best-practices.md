# Phase 4: Best Practices & Standards

## Best Practices & Standards Review

Full report: `.full-review/04a-best-practices-standards.md`

### Finding Summary: 5 Critical, 8 High, 10 Medium, 6 Low, 10 Positive

### Critical (5)

| ID | Finding | Standard Violated | Impact |
|----|---------|-------------------|--------|
| BP-C1 | **Three competing modal implementations** with inconsistent a11y (Jinja2 macro, JS component, inline dashboard HTML + 2 inline modals in base.html) | WCAG 4.1.2 | Screen reader/keyboard users get different behavior per page |
| BP-C2 | **262 native alert()/confirm() calls** despite shipping ToastManager and Modal components | WCAG 4.1.3 | Main thread blocked, unstyled, inaccessible |
| BP-C3 | **161 inline onclick handlers** across 23 templates | Separation of concerns, CSP | XSS vectors, prevents CSP enforcement |
| BP-C4 | **380 inline style attributes** across 35 templates (base.html has 22) | Design system adoption | Design tokens entirely bypassed |
| BP-C5 | **Zero `<fieldset>` elements** in all 48 templates | WCAG 1.3.1 | Checkbox/radio groups have no programmatic grouping |

### High (8)

| ID | Finding | Impact |
|----|---------|--------|
| BP-H1 | Duplicate FocusTrap implementations (utils/ vs modules/) | Inconsistent keyboard behavior |
| BP-H2 | Duplicate ScreenReader Announcer (utils/ vs modules/) | Potential duplicate announcements |
| BP-H3 | 846 hardcoded hex colors in CSS despite token system | Design tokens bypassed in 40% of CSS |
| BP-H4 | Duplicate CSS rules in style.css with conflicting values | `.event-type-core` green in first def, red in second |
| BP-H5 | Dashboard loads external frameworks (Font Awesome, Bootstrap classes without Bootstrap) | Visual inconsistency, extra payload |
| BP-H6 | No semantic HTML landmarks on most pages (only 17/48 templates) | Screen reader navigation broken |
| BP-H7 | ES module/global script race condition in base.html | Future runtime errors if globals referenced early |
| BP-H8 | 150 innerHTML assignments in JS without sanitization | XSS vectors in 20 files |

### Key Metrics

| Metric | Value | Assessment |
|--------|-------|------------|
| Inline `style` attributes | 380 across 35 templates | Poor |
| Inline `onclick` handlers | 161 across 23 templates | Poor |
| `alert()`/`confirm()` calls | 262 across 21 files | Poor |
| Hardcoded hex colors in CSS | 846 across 20 files | Poor |
| `var()` token references | 1,783 across 21 files | Good (where adopted) |
| ARIA attributes | 120 across 14 templates | Moderate |
| Semantic landmarks | 64 across 17 templates | Low |
| `<fieldset>` elements | 0 | Critical gap |
| `window.*` assignments | 182 across 28 files | High pollution |

### Positive Findings (10)
1. Comprehensive design token system (246 lines, well-documented)
2. Skip-to-content link and keyboard navigation infrastructure
3. Reduced motion + high contrast media query support
4. 44x44px touch targets, iOS zoom prevention, safe area insets
5. Proper ARIA on navigation (aria-haspopup, aria-expanded, hidden)
6. Well-designed modal_base.html Jinja2 macro
7. API client with timeout, retry, CSRF, offline detection
8. Comprehensive responsive breakpoints (6 breakpoints + landscape)
9. Accessible toast notification system (aria-live regions)
10. Strong login form accessibility (labels, autocomplete, aria-describedby)

---

## DevOps & Tooling Review

Full report: `.full-review/04b-devops-tooling.md`

### Finding Summary: 3 Critical, 4 High, 6 Medium, 4 Low

### Critical (3)

| ID | Finding | Impact |
|----|---------|--------|
| DT-C1 | **Zero frontend build pipeline** -- no bundler, minifier, preprocessor. 708KB JS + 400KB CSS served raw | 1MB+ per page load, 17+ HTTP requests |
| DT-C2 | **No cache busting** with 1-year immutable cache headers in nginx. Users get stale JS/CSS after every deploy | Silent data corruption from stale code |
| DT-C3 | **No CI quality gates** -- both GitHub Actions workflows only run Claude AI review. pytest never runs in CI | Regressions merge silently |

### High (4)

| ID | Finding | Impact |
|----|---------|--------|
| DT-H1 | No JavaScript testing framework (no Jest, Vitest, Cypress, Playwright) | 14,117 lines of untested frontend code |
| DT-H2 | No JS/CSS linting (no ESLint, Prettier, Stylelint) | 250 console.log, only 2/37 files use strict |
| DT-H3 | No pre-commit hooks (no husky, no .pre-commit-config.yaml) | No automated quality checks |
| DT-H4 | No Python linting or type checking (no ruff, flake8, mypy) | Backend quality relies on manual review |

### Current Tooling State

| Category | Status |
|----------|--------|
| JS Bundler | Not present |
| CSS Preprocessor | Not present |
| JS/CSS Minification | Not present |
| Asset Fingerprinting | Not present |
| JS Linter (ESLint) | Not present |
| CSS Linter (Stylelint) | Not present |
| Code Formatter | Not present |
| Pre-commit Hooks | Not present |
| JS Test Framework | Not present |
| Python Linter | Not present |
| CI Test Runner | Not present |
| CI Quality Gates | Not present |
| Dependency Scanning | Not present |
| Error Monitoring | Not present |
| Live Reload (dev) | Not present |

### Recommended Pipeline

| Phase | Action | Timeframe |
|-------|--------|-----------|
| 1 | Add Vite bundler + ESLint + Prettier + ruff + pre-commit hooks | 1-2 days |
| 2 | Add CI workflow (pytest, lint, build) + cache busting + .dockerignore | 3-5 days |
| 3 | Add Vitest for JS unit tests + Playwright for E2E | 1-2 weeks |
| 4 | Error monitoring, dependency scanning, nginx consolidation | Ongoing |

### Estimated Performance Impact

| Metric | Current | After Pipeline |
|--------|---------|---------------|
| JS payload | ~708KB raw | ~150-200KB minified+gzipped |
| CSS payload | ~400KB raw | ~80-100KB minified+gzipped |
| HTTP requests (base) | 17+ | 4-5 |
| Time to interactive (3G) | ~3-5s | ~1-2s |
