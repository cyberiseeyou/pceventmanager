# Spec 02 — Juicer Production Scheduling

> **Source image:** Image 2 of 7, section "1. Juicer Production Scheduling". This file also depends on `01-key-concepts.md` for definitions of Primary Juicer, Backup Juicer, bumping, and manual review pool.

## Verbatim spec

**Sort order:** For each event (sorted by start date, first to last):

1. Get event start date → Get Primary Juicer for that day.
2. Primary Juicer available (no time off)?
   - **YES** → Has CORE scheduled? → Bump CORE if yes → Assign Production @ **9:00 AM**.
   - **NO** → Check Backup Juicer.
3. Backup Juicer exists and available?
   - **YES** → Has CORE scheduled? → Bump CORE if yes → Assign @ **9:00 AM**.
   - **NO** → Within due date window? → Try next day OR mark unschedulable.

Plus these annotations (starred ★ in the image):
- ★ Also assign matching Juicer Survey to same person @ **5:00 PM**.
- ★ Bumped CORE events go back to CORE/Supervisor pool (sorted by due date).

## Inputs

- `juicer_production_events` — all unscheduled events with `event_type == 'Juicer Production'`.
- `rotation_assignments` where `rotation_type == 'juicer'` — used to look up Primary and Backup Juicer for each day of week.
- `schedule_exceptions` where `rotation_type == 'juicer'` — per-date overrides of the rotation.
- `employee_time_off` where `status == 'approved'` — blocks employees on the target date.
- `employee_weekly_availability`, `employee_availability_override` — blocks employees on days they don't work.
- `posted_schedules` for the target date + employee — to detect CORE conflicts and to drive CORE bumping.
- `current_run_pending_schedules` — to detect CORE events that were scheduled earlier in this run and must be bumped.
- `juicer_survey_events` — the set of unscheduled Juicer Survey events, used to find the "matching Survey" by event number.

## Outputs

For each Juicer Production event, exactly one of:

1. **Successful proposal** — a `PendingSchedule` with:
   - `event_ref_num` = the Production's ref num
   - `employee_id` = Primary or Backup Juicer
   - `schedule_datetime` = target date @ 9:00 AM
   - `schedule_time` = 09:00:00
   - `status` = 'proposed'
   - `failure_reason` = NULL

2. **Successful proposal + bump** — same as above, PLUS:
   - The bumped CORE is:
     - If the CORE was previously posted: a second PendingSchedule is created for the CORE with `is_swap=True`, `bumped_posted_schedule_id=<old schedule id>`, the CORE's old `employee_id` cleared, `schedule_datetime` cleared (it needs re-scheduling), and the CORE is added to category 3's processing pool with due-date sort.
     - If the CORE was a PendingSchedule from earlier in the same run: the existing PendingSchedule is re-opened (cleared `employee_id`, `schedule_datetime`) and re-queued to category 3.

3. **Successful proposal + matching Survey** — the PendingSchedule for the Production, PLUS a second PendingSchedule for the matching Juicer Survey with `employee_id` = same person, `schedule_datetime` = same date @ 5:00 PM.

4. **Retry on next day** — the Production's target date moves forward by 1 day (still within `due_datetime`); the full decision tree runs again with the new date. Each day tried counts as one retry.

5. **Manual review** — a `PendingSchedule` with:
   - `event_ref_num` = the Production's ref num
   - `employee_id` = NULL
   - `schedule_datetime` = NULL
   - `schedule_time` = NULL
   - `failure_reason` = explanatory text, e.g., "Primary and Backup Juicer both unavailable on all days within due date window (<start>–<due>)"
   - `status` = 'proposed'

## Pre-conditions

- Phase 1 and Phase 2 have run.
- `juicer_production_events` is sorted by `start_datetime` ascending.
- No Juicer Production PendingSchedule exists in the current run yet (this category has not started).
- The CORE/Supervisor category has NOT started yet.

## Post-conditions

- Every Juicer Production event in `juicer_production_events` has exactly one PendingSchedule (successful or manual review) in this run.
- Every Juicer Production that was successfully scheduled has its matching Juicer Survey (if one exists) also scheduled to the same employee on the same date @ 5:00 PM.
- Every CORE that was bumped is present in the CORE/Supervisor processing pool with:
  - its prior posted Schedule removed (for bumps of posted schedules), OR
  - its prior PendingSchedule re-opened (for bumps of in-run schedules).
- The CORE/Supervisor pool remains sorted by due date ascending, including newly-bumped entries.

## Branches

| ID | Description |
|---|---|
| JP1 | Sort juicer_production_events by start_datetime ascending |
| JP2 | For each event, get target_date = event.start_datetime.date() |
| JP3 | Look up Primary Juicer via RotationAssignment where day_of_week = target_date.weekday() and rotation_type = 'juicer' |
| JP4 | Look up ScheduleException for (target_date, 'juicer') — if present, override rotation |
| JP5 | Primary Juicer available? Check: NOT in unavailable_on(target_date). "unavailable_on" = approved time off OR weekly unavailability OR availability override |
| JP6 | Primary Juicer available YES + has CORE on target_date → bump the CORE, assign Production @ 9 AM |
| JP7 | Primary Juicer available YES + no CORE on target_date → assign Production @ 9 AM directly |
| JP8 | Primary Juicer available NO → proceed to Backup Juicer check |
| JP9 | Backup Juicer exists (RotationAssignment.backup_employee_id is not null) and available? |
| JP10 | Backup Juicer available YES + has CORE on target_date → bump the CORE, assign Production @ 9 AM to backup |
| JP11 | Backup Juicer available YES + no CORE on target_date → assign Production @ 9 AM to backup |
| JP12 | Backup Juicer unavailable (on PTO or no backup in rotation) → "Within due date window?" branch |
| JP13 | target_date + 1 day < due_datetime.date() → retry the whole decision tree with target_date := target_date + 1 |
| JP14 | target_date + 1 day >= due_datetime.date() → mark event as manual review with a clear reason |
| JP15 | After a successful assignment: find matching Juicer Survey (same event number, unscheduled) → assign to same employee on same date @ 5 PM |
| JP16 | Matching Juicer Survey does not exist → no Survey action, continue to next Production |
| JP17 | Bumped CORE is a posted Schedule → delete the old Schedule, create a bump PendingSchedule (is_swap=True), enqueue the CORE into category 3 pool sorted by due date |
| JP18 | Bumped CORE is an in-run PendingSchedule → clear the old PendingSchedule's employee and datetime, keep the row as "needs reprocessing", enqueue into category 3 pool sorted by due date |
| JP19 | "Has CORE scheduled" check must examine BOTH posted Schedule rows AND in-run PendingSchedule rows for (employee, target_date) — a CORE assigned earlier in the same run (e.g., from a previous retry or from a bumped-then-rescheduled CORE) counts |

## Edge cases

- **Primary Juicer on PTO; Backup Juicer has a CORE conflict:** The backup juicer is available (no PTO) but has a CORE. Under the spec, we bump the CORE and assign the backup juicer. This is allowed because the backup is being used due to PTO on the primary, not due to a CORE conflict on the primary — and once we commit to the backup, the backup's own CORE is subject to bumping just like the primary's would be.
- **Primary Juicer is not in the rotation at all (no RotationAssignment row for that day):** `get_rotation_employee(target_date, 'juicer')` returns `(None, None)`. Both JP5 and JP9 evaluate as "not available" → JP12.
- **Primary Juicer == Backup Juicer (same employee in both fields):** Treat backup as absent. If primary is unavailable, JP9 evaluates as "backup does not exist".
- **Juicer Production on day D already has a CORE posted to the primary juicer, but the CORE's own due date is BEFORE the Production's start date:** We still bump the CORE — the spec does not exempt "CORE already past its due date" from bumping. A CORE whose due date has already passed should not have been in the schedule in the first place; bumping it is harmless.
- **Juicer Production has no matching Juicer Survey:** JP16 branch; no Survey action. The Production is still scheduled.
- **Juicer Production retries 3 times across days D, D+1, D+2; on D+2 both primary and backup are available and no CORE conflict:** Success on D+2. The PendingSchedule's `schedule_datetime` uses D+2, not D.
- **Juicer Production has a `due_datetime` of D+1 (very narrow window):** If the primary on D is on PTO, try backup on D. If both are unavailable on D, JP13: is D+1 < D+1? No. So JP14: manual review. We do NOT retry on D+1 because D+1 is the due date itself (strict less-than).
- **Bump cascade:** Juicer Production on day D bumps CORE A. CORE A re-enters category 3, which later in its processing bumps CORE B (with a later due date than CORE A). CORE B re-enters category 3 too. Both must eventually be scheduled or land in manual review. The spec's "bump LATEST due date" rule ensures termination.
- **Matching Survey has a due date that has already passed:** Assign the Survey anyway (we're pairing to the Production's date, not the Survey's due date). The Survey's due date is informational once a matching Production exists.

## Do NOT

- Do NOT check "Primary Juicer has CORE" before checking "Primary Juicer available". The order is: (1) PTO check, (2) CORE conflict check (and bump if needed). An available primary with a CORE still wins over the backup.
- Do NOT use the Backup Juicer because the Primary Juicer has a CORE conflict. Backup is ONLY used when the Primary is on PTO or otherwise unavailable (weekly unavailability, override). CORE conflicts are resolved by bumping, not by falling back.
- Do NOT silently drop a Juicer Production event. Every event must produce a PendingSchedule.
- Do NOT schedule a Juicer Production at any time other than 9:00 AM. The time is fixed.
- Do NOT schedule a Juicer Survey's assignment time at any time other than 5:00 PM.
- Do NOT pair a Juicer Survey to a Production whose event numbers don't match. The matching is by the 6-digit event number embedded in both `project_name` strings.
- Do NOT retry on a day that's past the event's `due_datetime`. The retry loop terminates at `due_datetime.date() - 1` at latest.
- Do NOT re-open a bumped CORE into category 1. Bumped CORE always goes back to category 3.
- Do NOT forget to delete the old Schedule row when bumping a posted CORE — otherwise the post-review check will see both the bumped PendingSchedule AND the old Schedule and detect a double-book.

## Traceability table

| Branch ID | Plan task | Test case | Implementation location |
|---|---|---|---|
| JP1 | `02-juicer-production.md` T1 | `test_juicer_production_sorted_by_start_date` | TBD |
| JP2 | `02-juicer-production.md` T2 | `test_juicer_production_uses_start_date_as_target` | TBD |
| JP3, JP4 | `02-juicer-production.md` T3 | `test_get_primary_juicer_with_exception_override` | TBD |
| JP5 | `02-juicer-production.md` T4 | `test_primary_juicer_pto_detected` | TBD |
| JP6, JP7 | `02-juicer-production.md` T5, T6 | `test_primary_juicer_assigned_with_bump`, `test_primary_juicer_assigned_no_bump` | TBD |
| JP8, JP9 | `02-juicer-production.md` T7 | `test_backup_juicer_only_on_primary_pto` | TBD |
| JP10, JP11 | `02-juicer-production.md` T8, T9 | `test_backup_juicer_assigned_with_bump`, `test_backup_juicer_assigned_no_bump` | TBD |
| JP12 | `02-juicer-production.md` T10 | `test_both_juicers_unavailable_retry_next_day` | TBD |
| JP13, JP14 | `02-juicer-production.md` T11 | `test_retry_within_window`, `test_retry_past_due_manual_review` | TBD |
| JP15, JP16 | `02-juicer-production.md` T12 | `test_matching_survey_scheduled_at_5pm`, `test_no_matching_survey_no_action` | TBD |
| JP17 | `02-juicer-production.md` T13 | `test_bump_posted_core_creates_swap_pending` | TBD |
| JP18 | `02-juicer-production.md` T14 | `test_bump_in_run_core_reopens_pending` | TBD |
| JP19 | `02-juicer-production.md` T15 | `test_has_core_checks_both_posted_and_in_run` | TBD |
