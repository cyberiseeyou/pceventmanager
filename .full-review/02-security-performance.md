# Phase 2: Security & Performance Review

## Security Findings (21 total)

Full report: `docs/SECURITY_AUDIT_UI_UX.md` (783 lines)

### Critical (3)

| ID | Finding | CVSS | CWE | Impact |
|----|---------|------|-----|--------|
| SEC-C1 | **XSS via 161 inline onclick handlers** with Jinja2 template variable interpolation. Escape strategy (`\|replace("'", "\\'")`) is insufficient against payloads with double-quotes, HTML entities, or attribute-closing sequences. | 8.1 | CWE-79 | Full XSS if attacker controls event data (e.g., via API sync) |
| SEC-C2 | **XSS via 195 innerHTML assignments** without consistent sanitization. `escapeHtml()` exists in 13 files but is not used consistently. Many innerHTML assignments inject server/API data directly. | 7.5 | CWE-79 | Secondary XSS through re-injection |
| SEC-C3 | **Plaintext credentials in `.env.test`** -- contains Redis password (`Redneck2013`), settings encryption key, and Walmart user ID. File is untracked but not in `.gitignore`. | 7.5 | CWE-798 | Credential exposure |

### High (6)

| ID | Finding | File | Impact |
|----|---------|------|--------|
| SEC-H1 | **Security headers never applied** -- `SECURITY_HEADERS` dict defined in `config.py` (HSTS, X-Content-Type-Options, X-Frame-Options, CSP) but NO `after_request` hook in `__init__.py` to apply them | `config.py`, `__init__.py` | All security headers missing from responses |
| SEC-H2 | **CSP allows `unsafe-inline`** -- Even if headers were applied, the CSP policy (`script-src 'self' 'unsafe-inline'`) permits all inline script execution, negating XSS protection | `config.py:159` | CSP provides no XSS protection |
| SEC-H3 | **Broken CSRF in ai-assistant.js** -- Reads token from `data-csrf` attribute that doesn't exist on any DOM element. AI assistant API calls have zero CSRF protection. | `ai-assistant.js` | CSRF bypass for AI features |
| SEC-H4 | **CSRF cookie without Secure flag** -- `httponly=False` (intentional for JS access) but `secure` defaults to `False` | `__init__.py:323` | CSRF token exposed over HTTP |
| SEC-H5 | **External CDN resources without SRI** -- Bootstrap, Font Awesome loaded from CDN without integrity checks on some pages | Dashboard templates | Supply chain attack vector |
| SEC-H6 | **Dual CSRF header names** -- `csrf_helper.js` uses `X-CSRF-Token`, `api-client.js` uses `X-CSRFToken`. Server must accept both or one silently fails. | `csrf_helper.js`, `api-client.js` | Silent CSRF validation failure |

### Medium (8)

| ID | Finding | Impact |
|----|---------|--------|
| SEC-M1 | `document.write()` XSS (12 hits) | DOM manipulation vulnerability |
| SEC-M2 | Raw fetch() without timeout on 3 highest-traffic pages | Indefinite request hang |
| SEC-M3 | ES module race condition -- globals may be undefined | Silent functionality failure |
| SEC-M4 | Keyboard shortcuts fire during text input (no input focus check) | Unintended actions during typing |
| SEC-M5 | Clickjacking potential -- X-Frame-Options defined but not applied | Page embeddable in iframe |
| SEC-M6 | Open redirect risk in login flow | Redirect to attacker-controlled URL |
| SEC-M7 | External image/resource loads without validation | Information leakage |
| SEC-M8 | Weak default SECRET_KEY in development | Session forgery in dev |

### Low (4)

| ID | Finding | Impact |
|----|---------|--------|
| SEC-L1 | Session heartbeat without rate limiting | DoS amplification |
| SEC-L2 | jQuery 3.6.0 known vulnerabilities | Known CVEs |
| SEC-L3 | Auto-refresh without user control | UX/data loss |
| SEC-L4 | Single `\|safe` filter in `modal_base.html` | Contained XSS risk |

### Positive Security Observations
- Jinja2 auto-escaping enabled (no `{% autoescape false %}`)
- No `eval()` or string-based `setTimeout()`
- No `postMessage` handlers or prototype pollution patterns
- `ai-chat.js` correctly implements HTML escaping before markdown rendering
- `validation-engine.js` well-structured with no innerHTML usage
- Session management includes activity tracking, heartbeat, and timeout
- SRI hashes present on `daily_validation.html` CDN resources

---

## Performance Findings (23 total)

Full report: `.full-review/02-performance-scalability.md`

### Critical (4)

| ID | Finding | Impact |
|----|---------|--------|
| PERF-C1 | **8+ render-blocking CSS files** delivered individually with no bundling/minification (114KB base CSS). Adds 400-800ms to FCP. | +400-800ms FCP |
| PERF-C2 | **ES module/global script race condition** -- `type="module"` deferred by spec but consumed by sync `<script>` tags, creating silent failures | Silent functionality breakdown |
| PERF-C3 | **`* { transition: all 0.3s }` wildcard rule** in `daily_validation.html` -- animates every CSS property change on every element. Dashboard has setInterval(1s) timer causing continuous reflows. | Continuous layout thrashing |
| PERF-C4 | **45 `location.reload()` calls** as primary state update mechanism. Each reload re-downloads 633KB JS + 299KB CSS. | Full re-download after every action |

### High (9)

| ID | Finding | Impact |
|----|---------|--------|
| PERF-H1 | 633KB unminified JS across 37 files, no bundling | +1-2s load on 3G |
| PERF-H2 | 299KB unminified CSS across 23 files, no bundling | +500ms load |
| PERF-H3 | ~188KB (5,480 lines) uncacheable inline JS in templates | No browser caching |
| PERF-H4 | ~98KB (2,958 lines) uncacheable inline CSS in templates | No browser caching |
| PERF-H5 | `daily-view.js` is 160KB single file -- no code splitting | Long parse/compile |
| PERF-H6 | Dashboard pages load Bootstrap 4.6 + Font Awesome (~100KB extra CSS) | Redundant framework download |
| PERF-H7 | No cache busting mechanism -- `url_for('static')` with no hash/version | Stale assets after deploy |
| PERF-H8 | 14+ JS + 8+ CSS = 22+ HTTP requests per page before page-specific assets | Connection saturation |
| PERF-H9 | CacheManager exists but is never used in any page/component | Missed optimization |

### Medium (6)

| ID | Finding | Impact |
|----|---------|--------|
| PERF-M1 | Google Fonts loaded without `display=swap` for icon font | FOIT for icons |
| PERF-M2 | No `<link rel="preconnect">` for Google Fonts CDN | Extra DNS/TLS time |
| PERF-M3 | No lazy loading for below-fold content | Unnecessary initial work |
| PERF-M4 | Large DOM on dashboard pages (hundreds of nodes from inline templates) | Slow selectors |
| PERF-M5 | `daily_validation.html` 1s setInterval timer + wildcard transition = continuous reflow | CPU burn |
| PERF-M6 | No `async`/`defer` on sync script tags | Parser blocking |

### Low (4)

| ID | Finding | Impact |
|----|---------|--------|
| PERF-L1 | Print schedule generates full HTML doc via template literal | Uncacheable print view |
| PERF-L2 | Responsive breakpoints duplicated in style.css + responsive.css | Extra CSS weight |
| PERF-L3 | `formatTime()` duplicated in 5 files instead of shared utility | Code bloat |
| PERF-L4 | No HTTP/2 push or resource hints | Missed optimization |

### Key Performance Metrics

| Metric | Value |
|--------|-------|
| Total unminified JS | 633KB across 37 files |
| Total unminified CSS | 299KB across 23 files |
| Uncacheable inline JS | ~188KB (5,480 lines) |
| Uncacheable inline CSS | ~98KB (2,958 lines) |
| location.reload() calls | 45 across 20 files |
| Largest single JS file | daily-view.js at 160KB |
| Largest template | approved_events.html at 73KB |
| Base page HTTP requests | 22+ before page-specific assets |

---

## Critical Issues for Phase 3 Context

### Testing implications
1. **SEC-C1 & SEC-C2**: XSS vulnerabilities need security test cases -- test that event names with special characters are properly escaped
2. **SEC-H1**: Need test to verify security headers are present on responses
3. **SEC-H3**: Need test for AI assistant CSRF token retrieval
4. **PERF-C2**: Need test for module loading race condition
5. **PERF-C4**: Test that DOM updates work correctly without full page reload

### Documentation implications
1. **SEC-C3**: Document `.env.test` handling and credential management
2. **SEC-H6**: Document canonical CSRF header name
3. **PERF-C1**: Document build pipeline requirements
4. **PERF-H7**: Document cache busting strategy
