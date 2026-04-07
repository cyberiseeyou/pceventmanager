# Background Sync Daemon — Design Spec

**Date:** 2026-04-06
**Status:** Draft
**Author:** Claude + Elliot

---

## Problem

Every time a user logs in (or the session times out from idle), the app hits the Crossmark MVRetail API for a full data refresh — a 40+ second wait. Supervisor sessions have a 10-minute inactivity timeout, making this a frequent pain point. Meanwhile, upstream changes (new events, cancellations) aren't detected until the next login, meaning the local schedule can drift out of sync with Crossmark.

## Goals

1. **Background sync daemon** — Poll Crossmark MVRetail every 5 minutes, incrementally upsert changes into the local SQLite database, and detect conflicts.
2. **Eliminate login wait** — With data always fresh, login does a quick delta check (< 2s) instead of a full 40s refresh.
3. **Persistent supervisor sessions** — Give supervisors the same 30-day persistent login that leads/specialists already have, with a PIN/biometric app lock for security.
4. **Change awareness** — Notify the supervisor via push notification when upstream changes are detected (new events, cancellations, conflicts).
5. **Conflict detection** — Flag discrepancies between local and Crossmark data (e.g., local shows scheduled but Crossmark doesn't) as red flags for manual investigation.

## Non-Goals

- Auto-running the auto-scheduler. The supervisor decides when to re-optimize.
- Bidirectional sync changes. Push to Crossmark remains as-is (existing Celery tasks / manual triggers).
- Replacing the existing `DatabaseRefreshService` — it stays as a fallback if the daemon is down.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    Flask App (ser6)                  │
│                                                     │
│  ┌──────────────┐    ┌───────────────────────────┐  │
│  │  APScheduler  │───▶│  SyncDaemon Service       │  │
│  │  (every 5min) │    │  - fetch from Crossmark   │  │
│  └──────────────┘    │  - incremental upsert      │  │
│                      │  - detect conflicts         │  │
│                      │  - log to SyncChangeLog     │  │
│                      │  - send push notifications  │  │
│                      └───────────┬───────────────┘  │
│                                  │                   │
│                      ┌───────────▼───────────────┐  │
│                      │  SQLite Database            │  │
│                      │  - Event, Schedule, etc.    │  │
│                      │  - SyncChangeLog (new)      │  │
│                      └───────────────────────────┘  │
│                                                     │
│  ┌──────────────┐    ┌───────────────────────────┐  │
│  │  Auth Route   │───▶│  Quick delta check on     │  │
│  │  (login)      │    │  login (< 2s) instead of  │  │
│  └──────────────┘    │  full 40s refresh          │  │
│                      └───────────────────────────┘  │
│                                                     │
│  ┌──────────────┐    ┌───────────────────────────┐  │
│  │  Lock Screen  │───▶│  PIN or WebAuthn biometric │  │
│  │  (client-side)│    │  after inactivity          │  │
│  └──────────────┘    └───────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## Component 1: SyncChangeLog Model

**File:** `app/models/sync_change_log.py`

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT, PK | Auto-increment |
| `change_type` | VARCHAR(20) | `new_event`, `cancelled`, `modified`, `conflict` |
| `entity_type` | VARCHAR(20) | `event` (expandable to `schedule`, `employee`) |
| `entity_id` | VARCHAR(100) | `project_ref_num` or `external_id` of the affected record |
| `summary` | TEXT | Human-readable description, e.g., "New event: Digital Setup at Store #1234 on Apr 10" |
| `field_changes` | JSON, nullable | For `modified`/`conflict`: `{"start_datetime": {"local": "...", "upstream": "..."}}` |
| `is_conflict` | BOOLEAN | `True` = red flag needing investigation |
| `detected_at` | DATETIME | When the daemon detected this change |
| `resolved` | BOOLEAN, default False | Only meaningful for conflicts |
| `resolution_notes` | TEXT, nullable | Supervisor's notes on how a conflict was resolved |

**Indexes:** `idx_sync_changelog_type_status(change_type, resolved)`, `idx_sync_changelog_detected(detected_at)`

---

## Component 2: Persistent Supervisor Sessions + App Lock

### 2a. Persistent Sessions

**File to modify:** `app/routes/auth.py`

**Change:** Add `'supervisor'` to `PERSISTENT_SESSION_ROLES`.

Currently:
```python
PERSISTENT_SESSION_ROLES = ['lead', 'specialist']
```

After:
```python
PERSISTENT_SESSION_ROLES = ['lead', 'specialist', 'supervisor']
```

This gives supervisors the same 30-day session TTL with no inactivity timeout. The `_is_persistent_session()` helper already gates all the timeout logic.

### 2b. App Lock Screen

**Purpose:** Prevent unauthorized access on shared/unattended devices when supervisor is persistently logged in.

**Lock trigger:** After configurable inactivity period (default: 5 minutes of no interaction). Client-side JavaScript timer tracks mouse/touch/keyboard activity.

**Unlock methods (supervisor chooses during setup):**

1. **PIN (always available):**
   - 4-6 digit PIN set by supervisor on first use after this feature ships
   - Stored as bcrypt hash in Redis session data (alongside existing session fields)
   - Verified server-side via `POST /api/auth/verify-pin`
   - 5 failed attempts = session destroyed, must re-login

2. **WebAuthn Biometric (where supported):**
   - Supervisor registers device fingerprint/face via WebAuthn API
   - Credential stored in `PushSubscription`-adjacent table or new `WebAuthnCredential` model
   - On lock screen, browser prompts for biometric
   - Falls back to PIN if biometric unavailable or fails

**Implementation:** The lock is a full-screen overlay rendered client-side. The server session remains alive. The overlay intercepts all interaction until PIN/biometric verification succeeds.

**New files:**
- `app/static/js/components/app-lock.js` — lock screen UI and inactivity timer
- `app/templates/components/app-lock.html` — lock screen template partial
- `app/routes/auth.py` — new endpoints: `POST /api/auth/set-pin`, `POST /api/auth/verify-pin`, WebAuthn registration/verification endpoints

---

## Component 3: Sync Daemon Service

**New file:** `app/services/sync_daemon.py`

### Core Loop (APScheduler job, every 5 minutes)

```
1. ensure_authenticated()
   └─ Reuse existing SessionAPIService singleton
   └─ Auto-reauths if session expired (< 1 hour)

2. Fetch upstream data (parallel, ~20s)
   ├─ get_all_planning_events_parallel() — full 150-day window
   └─ get_scheduled_events() — scheduling API data

3. Incremental comparison
   For each upstream event:
   ├─ Lookup local Event by external_id / project_ref_num
   ├─ NOT FOUND locally → INSERT new event
   │   └─ Log: SyncChangeLog(change_type='new_event')
   ├─ FOUND, fields match → SKIP
   ├─ FOUND, only safe fields differ → UPDATE local record
   │   └─ Safe fields (auto-apply): project_name, store_name,
   │   │   estimated_time, condition (when no local schedule exists)
   │   └─ Log: SyncChangeLog(change_type='modified')
   └─ FOUND, protected fields differ → FLAG as conflict
       └─ Protected fields (never auto-overwrite):
       │   start_datetime, due_datetime,
       │   is_scheduled (local) vs upstream scheduled status,
       │   any field on an event that has a local Schedule record
       └─ Log: SyncChangeLog(change_type='conflict', is_conflict=True)
       └─ DO NOT overwrite local data

   For each local event NOT in upstream:
   └─ Event removed/cancelled upstream
       └─ Update local condition to 'Cancelled'
       └─ Log: SyncChangeLog(change_type='cancelled')

4. Send push notification if changes detected
   └─ FYI: "Sync: 3 new events, 1 cancelled"
   └─ Alert: "Conflict: Event #1234 schedule mismatch — investigate"
   └─ Target: supervisor role push subscriptions only

5. Update sync metadata
   └─ Store last_successful_sync timestamp in SystemSetting
   └─ Store last_sync_duration for monitoring
```

### Conflict Detection Rules

| Scenario | Classification | Action |
|----------|---------------|--------|
| New event in Crossmark, not in local | `new_event` | Auto-insert |
| Event in local, not in Crossmark | `cancelled` | Auto-update condition to Cancelled |
| Crossmark changed project_name, store_name, estimated_time | `modified` | Auto-update |
| Crossmark changed start_datetime or due_datetime | `conflict` | Flag, don't overwrite |
| Local `is_scheduled=True`, Crossmark shows unscheduled | `conflict` | Flag, don't overwrite |
| Local `is_scheduled=False`, Crossmark shows scheduled by someone else | `conflict` | Flag, don't overwrite |
| Crossmark shows cancelled, local shows active with schedule | `conflict` | Flag (cancellation + existing schedule needs attention) |
| Crossmark shows cancelled, local shows active without schedule | `cancelled` | Auto-apply cancellation |

### Registration in Flask App

**File to modify:** `app/__init__.py` → `setup_background_tasks()`

Add alongside the existing Walmart session cleanup job:

```python
from app.services.sync_daemon import run_sync_cycle

scheduler.add_job(
    func=run_sync_cycle,
    trigger=IntervalTrigger(seconds=300),  # 5 minutes
    id='crossmark_sync_daemon',
    name='Crossmark MVRetail background sync',
    max_instances=1,  # prevent overlapping runs
    misfire_grace_time=60
)
```

### SQLite Write Locking

SQLite allows one writer at a time. The daemon runs every 5 min and writes for a few seconds at most. Risk of contention with the Flask app is low but we mitigate by:
- Using short, batched transactions (commit every 50 records)
- Setting `PRAGMA busy_timeout = 5000` (wait up to 5s for lock)
- The daemon runs in the same process, so Flask-SQLAlchemy's scoped session handles coordination

---

## Component 4: Login Flow Change

**File to modify:** `app/routes/auth.py` (login route), `app/services/database_refresh_service.py`

### New Login Flow

```
User submits credentials
  └─ Authenticate against Crossmark API (existing logic)
  └─ Create persistent Redis session (30-day TTL, no inactivity timeout)
  └─ Check: has daemon synced within last 5 minutes?
      ├─ YES → Skip loading page, redirect straight to app
      │   └─ Show "Last synced X min ago" indicator in header
      └─ NO → Fall back to current DatabaseRefreshService.refresh()
          └─ Loading page with progress bar (existing behavior)
          └─ This handles: first run, daemon crashed, daemon disabled
```

**How to check daemon health:**
- Read `last_successful_sync` from `SystemSetting`
- If `now - last_successful_sync < 5 minutes` → daemon is healthy, skip refresh

---

## Component 5: Push Notifications for Supervisor

### Investigation Needed

The existing Web Push infrastructure (`PushSubscription` model, VAPID keys, `/api/push` endpoints) should work for supervisors. The hypothesis is that push subscriptions persist in the browser's service worker independently of server session state. With persistent sessions, this should be reliable.

**Action items:**
1. Verify VAPID keys are configured in `.env`
2. Test that supervisor can register a push subscription
3. Verify subscription survives the (now removed) inactivity timeout
4. If the service worker registration is gated behind a role check, ensure supervisor is included

### Notification Format

**FYI notifications (informational):**
```json
{
  "title": "Crossmark Sync Update",
  "body": "3 new events added, 1 cancelled since last check",
  "icon": "/static/img/icon-192.png",
  "data": {"url": "/sync/changes"}
}
```

**Conflict notifications (actionable):**
```json
{
  "title": "⚠ Schedule Conflict Detected",
  "body": "Event #1234 shows different schedule in Crossmark — tap to review",
  "icon": "/static/img/icon-192.png",
  "tag": "sync-conflict",
  "requireInteraction": true,
  "data": {"url": "/sync/conflicts"}
}
```

### New UI Pages

- **`/sync/changes`** — Activity feed of all recent sync changes (SyncChangeLog). Filterable by type.
- **`/sync/conflicts`** — Filtered view showing only unresolved conflicts with side-by-side local vs upstream data.

---

## Key Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `app/models/sync_change_log.py` | CREATE | SyncChangeLog model |
| `app/services/sync_daemon.py` | CREATE | Daemon service with sync loop |
| `app/routes/auth.py` | MODIFY | Persistent supervisor sessions, PIN endpoints, login flow change |
| `app/__init__.py` | MODIFY | Register daemon APScheduler job, register new model |
| `app/services/database_refresh_service.py` | MODIFY | Add daemon health check bypass |
| `app/static/js/components/app-lock.js` | CREATE | Lock screen UI + inactivity timer |
| `app/templates/components/app-lock.html` | CREATE | Lock screen template |
| `app/templates/sync_changes.html` | CREATE | Sync activity feed page |
| `app/templates/sync_conflicts.html` | CREATE | Conflict review page |
| `app/routes/sync.py` | CREATE | Routes for /sync/changes, /sync/conflicts |
| `migrations/versions/xxx_add_sync_change_log.py` | CREATE | Migration for new table |

---

## Testing Strategy

1. **Unit tests for SyncDaemon:**
   - Mock API responses, verify correct change detection (new, modified, conflict, cancelled)
   - Verify conflict rules produce correct classifications
   - Verify SyncChangeLog records are created correctly

2. **Integration test for login flow:**
   - With recent daemon sync → verify loading page is skipped
   - Without recent sync → verify fallback to full refresh

3. **Manual testing:**
   - Run daemon, add event in Crossmark, verify it appears locally within 5 min
   - Cancel event in Crossmark, verify local update
   - Manually change a schedule datetime in local DB, let daemon detect conflict
   - Verify push notification delivery to supervisor device
   - Test PIN lock/unlock cycle
   - Test WebAuthn registration and biometric unlock

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| SQLite write contention between daemon and Flask requests | Short batched transactions, `busy_timeout=5000`, same-process scoped sessions |
| API rate limiting from 5-min polling | Monitor response codes; back off to 15 min if 429s detected |
| Daemon crash goes unnoticed | Log last_successful_sync; login flow checks daemon health and falls back |
| Push notifications not working for supervisor | Investigate as part of implementation; service worker is session-independent |
| Parallel API fetch takes > 5 min (overlapping runs) | `max_instances=1` on APScheduler prevents overlap |
| Stale conflicts pile up | Periodic cleanup: auto-resolve conflicts older than 30 days with note "auto-expired" |

---

## Implementation Order

1. **SyncChangeLog model + migration** — Foundation for everything else
2. **SyncDaemon service** — Core sync loop with change detection
3. **APScheduler registration** — Wire daemon into app startup
4. **Persistent supervisor sessions** — Change `PERSISTENT_SESSION_ROLES`
5. **Login flow change** — Quick delta check, skip loading page
6. **Push notification integration** — Investigate + wire daemon to push service
7. **App lock screen (PIN)** — Basic security for persistent sessions
8. **App lock screen (WebAuthn)** — Biometric unlock
9. **Sync UI pages** — /sync/changes and /sync/conflicts views
10. **Testing** — Unit + integration + manual verification
