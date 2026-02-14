# Scheduling Rules by Event Type

This document organizes **all** scheduling rules by event type, making it easy to look up every constraint, timing rule, and business logic that applies to a specific event type in one place.

For the category-based view of these same rules, see [scheduling_validation_rules.md](scheduling_validation_rules.md).

**Source files**: `constraint_validator.py`, `scheduling_engine.py`, `schedule_verification.py`, `cpsat_scheduler.py`, `rotation_manager.py`, `shift_block_config.py`

---

## Auto-Scheduler Priority Order

Events are processed in wave order. Higher-priority events are scheduled first and can bump lower-priority ones.

| Wave | Event Type | Priority | Description |
|------|-----------|----------|-------------|
| 1 | Juicer (Production, Survey, Deep Clean) | 1 (highest) | Rotation-based, can bump Core events |
| 2 | Core | 6 | Day-by-day bump-first logic, Supervisor paired inline |
| — | Supervisor | 7 | Auto-paired with Core (not scheduled independently) |
| 3 | Freeosk | 4 | Primary Lead priority |
| 4 | Digital Setup / Refresh / Teardown / Digitals | 2–5, 8 | Lead-only, rotating time slots |
| — | Full-Day Other (8+ hours) | 9 | Scheduled before regular Other events |
| 5 | Other | 9 (lowest) | Club Supervisor → Lead fallback |

Within each wave, events are sorted by **due date** (earliest first), then by **type priority** (lower number = higher).

---

## Juicer Production

### Role Requirements
- **Eligible roles**: Juicer Barista, Club Supervisor (hard constraint)
- **Juicer-trained employees** are also eligible as fallbacks

### Assignment Logic
- **Rotation-based**: Uses the `juicer` rotation assignment for the target date
- Rotation exceptions override weekly rotation for specific dates
- **Fallback priority**: Other Juicer Baristas → juicer-trained employees
- Assigned employee is determined by `RotationManager.get_rotation_employee(date, 'juicer')`

### Scheduling Date
- **Always scheduled on the event's start date** — never auto-moved to a different day
- Only manual user intervention can change the scheduled date

### Default Time
- **9:00 AM** (matched by event name containing `JUICER-PRODUCTION-SPCLTY`)

### Key Rules
| Rule | Source | Description |
|------|--------|-------------|
| RULE-001 | validation_rules | One Core OR one Juicer Production per employee per day (Club Supervisor exempt) |
| RULE-006 | validation_rules | If scheduled for Juicer Production, employee must NOT have Core on same day |
| RULE-009 | validation_rules | Paired with Juicer Survey (Production at 9 AM, Survey at 5 PM) |
| RULE-015 | validation_rules | Juicer Deep Clean must NOT be on a day with Juicer Production |
| RULE-019 | validation_rules | Max **5 Juicer Production events per employee per week** |
| RULE-020 | validation_rules | Same product cannot be scheduled on the same day |
| H13 | cpsat_scheduler | Juicer-Core mutual exclusion (same day, same employee) |
| Wave 1 | scheduling_engine | Can **bump** existing Core events if the rotation Juicer already has a Core event that day |

### Bumping Behavior
When a Juicer rotation employee has Core events on the same day:
1. Core events are bumped (unscheduled)
2. Bumped Core events are rescheduled in Wave 2
3. Bumpable constraints (DAILY_LIMIT, ALREADY_SCHEDULED) are ignored for Juicer scheduling
4. Non-bumpable constraints (TIME_OFF, AVAILABILITY, ROLE, DUE_DATE) still block scheduling

### Verification Checks
- **Critical**: Employee must be qualified (Juicer Barista or Club Supervisor)
- **Warning**: Employee is not the rotation Juicer for the day
- **Critical**: Employee also has Core event same day (Juicer-Core conflict)

---

## Juicer Survey

### Role Requirements
- **Eligible roles**: Juicer Barista, Club Supervisor (hard constraint)

### Assignment Logic
- **Paired with Juicer Production** — same employee, same day
- Automatically created when Juicer Production is scheduled (via pairing logic)
- In CP-SAT solver, survey events are removed from the main event list and handled implicitly through pairing

### Default Time
- **5:00 PM**

### Key Rules
| Rule | Source | Description |
|------|--------|-------------|
| RULE-009 | validation_rules | Must be paired with Juicer Production on same day |
| H17 | cpsat_scheduler | Same day, same employee as paired Production event |

---

## Juicer Deep Clean

### Role Requirements
- **Eligible roles**: Juicer Barista, Club Supervisor (hard constraint)

### Default Time
- **9:00 AM**

### Key Rules
| Rule | Source | Description |
|------|--------|-------------|
| RULE-015 | validation_rules | Must NOT be scheduled on a day that has a Juicer Production event (global — no Juicer Production for *any* employee that day) |
| H14 | cpsat_scheduler | Day-level exclusion with Juicer Production (not just per-employee — entire calendar day) |

---

## Core

### Role Requirements
- **Eligible roles**: All employees (Lead Event Specialist, Event Specialist, Juicer Barista when not juicing)
- **Club Supervisor**: Soft constraint discourages assignment to Core events (penalty in CP-SAT)

### Assignment Logic (Wave 2 — Day-by-Day Bump-First)
Three subwaves, each tries all valid days before moving to the next subwave:

| Subwave | Employee Pool | Slot Priority |
|---------|--------------|---------------|
| 2.1 | Lead Event Specialists | Primary Lead at Block 1 → Other Leads at Block 1 → Other Leads at rotating slots → Bump less urgent event |
| 2.2 | Juicer Baristas (not juicing that day) | Bump less urgent event → Empty slot |
| 2.3 | Event Specialists | Bump less urgent event → Empty slot |

### Scheduling Date
- Scheduled within the window from **start date** to **due date** (exclusive)
- Events are tried day-by-day starting from the earliest valid date

### Default Time / Shift Block System
Core events use an **8-block shift system** with configurable arrive times:

| Block | Default Arrive Time | Order (≤8 events) | Order (>8 events) |
|-------|--------------------|--------------------|---------------------|
| 1 | 10:15 AM | 1st | 1st |
| 2 | 10:15 AM | 2nd | 5th |
| 3 | 10:45 AM | 3rd | 2nd |
| 4 | 10:45 AM | 4th | 6th |
| 5 | 11:15 AM | 5th | 3rd |
| 6 | 11:15 AM | 6th | 7th |
| 7 | 11:45 AM | 7th | 4th |
| 8 | 11:45 AM | 8th | 8th |

- **RULE-013**: ≤8 events/day → sequential order (1, 2, 3, 4, 5, 6, 7, 8)
- **RULE-014**: >8 events/day → interleaved order (1, 3, 5, 7, 2, 4, 6, 8)
- **RULE-003**: Primary Lead always gets **Block 1** (soft bonus in CP-SAT: `WEIGHT_LEAD_BLOCK1 = 25`)

### Key Rules
| Rule | Source | Description |
|------|--------|-------------|
| RULE-001 | validation_rules | Max **1 Core event per employee per day** (Club Supervisor exempt) |
| RULE-003 | validation_rules | Primary Lead always at Block 1 |
| RULE-005 | validation_rules | Non-Supervisor employees with support events (Freeosk, Digital) MUST also have Core or Juicer |
| RULE-006 | validation_rules | Cannot be on same day as Juicer Production for same employee |
| RULE-007 | validation_rules | Must have paired Supervisor event on same day |
| RULE-018 | validation_rules | Max **6 Core events per employee per week** (Sunday–Saturday) |
| H11 | cpsat_scheduler | 1 Core per employee per day (hard) |
| H12 | cpsat_scheduler | 6 Core per employee per week (hard) |
| H13 | cpsat_scheduler | Juicer-Core mutual exclusion per employee per day |
| H21 | cpsat_scheduler | One employee per block per day (block uniqueness) |

### Bumping Rules
- More urgent Core event (earlier due date) can **bump** a less urgent Core event
- Max **3 bumps per event** to prevent infinite loops
- Bump strategy: Forward-move first (reschedule bumped event to later date) → Traditional bump (mark as superseded)
- Bumped events cascade through subwaves for rescheduling
- **Rescue pass**: After all waves, urgent failed Core events (due within 7 days) get another bump attempt

### Verification Checks
- **Critical**: Employee has >1 Core event on same day
- **Warning**: Core event not at a standard time slot
- **Warning**: Core events imbalanced across shifts (some slots have events, others empty)
- **Warning**: No Lead at opening or closing shift

---

## Supervisor

### Role Requirements
- **Priority 1**: Club Supervisor (if available that day)
- **Priority 2**: Primary Lead Event Specialist (if Club Supervisor unavailable)
- Any Lead Event Specialist or Club Supervisor can be assigned

### Assignment Logic
- **Auto-paired with Core events** — not scheduled independently
- Scheduled inline during Wave 2 when the corresponding Core event is scheduled
- Matched by 6-digit event number in the project name
TODO: Need to make sure we filter out events that have been cancelled. Currently when finding it's supervisor pair it nust returns the match but we need the match that is not cacelled. 
- **Orphaned supervisor pass**: After Wave 2, any Supervisor events whose Core was scheduled in a prior run get scheduled
TODO: any Supervisor events that do not have a paired CORE need to see where it's CORE is scheduled and schedule it accordingly. IF it cannot be found then it shoukd be noted.

### Default Time
- **12:00 PM (Noon)**

### Key Rules
| Rule | Source | Description |
|------|--------|-------------|
| RULE-004 | validation_rules | Club Supervisor first, Primary Lead fallback |
| RULE-007 | validation_rules | All Core events MUST have their Supervisor counterpart |
| RULE-008 | validation_rules | No orphaned Supervisors — cannot exist without corresponding Core |
| H16 | cpsat_scheduler | Core-Supervisor must be on same day |

### Special Behavior
- **Overlap allowed**: Supervisor events skip the time-overlap check in `ConstraintValidator._check_already_scheduled()` because they are expected to overlap with Core events
- In CP-SAT solver, Supervisor scheduled status is directly tied to Core's: `v_sup_scheduled[sid] = v_scheduled[core_id]`

### Verification Checks
- **Warning**: Not assigned to Club Supervisor or Lead
- **Warning**: Not scheduled at expected noon time
- **Warning**: Core event exists without paired Supervisor

---

## Freeosk

### Role Requirements
- **Lead-only event**: Lead Event Specialist or Club Supervisor (hard constraint)
- **Primary Lead** preferred (assigned first)

### Assignment Logic (Wave 3)
- Priority: **Primary Lead → Other Leads → Club Supervisor** (fallback)
- Assigned via `_schedule_primary_lead_event()`
- **RULE-002**: Primary Lead should be assigned daily Freeosk

### Scheduling Date
- Scheduled on the event's **start date** — does not auto-move to other days

### Default Times
| Condition | Time |
|-----------|------|
| **Setup day (Friday)** — Freeosk Setup | 10:00 AM |
| **Setup day (Friday)** — Freeosk Refresh | 12:00 PM (Noon) |
| **Setup day (Friday)** — Other Freeosk | 12:00 PM (Noon) |
| **Non-setup day** — Freeosk Refresh | 10:00 AM |
| **Non-setup day** — Other Freeosk | 12:00 PM (Noon) |
| Freeosk Troubleshooting | 12:00 PM (Noon) |

### Key Rules
| Rule | Source | Description |
|------|--------|-------------|
| RULE-002 | validation_rules | Primary Lead should have daily Freeosk |
| RULE-005 | validation_rules | Non-Supervisor employees must also have Core or Juicer (base event requirement) |
| RULE-010 | validation_rules | Friday timing: Setup at 10 AM, Refresh at Noon |
| RULE-011 | validation_rules | Non-setup days: Refresh at 10 AM, others at Noon |
| H18 | cpsat_scheduler | Support event requires base event (Core or Juicer) same day, same employee. Club Supervisor exempt |

### Verification Checks
- **Critical**: Assigned to non-Lead/non-Supervisor employee

---

## Digital Setup

### Role Requirements
- **Lead-only event**: Lead Event Specialist or Club Supervisor (hard constraint)
- **Primary Lead** preferred

### Assignment Logic (Wave 4)
- Priority: **Primary Lead → Other Leads → Club Supervisor** (fallback)
- Assigned via `_schedule_primary_lead_event()`

### Scheduling Date
- Scheduled on the event's **start date** — does not auto-move to other days

### Default Times
- **Rotating 15-minute slots**: 10:15, 10:30, 10:45, 11:00 AM (configurable via `event_time_settings`)
- Each Digital Setup on the same day gets the next slot in rotation

### Key Rules
| Rule | Source | Description |
|------|--------|-------------|
| RULE-002 | validation_rules | On **Saturdays** (Digital Setup days), a different lead should handle Digital Refresh |
| RULE-005 | validation_rules | Non-Supervisor employees must also have Core or Juicer same day |
| H18 | cpsat_scheduler | Support event requires base event. Club Supervisor exempt |

### Verification Checks
- **Critical**: Assigned to non-Lead/non-Supervisor employee

---

## Digital Refresh

### Role Requirements
- **Lead-only event**: Lead Event Specialist or Club Supervisor (hard constraint)
- **Primary Lead** assigned (RULE-002)

### Assignment Logic (Wave 4)
- Priority: **Primary Lead → Other Leads → Club Supervisor** (fallback)
- Assigned via `_schedule_primary_lead_event()`
- **Saturday exception**: When Digital Setups exist, a **different lead** (or Club Supervisor) handles Digital Refresh

### Scheduling Date
- Scheduled on the event's start date

### Default Time
- Same rotating slots as Digital Setup (10:15, 10:30, 10:45, 11:00 AM)

### Key Rules
| Rule | Source | Description |
|------|--------|-------------|
| RULE-002 | validation_rules | Primary Lead assigned; different lead on Saturdays with Digital Setup |
| RULE-005 | validation_rules | Non-Supervisor employees must also have Core or Juicer same day |
| H18 | cpsat_scheduler | Support event requires base event. Club Supervisor exempt |

---

## Digital Teardown

### Role Requirements
- **Lead-only event**: Lead Event Specialist or Club Supervisor (hard constraint)
- **Secondary Lead** preferred

### Assignment Logic (Wave 4)
- Priority: **Secondary Lead → Club Supervisor** (fallback)
- Assigned via `_schedule_secondary_lead_event()`
- Secondary Lead is any Lead Event Specialist who is NOT the Primary Lead for that day

### Scheduling Date
- Scheduled on the event's start date

### Default Times (Friday)
- **Rotating 15-minute slots from 5:00 PM**: 5:00, 5:15, 5:30, 5:45 PM (and continuing if more events)
- Configurable via `event_time_settings` (fallback defaults: 6:00, 6:15, 6:30, 6:45 PM)

### Key Rules
| Rule | Source | Description |
|------|--------|-------------|
| RULE-012 | validation_rules | Friday Digital Teardowns at 5:00–5:45 PM |
| RULE-005 | validation_rules | Non-Supervisor employees must also have Core or Juicer same day |
| H18 | cpsat_scheduler | Support event requires base event. Club Supervisor exempt |

---

## Digitals (Generic)

### Role Requirements
- **Lead-only event**: Lead Event Specialist or Club Supervisor (hard constraint)

### Assignment Logic (Wave 4)
- Routed by event name: `TEARDOWN` → Secondary Lead path, `SETUP`/`REFRESH` → Primary Lead path
- Unknown Digital subtypes default to Primary Lead path

### Key Rules
| Rule | Source | Description |
|------|--------|-------------|
| RULE-005 | validation_rules | Non-Supervisor employees must also have Core or Juicer same day |
| H18 | cpsat_scheduler | Support event requires base event. Club Supervisor exempt |

### Verification Checks
- **Critical**: Assigned to non-Lead/non-Supervisor employee

---

## Other

### Role Requirements
- **Priority 1**: Club Supervisor
- **Priority 2**: Any Lead Event Specialist (fallback)
- Listed under `LEAD_ONLY_EVENT_TYPES` in `constraint_validator.py`

### Assignment Logic (Wave 5)
- Club Supervisor at noon → Any available Lead at noon
- Time conflict checks are **skipped** for Other events (both Club Supervisor and Leads)
- Only checks: time-off and weekly availability

### Full-Day Other Events (8+ hours)
Handled **before** regular Other events in a separate pass:
- Schedule on **start date** (like Juicer events)
- Employee pool: **Leads → Specialists → Juicers** (NOT Club Supervisor)
- Cannot work with Core or Juicer event on same day
- One full-day event per employee per day
- H20 (CP-SAT): Full-day events block Core/Juicer on same day for same employee

### Default Time
- **12:00 PM (Noon)** for regular Other events
- **9:00 AM** for full-day Other events

### Key Rules
| Rule | Source | Description |
|------|--------|-------------|
| RULE-005 | validation_rules | Non-Supervisor employees must also have Core or Juicer same day |
| H18 | cpsat_scheduler | Support event requires base event. Club Supervisor exempt |
| H20 | cpsat_scheduler | Full-day events (≥480 min) block Core/Juicer on same day |

---

## Cross-Cutting Rules

These rules apply to **all event types** regardless of category.

### Availability & Time Off
| Rule | Severity | Description |
|------|----------|-------------|
| RULE-016 | Hard | No employee scheduled outside their weekly availability pattern |
| RULE-016 | Hard | No employee scheduled during requested time-off |
| Company Holidays | Hard | No scheduling on company holidays (checked via `CompanyHoliday.is_holiday()`) |
| Locked Days | Hard | No scheduling on locked days |

### Scheduling Window
| Rule | Description |
|------|-------------|
| 3-Day Window | Events must have a due date at least 3 days in the future to be auto-scheduled |
| 3-Week Horizon | Only events with start dates within the next 3 weeks are considered |
| Start Date | Events cannot be scheduled before their start date (hard constraint, no exceptions) |
| Due Date | Events must be scheduled strictly before their due date |

### Fairness & Distribution
| Rule | Source | Description |
|------|--------|-------------|
| RULE-017 | validation_rules | Scheduling should be randomized — employees should not consistently get the same time |
| RULE-020 | validation_rules | Same product (by name/brand) cannot be scheduled on the same day |
| RULE-021 | validation_rules | Events prioritized by due date (earliest first); bypassed only for RULE-020 |
| S9 | cpsat_scheduler | Minimize max-min spread of Core assignments across employees (fairness penalty) |

### Support Event Base Requirement (RULE-005 / H18)
Non-Supervisor employees scheduled for Freeosk, Digital, or Other events **must** also have a Core or Juicer event on the same day. Club Supervisor is exempt.

### Club Supervisor Restrictions
- Should **not** be assigned to regular Core events (soft constraint)
- **Allowed** event types: Supervisor, Digitals, Freeosk, Juicer Production, Juicer Survey, Juicer Deep Clean
- Exempt from single Core/Juicer daily limit (RULE-001)
- Exempt from support-event base requirement (H18)

---

## Quick Reference Tables

### Role Eligibility by Event Type

| Event Type | Event Specialist | Lead Event Specialist | Juicer Barista | Club Supervisor |
|------------|:---:|:---:|:---:|:---:|
| **Core** | Yes | Yes (Block 1 priority) | Yes (when not juicing) | Discouraged (soft) |
| **Juicer Production** | No | No | Yes | Yes |
| **Juicer Survey** | No | No | Yes | Yes |
| **Juicer Deep Clean** | No | No | Yes | Yes |
| **Supervisor** | No | Yes (Priority 2) | No | Yes (Priority 1) |
| **Freeosk** | No | Yes (Primary preferred) | No | Yes (fallback) |
| **Digital Setup** | No | Yes (Primary preferred) | No | Yes (fallback) |
| **Digital Refresh** | No | Yes (Primary preferred) | No | Yes (fallback) |
| **Digital Teardown** | No | Yes (Secondary preferred) | No | Yes (fallback) |
| **Digitals** | No | Yes | No | Yes |
| **Other** | No | Yes (fallback) | No | Yes (Priority 1) |

### Default Times

| Event Type | Default Time | Notes |
|------------|-------------|-------|
| Juicer Production | 9:00 AM | Fixed |
| Juicer Survey | 5:00 PM | Paired with Production |
| Juicer Deep Clean | 9:00 AM | Fixed |
| Core | 10:15 AM (Block 1) | 8-block system, configurable |
| Supervisor | 12:00 PM | Fixed, paired with Core |
| Freeosk | 10:00 AM | Varies by day (see Freeosk section) |
| Digital Setup | 10:15 AM+ | 15-min rotating slots |
| Digital Refresh | 10:15 AM+ | 15-min rotating slots |
| Digital Teardown | 5:00 PM+ | 15-min rotating slots (Fridays) |
| Other | 12:00 PM | Noon |
| Full-Day Other | 9:00 AM | 8+ hour events |

### Weekly Limits

| Event Type | Limit | Period |
|------------|-------|--------|
| Core | 1 per day | Daily (per employee) |
| Core | 6 per week | Sunday–Saturday (per employee) |
| Juicer Production | 5 per week | Sunday–Saturday (per employee) |
| Work Days | 6 per week | Sunday–Saturday (per employee) |

### Verification Severity Levels

| Severity | Effect | Examples |
|----------|--------|----------|
| **Critical** | Blocks approval | Role mismatch, >1 Core/day, time-off conflict, due date violation |
| **Warning** | Allows with confirmation | Shift imbalance, wrong rotation Juicer, non-standard time |
| **Info** | FYI only | Coverage notes |

---

*Document last updated: 2026-02-12*
*Sources: scheduling_validation_rules.md (21 rules), constraint_validator.py, scheduling_engine.py, schedule_verification.py, cpsat_scheduler.py, rotation_manager.py*
