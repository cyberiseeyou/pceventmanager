# Spec 06 — Digitals Scheduling

> **Source image:** Image 4 of 7, section "5. Digitals Scheduling".

## Verbatim spec

**Sort into subcategories:**

| Subcategory | Name Ends With | Days | Process Order |
|---|---|---|---|
| Setup | `Digital Demo Setup` | Saturdays | 1st |
| Refresh | `Digital Demo Refresh` | Any day | 2nd |
| Teardown | `Digital Demo Tear Down` | Any day | 3rd |

**Setup & Refresh:**
Priority: Primary Lead (+primary event) → Backup Lead (+primary event) → Club Supervisor.
Times: Setup `10:15 +15min each` | Refresh (Sat) `12:00 +15min` | Refresh (other) `10:15 +15min`.

**Teardown (unique logic):**
Find a Lead ≠ Primary Lead who is scheduled that day → Assign.
No non-Primary Leads available? → Club Supervisor unconditionally.
Times: `5:00 PM +15min each`.

## Inputs

- `digital_events` — all unscheduled events with `event_type IN ('Digitals', 'Digital Setup', 'Digital Refresh', 'Digital Teardown')`. The codebase has several type strings; for partitioning, use the name-ends-with rule from the table (which is authoritative) regardless of the `event_type` column value.
- `rotation_assignments` where `rotation_type == 'primary_lead'`.
- `employee_time_off`, `employee_weekly_availability`, `employee_availability_override`.
- `posted_schedules` + `current_run_pending_schedules`.
- `club_supervisor_employee`.

## Outputs

Per Digital event: one PendingSchedule (proposal or manual review). Assigned times follow the subcategory rules and use per-event 15-minute offsets within the subcategory.

## Pre-conditions

- Categories 1–4 have completed (Juicer Production, Juicer Survey, CORE + Supervisor, Freeosk).
- `digital_events` is partitioned into Setup, Refresh, Teardown by the name-ends-with rule.
- Each subcategory list is sorted by `start_datetime` ascending.

## Post-conditions

- Every Digital event has exactly one PendingSchedule.
- Setup events only appear on Saturdays; any Setup event whose `start_datetime.date()` is not a Saturday goes to manual review with a clear reason.
- Times within a subcategory on a given date are unique and follow the +15 min rule:
  - Setup on Saturday D: event 1 at 10:15, event 2 at 10:30, event 3 at 10:45, ...
  - Refresh on Saturday D: event 1 at 12:00, event 2 at 12:15, ...
  - Refresh on non-Saturday D: event 1 at 10:15, event 2 at 10:30, ...
  - Teardown on day D: event 1 at 17:00 (5:00 PM), event 2 at 17:15, ...

## Branches

### Setup subcategory
| ID | Description |
|---|---|
| D1 | Partition digital_events: Setup = name endswith "Digital Demo Setup" |
| D2 | Setup event's start_datetime.date() is a Saturday → proceed with scheduling |
| D3 | Setup event's start_datetime.date() is NOT a Saturday → manual review with reason "Digital Demo Setup events must be on Saturdays; event has start date <date> (<DoW>)" |
| D4 | Setup time base = 10:15; per-event offset = +15 min for each Setup on the same date (so all Setups on day D get unique times starting at 10:15) |
| D5 | Employee priority: Primary Lead (+ has primary event on target_date) → Backup Lead (+ has primary event) → Club Supervisor unconditionally |

### Refresh subcategory
| ID | Description |
|---|---|
| D6 | Partition: Refresh = name endswith "Digital Demo Refresh" |
| D7 | Refresh can be on any day |
| D8 | Refresh time base = 12:00 if target_date is Saturday; 10:15 otherwise. Per-event offset = +15 min |
| D9 | Employee priority: Primary Lead (+ has primary event) → Backup Lead (+ has primary event) → Club Supervisor unconditionally |

### Teardown subcategory
| ID | Description |
|---|---|
| D10 | Partition: Teardown = name endswith "Digital Demo Tear Down" |
| D11 | Teardown can be on any day |
| D12 | Teardown time base = 17:00 (5:00 PM); per-event offset = +15 min |
| D13 | Employee priority (UNIQUE): find any Lead Event Specialist (job_title == 'Lead Event Specialist') who is scheduled on target_date AND is NOT the Primary Lead for target_date → assign |
| D14 | "Scheduled on target_date" means they have any PendingSchedule (successful, in-run) OR posted Schedule on that date, regardless of event type (primary or secondary). This is LESS restrictive than "has primary event" — a lead who has only a Freeosk on that day is eligible. |
| D15 | If no non-Primary Lead is scheduled → Club Supervisor unconditionally @ target_date + teardown_time_for_date(target_date) |

## Edge cases

- **Setup event on a Friday:** D3 → manual review.
- **Setup event on a Saturday with no Primary Lead available + no Backup + CS on PTO:** Manual review.
- **Two Setup events on the same Saturday:** D4 gives them 10:15 and 10:30. Ordering: by `start_datetime` if equal then by event_ref_num ascending.
- **Refresh on a Tuesday:** D8 → time base 10:15.
- **Refresh on a Saturday when a Setup already exists on that Saturday:** Setup uses 10:15, 10:30, ...; Refresh uses 12:00, 12:15, ... — they don't collide.
- **Teardown when only the Primary Lead is scheduled that day:** D13 fails (no Lead ≠ Primary Lead). Fall to D15: Club Supervisor unconditionally.
- **Teardown when the Primary Lead is also the Club Supervisor:** Impossible in practice (job_title mismatch).
- **Teardown when multiple non-Primary Leads are scheduled:** Pick deterministically. Tiebreaker: by employee_id ascending. Log the choice.
- **Digital event whose name matches NEITHER "Digital Demo Setup" NOR "Refresh" NOR "Tear Down":** Log a warning, treat as manual review with reason "Digital event with unrecognized name pattern: <name>".

## Do NOT

- Do NOT allow a Setup to be scheduled on a day other than Saturday. No retry-to-next-Saturday logic; the event's start_datetime must already be a Saturday.
- Do NOT confuse "Digital Teardown" with other secondary events. Teardown does NOT require "has primary event" — only "is scheduled that day".
- Do NOT fall back to the Primary Lead for Teardown. The spec is explicit: Lead ≠ Primary Lead.
- Do NOT use the same time for two Digital events in the same subcategory on the same day. +15 min offsets are required.
- Do NOT use `event_type` column to determine Setup/Refresh/Teardown. Use the name pattern from the spec table. The event_type column is unreliable (generic "Digitals" is used for all three in some datasets).
- Do NOT schedule a Setup at any base time other than 10:15.
- Do NOT schedule a Refresh at any base time other than 12:00 (Saturdays) or 10:15 (other days).
- Do NOT schedule a Teardown at any base time other than 17:00.

## Traceability table

| Branch ID | Plan task | Test case | Implementation location |
|---|---|---|---|
| D1, D2 | `06-digitals.md` T1 | `test_setup_saturday_only_allowed` | TBD |
| D3 | `06-digitals.md` T2 | `test_setup_non_saturday_manual_review` | TBD |
| D4 | `06-digitals.md` T3 | `test_setup_15min_offsets` | TBD |
| D5 | `06-digitals.md` T4 | `test_setup_employee_priority` | TBD |
| D6, D7 | `06-digitals.md` T5 | `test_refresh_any_day` | TBD |
| D8 | `06-digitals.md` T6 | `test_refresh_saturday_vs_other_time` | TBD |
| D9 | `06-digitals.md` T7 | `test_refresh_employee_priority` | TBD |
| D10, D11 | `06-digitals.md` T8 | `test_teardown_any_day` | TBD |
| D12 | `06-digitals.md` T9 | `test_teardown_5pm_offsets` | TBD |
| D13, D14 | `06-digitals.md` T10 | `test_teardown_non_primary_lead_scheduled_that_day` | TBD |
| D15 | `06-digitals.md` T11 | `test_teardown_cs_fallback_unconditional` | TBD |
