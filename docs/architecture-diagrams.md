# Architecture Diagrams

> Updated: March 21, 2026

Mermaid diagrams documenting the system architecture, data flows, and key workflows.

---

## 1. System Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        PWA["PWA (Installable)"]
        SW["Service Worker<br/>Cache + Offline"]
        MOBILE["Mobile Bottom Nav"]
        DESKTOP["Desktop Sidebar"]
    end

    subgraph "External Systems"
        WALMART["Walmart Retail Link EDR"]
        MVRETAIL["MVRetail Crossmark API"]
        OLLAMA["Ollama Local LLM"]
    end

    subgraph "Presentation"
        TEMPLATES["Jinja2 Templates<br/>(role-aware)"]
        JS["ES6 Frontend Modules"]
        CSS["Design Token System"]
    end

    subgraph "Application"
        AUTH["Auth + RBAC<br/>(Redis Sessions)"]
        ROUTES["26 Flask Blueprints"]
        GREEDY["Greedy Scheduler"]
        CPSAT["CP-SAT Solver<br/>(OR-Tools)"]
        SERVICES["Business Services"]
        AI["RAG AI Assistant"]
        ML["ML Employee Ranking"]
    end

    subgraph "Data Layer"
        MODELS["35 SQLAlchemy Models"]
        DB[("PostgreSQL / SQLite")]
        REDIS[("Redis<br/>Sessions + Cache")]
    end

    subgraph "Background"
        CELERY["Celery Workers"]
        APSCHEDULER["APScheduler"]
    end

    PWA --> SW
    PWA --> TEMPLATES
    MOBILE --> ROUTES
    DESKTOP --> ROUTES
    TEMPLATES --> ROUTES
    JS --> ROUTES

    ROUTES --> AUTH
    ROUTES --> SERVICES
    ROUTES --> AI
    SERVICES --> GREEDY
    SERVICES --> CPSAT
    SERVICES --> ML
    SERVICES --> MODELS
    MODELS --> DB
    AUTH --> REDIS

    SERVICES --> MVRETAIL
    SERVICES --> WALMART
    AI --> OLLAMA
    CELERY --> MVRETAIL
    APSCHEDULER --> SERVICES
```

---

## 2. Role-Based Access Hierarchy

```mermaid
graph TB
    subgraph "Authentication"
        CL["Crossmark Login<br/>(Username + Password)"]
        PL["PIN Login<br/>(Employee ID + PIN)"]
    end

    subgraph "Roles"
        SUP["Supervisor<br/>Full Access"]
        LEAD["Lead<br/>Team View + Personal"]
        SPEC["Specialist<br/>Personal Only"]
    end

    subgraph "Supervisor Pages"
        CMD["Command Center"]
        DV["Daily View"]
        CAL["Calendar"]
        AUTO["Auto-Scheduler"]
        EMP["Employee Management"]
        ATT_S["Attendance (edit)"]
        AVAIL["Availability Management"]
        REPORTS["Reports (7 types)"]
        PRINT["Printing / PDFs"]
        VALID["Weekly Validation"]
        ADMIN["Settings / Admin"]
        INV["Demo Supplies"]
        LOST["Lost Demos"]
    end

    subgraph "Lead Pages"
        TEAM_DV["Team Daily View<br/>(read-only schedule)"]
        LEAD_ATT["Lead Attendance<br/>(record only)"]
        TEAM_TO["Team Time Off<br/>(view approved)"]
    end

    subgraph "Shared Pages (Specialist + Lead)"
        DASH["My Dashboard"]
        EVENTS["My Events"]
        MONTHLY["Monthly Schedule"]
        TIMEOFF["My Time Off<br/>(submit requests)"]
    end

    CL --> SUP
    PL --> LEAD
    PL --> SPEC

    SUP --> CMD & DV & CAL & AUTO & EMP & ATT_S & AVAIL & REPORTS & PRINT & VALID & ADMIN & INV & LOST
    SUP --> TEAM_DV

    LEAD --> DASH & EVENTS & MONTHLY & TIMEOFF
    LEAD --> TEAM_DV & LEAD_ATT & TEAM_TO

    SPEC --> DASH & EVENTS & MONTHLY & TIMEOFF

    style SUP fill:#0ea5e9,color:#fff
    style LEAD fill:#8b5cf6,color:#fff
    style SPEC fill:#22c55e,color:#fff
```

---

## 3. Authentication Flow

```mermaid
sequenceDiagram
    participant User
    participant Browser
    participant Flask as Flask App
    participant Redis as Redis
    participant API as Crossmark API

    Note over User,API: Supervisor Login Flow
    User->>Browser: Enter Crossmark credentials
    Browser->>Flask: POST /login
    Flask->>Flask: Clear singleton external_api state<br/>(phpsessid, cookies, authenticated)
    Flask->>API: Authenticate with Crossmark
    API-->>Flask: Success + user info
    Flask->>Flask: Destroy any old session cookie
    Flask->>Redis: Save new session (24h TTL)
    Flask-->>Browser: Set session_id cookie + redirect to /loading
    Browser->>Flask: GET /loading (SSE progress)
    Flask->>API: Sync events/employees
    Flask-->>Browser: Redirect to Daily View

    Note over User,API: Employee PIN Login Flow
    User->>Browser: Enter Employee ID + PIN
    Browser->>Flask: POST /employee-login
    Flask->>Flask: Look up Employee by ID
    Flask->>Flask: Verify PIN (bcrypt)
    Flask->>Flask: Destroy any old session cookie
    Flask->>Redis: Save new session with role
    Flask-->>Browser: Set session_id cookie
    Browser->>Browser: Redirect to My Dashboard

    Note over User,API: Session Lifecycle
    loop Every page load
        Browser->>Flask: Request with session_id cookie
        Flask->>Redis: Validate session
        Flask->>Flask: Check inactivity (10 min)
        alt Session valid
            Flask->>Redis: Update last_activity
            Flask-->>Browser: Serve page
        else Session expired
            Flask->>Redis: Delete session
            Flask-->>Browser: Redirect to login
        end
    end
```

---

## 4. Auto-Scheduler Pipeline

```mermaid
flowchart TB
    START([User clicks Run Auto-Schedule]) --> SOLVER{Solver Type?}

    SOLVER -->|CP-SAT| CPSAT_P1["Phase 1: Due-Date Priority Pre-Pass<br/>(swap posted schedules)"]
    SOLVER -->|Greedy| G_W1["Wave 1: Juicer Rotation Events"]

    subgraph "CP-SAT Solver (Optimal)"
        CPSAT_P1 --> CPSAT_P2["Phase 2: Solver WITHOUT bumping<br/>(assign unscheduled events)"]
        CPSAT_P2 --> CPSAT_INJ["Inject Phase 2 results<br/>as existing assignments"]
        CPSAT_INJ --> CPSAT_P3["Phase 3: Solver WITH bumping<br/>(retry Phase 2 failures)"]
        CPSAT_P3 --> CPSAT_P4["Phase 4: Due-Date Priority Post-Pass"]
        CPSAT_P4 --> CPSAT_REV["Post-Solve Review<br/>(remove constraint violations)"]
    end

    subgraph "Greedy Engine (Fallback)"
        G_W1 --> G_W2["Wave 2: Core Events<br/>(empty-slot-first, then bump)"]
        G_W2 --> G_W3["Wave 3: Freeosk/Digital Events"]
        G_W3 --> G_W4["Wave 4: Non-Production Juicer"]
        G_W4 --> G_W5["Wave 5: Other Events"]
    end

    CPSAT_REV --> PENDING["Create PendingSchedule Records"]
    G_W5 --> PENDING

    PENDING --> REVIEW["Supervisor Reviews<br/>Proposed Assignments"]
    REVIEW --> EDIT{"Edit needed?"}
    EDIT -->|Yes| MODIFY["Modify assignment"]
    MODIFY --> REVIEW
    EDIT -->|No| APPROVE["Approve All"]

    APPROVE --> BUMP_CHECK{"Locked day<br/>conflicts?"}
    BUMP_CHECK -->|Yes| WARN["Show warning<br/>(409 Conflict)"]
    WARN --> FORCE{"Force override?"}
    FORCE -->|Yes| EXECUTE
    FORCE -->|No| REVIEW
    BUMP_CHECK -->|No| EXECUTE

    EXECUTE["Execute Approval:<br/>1. Delete superseded schedules<br/>2. Unschedule bumped events<br/>3. Create Schedule records<br/>4. Sync to Crossmark API"]
    EXECUTE --> DONE([Schedules Live])

    style CPSAT_P2 fill:#dbeafe,stroke:#3b82f6
    style CPSAT_P3 fill:#fef3c7,stroke:#f59e0b
    style G_W2 fill:#dbeafe,stroke:#3b82f6
```

---

## 5. Bump Logic Detail

```mermaid
flowchart TB
    EVENT["Core Event needs scheduling"] --> SEARCH["Search days: start_date → due_date"]
    SEARCH --> DAY_CHECK{"Check each day"}

    DAY_CHECK --> TODAY{"Today or earlier?"}
    TODAY -->|Yes| SKIP_T["Skip (in-progress)"]

    TODAY -->|No| LOCKED{"Day locked?"}
    LOCKED -->|Yes| SKIP_L["Skip (locked)"]

    LOCKED -->|No| BUFFER{"Within 3-day buffer?"}
    BUFFER -->|Yes| BUMPED{"Was this event bumped?"}
    BUMPED -->|No| SKIP_B["Skip (buffer)"]
    BUMPED -->|Yes| TRY_SLOT["Try empty slot<br/>(bypasses buffer)"]

    BUFFER -->|No| TRY_SLOT

    TRY_SLOT --> SLOT_FOUND{"Empty slot?"}
    SLOT_FOUND -->|Yes| SCHEDULED(["Scheduled!"])

    SLOT_FOUND -->|No| TRY_BUMP["Try bump less-urgent event"]
    TRY_BUMP --> BUMP_FOUND{"Bumpable event<br/>with later due date?"}
    BUMP_FOUND -->|Yes| DO_BUMP["Take slot, re-queue bumped event"]
    BUMP_FOUND -->|No| NEXT_DAY["Try next day"]

    DO_BUMP --> REQUEUE["Bumped event enters queue<br/>(marked for buffer bypass)"]
    REQUEUE --> SCHEDULED

    NEXT_DAY --> DAY_CHECK
    SKIP_T --> DAY_CHECK
    SKIP_L --> DAY_CHECK
    SKIP_B --> DAY_CHECK

    DAY_CHECK -->|No more days| FAILED(["Failed — create failure record"])

    style SCHEDULED fill:#d1fae5,stroke:#10b981
    style FAILED fill:#fee2e2,stroke:#ef4444
    style DO_BUMP fill:#fef3c7,stroke:#f59e0b
```

---

## 6. Time-Off Approval Workflow

```mermaid
stateDiagram-v2
    [*] --> Pending: Employee submits request

    Pending --> Approved: Supervisor approves
    Pending --> Denied: Supervisor denies (with reason)

    Approved --> [*]: Blocks scheduling for those dates
    Denied --> [*]: Does NOT block scheduling

    note right of Pending
        Visible in "Pending Approvals" tab
    end note

    note right of Approved
        Visible in "Time Off Requests" tab
        with green badge
    end note

    note right of Denied
        Visible in "Time Off Requests" tab
        with red badge + reason
    end note
```

Note: Supervisor-created time-off entries (via the Availability page) default directly to `approved` status — they skip the pending step.

---

## 7. PWA & Offline Architecture

```mermaid
flowchart LR
    subgraph "Browser"
        APP["PC Events App"]
        SW["Service Worker"]
        CACHE["Cache Storage"]
        LS["localStorage"]
    end

    subgraph "Network"
        SERVER["Flask Server"]
    end

    APP -->|"fetch()"| SW
    SW -->|"Strategy: cache-first"| STATIC["/static/* assets"]
    SW -->|"Strategy: network-first"| API_REQ["/api/* requests"]
    SW -->|"Strategy: network-first + fallback"| HTML_REQ["HTML pages"]

    STATIC --> CACHE
    API_REQ -->|Online| SERVER
    API_REQ -->|Offline| CACHE
    API_REQ -->|Both fail| ERROR["Return {error: 'Offline'}"]
    HTML_REQ -->|Online| SERVER
    HTML_REQ -->|Offline| CACHE
    HTML_REQ -->|Both fail| OFFLINE["/offline page"]

    LS -->|"pwaInstallDismissed"| INSTALL["Install banner state"]
    LS -->|"pc_schedule_fingerprint"| NOTIF["Change detection"]

    style OFFLINE fill:#fee2e2,stroke:#ef4444
    style CACHE fill:#dbeafe,stroke:#3b82f6
```

### Caching Strategies

| Pattern | Used For | Behavior |
|---------|----------|----------|
| **Cache-first** | `/static/*` (CSS, JS, images) | Serve from cache immediately, fetch in background |
| **Network-first** | `/api/*` (data requests) | Try network, cache response, serve stale on failure |
| **Network-first + fallback** | HTML pages | Try network, then cache, then `/offline` page |

---

## 8. Database Model Relationships

```mermaid
erDiagram
    Employee ||--o{ Schedule : "assigned to"
    Employee ||--o{ EmployeeTimeOff : "requests"
    Employee ||--o{ EmployeeAttendance : "tracked"
    Employee ||--o{ RotationAssignment : "assigned"
    Employee ||--o{ EmployeeWeeklyAvailability : "has"
    Employee ||--o{ EmployeeAvailabilityOverride : "overrides"

    Event ||--o{ Schedule : "scheduled as"
    Event ||--o{ Note : "has"
    Event ||--o| LostDemo : "confirmed as"
    Event ||--o{ PendingSchedule : "proposed"
    Event ||--o| EventTypeOverride : "overridden"
    Event ||--o| EventSchedulingOverride : "configured"

    SchedulerRunHistory ||--o{ PendingSchedule : "produces"
    SchedulerRunHistory ||--o{ ScheduleNotification : "generates"

    PendingSchedule }o--|| Employee : "assigned to"
    PendingSchedule }o--|| Event : "for event"

    Schedule }o--|| Employee : "assigned to"
    Schedule }o--|| Event : "for event"

    Employee {
        string id PK "US######"
        string name
        string job_title
        boolean is_active
        string pin_hash
        boolean has_account
    }

    Event {
        string project_ref_num PK
        string event_type
        datetime start_datetime
        datetime due_datetime
        string condition
    }

    Schedule {
        int id PK
        string event_ref_num FK
        string employee_id FK
        datetime schedule_datetime
        int shift_block
    }

    PendingSchedule {
        int id PK
        int scheduler_run_id FK
        string status "pending|approved|superseded|api_failed"
        boolean is_swap
        string bumped_event_ref_num
    }

    EmployeeTimeOff {
        int id PK
        string employee_id FK
        date start_date
        date end_date
        string status "pending|approved|denied"
        string reviewed_by
        string denial_reason
    }
```

---

## 9. Event Priority & Scheduling Order

```mermaid
graph LR
    subgraph "Priority Order (1 = highest)"
        J["1. Juicer Production<br/>9h, rotation only"]
        DS["2. Digital Setup<br/>30min, Lead/Supervisor"]
        DR["3. Digital Refresh<br/>15min, Lead/Supervisor"]
        F["4. Freeosk<br/>15min, Lead/Supervisor"]
        DT["5. Digital Teardown<br/>15min, Lead/Supervisor"]
        C["6. Core<br/>6.5h, max 1/day, 6/week"]
        S["7. Supervisor<br/>5min, auto-paired with Core"]
        D["8. Digitals<br/>15min, Lead/Supervisor"]
        O["9. Other<br/>15min, any employee"]
    end

    J --> DS --> DR --> F --> DT --> C --> S --> D --> O

    style J fill:#FF6B6B,color:#fff
    style C fill:#95E1D3,color:#000
    style S fill:#DDA0DD,color:#000
    style DS fill:#4ECDC4,color:#fff
    style DR fill:#4ECDC4,color:#fff
    style DT fill:#4ECDC4,color:#fff
    style D fill:#4ECDC4,color:#fff
    style F fill:#FFD93D,color:#000
    style O fill:#e5e7eb,color:#000
```

---

## 10. Deployment Architecture

```mermaid
graph TB
    INTERNET["Internet (HTTPS)"] --> CF["Cloudflare Tunnel<br/>(zero-trust, DDoS, SSL)"]
    CF --> NGINX["Nginx Reverse Proxy<br/>(static files, security headers)"]
    NGINX --> GUNICORN["Gunicorn WSGI<br/>(1 gevent worker, 120s timeout)"]

    GUNICORN --> FLASK["Flask App"]
    FLASK --> PG[("PostgreSQL 15")]
    FLASK --> REDIS_D[("Redis 7<br/>(sessions + cache)")]
    FLASK --> CELERY_D["Celery Worker<br/>(background sync)"]
    CELERY_D --> REDIS_D

    style CF fill:#f59e0b,color:#fff
    style GUNICORN fill:#3b82f6,color:#fff
    style PG fill:#336791,color:#fff
    style REDIS_D fill:#dc382d,color:#fff
```

> **Critical**: Single Gunicorn worker is required — Walmart EDR MFA uses global session state that doesn't work with multiple workers.
