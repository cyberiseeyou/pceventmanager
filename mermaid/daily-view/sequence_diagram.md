# Daily View Data Flow - Sequence Diagram

This diagram shows the complete flow from user authentication to the daily schedule view being fully rendered with data.

## Main Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant Browser
    participant login.js
    participant auth.py as auth.py (Backend)
    participant CrossmarkAPI as Crossmark API
    participant Redis
    participant main.py as main.py (Backend)
    participant Template as daily_view.html
    participant DailyViewJS as daily-view.js
    participant api.py as api.py (Backend)
    participant Database as PostgreSQL

    %% ========================
    %% PHASE 1: Authentication
    %% ========================
    rect rgb(240, 248, 255)
        Note over User, Redis: Phase 1: User Authentication
        User->>Browser: Enter credentials
        Browser->>login.js: Submit login form
        login.js->>auth.py: POST /login (username, password)
        
        auth.py->>auth.py: Apply rate limit (5/min)
        auth.py->>CrossmarkAPI: external_api.login()
        CrossmarkAPI-->>auth.py: Auth success + user info
        
        auth.py->>auth.py: Extract/parse user name
        auth.py->>auth.py: Generate session_id (secrets.token_urlsafe)
        auth.py->>auth.py: Check event_times_configured
        
        auth.py->>Redis: save_session(session_id, session_data, ttl=86400)
        Redis-->>auth.py: OK
        
        auth.py-->>Browser: Response + Set-Cookie: session_id
        Browser->>Browser: Redirect to /schedule/daily/{today}
    end

    %% ========================
    %% PHASE 2: Route Handling
    %% ========================
    rect rgb(255, 248, 240)
        Note over Browser, Template: Phase 2: Route & Template Rendering
        Browser->>main.py: GET /schedule/daily/2025-12-16
        
        main.py->>auth.py: @require_authentication() decorator
        auth.py->>Redis: get_session(session_id)
        Redis-->>auth.py: session_data
        auth.py->>auth.py: Check expiration & inactivity
        auth.py-->>main.py: Authenticated ✓
        
        main.py->>main.py: Parse date, validate format
        main.py->>Database: Query RotationAssignment (juicer, lead)
        Database-->>main.py: Rotation data
        main.py->>Database: Query active Employees
        Database-->>main.py: Employee list
        
        main.py->>Template: render_template('daily_view.html', context)
        Template-->>Browser: HTML page (includes daily-view.js)
    end

    %% ========================
    %% PHASE 3: JavaScript Data Loading
    %% ========================
    rect rgb(240, 255, 240)
        Note over Browser, Database: Phase 3: Frontend Data Loading
        Browser->>DailyViewJS: DOMContentLoaded → new DailyView(date)
        
        DailyViewJS->>DailyViewJS: init()
        
        %% Load Summary
        DailyViewJS->>api.py: GET /api/daily-summary/{date}
        api.py->>Database: Query event types, timeslots
        Database-->>api.py: Summary data
        api.py-->>DailyViewJS: { event_types, timeslot_coverage }
        DailyViewJS->>DailyViewJS: renderEventTypeSummary()
        DailyViewJS->>DailyViewJS: renderTimeslotCoverage()
        
        %% Load Attendance
        DailyViewJS->>api.py: GET /api/attendance/scheduled-employees/{date}
        api.py->>Database: Query attendance records
        Database-->>api.py: Attendance data
        api.py-->>DailyViewJS: { scheduled_employees }
        DailyViewJS->>DailyViewJS: renderAttendanceList()
        
        %% Load Events
        DailyViewJS->>api.py: GET /api/daily-events/{date}
        api.py->>Database: Query Schedules + Events + Employees (JOIN)
        Database-->>api.py: Schedule/Event/Employee rows
        api.py->>api.py: build_event_dict() for each
        api.py->>api.py: Pair Core events with Supervisors
        api.py-->>DailyViewJS: { events: [...] }
        
        DailyViewJS->>DailyViewJS: renderEventCards(events)
        DailyViewJS->>DailyViewJS: attachEventCardListeners()
        DailyViewJS-->>User: Daily View fully rendered ✓
    end
```

## Simplified Overview

```mermaid
flowchart LR
    subgraph Authentication
        A[User Login] --> B[Crossmark API Auth]
        B --> C[Create Redis Session]
        C --> D[Set Cookie & Redirect]
    end
    
    subgraph Routing
        D --> E[daily_schedule_view]
        E --> F[Check Auth Decorator]
        F --> G[Query Rotations/Employees]
        G --> H[Render Template]
    end
    
    subgraph "Frontend Data Loading"
        H --> I[DailyView.init]
        I --> J[loadDailySummary]
        I --> K[loadAttendance]
        I --> L[loadDailyEvents]
        J --> M[Render Summary]
        K --> N[Render Attendance]
        L --> O[Render Event Cards]
    end
```

## Key Functions Reference

| Step | Function | File | Description |
|------|----------|------|-------------|
| 1 | `login()` | auth.py | POST /login - authenticate with Crossmark |
| 2 | `save_session()` | auth.py | Store session in Redis (24h TTL) |
| 3 | `daily_schedule_view()` | main.py | GET /schedule/daily/{date} |
| 4 | `require_authentication()` | auth.py | Decorator to validate session |
| 5 | `DailyView.init()` | daily-view.js | Initialize and load all data |
| 6 | `loadDailySummary()` | daily-view.js | Fetch /api/daily-summary |
| 7 | `loadAttendance()` | daily-view.js | Fetch /api/attendance/scheduled-employees |
| 8 | `loadDailyEvents()` | daily-view.js | Fetch /api/daily-events |
| 9 | `get_daily_events()` | api.py | Query and parse event data |
| 10 | `renderEventCards()` | daily-view.js | Generate event card HTML |
