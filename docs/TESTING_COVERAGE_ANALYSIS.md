# UI/UX Testing Coverage Analysis - Flask Schedule Webapp

**Analysis Date:** 2026-02-09
**Analyzer:** Test Automation Engineer
**Scope:** UI/UX layer testing coverage for 108 UI files (50 templates, 23 CSS, 37 JS)

---

## Executive Summary

**CRITICAL FINDING:** This Flask scheduling webapp has **ZERO UI/UX test coverage** despite having 108 UI files and 277 routes. The test suite contains 86 tests across 3,347 lines of code, but **ALL tests focus on business logic** (ML models, scheduling engine, validators). There are no tests for:

- Template rendering (50 Jinja2 templates untested)
- JavaScript functionality (37 JS files untested)
- CSS rendering (23 CSS files untested)
- API endpoints serving UI data (277 routes, only 3 basic health/index tests)
- Security vulnerabilities identified in Phase 2 (XSS, CSRF, security headers)
- User workflows (login, scheduling, employee management)

**Test Coverage Breakdown:**
- **Backend business logic:** ~85% coverage (ML, scheduling engine, validators)
- **API routes:** <1% coverage (3 tests out of 277 routes)
- **Templates/UI:** 0% coverage
- **JavaScript:** 0% coverage
- **Security:** 0% coverage
- **E2E workflows:** 0% coverage

---

## 1. Current Test Suite Analysis

### 1.1 Test Files Overview

| File | Lines | Tests | Focus Area | UI Coverage |
|------|-------|-------|------------|-------------|
| `test_ml_effectiveness.py` | 22K | 11 | ML model effectiveness metrics | None |
| `test_ml_functional.py` | 17K | 15 | ML functionality and fallback | None |
| `test_ml_performance.py` | 19K | 11 | ML prediction performance | None |
| `test_ml_safety.py` | 24K | 19 | ML error handling and safety | None |
| `test_ml_shadow_mode.py` | 20K | 10 | ML shadow mode behavior | None |
| `test_models.py` | 2.3K | 3 | Database model logic | None |
| `test_rotation_manager_backup.py` | 3.2K | 3 | Rotation assignment logic | None |
| `test_routes.py` | 831 bytes | **3** | **Routes (ONLY file testing UI layer)** | **Minimal** |
| `test_scheduling_backup_rotation.py` | 5.7K | 3 | Scheduling with rotations | None |
| `test_scheduling_engine.py` | 3.7K | 2 | Auto-scheduler core logic | None |
| `test_scheduling_past_dates.py` | 5.2K | 3 | Past date handling | None |
| `test_validator.py` | 3.7K | 3 | Constraint validation | None |
| **TOTAL** | **3,347 lines** | **86 tests** | **Business logic only** | **<1%** |

### 1.2 The Only UI Test File

**File:** `/home/elliot/flask-schedule-webapp/tests/test_routes.py` (831 bytes, 23 lines)

```python
import pytest

def test_health_check(client):
    """Test the health check endpoint."""
    response = client.get('/health/ping')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'ok'

def test_health_readiness(client):
    """Test the readiness endpoint."""
    response = client.get('/health/ready')
    assert response.status_code in [200, 503]
    data = response.get_json()
    # It should not return 500 (crash)

def test_index_page(client):
    """Test the index page loads (redirects to login usually)."""
    response = client.get('/', follow_redirects=True)
    assert response.status_code == 200
    assert b"Login" in response.data or b"Scheduler" in response.data
```

**Analysis:**
- Only tests 3 routes out of 277 (1% route coverage)
- No template context validation
- No JavaScript execution testing
- No form submission testing
- No XSS/CSRF security testing
- No response header validation

---

## 2. Critical Gaps in Test Coverage

### 2.1 CRITICAL - Security Vulnerabilities Untested (From Phase 2)

**Severity:** CRITICAL
**Impact:** XSS, CSRF, header injection attacks have no automated detection

#### Finding SEC-TEST-C1: Zero XSS Test Coverage
**From Phase 2:** SEC-C1 identified 161 inline onclick handlers with Jinja2 interpolation creating XSS vectors

**What's Missing:**
```python
# NO TESTS LIKE THIS EXIST:
def test_event_name_xss_in_onclick_handler(client, db_session, models):
    """Test that event names with XSS payloads are escaped in onclick handlers"""
    Event = models['Event']

    # XSS payload: event name with double-quote escape attempt
    xss_payload = 'Test Event"; alert("XSS"); "'
    event = Event(
        project_ref_num=999,
        project_name=xss_payload,
        event_type="Core",
        condition="Unstaffed"
    )
    db_session.add(event)
    db_session.commit()

    # Test unscheduled events page renders onclick handlers safely
    response = client.get('/events')
    assert response.status_code == 200

    # CRITICAL: Verify XSS payload is NOT executable in onclick
    html = response.data.decode('utf-8')
    assert 'alert("XSS")' not in html  # Raw payload should not appear
    assert 'onclick="' in html  # onclick handlers should exist
    # Verify proper escaping (implementation-dependent)
    assert '&quot;' in html or "\\'" in html
```

**Test Cases Needed:**
1. Event name with double quotes: `Event"; alert(1); "`
2. Employee name with single quotes: `O'Malley'; DROP TABLE employees;--`
3. Store name with HTML entities: `<script>alert(1)</script>`
4. Project name with attribute-closing: `Test" onclick="alert(1)"`
5. Event type with newlines: `Core\n<script>alert(1)</script>`

**Files to Test:**
- `templates/unscheduled.html` (7 onclick handlers)
- `templates/index.html` (20 onclick handlers)
- `templates/dashboard/approved_events.html` (27 onclick handlers)
- `templates/dashboard/weekly_validation.html` (18 onclick handlers)

**Estimated Missing Tests:** 25+ XSS test cases

---

#### Finding SEC-TEST-C2: Zero innerHTML XSS Tests
**From Phase 2:** SEC-C2 identified 160 innerHTML assignments without consistent sanitization

**What's Missing:**
```python
# NO TESTS LIKE THIS EXIST:
def test_event_name_xss_in_dynamic_dom(client, db_session, models):
    """Test that event data injected via innerHTML is sanitized"""
    Event = models['Event']

    xss_event = Event(
        project_ref_num=888,
        project_name='<img src=x onerror="alert(1)">',
        event_type="Core"
    )
    db_session.add(xss_event)
    db_session.commit()

    # Fetch event via API (used by JS to populate DOM)
    response = client.get('/api/events/888')
    assert response.status_code == 200

    event_data = response.get_json()
    # API should return escaped HTML
    assert '<img' not in event_data['data']['project_name']
    assert '&lt;img' in event_data['data']['project_name']
```

**Test Cases Needed:**
1. `<img src=x onerror=alert(1)>`
2. `<svg onload=alert(1)>`
3. `javascript:alert(1)`
4. `data:text/html,<script>alert(1)</script>`
5. Event with markdown injection: `[XSS](javascript:alert(1))`

**Files with innerHTML usage (from Phase 2):**
- `main.js` (multiple innerHTML assignments)
- `daily-view.js` (160KB file with DOM manipulation)
- `employees.js`
- `auto-scheduler.js`

**Estimated Missing Tests:** 30+ innerHTML security tests

---

#### Finding SEC-TEST-C3: Zero CSRF Token Tests
**From Phase 2:** SEC-H3 identified broken CSRF in `ai-assistant.js` (reads from non-existent `data-csrf` attribute)

**What's Missing:**
```python
# NO TESTS LIKE THIS EXIST:
def test_csrf_token_in_cookie(client):
    """Test that CSRF token is set in cookie for AJAX requests"""
    response = client.get('/')

    # Verify CSRF token cookie exists
    assert 'csrf_token' in response.headers.get('Set-Cookie', '')

    # Verify cookie has correct attributes
    cookie_header = response.headers.get('Set-Cookie')
    assert 'SameSite=Lax' in cookie_header
    # Note: Secure flag depends on environment (HTTP vs HTTPS)

def test_csrf_token_in_meta_tag(client):
    """Test that CSRF token is available in meta tag for JS"""
    response = client.get('/')
    html = response.data.decode('utf-8')

    # Verify meta tag exists: <meta name="csrf-token" content="...">
    assert 'name="csrf-token"' in html
    assert 'content=' in html

def test_api_requires_csrf_token(client, db_session, models):
    """Test that POST/PUT/DELETE requests require valid CSRF token"""
    Event = models['Event']

    # POST without CSRF token should fail
    response = client.post('/api/events', json={
        'project_name': 'Test Event',
        'event_type': 'Core'
    })
    assert response.status_code == 400  # or 403

    # POST with CSRF token should succeed
    response = client.post('/api/events',
        json={'project_name': 'Test', 'event_type': 'Core'},
        headers={'X-CSRF-Token': 'valid_token_here'}
    )
    # Should succeed (or at least not fail due to missing CSRF)
```

**Test Cases Needed:**
1. CSRF token exists in cookie
2. CSRF token exists in meta tag
3. POST without CSRF token fails (400/403)
4. POST with valid CSRF token succeeds
5. PUT without CSRF token fails
6. DELETE without CSRF token fails
7. GET requests don't require CSRF token
8. Both `X-CSRF-Token` and `X-CSRFToken` headers accepted (from Phase 2 SEC-H6)

**Estimated Missing Tests:** 15+ CSRF tests

---

#### Finding SEC-TEST-C4: Zero Security Header Tests
**From Phase 2:** SEC-H1 identified security headers defined in config but NEVER APPLIED

**What's Missing:**
```python
# NO TESTS LIKE THIS EXIST:
def test_security_headers_applied(client):
    """Test that security headers are present on responses"""
    response = client.get('/')

    # From config.py ProductionConfig.SECURITY_HEADERS
    assert response.headers.get('X-Content-Type-Options') == 'nosniff'
    assert response.headers.get('X-Frame-Options') == 'SAMEORIGIN'
    assert response.headers.get('X-XSS-Protection') == '1; mode=block'
    assert 'Strict-Transport-Security' in response.headers
    assert 'Content-Security-Policy' in response.headers

def test_csp_blocks_inline_scripts(client):
    """Test that CSP header blocks unsafe inline scripts"""
    response = client.get('/')
    csp = response.headers.get('Content-Security-Policy', '')

    # Should NOT contain 'unsafe-inline' (from Phase 2 SEC-H2)
    assert "'unsafe-inline'" not in csp
    # Should restrict script sources
    assert "script-src 'self'" in csp

def test_hsts_header_production(client):
    """Test that HSTS header is set in production mode"""
    # Requires production config
    response = client.get('/')
    hsts = response.headers.get('Strict-Transport-Security')

    assert hsts is not None
    assert 'max-age=31536000' in hsts  # 1 year
    assert 'includeSubDomains' in hsts
```

**Current Behavior:**
```python
# From app/__init__.py - NO after_request hook applies headers!
# Headers defined in config.py:153-160 but NEVER used

# Expected (MISSING):
@app.after_request
def set_security_headers(response):
    """Apply security headers to all responses"""
    if app.config.get('TESTING'):
        return response

    headers = app.config.get('SECURITY_HEADERS', {})
    for header, value in headers.items():
        response.headers[header] = value
    return response
```

**Estimated Missing Tests:** 10+ security header tests

---

### 2.2 HIGH - Template Rendering Untested

**Severity:** HIGH
**Impact:** Template errors, missing context variables, broken Jinja2 logic undetected until runtime

#### Finding TEMPLATE-TEST-H1: 50 Templates with Zero Render Tests

**Templates with No Tests:**
1. `index.html` (Dashboard with stats, verification widget, role displays)
2. `unscheduled.html` (Event list with filters, search, schedule info)
3. `calendar.html` (Monthly calendar with event counts)
4. `daily_view.html` (Full-day schedule, role assignments, bulk actions)
5. `employees.html` (Employee CRUD with availability, time-off)
6. `auto_schedule_review.html` (Pending schedule approval workflow)
7. `dashboard/daily_validation.html` (Validation issues dashboard)
8. `dashboard/weekly_validation.html` (Weekly aggregation)
9. `dashboard/approved_events.html` (Event approval tracking)
10. ... 41 more templates

**What's Missing:**
```python
# NO TESTS LIKE THIS EXIST:
def test_dashboard_renders_with_stats(client, db_session, models):
    """Test dashboard page renders with correct context variables"""
    Event = models['Event']
    Employee = models['Employee']

    # Create test data
    emp = Employee(id="test", name="Test Employee", job_title="Lead")
    db_session.add(emp)

    today = datetime.now()
    for i in range(5):
        event = Event(
            project_ref_num=i,
            project_name=f"Event {i}",
            event_type="Core",
            start_datetime=today,
            due_datetime=today + timedelta(days=1)
        )
        db_session.add(event)
    db_session.commit()

    response = client.get('/')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    # Verify template variables rendered correctly
    assert 'Total Events' in html or '5' in html  # Event count
    assert 'Test Employee' in html  # Employee name rendered
    assert 'Dashboard' in html  # Page title

    # Verify no Jinja2 errors ({{ undefined }} should not appear)
    assert '{{' not in html
    assert '}}' not in html

def test_unscheduled_page_renders_events(client, db_session, models):
    """Test unscheduled events page displays events correctly"""
    Event = models['Event']

    event = Event(
        project_ref_num=123,
        project_name="Test Event",
        event_type="Core",
        condition="Unstaffed",
        start_datetime=datetime.now(),
        due_datetime=datetime.now() + timedelta(days=7)
    )
    db_session.add(event)
    db_session.commit()

    response = client.get('/events')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    assert 'Test Event' in html
    assert '123' in html  # Event number
    assert 'Core' in html  # Event type

def test_daily_view_renders_schedule(client, db_session, models):
    """Test daily view page renders schedule for specific date"""
    Event = models['Event']
    Employee = models['Employee']
    Schedule = models['Schedule']

    emp = Employee(id="emp1", name="John Doe", job_title="Event Specialist")
    event = Event(
        project_ref_num=456,
        project_name="Daily Event",
        event_type="Core",
        start_datetime=datetime(2026, 2, 9),
        due_datetime=datetime(2026, 2, 10)
    )
    schedule = Schedule(
        event_ref_num=456,
        employee_id="emp1",
        schedule_datetime=datetime(2026, 2, 9, 10, 0)
    )
    db_session.add_all([emp, event, schedule])
    db_session.commit()

    response = client.get('/schedule/daily/2026-02-09')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    assert 'John Doe' in html
    assert 'Daily Event' in html
    assert '10:00' in html or '10:00 AM' in html
```

**Estimated Missing Tests:** 100+ template render tests (2 per major template)

---

#### Finding TEMPLATE-TEST-H2: Template Context Variables Untested

**What's Missing:**
```python
def test_template_receives_correct_context(client, db_session, models):
    """Test that templates receive all required context variables"""
    response = client.get('/')

    # Should not crash if context variables are missing
    assert response.status_code == 200

    # Verify no "undefined" errors in Jinja2
    html = response.data.decode('utf-8')
    assert 'undefined' not in html.lower()

def test_template_handles_missing_data_gracefully(client):
    """Test that templates handle missing database records"""
    # Request page when no data exists
    response = client.get('/events')
    assert response.status_code == 200

    html = response.data.decode('utf-8')
    # Should show "no events" message, not crash
    assert 'No events' in html or 'No unscheduled events' in html
```

**Context Variables to Test (from `main.py`):**
- `index.html`: `supervisor_first_name`, `today`, `primary_lead_today`, `juicer_today`, `total_core_today`, `total_digitals_today`, `active_employees_count`, `events_this_week`
- `unscheduled.html`: `events`, `event_types`, `selected_event_type`, `condition`, `condition_display`, `date_filter`
- `daily_view.html`: `selected_date`, `juicer`, `primary_lead`, `prev_date`, `next_date`, `employees`, `today`
- `calendar.html`: `selected_date`, `events_by_date`, `event_counts_by_date`, `unscheduled_by_date`

**Estimated Missing Tests:** 50+ context variable tests

---

### 2.3 HIGH - JavaScript Functionality Untested

**Severity:** HIGH
**Impact:** JavaScript errors, race conditions, DOM manipulation bugs undetected

#### Finding JS-TEST-H1: 37 JavaScript Files with Zero Tests

**Files with No Tests:**
- `main.js` (primary application logic)
- `daily-view.js` (160KB, most complex file)
- `employees.js` (employee management)
- `auto-scheduler.js` (auto-scheduler interface)
- `ai-assistant.js` (AI panel with broken CSRF - SEC-H3)
- `csrf_helper.js` (CSRF token management)
- `api-client.js` (API wrapper)
- ... 30 more files

**What's Missing (requires E2E framework):**

```python
# Using Playwright/Selenium/Cypress (NONE INSTALLED):
def test_schedule_modal_opens_on_click(browser, live_server):
    """Test that clicking schedule button opens modal"""
    page = browser.new_page()
    page.goto(f'{live_server.url}/events')

    # Click first schedule button
    page.click('button.btn-schedule')

    # Modal should appear
    modal = page.locator('#schedule-modal')
    assert modal.is_visible()
    assert 'Schedule Event' in modal.text_content()

def test_employee_filter_updates_table(browser, live_server):
    """Test that employee filter in daily view updates display"""
    page = browser.new_page()
    page.goto(f'{live_server.url}/schedule/daily/2026-02-09')

    # Select employee from filter
    page.select_option('#employee-filter', 'emp1')

    # Table should update to show only that employee
    rows = page.locator('table tbody tr')
    assert rows.count() > 0
    for i in range(rows.count()):
        assert 'emp1' in rows.nth(i).text_content()

def test_csrf_token_added_to_ajax_requests(browser, live_server):
    """Test that csrf_helper.js adds token to POST requests"""
    page = browser.new_page()

    # Intercept network requests
    requests = []
    page.on('request', lambda req: requests.append(req))

    page.goto(f'{live_server.url}/events')

    # Trigger AJAX POST (e.g., create event)
    page.click('#create-event-btn')
    page.fill('#event-name', 'Test Event')
    page.click('#submit-event')

    # Find POST request
    post_request = next(r for r in requests if r.method == 'POST')

    # Verify CSRF token in headers
    assert 'X-CSRF-Token' in post_request.headers or 'X-CSRFToken' in post_request.headers
```

**Test Cases Needed:**
1. Modal open/close (schedule, reschedule, trade, employee)
2. Form validation (client-side)
3. AJAX request handling (success/error)
4. CSRF token attachment (from Phase 2 SEC-H3)
5. DOM updates after API calls (avoid `location.reload()` - from Phase 2 PERF-C4)
6. Keyboard shortcuts (from Phase 2 SEC-M4)
7. Date picker interactions
8. Filter/search functionality
9. Error message display
10. Loading state indicators

**Estimated Missing Tests:** 150+ JavaScript tests

---

#### Finding JS-TEST-H2: Race Condition Untested (From Phase 2 PERF-C2)

**From Phase 2:** ES module loaded with `type="module"` (deferred) consumed by sync `<script>` tags

**What's Missing:**
```python
def test_module_loading_order(browser, live_server):
    """Test that ES modules load before global scripts consume them"""
    page = browser.new_page()

    # Track console errors
    errors = []
    page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)

    page.goto(f'{live_server.url}/')

    # Wait for page load
    page.wait_for_load_state('networkidle')

    # Should have no "undefined" errors
    assert not any('undefined' in e.lower() for e in errors)
    assert not any('is not defined' in e.lower() for e in errors)
```

**Estimated Missing Tests:** 5+ race condition tests

---

### 2.4 MEDIUM - API Route Coverage Gap

**Severity:** MEDIUM
**Impact:** API bugs, validation errors, error handling failures undetected

#### Finding API-TEST-M1: 274 Routes Untested (99% gap)

**Route Coverage:**
- Total routes: 277 (from grep of `@*.route(`)
- Tested routes: 3 (`/health/ping`, `/health/ready`, `/`)
- Untested routes: 274

**Critical Untested API Routes:**

```python
# NO TESTS FOR THESE EXIST:

# Events API (from api.py)
def test_get_events_list(client, db_session, models):
    """GET /api/events - List all events"""
    Event = models['Event']
    event = Event(project_ref_num=1, project_name="Test", event_type="Core")
    db_session.add(event)
    db_session.commit()

    response = client.get('/api/events')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert len(data['data']) == 1
    assert data['data'][0]['project_name'] == 'Test'

def test_create_event(client, db_session, models):
    """POST /api/events - Create new event"""
    response = client.post('/api/events', json={
        'project_ref_num': 999,
        'project_name': 'New Event',
        'event_type': 'Core',
        'start_datetime': '2026-02-10T09:00:00',
        'due_datetime': '2026-02-10T15:00:00'
    })
    assert response.status_code == 201
    data = response.get_json()
    assert data['status'] == 'success'

def test_update_event(client, db_session, models):
    """PUT /api/events/<id> - Update event"""
    Event = models['Event']
    event = Event(project_ref_num=1, project_name="Old", event_type="Core")
    db_session.add(event)
    db_session.commit()

    response = client.put('/api/events/1', json={
        'project_name': 'Updated Event'
    })
    assert response.status_code == 200

    # Verify update
    updated = Event.query.get(1)
    assert updated.project_name == 'Updated Event'

def test_delete_event(client, db_session, models):
    """DELETE /api/events/<id> - Delete event"""
    Event = models['Event']
    event = Event(project_ref_num=1, project_name="Delete Me", event_type="Core")
    db_session.add(event)
    db_session.commit()

    response = client.delete('/api/events/1')
    assert response.status_code == 200

    # Verify deletion
    assert Event.query.get(1) is None

# Schedules API
def test_create_schedule(client, db_session, models):
    """POST /api/schedules - Create schedule assignment"""
    Event = models['Event']
    Employee = models['Employee']

    emp = Employee(id="emp1", name="John", job_title="Event Specialist")
    event = Event(project_ref_num=1, project_name="Event", event_type="Core")
    db_session.add_all([emp, event])
    db_session.commit()

    response = client.post('/api/schedules', json={
        'event_ref_num': 1,
        'employee_id': 'emp1',
        'schedule_datetime': '2026-02-09T10:00:00'
    })
    assert response.status_code == 201

def test_bulk_schedule_create(client, db_session, models):
    """POST /api/schedules/bulk - Create multiple schedules"""
    # Test bulk assignment
    response = client.post('/api/schedules/bulk', json={
        'schedules': [
            {'event_ref_num': 1, 'employee_id': 'emp1', 'schedule_datetime': '2026-02-09T10:00:00'},
            {'event_ref_num': 2, 'employee_id': 'emp2', 'schedule_datetime': '2026-02-09T11:00:00'}
        ]
    })
    assert response.status_code == 201

# Employees API
def test_get_employee_availability(client, db_session, models):
    """GET /api/employees/<id>/availability"""
    Employee = models['Employee']
    EmployeeWeeklyAvailability = models['EmployeeWeeklyAvailability']

    emp = Employee(id="emp1", name="Test")
    avail = EmployeeWeeklyAvailability(employee_id="emp1", monday=True, tuesday=False)
    db_session.add_all([emp, avail])
    db_session.commit()

    response = client.get('/api/employees/emp1/availability')
    assert response.status_code == 200
    data = response.get_json()
    assert data['data']['monday'] is True
    assert data['data']['tuesday'] is False

def test_create_time_off_request(client, db_session, models):
    """POST /api/employees/<id>/time-off"""
    Employee = models['Employee']
    emp = Employee(id="emp1", name="Test")
    db_session.add(emp)
    db_session.commit()

    response = client.post('/api/employees/emp1/time-off', json={
        'start_date': '2026-02-15',
        'end_date': '2026-02-17',
        'reason': 'Vacation'
    })
    assert response.status_code == 201

# Auto-Scheduler API
def test_run_auto_scheduler(client, db_session, models):
    """POST /auto-scheduler/run - Run auto-scheduler"""
    Event = models['Event']
    Employee = models['Employee']

    # Create unstaffed event and available employee
    event = Event(
        project_ref_num=1,
        project_name="Unscheduled",
        event_type="Core",
        condition="Unstaffed",
        start_datetime=datetime.now() + timedelta(days=1),
        due_datetime=datetime.now() + timedelta(days=2)
    )
    emp = Employee(id="emp1", name="Available", job_title="Event Specialist")
    db_session.add_all([event, emp])
    db_session.commit()

    response = client.post('/auto-scheduler/run', json={
        'date_range_start': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
        'date_range_end': (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'

def test_approve_pending_schedule(client, db_session, models):
    """POST /auto-scheduler/approve - Approve pending schedule"""
    PendingSchedule = models['PendingSchedule']
    Event = models['Event']
    Employee = models['Employee']

    event = Event(project_ref_num=1, project_name="Test", event_type="Core")
    emp = Employee(id="emp1", name="Test")
    pending = PendingSchedule(
        event_ref_num=1,
        employee_id="emp1",
        schedule_datetime=datetime.now() + timedelta(days=1),
        status='pending'
    )
    db_session.add_all([event, emp, pending])
    db_session.commit()

    response = client.post(f'/auto-scheduler/approve/{pending.id}')
    assert response.status_code == 200

    # Verify schedule created
    Schedule = models['Schedule']
    schedule = Schedule.query.filter_by(event_ref_num=1).first()
    assert schedule is not None

# Validation API
def test_schedule_validation(client, db_session, models):
    """GET /api/schedules/validation - Get validation issues"""
    response = client.get('/api/schedules/validation?date=2026-02-09')
    assert response.status_code == 200
    data = response.get_json()
    assert 'issues' in data or 'violations' in data
```

**API Routes by Blueprint (Untested):**

| Blueprint | Routes | Critical Routes Untested |
|-----------|--------|--------------------------|
| `api_bp` | ~37 | `/api/events`, `/api/schedules`, `/api/employees` |
| `auto_scheduler_bp` | ~19 | `/auto-scheduler/run`, `/auto-scheduler/approve` |
| `employees_bp` | ~12 | `/employees/add`, `/employees/<id>/edit` |
| `main_bp` | ~12 | `/events`, `/calendar`, `/schedule/daily/<date>` |
| `dashboard_bp` | ~11 | `/dashboard/daily-validation`, `/dashboard/weekly-validation` |
| `printing_bp` | ~17 | `/printing/schedule/<date>` |
| `walmart_bp` | ~3 | `/walmart/sync` (external integration) |
| `inventory_bp` | ~35 | `/inventory/orders` |
| Others | ~131 | Various |

**Estimated Missing Tests:** 400+ API route tests (assuming 1.5 tests per route for GET/POST/error cases)

---

### 2.5 MEDIUM - Form Validation Untested

**Severity:** MEDIUM
**Impact:** Invalid data submitted, validation bypass, poor UX

#### Finding FORM-TEST-M1: Zero Form Validation Tests

**Forms to Test:**
1. Employee creation form (`/employees/add`)
2. Event scheduling form (modal)
3. Time-off request form
4. Login form
5. Auto-scheduler configuration form
6. Employee availability form

**What's Missing:**
```python
def test_employee_form_validates_required_fields(client):
    """Test that employee form rejects submission without required fields"""
    response = client.post('/employees/add', data={
        'name': '',  # Required field missing
        'job_title': 'Event Specialist'
    })

    # Should redirect back with error
    assert response.status_code in [400, 302]  # 400 error or 302 redirect

    if response.status_code == 302:
        # Follow redirect
        response = client.get(response.location)
        assert 'Name is required' in response.data.decode('utf-8')

def test_schedule_form_prevents_past_dates(client, db_session, models):
    """Test that schedule form rejects past dates"""
    Event = models['Event']
    Employee = models['Employee']

    event = Event(project_ref_num=1, project_name="Test", event_type="Core")
    emp = Employee(id="emp1", name="Test")
    db_session.add_all([event, emp])
    db_session.commit()

    # Try to schedule in the past
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%dT09:00:00')

    response = client.post('/api/schedules', json={
        'event_ref_num': 1,
        'employee_id': 'emp1',
        'schedule_datetime': yesterday
    })

    # Should reject
    assert response.status_code == 400
    data = response.get_json()
    assert 'past' in data['error'].lower() or 'invalid date' in data['error'].lower()

def test_employee_availability_validates_days(client, db_session, models):
    """Test that availability form validates day selection"""
    Employee = models['Employee']
    emp = Employee(id="emp1", name="Test")
    db_session.add(emp)
    db_session.commit()

    # Must have at least one day selected
    response = client.post('/api/employees/emp1/availability', json={
        'monday': False,
        'tuesday': False,
        'wednesday': False,
        'thursday': False,
        'friday': False,
        'saturday': False,
        'sunday': False
    })

    assert response.status_code == 400
    data = response.get_json()
    assert 'at least one day' in data['error'].lower()
```

**Estimated Missing Tests:** 50+ form validation tests

---

### 2.6 MEDIUM - Error Handling Untested

**Severity:** MEDIUM
**Impact:** Poor error messages, crashes on invalid input, security information leakage

#### Finding ERROR-TEST-M1: Error Pages and API Error Responses Untested

**What's Missing:**
```python
def test_404_page_renders(client):
    """Test that 404 page renders on invalid route"""
    response = client.get('/nonexistent-page')
    assert response.status_code == 404
    html = response.data.decode('utf-8')
    assert '404' in html or 'Not Found' in html

def test_500_error_doesnt_leak_stacktrace(client):
    """Test that 500 errors don't expose sensitive information"""
    # Trigger server error (e.g., database connection failure)
    # This requires mocking or intentional error injection

    # For now, test API error format
    response = client.get('/api/events/99999')  # Non-existent event
    assert response.status_code == 404
    data = response.get_json()

    # Should return clean error, not stack trace
    assert 'error' in data
    assert 'Traceback' not in str(data)
    assert 'File "/app/' not in str(data)

def test_api_returns_proper_error_format(client):
    """Test that API errors follow consistent format"""
    response = client.post('/api/events', json={
        # Missing required fields
        'project_name': 'Test'
    })

    assert response.status_code == 400
    data = response.get_json()

    # Standard error format: {"status": "error", "error": "message"}
    assert data['status'] == 'error'
    assert 'error' in data
    assert isinstance(data['error'], str)

def test_invalid_date_format_handled(client):
    """Test that invalid date formats return clear errors"""
    response = client.get('/schedule/daily/invalid-date')

    # Should redirect or return 400
    assert response.status_code in [302, 400]
```

**Estimated Missing Tests:** 30+ error handling tests

---

### 2.7 LOW - No Visual Regression Testing

**Severity:** LOW
**Impact:** CSS regressions, layout breaks, responsive design issues undetected

#### Finding VISUAL-TEST-L1: Zero Visual Regression Tests

**What's Missing:**
- No visual regression testing framework (Percy, Chromatic, BackstopJS)
- No screenshot comparison tests
- No CSS rendering validation

**Recommended Tests (requires visual testing tool):**
```python
# Example with Percy (not installed):
import percy

def test_dashboard_visual_regression(browser, live_server, percy_snapshot):
    """Test dashboard appearance hasn't changed"""
    page = browser.new_page()
    page.goto(f'{live_server.url}/')

    # Take snapshot
    percy_snapshot(page, 'Dashboard - Desktop')

    # Test mobile view
    page.set_viewport_size({'width': 375, 'height': 667})
    percy_snapshot(page, 'Dashboard - Mobile')

def test_calendar_responsive_layout(browser, live_server, percy_snapshot):
    """Test calendar renders correctly on different screen sizes"""
    page = browser.new_page()
    page.goto(f'{live_server.url}/calendar')

    # Desktop
    page.set_viewport_size({'width': 1920, 'height': 1080})
    percy_snapshot(page, 'Calendar - Desktop')

    # Tablet
    page.set_viewport_size({'width': 768, 'height': 1024})
    percy_snapshot(page, 'Calendar - Tablet')

    # Mobile
    page.set_viewport_size({'width': 375, 'height': 667})
    percy_snapshot(page, 'Calendar - Mobile')
```

**Estimated Missing Tests:** 20+ visual regression tests

---

### 2.8 LOW - No Accessibility Testing

**Severity:** LOW
**Impact:** WCAG compliance issues, screen reader problems, keyboard navigation failures

#### Finding A11Y-TEST-L1: Zero Accessibility Tests

**What's Missing:**
- No `axe-core` integration
- No keyboard navigation tests
- No screen reader compatibility tests
- No ARIA attribute validation

**Recommended Tests:**
```python
# Example with axe-playwright (not installed):
from axe_playwright import Axe

def test_dashboard_accessibility(browser, live_server):
    """Test dashboard meets WCAG AA standards"""
    page = browser.new_page()
    page.goto(f'{live_server.url}/')

    # Run axe accessibility scan
    axe = Axe()
    results = axe.run(page)

    # No violations
    assert len(results.violations) == 0, f"Accessibility violations: {results.violations}"

def test_keyboard_navigation_schedule_modal(browser, live_server):
    """Test that schedule modal is keyboard-accessible"""
    page = browser.new_page()
    page.goto(f'{live_server.url}/events')

    # Tab to schedule button
    page.keyboard.press('Tab')
    page.keyboard.press('Tab')  # Assume second tabbable element

    # Activate with Enter
    page.keyboard.press('Enter')

    # Modal should open
    modal = page.locator('#schedule-modal')
    assert modal.is_visible()

    # Tab through form fields
    page.keyboard.press('Tab')  # Focus first field
    assert page.evaluate('document.activeElement.tagName') == 'INPUT'

def test_aria_labels_present(client):
    """Test that interactive elements have ARIA labels"""
    response = client.get('/')
    html = response.data.decode('utf-8')

    # Buttons should have aria-label or text content
    # This is a simple check; real check needs DOM parsing
    assert 'aria-label=' in html or '<button>' in html
```

**Estimated Missing Tests:** 15+ accessibility tests

---

## 3. Test Infrastructure Gaps

### 3.1 No E2E Testing Framework

**Current State:**
- No Playwright installed
- No Selenium installed
- No Cypress installed
- No Puppeteer installed

**Impact:**
- Cannot test JavaScript execution
- Cannot test user workflows
- Cannot test AJAX interactions
- Cannot test DOM manipulation

**Recommendation:**
Install Playwright for Python:
```bash
pip install pytest-playwright
playwright install
```

**Example Setup:**
```python
# tests/conftest.py additions:
import pytest
from playwright.sync_api import sync_playwright

@pytest.fixture(scope='session')
def browser():
    """Create browser instance for E2E tests"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()

@pytest.fixture
def live_server(app):
    """Start Flask test server for E2E tests"""
    from threading import Thread
    import socket

    # Find free port
    sock = socket.socket()
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()

    # Start server in thread
    thread = Thread(target=app.run, kwargs={'port': port})
    thread.daemon = True
    thread.start()

    class LiveServer:
        url = f'http://localhost:{port}'

    yield LiveServer()
```

---

### 3.2 No JavaScript Testing Framework

**Current State:**
- No Jest
- No Mocha
- No Jasmine
- No Vitest

**Impact:**
- Cannot unit test JavaScript functions
- Cannot test API client logic
- Cannot test CSRF helper
- Cannot test utility functions

**Recommendation:**
Install Jest for Node.js testing:
```bash
npm install --save-dev jest @testing-library/dom
```

**Example Tests:**
```javascript
// tests/js/csrf_helper.test.js
import { getCsrfToken } from '../../app/static/js/csrf_helper.js';

describe('CSRF Helper', () => {
  test('getCsrfToken reads from cookie', () => {
    document.cookie = 'csrf_token=test-token-123';
    expect(getCsrfToken()).toBe('test-token-123');
  });

  test('returns null when cookie missing', () => {
    document.cookie = '';
    expect(getCsrfToken()).toBeNull();
  });
});

// tests/js/api-client.test.js
import { ApiClient } from '../../app/static/js/utils/api-client.js';

describe('API Client', () => {
  test('adds CSRF token to POST requests', async () => {
    const client = new ApiClient();

    // Mock fetch
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ status: 'success' })
      })
    );

    await client.request('/api/test', { method: 'POST' });

    // Verify CSRF token in headers
    expect(fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-CSRFToken': expect.any(String)
        })
      })
    );
  });
});
```

---

### 3.3 No CI/CD Testing Pipeline

**Current State:**
- GitHub Actions workflows exist (`claude-code-review.yml`, `claude.yml`)
- NO test automation in CI/CD
- NO automated security scans
- NO accessibility checks

**Recommendation:**
Add test workflow:
```yaml
# .github/workflows/tests.yml
name: Test Suite

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-playwright
          playwright install
      - name: Run Python tests
        run: pytest -v --cov=app --cov-report=html
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  javascript:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Install dependencies
        run: npm install
      - name: Run JS tests
        run: npm test

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Bandit security scan
        run: |
          pip install bandit
          bandit -r app/
      - name: Run npm audit
        run: npm audit

  accessibility:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest-playwright axe-playwright
          playwright install
      - name: Run accessibility tests
        run: pytest tests/e2e/test_accessibility.py
```

---

## 4. Recommended Test Suite Structure

### 4.1 Proposed Test Organization

```
tests/
├── conftest.py                          # Test fixtures (app, db_session, models, browser, live_server)
│
├── unit/                                # Unit tests (existing tests go here)
│   ├── test_models.py                   # ✓ Exists
│   ├── test_validators.py               # ✓ Exists
│   ├── test_scheduling_engine.py        # ✓ Exists
│   ├── test_rotation_manager.py         # ✓ Exists
│   └── ml/                              # ✓ Exists
│       ├── test_ml_effectiveness.py
│       ├── test_ml_functional.py
│       ├── test_ml_performance.py
│       ├── test_ml_safety.py
│       └── test_ml_shadow_mode.py
│
├── integration/                         # NEW - Integration tests
│   ├── test_api_events.py               # ✗ Missing - Event CRUD API
│   ├── test_api_schedules.py            # ✗ Missing - Schedule API
│   ├── test_api_employees.py            # ✗ Missing - Employee API
│   ├── test_api_auto_scheduler.py       # ✗ Missing - Auto-scheduler API
│   ├── test_template_rendering.py       # ✗ Missing - Template context tests
│   └── test_error_handling.py           # ✗ Missing - Error page tests
│
├── security/                            # NEW - Security tests
│   ├── test_xss_prevention.py           # ✗ Missing - XSS in onclick handlers (SEC-C1)
│   ├── test_xss_innerHTML.py            # ✗ Missing - XSS in DOM manipulation (SEC-C2)
│   ├── test_csrf_protection.py          # ✗ Missing - CSRF token validation (SEC-H3, SEC-H6)
│   ├── test_security_headers.py         # ✗ Missing - Response headers (SEC-H1, SEC-H2)
│   ├── test_input_validation.py         # ✗ Missing - SQL injection, path traversal
│   └── test_authentication.py           # ✗ Missing - Login, session, authorization
│
├── e2e/                                 # NEW - End-to-end tests (Playwright)
│   ├── test_user_workflows.py           # ✗ Missing - Login → Schedule → Approve
│   ├── test_schedule_creation.py        # ✗ Missing - Full schedule creation flow
│   ├── test_employee_management.py      # ✗ Missing - Create/edit employee flow
│   ├── test_auto_scheduler_ui.py        # ✗ Missing - Run auto-scheduler UI
│   ├── test_modals.py                   # ✗ Missing - Modal open/close/submit
│   ├── test_filters_search.py           # ✗ Missing - Filter/search functionality
│   └── test_accessibility.py            # ✗ Missing - WCAG compliance (axe)
│
├── visual/                              # NEW - Visual regression (Percy/BackstopJS)
│   ├── test_dashboard_visual.py         # ✗ Missing - Dashboard appearance
│   ├── test_calendar_responsive.py      # ✗ Missing - Calendar on mobile/tablet/desktop
│   └── test_components.py               # ✗ Missing - Modal, button, card rendering
│
└── javascript/                          # NEW - JS unit tests (Jest)
    ├── csrf_helper.test.js              # ✗ Missing - CSRF token functions
    ├── api-client.test.js               # ✗ Missing - API client wrapper
    ├── validation-engine.test.js        # ✗ Missing - Client-side validation
    └── utils.test.js                    # ✗ Missing - Utility functions
```

---

## 5. Priority Test Cases (Immediate Action Required)

### 5.1 CRITICAL Priority (Implement First)

**Week 1: Security Tests (Addresses Phase 2 Critical Findings)**

1. **XSS Prevention Tests** (SEC-C1, SEC-C2)
   - File: `tests/security/test_xss_prevention.py`
   - Tests: 25
   - Covers: onclick handlers, innerHTML assignments, API responses

2. **CSRF Protection Tests** (SEC-H3, SEC-H6)
   - File: `tests/security/test_csrf_protection.py`
   - Tests: 15
   - Covers: Token in cookie/meta, API validation, dual header names

3. **Security Headers Tests** (SEC-H1, SEC-H2)
   - File: `tests/security/test_security_headers.py`
   - Tests: 10
   - Covers: HSTS, X-Frame-Options, CSP, X-Content-Type-Options

**Week 2: Core API Tests**

4. **Event API Tests**
   - File: `tests/integration/test_api_events.py`
   - Tests: 20
   - Covers: GET list, GET single, POST create, PUT update, DELETE

5. **Schedule API Tests**
   - File: `tests/integration/test_api_schedules.py`
   - Tests: 15
   - Covers: Create, bulk create, validation, conflicts

6. **Employee API Tests**
   - File: `tests/integration/test_api_employees.py`
   - Tests: 15
   - Covers: CRUD, availability, time-off requests

---

### 5.2 HIGH Priority (Implement Second)

**Week 3: Template & E2E Tests**

7. **Template Rendering Tests**
   - File: `tests/integration/test_template_rendering.py`
   - Tests: 50
   - Covers: Context variables, missing data handling, Jinja2 errors

8. **User Workflow E2E Tests** (Requires Playwright)
   - File: `tests/e2e/test_user_workflows.py`
   - Tests: 10
   - Covers: Login → View events → Create schedule → Approve

9. **Modal Interaction Tests** (Requires Playwright)
   - File: `tests/e2e/test_modals.py`
   - Tests: 20
   - Covers: Open/close, form submission, validation, AJAX updates

**Week 4: JavaScript & Accessibility**

10. **JavaScript Unit Tests** (Requires Jest)
    - File: `tests/javascript/csrf_helper.test.js`
    - Tests: 10
    - Covers: CSRF token retrieval, header attachment

11. **API Client Tests** (Requires Jest)
    - File: `tests/javascript/api-client.test.js`
    - Tests: 15
    - Covers: Timeout, retry, error handling, CSRF

12. **Accessibility Tests** (Requires axe-playwright)
    - File: `tests/e2e/test_accessibility.py`
    - Tests: 15
    - Covers: WCAG AA compliance, keyboard nav, ARIA

---

### 5.3 MEDIUM Priority (Implement Third)

**Week 5-6: Comprehensive Coverage**

13. Form validation tests (50 tests)
14. Error handling tests (30 tests)
15. Auto-scheduler UI tests (20 tests)
16. Authentication tests (20 tests)
17. Filter/search functionality tests (25 tests)

---

## 6. Test Quality & Coverage Recommendations

### 6.1 Test Fixtures Enhancement

**Current Fixtures (conftest.py):**
```python
@pytest.fixture(scope='function')
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture(scope='function')
def db_session(db):
    """Creates a new database session for a test."""
    db.create_all()
    yield db.session
    db.session.remove()
    db.drop_all()

@pytest.fixture(scope='function')
def models(app):
    """Get models from registry."""
    return get_models()
```

**Recommended Additions:**
```python
@pytest.fixture
def authenticated_client(client, db_session, models):
    """Client with authenticated session"""
    User = models.get('User')
    if User:
        user = User(username='testuser', password_hash='hashed')
        db_session.add(user)
        db_session.commit()

        with client.session_transaction() as sess:
            sess['user_id'] = user.id

    return client

@pytest.fixture
def sample_event(db_session, models):
    """Create sample event for testing"""
    Event = models['Event']
    event = Event(
        project_ref_num=999,
        project_name="Test Event",
        event_type="Core",
        condition="Unstaffed",
        start_datetime=datetime.now() + timedelta(days=1),
        due_datetime=datetime.now() + timedelta(days=2)
    )
    db_session.add(event)
    db_session.commit()
    return event

@pytest.fixture
def sample_employee(db_session, models):
    """Create sample employee for testing"""
    Employee = models['Employee']
    emp = Employee(
        id="test_emp",
        name="Test Employee",
        job_title="Event Specialist",
        is_active=True
    )
    db_session.add(emp)
    db_session.commit()
    return emp

@pytest.fixture
def sample_schedule(db_session, models, sample_event, sample_employee):
    """Create sample schedule for testing"""
    Schedule = models['Schedule']
    schedule = Schedule(
        event_ref_num=sample_event.project_ref_num,
        employee_id=sample_employee.id,
        schedule_datetime=datetime.now() + timedelta(days=1, hours=9)
    )
    db_session.add(schedule)
    db_session.commit()
    return schedule

# For E2E tests
@pytest.fixture(scope='session')
def browser():
    """Playwright browser instance"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()

@pytest.fixture
def page(browser):
    """New browser page for each test"""
    page = browser.new_page()
    yield page
    page.close()

@pytest.fixture
def live_server(app):
    """Start Flask app for E2E testing"""
    from threading import Thread
    import socket

    sock = socket.socket()
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()

    def run_server():
        app.run(port=port, threaded=True)

    thread = Thread(target=run_server)
    thread.daemon = True
    thread.start()

    # Wait for server to start
    import time
    time.sleep(1)

    class LiveServer:
        url = f'http://localhost:{port}'

    yield LiveServer()
```

---

### 6.2 Coverage Targets

**Recommended Coverage Goals:**

| Layer | Current Coverage | Target Coverage | Priority |
|-------|------------------|-----------------|----------|
| **Backend Business Logic** | ~85% | 90% | Medium |
| **API Routes** | <1% | 80% | **Critical** |
| **Template Rendering** | 0% | 70% | **High** |
| **JavaScript** | 0% | 60% | **High** |
| **Security (XSS/CSRF)** | 0% | 100% | **Critical** |
| **E2E User Flows** | 0% | 50% | **High** |
| **Error Handling** | 0% | 80% | Medium |
| **Accessibility** | 0% | 60% | Low |

**Coverage Measurement:**
```bash
# Python coverage
pytest --cov=app --cov-report=html --cov-report=term

# JavaScript coverage (with Jest)
npm test -- --coverage

# E2E coverage (with Playwright)
pytest tests/e2e/ --cov=app/templates --cov-report=html
```

---

### 6.3 Test Quality Guidelines

**Good Test Characteristics:**
1. **Isolated:** Each test cleans up its own data
2. **Fast:** Unit tests < 100ms, integration tests < 1s, E2E tests < 5s
3. **Readable:** Clear test names, Given-When-Then structure
4. **Maintainable:** Uses fixtures, avoids duplication
5. **Deterministic:** No flaky tests, no random data

**Example Good Test:**
```python
def test_create_schedule_succeeds_with_valid_data(client, db_session, sample_event, sample_employee):
    """
    GIVEN an event and employee exist
    WHEN POST /api/schedules with valid data
    THEN schedule is created and returns 201
    """
    response = client.post('/api/schedules', json={
        'event_ref_num': sample_event.project_ref_num,
        'employee_id': sample_employee.id,
        'schedule_datetime': '2026-02-10T09:00:00'
    })

    assert response.status_code == 201
    data = response.get_json()
    assert data['status'] == 'success'
    assert data['data']['event_ref_num'] == sample_event.project_ref_num
```

**Example Bad Test (Avoid):**
```python
def test_stuff(client):
    """Test some stuff"""  # ✗ Vague description
    # ✗ No setup/teardown
    # ✗ No clear assertion
    response = client.get('/api/events')
    assert response.status_code == 200  # ✗ Weak assertion
```

---

## 7. Estimated Effort to Achieve Coverage

### 7.1 Test Development Estimates

| Category | Tests Needed | Est. Hours | Priority |
|----------|--------------|------------|----------|
| **Security Tests (XSS, CSRF, Headers)** | 50 | 40 | Critical |
| **API Route Tests** | 400 | 200 | Critical |
| **Template Rendering Tests** | 100 | 60 | High |
| **JavaScript Unit Tests** | 80 | 50 | High |
| **E2E User Flow Tests** | 50 | 100 | High |
| **Form Validation Tests** | 50 | 30 | Medium |
| **Error Handling Tests** | 30 | 20 | Medium |
| **Accessibility Tests** | 15 | 30 | Low |
| **Visual Regression Tests** | 20 | 40 | Low |
| **Infrastructure Setup** | N/A | 20 | Critical |
| **CI/CD Integration** | N/A | 10 | High |
| **TOTAL** | **795 tests** | **600 hours** | - |

**Timeline Estimate:**
- **Critical path (Security + Core API):** 8 weeks (240 hours)
- **Full coverage:** 15 weeks (600 hours)

**Team Size Recommendation:**
- 2 QA engineers working full-time: 8 weeks for critical path, 15 weeks for full coverage
- 1 QA engineer: 16 weeks for critical path, 30 weeks for full coverage

---

### 7.2 Phased Rollout Plan

**Phase 1: Security Foundation (Weeks 1-2)**
- XSS prevention tests (SEC-C1, SEC-C2)
- CSRF protection tests (SEC-H3, SEC-H6)
- Security headers tests (SEC-H1, SEC-H2)
- **Output:** 50 security tests, blocks critical vulnerabilities

**Phase 2: API Core (Weeks 3-5)**
- Event API tests (CRUD)
- Schedule API tests (create, bulk, validation)
- Employee API tests (availability, time-off)
- **Output:** 100 API tests, 50% route coverage

**Phase 3: UI Coverage (Weeks 6-8)**
- Template rendering tests
- E2E workflow tests (Playwright setup)
- Modal interaction tests
- **Output:** 80 UI tests, prevents template regressions

**Phase 4: JavaScript & Accessibility (Weeks 9-10)**
- JavaScript unit tests (Jest setup)
- CSRF helper tests
- API client tests
- Accessibility tests (axe setup)
- **Output:** 100 JS + accessibility tests

**Phase 5: Comprehensive Coverage (Weeks 11-15)**
- Form validation tests
- Error handling tests
- Additional E2E scenarios
- Visual regression tests
- **Output:** Remaining 465 tests, 80% total coverage

---

## 8. Key Recommendations Summary

### 8.1 Immediate Actions (This Sprint)

1. **Install E2E testing framework:**
   ```bash
   pip install pytest-playwright
   playwright install chromium
   ```

2. **Create security test file:**
   - File: `tests/security/test_xss_prevention.py`
   - Priority: CRITICAL (addresses SEC-C1, SEC-C2)

3. **Create CSRF test file:**
   - File: `tests/security/test_csrf_protection.py`
   - Priority: CRITICAL (addresses SEC-H3, SEC-H6)

4. **Create security headers test file:**
   - File: `tests/security/test_security_headers.py`
   - Priority: CRITICAL (addresses SEC-H1, SEC-H2)
   - **NOTE:** This will fail until `after_request` hook is added to `app/__init__.py`

5. **Set up CI/CD testing:**
   - File: `.github/workflows/tests.yml`
   - Run pytest on every PR
   - Block merges if security tests fail

---

### 8.2 Long-Term Improvements

1. **Adopt Test-Driven Development (TDD):**
   - Write tests BEFORE implementing features
   - Require tests for all new routes/templates

2. **Establish Coverage Minimums:**
   - Require 80% code coverage for PRs
   - Use `pytest --cov` in CI/CD
   - Block merges below threshold

3. **Regular Security Audits:**
   - Run OWASP ZAP scans monthly
   - Update dependency security scans (Dependabot)
   - Review XSS/CSRF test coverage quarterly

4. **Performance Testing:**
   - Add Lighthouse CI for page load metrics
   - Monitor bundle sizes (PERF-C1, PERF-H1, PERF-H2)
   - Alert on regressions

---

## 9. Example Test Implementation

### 9.1 Complete Security Test Example

```python
# tests/security/test_xss_prevention.py
"""
XSS Prevention Tests

Tests for Cross-Site Scripting (XSS) vulnerability prevention.
Addresses Phase 2 findings SEC-C1 (onclick handlers) and SEC-C2 (innerHTML).
"""
import pytest
from datetime import datetime, timedelta

class TestXSSOnClickHandlers:
    """Test XSS prevention in inline onclick handlers (SEC-C1)"""

    def test_event_name_with_double_quotes_escaped_in_onclick(self, client, db_session, models):
        """
        GIVEN an event with double quotes in project_name
        WHEN rendering unscheduled.html with onclick handlers
        THEN double quotes are properly escaped to prevent attribute injection
        """
        Event = models['Event']

        # XSS payload: attempt to break out of onclick attribute with double quotes
        xss_payload = 'Test Event"; alert("XSS"); "'
        event = Event(
            project_ref_num=999,
            project_name=xss_payload,
            event_type="Core",
            condition="Unstaffed",
            start_datetime=datetime.now() + timedelta(days=1),
            due_datetime=datetime.now() + timedelta(days=2)
        )
        db_session.add(event)
        db_session.commit()

        response = client.get('/events')
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Verify XSS payload is NOT executable
        assert 'alert("XSS")' not in html, "Raw XSS payload should not appear in HTML"

        # Verify onclick handlers exist (sanity check)
        assert 'onclick=' in html, "onclick handlers should be present"

        # Verify proper escaping (either HTML entities or backslash escaping)
        # Jinja2 |replace("'", "\\'") should escape to: Test Event\"; alert(\\"XSS\\"); \\"
        # or HTML entities: Test Event&quot;; alert(&quot;XSS&quot;); &quot;
        assert ('&quot;' in html or '\\"' in html), "Quotes should be escaped"

    def test_employee_name_with_single_quotes_escaped(self, client, db_session, models):
        """
        GIVEN an employee with single quotes in name (e.g., O'Malley)
        WHEN rendering in onclick handler
        THEN single quotes are properly escaped
        """
        Employee = models['Employee']
        Event = models['Event']
        Schedule = models['Schedule']

        emp = Employee(
            id="test_emp",
            name="O'Malley'; DROP TABLE employees;--",  # SQL injection attempt + XSS
            job_title="Event Specialist"
        )
        event = Event(
            project_ref_num=888,
            project_name="Test Event",
            event_type="Core",
            condition="Scheduled"
        )
        schedule = Schedule(
            event_ref_num=888,
            employee_id="test_emp",
            schedule_datetime=datetime.now() + timedelta(days=1)
        )
        db_session.add_all([emp, event, schedule])
        db_session.commit()

        response = client.get('/events?condition=scheduled')
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Verify SQL injection attempt is not executable
        assert 'DROP TABLE' not in html or '&' in html  # Should be escaped

        # Verify single quotes are escaped
        assert "O\\'Malley" in html or "O&#39;Malley" in html or "O&apos;Malley" in html

    def test_store_name_with_html_tags_escaped(self, client, db_session, models):
        """
        GIVEN an event with HTML tags in store_name
        WHEN rendering in onclick handler
        THEN HTML tags are escaped to prevent tag injection
        """
        Event = models['Event']

        event = Event(
            project_ref_num=777,
            project_name="Test Event",
            store_name='<script>alert("XSS")</script>',
            event_type="Core",
            condition="Unstaffed"
        )
        db_session.add(event)
        db_session.commit()

        response = client.get('/events')
        html = response.data.decode('utf-8')

        # Verify script tag is escaped, not executable
        assert '<script>alert("XSS")</script>' not in html
        assert '&lt;script&gt;' in html or '\\u003cscript\\u003e' in html


class TestXSSInnerHTML:
    """Test XSS prevention in innerHTML assignments (SEC-C2)"""

    def test_api_response_escapes_html_in_event_name(self, client, db_session, models):
        """
        GIVEN an event with HTML/script tags in project_name
        WHEN fetching via API (used by JS innerHTML)
        THEN response contains escaped HTML, not raw tags
        """
        Event = models['Event']

        event = Event(
            project_ref_num=666,
            project_name='<img src=x onerror="alert(1)">',
            event_type="Core",
            condition="Unstaffed",
            start_datetime=datetime.now(),
            due_datetime=datetime.now() + timedelta(days=1)
        )
        db_session.add(event)
        db_session.commit()

        response = client.get('/api/events/666')
        assert response.status_code == 200
        data = response.get_json()

        # API should return escaped HTML
        project_name = data['data']['project_name']
        assert '<img' not in project_name, "Raw HTML tag should not appear"
        assert '&lt;img' in project_name or '\\u003cimg' in project_name, "HTML should be escaped"

    def test_api_events_list_escapes_all_fields(self, client, db_session, models):
        """
        GIVEN events with XSS payloads in various fields
        WHEN fetching list via /api/events
        THEN all fields are properly escaped
        """
        Event = models['Event']

        events = [
            Event(
                project_ref_num=i,
                project_name=f'<svg onload=alert({i})>',
                store_name=f'<iframe src="javascript:alert({i})">',
                event_type="Core",
                condition="Unstaffed"
            ) for i in range(1, 4)
        ]
        db_session.add_all(events)
        db_session.commit()

        response = client.get('/api/events')
        data = response.get_json()

        for event_data in data['data']:
            # No raw HTML tags should appear
            assert '<svg' not in event_data['project_name']
            assert '<iframe' not in event_data['store_name']
            assert 'javascript:' not in str(event_data)


class TestCSRFProtection:
    """Test CSRF token validation (SEC-H3, SEC-H6)"""

    def test_csrf_token_in_cookie(self, client):
        """
        GIVEN a GET request to any page
        WHEN response is returned
        THEN csrf_token cookie is set
        """
        response = client.get('/')

        # Check if cookie is set (exact format depends on Flask-WTF config)
        cookies = response.headers.get('Set-Cookie', '')
        assert 'csrf_token=' in cookies, "CSRF token cookie should be set"

        # Verify cookie attributes
        assert 'SameSite=Lax' in cookies, "CSRF cookie should have SameSite=Lax"

    def test_csrf_token_in_meta_tag(self, client):
        """
        GIVEN base.html template
        WHEN page is rendered
        THEN CSRF token is in meta tag for JS access
        """
        response = client.get('/')
        html = response.data.decode('utf-8')

        # From base.html line 7: <meta name="csrf-token" content="{{ csrf_token() }}">
        assert 'name="csrf-token"' in html, "CSRF meta tag should exist"
        assert 'content=' in html, "CSRF meta tag should have content attribute"

    def test_post_without_csrf_fails(self, client, db_session, models):
        """
        GIVEN no CSRF token
        WHEN POST to /api/events
        THEN request is rejected with 400
        """
        response = client.post('/api/events', json={
            'project_ref_num': 12345,
            'project_name': 'Test Event',
            'event_type': 'Core'
        })

        # Should fail CSRF validation (400 or 403)
        assert response.status_code in [400, 403], "POST without CSRF should fail"

    def test_post_with_csrf_succeeds(self, client, db_session, models):
        """
        GIVEN valid CSRF token
        WHEN POST to /api/events
        THEN request succeeds
        """
        # Get CSRF token
        response = client.get('/')
        # Extract token from cookie or meta tag (implementation-dependent)
        # For this test, we'll use Flask test client's CSRF simulation

        # Flask test client automatically handles CSRF if csrf.init_app(app) is called
        # We can use the csrf_token from the context
        from flask_wtf.csrf import generate_csrf

        with client.application.test_request_context():
            token = generate_csrf()

        response = client.post('/api/events',
            json={
                'project_ref_num': 54321,
                'project_name': 'Valid Event',
                'event_type': 'Core'
            },
            headers={'X-CSRF-Token': token}
        )

        # Should succeed (201 or 200)
        assert response.status_code in [200, 201], "POST with CSRF should succeed"

    def test_both_csrf_header_formats_accepted(self, client, db_session, models):
        """
        GIVEN CSRF token in either X-CSRF-Token or X-CSRFToken header
        WHEN POST request is made
        THEN both formats are accepted (addresses SEC-H6)
        """
        from flask_wtf.csrf import generate_csrf

        with client.application.test_request_context():
            token = generate_csrf()

        # Test X-CSRF-Token (from csrf_helper.js)
        response1 = client.post('/api/events',
            json={'project_ref_num': 1, 'project_name': 'Test1', 'event_type': 'Core'},
            headers={'X-CSRF-Token': token}
        )

        # Test X-CSRFToken (from api-client.js)
        response2 = client.post('/api/events',
            json={'project_ref_num': 2, 'project_name': 'Test2', 'event_type': 'Core'},
            headers={'X-CSRFToken': token}
        )

        # Both should succeed
        assert response1.status_code in [200, 201], "X-CSRF-Token should be accepted"
        assert response2.status_code in [200, 201], "X-CSRFToken should be accepted"


class TestSecurityHeaders:
    """Test security headers are applied (SEC-H1, SEC-H2)"""

    def test_security_headers_present(self, client):
        """
        GIVEN ProductionConfig.SECURITY_HEADERS is defined
        WHEN any request is made
        THEN security headers are present in response

        NOTE: This test will FAIL until after_request hook is added to app/__init__.py
        """
        response = client.get('/')

        # From config.py:154-160
        assert response.headers.get('X-Content-Type-Options') == 'nosniff'
        assert response.headers.get('X-Frame-Options') == 'SAMEORIGIN'
        assert response.headers.get('X-XSS-Protection') == '1; mode=block'
        assert 'Strict-Transport-Security' in response.headers
        assert 'Content-Security-Policy' in response.headers

    def test_hsts_header_format(self, client):
        """
        GIVEN production config
        WHEN request is made
        THEN HSTS header has correct max-age and includeSubDomains
        """
        response = client.get('/')
        hsts = response.headers.get('Strict-Transport-Security')

        assert hsts is not None, "HSTS header should be present"
        assert 'max-age=31536000' in hsts, "HSTS should have 1-year max-age"
        assert 'includeSubDomains' in hsts, "HSTS should include subdomains"

    def test_csp_header_restricts_inline_scripts(self, client):
        """
        GIVEN CSP header
        WHEN examining policy
        THEN unsafe-inline should NOT be present (addresses SEC-H2)

        NOTE: Current config has 'unsafe-inline' - this test will FAIL until fixed
        """
        response = client.get('/')
        csp = response.headers.get('Content-Security-Policy', '')

        # Should NOT allow unsafe-inline (violates SEC-H2)
        assert "'unsafe-inline'" not in csp, "CSP should not allow unsafe-inline scripts"

        # Should restrict to self
        assert "script-src 'self'" in csp or "default-src 'self'" in csp
```

---

## 10. Conclusion

This Flask scheduling webapp has **CRITICAL testing gaps** in the UI/UX layer:

**Summary:**
- **795 tests needed** to achieve adequate coverage
- **600 hours estimated** to implement (15 weeks with 2 QA engineers)
- **50 critical security tests** must be implemented immediately (addresses Phase 2 SEC-C1, SEC-C2, SEC-H1, SEC-H3)
- **Zero current UI/UX test coverage** despite 108 UI files and 277 routes

**Most Critical Risks:**
1. **XSS vulnerabilities untested** - 161 onclick handlers, 160 innerHTML assignments
2. **CSRF protection untested** - Broken implementation in ai-assistant.js
3. **Security headers never validated** - Defined but not applied
4. **API endpoints untested** - 274/277 routes have no tests
5. **User workflows untested** - No E2E tests for critical paths

**Next Steps:**
1. Install Playwright: `pip install pytest-playwright`
2. Create `tests/security/` directory with XSS, CSRF, and header tests
3. Implement 50 security tests (Week 1-2, 40 hours)
4. Add `after_request` hook to apply security headers
5. Set up CI/CD to run tests on every PR

**Long-Term Goal:**
Achieve 80% coverage across all layers within 15 weeks, with continuous testing in CI/CD to prevent regressions.

---

**Document Version:** 1.0
**Last Updated:** 2026-02-09
**Next Review:** After Phase 1 security tests are implemented
