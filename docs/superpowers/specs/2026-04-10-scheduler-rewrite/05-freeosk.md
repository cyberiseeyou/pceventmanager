# Spec 05 — Freeosk Scheduling

> **Source image:** Image 4 of 7, section "4. Freeosk Scheduling".

## Verbatim spec

**Sort into subcategories** (process in order):

| Subcategory | Name Contains | Time | Process Order |
|---|---|---|---|
| Daily Service | `FSK-Daily Service-11AM` | 10:00 AM | 1st |
| Changeover | `CO-11AM` | 10:00 AM | 2nd |
| Troubleshooting | `Troubleshooting` | 12:00 PM | 3rd |

**Scheduling logic (same for all subcategories):** Schedule to event's **start date**.

1. Primary Lead available + has primary event? → Assign.
2. Backup Lead available + has primary event? → Assign.
3. Neither available? → Club Supervisor **unconditionally**.

## Inputs

- `freeosk_events` — all unscheduled events with `event_type == 'Freeosk'`.
- `rotation_assignments` where `rotation_type == 'primary_lead'`.
- `schedule_exceptions` where `rotation_type == 'primary_lead'`.
- `employee_time_off`, `employee_weekly_availability`, `employee_availability_override`.
- `posted_schedules` + `current_run_pending_schedules` — to check "has primary event" on the target date.
- `club_supervisor_employee`.

## Outputs

Per Freeosk event: one PendingSchedule (proposal or manual review) with the time determined by subcategory.

## Pre-conditions

- Categories 1, 2, 3 have completed (Juicer Production, Juicer Survey, CORE + Supervisor).
- `freeosk_events` is partitioned into three subcategory lists, each sorted by `start_datetime` ascending.

## Post-conditions

- Every Freeosk event has exactly one PendingSchedule.
- All successful assignments are at the time prescribed by the subcategory:
  - Daily Service: 10:00 AM
  - Changeover: 10:00 AM
  - Troubleshooting: 12:00 PM
- Within the category, all Daily Service events are processed before any Changeover event, and all Changeover events are processed before any Troubleshooting event.

## Branches

| ID | Description |
|---|---|
| F1 | Partition freeosk_events by name pattern: subcategory A (contains "FSK-Daily Service-11AM"), B (contains "CO-11AM"), C (contains "Troubleshooting") |
| F2 | Events that match no pattern: log a warning, treat as subcategory C (Troubleshooting default) so they still get scheduled at 12 PM. Alternative: manual review with reason "Freeosk event with unrecognized name pattern". Choice: manual review is safer — it surfaces the data issue. |
| F3 | Sort each subcategory list by start_datetime ascending |
| F4 | Process subcategory A fully before B, B fully before C |
| F5 | For each event in a subcategory, target_date = event.start_datetime.date() |
| F6 | Subcategory determines assigned_time: A = 10:00, B = 10:00, C = 12:00 |
| F7 | Primary Lead (from rotation for target_date's DoW, possibly overridden by ScheduleException) available + has primary event on target_date → assign |
| F8 | Primary Lead unavailable or no primary event → try Backup Lead |
| F9 | Backup Lead available + has primary event → assign |
| F10 | Backup Lead unavailable or no primary event → Club Supervisor unconditionally |
| F11 | Club Supervisor on PTO on target_date → manual review |

## Edge cases

- **Freeosk event whose name contains BOTH "FSK-Daily Service-11AM" and "CO-11AM"** (unlikely but possible in malformed data): match by first occurrence in the order A → B → C. Log a warning.
- **Freeosk event with past start_date:** start_date is in the past (e.g., a missed event being re-run). If start_date < today, the event cannot be scheduled on start_date. Options: (a) manual review with reason "Freeosk event's start date has passed"; (b) schedule today. The spec says "schedule to event's start date" — no retry logic for Freeosk. Choose (a).
- **Primary Lead has primary event but is on weekly unavailability for that DoW:** They fail the "available" check (weekly availability blocks them). Fall through to Backup.
- **No Lead Event Specialist employees at all in the club:** F7 and F9 both evaluate as "no such employee". Fall through to CS fallback at F10.
- **Freeosk Troubleshooting on a day nobody has a primary event:** Primary Lead and Backup Lead both fail "has primary event" check. Goes to Club Supervisor unconditionally @ 12 PM. This is intentional — Troubleshooting can run even when the club has no CORE that day.

## Do NOT

- Do NOT process Troubleshooting before Daily Service or Changeover. The order is strict: A → B → C.
- Do NOT assign a Freeosk Daily Service or Changeover at any time other than 10:00 AM.
- Do NOT assign a Freeosk Troubleshooting at any time other than 12:00 PM.
- Do NOT require Club Supervisor to have a primary event in F10 (unconditional CS fallback).
- Do NOT attempt to retry Freeosk on a different day if no one is available on start_date. The spec says schedule-to-start-date, with no retry semantics. Fall through CS fallback; if that also fails, manual review.

## Traceability table

| Branch ID | Plan task | Test case | Implementation location |
|---|---|---|---|
| F1 | `05-freeosk.md` T1 | `test_freeosk_subcategory_partition_by_name` | TBD |
| F2 | `05-freeosk.md` T2 | `test_freeosk_unrecognized_name_goes_to_manual_review` | TBD |
| F3, F4 | `05-freeosk.md` T3 | `test_freeosk_subcategory_processing_order` | TBD |
| F5, F6 | `05-freeosk.md` T4 | `test_freeosk_time_by_subcategory` | TBD |
| F7 | `05-freeosk.md` T5 | `test_freeosk_primary_lead_with_primary_event` | TBD |
| F8, F9 | `05-freeosk.md` T6 | `test_freeosk_backup_lead_with_primary_event` | TBD |
| F10 | `05-freeosk.md` T7 | `test_freeosk_cs_unconditional_fallback` | TBD |
| F11 | `05-freeosk.md` T8 | `test_freeosk_cs_pto_manual_review` | TBD |
