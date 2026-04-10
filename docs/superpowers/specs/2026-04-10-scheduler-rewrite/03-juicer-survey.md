# Spec 03 — Juicer Survey Scheduling

> **Source image:** Image 2 of 7, section "2. Juicer Survey Scheduling". This file depends on `01-key-concepts.md` and `02-juicer-production.md` (for matching-Production semantics).

## Verbatim spec

**Sort order:** For each Survey (sorted by start date):

1. Has matching Production (same start date)?
   - **YES** → Already scheduled with Production @ 5:00 PM (skip).
   - **NO** → Standalone Survey (Mon/Wed) — continue below.
2. For standalone: Primary Juicer available + has primary event?
   - **YES** → Assign @ 5:00 PM.
   - **NO** → Check Backup Juicer.
3. Backup Juicer available + has primary event?
   - **YES** → Assign @ 5:00 PM.
   - **NO** → Club Supervisor **unconditionally** @ 5:00 PM.

> **Note on "Mon/Wed":** The spec parenthetically calls out that standalone surveys occur on Mondays and Wednesdays. This is observational, not a constraint — the scheduler does NOT restrict standalone surveys to Mon/Wed. If a standalone survey has a start date on any other day, process it normally.

## Inputs

- `juicer_survey_events` — all unscheduled events with `event_type == 'Juicer Survey'`.
- `juicer_production_events` processed by the Juicer Production category — used to detect "matching Production" by event number (same 6-digit number embedded in project_name).
- `current_run_pending_schedules` from the Juicer Production category — the Surveys that were auto-paired in JP15 are already in here and must be detected as "already scheduled" in JS1.
- `rotation_assignments` where `rotation_type == 'juicer'` — for Primary and Backup Juicer lookup.
- `schedule_exceptions` where `rotation_type == 'juicer'`.
- `employee_time_off`, `employee_weekly_availability`, `employee_availability_override`.
- `posted_schedules` + `current_run_pending_schedules` — to check "has primary event" on the target date.
- `club_supervisor_employee` — the employee with `job_title == 'Club Supervisor'`.

## Outputs

For each Juicer Survey event, exactly one of:

1. **Skipped (already paired with Production)** — no action in this category; the PendingSchedule was created in the Juicer Production category.
2. **Successful standalone proposal** — a `PendingSchedule` with:
   - `event_ref_num` = Survey's ref num
   - `employee_id` = Primary Juicer OR Backup Juicer OR Club Supervisor
   - `schedule_datetime` = event's `start_datetime.date()` @ 5:00 PM
   - `schedule_time` = 17:00:00
   - `status` = 'proposed'
   - `failure_reason` = NULL
3. **Manual review** — when the Club Supervisor is on PTO and all other fallbacks were exhausted:
   - `employee_id` = NULL, `schedule_datetime` = NULL, `failure_reason` = explanatory.

## Pre-conditions

- Juicer Production category (spec 02) has completed.
- `juicer_survey_events` is sorted by `start_datetime` ascending.
- For every Juicer Production that was scheduled, its matching Survey (if any) already has a PendingSchedule with `schedule_time = 17:00:00`.

## Post-conditions

- Every Juicer Survey event has exactly one PendingSchedule in the run (either from category 1 via auto-pairing, or from category 1-completion via this category).
- No standalone Juicer Survey is silently dropped (this was a known bug in the old CP-SAT path).
- Every successful standalone Survey proposal is assigned @ 5:00 PM.

## Branches

| ID | Description |
|---|---|
| JS1 | For each Survey, look up matching Production by event number (6-digit match on project_name prefix or parenthesized ref). |
| JS2 | Matching Production exists AND was successfully scheduled with matching start date → this Survey is already handled by JP15; skip. Do NOT create a second PendingSchedule. |
| JS3 | Matching Production exists but was NOT scheduled (it went to manual review) → treat this Survey as STANDALONE and continue. (Edge case not drawn explicitly in image.) |
| JS4 | Matching Production does not exist → standalone Survey; continue. |
| JS5 | target_date = event.start_datetime.date() |
| JS6 | Look up Primary Juicer via rotation for target_date. |
| JS7 | Primary Juicer available (no PTO/unavailability)? |
| JS8 | Primary Juicer available YES AND has a primary event on target_date → Assign Survey to Primary Juicer @ 5:00 PM. Done. |
| JS9 | Primary Juicer available YES but does NOT have a primary event on target_date → fall through to Backup Juicer (the spec is explicit: "available + has primary event"). |
| JS10 | Primary Juicer unavailable → fall through to Backup Juicer. |
| JS11 | Backup Juicer exists and available? |
| JS12 | Backup Juicer available YES AND has a primary event on target_date → Assign Survey to Backup Juicer @ 5:00 PM. Done. |
| JS13 | Backup Juicer available YES but does NOT have a primary event on target_date → fall through to Club Supervisor. |
| JS14 | Backup Juicer unavailable or does not exist → fall through to Club Supervisor. |
| JS15 | Club Supervisor unconditional assignment @ 5:00 PM. No "has primary event" check (per Key Concepts: CS fallback is unconditional w.r.t. primary-event requirement). |
| JS16 | Club Supervisor is on PTO on target_date → manual review. |
| JS17 | Club Supervisor does not exist (no employee with job_title == 'Club Supervisor') → manual review. |

## Edge cases

- **Standalone Survey on a day when the Primary Juicer has no primary event:** Per JS9, the Primary Juicer (even if available) is skipped. This is the literal reading of "available + has primary event". The backup juicer (if available + has primary event) gets it. If neither does, CS fallback unconditionally.
- **Survey's matching Production failed to schedule:** JS3 branch — treat Survey as standalone. Do not assume the Survey is "attached" to a failed Production.
- **Survey start date is a Tuesday (not Mon/Wed):** The "Mon/Wed" note in the image is descriptive. Process normally.
- **Survey event has no matching Production AND the Primary Juicer is on PTO AND there is no Backup Juicer AND the Club Supervisor is also on PTO:** Manual review. The spec does not have a deeper fallback.
- **Multiple standalone Surveys on the same day:** Each is processed independently. They may all land on the Club Supervisor via fallback; there is no "one Survey per CS per day" cap (unlike primary events, Surveys are secondary).
- **Survey pairing is ambiguous (two Productions with the same event number on different dates):** The Survey's `start_datetime` must match one of them; use that as the pair. If neither matches, standalone.

## Do NOT

- Do NOT silently drop a standalone Survey. This was the pre-existing CP-SAT bug (`cpsat_scheduler.py:770–774` removed standalone surveys from `self.events` without a fallback path). The new implementation must produce a PendingSchedule for EVERY Survey.
- Do NOT require the Club Supervisor to have a primary event in JS15. The CS fallback is unconditional w.r.t. the "requires primary event" rule.
- Do NOT skip the CS PTO check. Unconditional means "w.r.t. has-primary-event and other-fallbacks-exhausted", NOT "ignore PTO".
- Do NOT schedule a standalone Survey at any time other than 5:00 PM.
- Do NOT use the Primary Juicer when they don't have a primary event — in that case, fall through to Backup Juicer (JS9). The spec is explicit: "available + has primary event".

## Traceability table

| Branch ID | Plan task | Test case | Implementation location |
|---|---|---|---|
| JS1, JS2 | `03-juicer-survey.md` T1 | `test_paired_survey_skipped` | TBD |
| JS3 | `03-juicer-survey.md` T2 | `test_survey_of_failed_production_treated_as_standalone` | TBD |
| JS4 | `03-juicer-survey.md` T3 | `test_survey_without_production_is_standalone` | TBD |
| JS5, JS6 | `03-juicer-survey.md` T4 | `test_standalone_survey_target_date_and_rotation_lookup` | TBD |
| JS7 | `03-juicer-survey.md` T5 | `test_standalone_survey_primary_pto_check` | TBD |
| JS8 | `03-juicer-survey.md` T6 | `test_standalone_survey_primary_assigned_when_has_primary_event` | TBD |
| JS9 | `03-juicer-survey.md` T7 | `test_standalone_survey_primary_without_primary_event_falls_through` | TBD |
| JS10 | `03-juicer-survey.md` T8 | `test_standalone_survey_primary_pto_falls_through` | TBD |
| JS11, JS12 | `03-juicer-survey.md` T9 | `test_standalone_survey_backup_assigned_when_has_primary_event` | TBD |
| JS13, JS14 | `03-juicer-survey.md` T10 | `test_standalone_survey_backup_falls_through` | TBD |
| JS15 | `03-juicer-survey.md` T11 | `test_standalone_survey_cs_unconditional_fallback` | TBD |
| JS16, JS17 | `03-juicer-survey.md` T12 | `test_standalone_survey_manual_review_when_cs_unavailable` | TBD |
