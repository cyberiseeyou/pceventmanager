# Spec 00 — Master Overview

> **Source image:** Image 1 of 7 ("Event Scheduling System Master Overview"). Every rule in this file must be traceable to that image.

## Verbatim spec

### Title
> **Event Scheduling System — Master Overview**
> Complete processing flow from input to scheduled events.
> Sam's Club #8135 — Product Connections / Acosta Group.

### PHASE 1 — Input Lists

Events arrive as two separate lists:

| List | Meaning |
|---|---|
| **Scheduled Events** | Already placed — no processing needed. |
| **Unscheduled Events** | Need processing → continue below. |

### PHASE 2 — CORE/Supervisor Pairing

> Find all CORE events and pair with their Supervisor counterpart (same 6-digit number and name prefix).

The output of Phase 2 is a set of (CORE, Supervisor) pairs plus any CORE events that have no matching Supervisor (left unpaired but still processed). Supervisor events that have no matching CORE are invalid input; they should be logged and skipped.

### PHASE 3 — Sort into Categories (process in the listed order)

| Order | Category | Sort key within category |
|---|---|---|
| 1st | Juicer Production | Start Date (ascending) |
| 2nd | Juicer Survey | Start Date (ascending) |
| 3rd | CORE + Supervisor | **Due Date** (ascending) |
| 4th | Freeosk | Start Date (ascending) |
| 5th | Digitals | Start Date (ascending) |
| 6th | Other | Start Date (ascending) |

The order above is **strict**: a category must fully finish processing (including any retries, bumps, and fallbacks) before the next category begins. Exception: when Juicer Production scheduling *bumps* a CORE/Supervisor event, the bumped event returns to the CORE/Supervisor pool (category 3) and is processed when that category runs — not mid-stream during category 1. See `02-juicer-production.md` for the exact bump-return semantics.

## Inputs

The scheduler's inputs on each run:

- `unscheduled_events` — all `Event` rows where `is_scheduled == False` AND `condition NOT IN ('Canceled', 'Expired')` AND `due_datetime > (today + 3 days)` (Normal mode) or `due_datetime > today` (Emergency mode).
- `posted_schedules` — all `Schedule` rows relevant to the scheduling window (used for conflict detection and for the "has a primary event" check on secondary events).
- `employees` — all active `Employee` rows (`is_active == True`, `termination_date IS NULL OR termination_date > today`).
- `rotation_assignments` — all `RotationAssignment` rows with `rotation_type IN ('juicer', 'primary_lead')`.
- `schedule_exceptions` — all `ScheduleException` rows (one-off rotation overrides for a specific date).
- `availability` — `EmployeeWeeklyAvailability`, `EmployeeAvailabilityOverride`, `EmployeeTimeOff` (only `status='approved'` time-off blocks scheduling).
- `mode` — `normal` or `emergency` (determines the earliest schedulable day).

## Outputs

- `PendingSchedule` rows (one per processed event) in a new `SchedulerRunHistory` row:
  - **Successful assignment:** `employee_id` set, `schedule_datetime` set, `schedule_time` set, `failure_reason=None`, `status='proposed'`.
  - **Manual review:** `employee_id=None`, `schedule_datetime=None`, `schedule_time=None`, `failure_reason` set with a human-readable message.
  - **Bump swap:** `is_swap=True`, `bumped_event_ref_num=<old event>`, `bumped_posted_schedule_id=<old schedule id>`, `swap_reason=<text>`.
- `SchedulerRunHistory` row with aggregate counters (`total_events_processed`, `events_scheduled`, `events_requiring_swaps`, `events_failed`, `solver_type='greedy'`).

## Pre-conditions

- Database is in a consistent state; no partial rollback from a prior run.
- A fresh `SchedulerRunHistory` row has been created with `status='running'`.
- No other scheduler run is currently in `status='running'` against the same database (enforced by a lock or by run-singleton check elsewhere).

## Post-conditions

- Every event in `unscheduled_events` has **exactly one** `PendingSchedule` row in this run, either a successful proposal or a manual-review entry. No event is silently dropped.
- No two primary events (CORE or Juicer Production) in the same run are proposed for the same `(employee_id, date)` pair.
- Every secondary event proposal (Juicer Survey, Supervisor, Freeosk, Digitals Setup/Refresh) either: (a) is assigned to an employee who also has a primary event on that day in the same run or already posted, OR (b) is assigned via Club Supervisor fallback.
- `SchedulerRunHistory.status = 'completed'` and all counters are accurate.

## Branches (decision points)

| ID | Description |
|---|---|
| M1 | Phase 1: event has `is_scheduled == True` → skip entirely, do not create a PendingSchedule for it |
| M2 | Phase 1: event has `condition IN ('Canceled', 'Expired')` → skip entirely |
| M3 | Phase 1: event has `due_datetime <= today + 3 days` (Normal mode) → skip, past scheduling window |
| M4 | Phase 2: CORE event has a matching Supervisor (same 6-digit number + same name prefix) → pair them |
| M5 | Phase 2: CORE event has NO matching Supervisor → process CORE alone, no Supervisor in result |
| M6 | Phase 2: Supervisor event has NO matching CORE → log warning, skip |
| M7 | Phase 3: category iteration order is strict — next category must not start until the current category is done |
| M8 | Phase 3: Juicer Production bumps a CORE → bumped CORE is queued back into category 3 pool, sorted by due date |

## Edge cases

- **Empty input:** zero unscheduled events → produce an empty `SchedulerRunHistory` with `status='completed'` and zero counts. Do not error.
- **All events in a single category:** if, e.g., only Freeosk events exist, categories 1/2/3/5/6 produce zero proposals; category 4 does its full work.
- **Simultaneous bumps:** a Juicer Production bumps CORE A; while processing CORE A in category 3, it bumps CORE B (which has a later due date). CORE B re-enters the pool in the same category 3 pass. Bumps can cascade within category 3 but cannot re-enter category 1 or category 2.
- **Run 192 reproducer:** on 2026-04-10 the inputs produced 15/17 failures. This spec's flow must schedule ≥12/17 events successfully on the same input (3 narrow-window MDay CORE events on May 8–10 are legitimate capacity exhaustion and may remain unschedulable; all 10 Juicer Production events and both wide-window CORE events must succeed).

## Do NOT

- Do not sort all events in one global list and iterate; the per-category order is non-negotiable.
- Do not use due date as the within-category sort key for Juicer Production, Juicer Survey, Freeosk, Digitals, or Other — those categories use start date.
- Do not skip a category because it's "empty at the start"; Juicer Production bumps may populate the CORE category later.
- Do not attempt to "optimize globally" by reordering events across categories. The spec is intentionally sequential for explainability.
- Do not produce a `PendingSchedule` with both `employee_id=None` AND `failure_reason=None`; that's an invalid state.
- Do not silently drop an event because it has no matching Production/Supervisor/pair; always produce either a successful proposal or a manual-review entry.

## Traceability table

| Branch ID | Plan task | Test case | Implementation location |
|---|---|---|---|
| M1 | `01-phase-infrastructure.md` T1 | `test_phase1_skips_already_scheduled` | TBD |
| M2 | `01-phase-infrastructure.md` T2 | `test_phase1_skips_canceled` | TBD |
| M3 | `01-phase-infrastructure.md` T3 | `test_phase1_skips_past_due` | TBD |
| M4 | `01-phase-infrastructure.md` T4 | `test_phase2_pairs_core_and_supervisor_by_6digit` | TBD |
| M5 | `01-phase-infrastructure.md` T5 | `test_phase2_unpaired_core_processes_alone` | TBD |
| M6 | `01-phase-infrastructure.md` T6 | `test_phase2_unpaired_supervisor_logs_and_skips` | TBD |
| M7 | `01-phase-infrastructure.md` T7 | `test_phase3_strict_category_order` | TBD |
| M8 | `02-juicer-production.md` T14, `04-core-supervisor.md` T1 | `test_bumped_core_returns_to_pool_sorted_by_due_date` | TBD |

(The "Implementation location" column is filled in as code lands.)
