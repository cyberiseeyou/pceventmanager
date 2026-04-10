# Spec 07 — Other Events Scheduling

> **Source images:** Image 4 of 7 bottom ("6. Other Events Scheduling" heading) and Image 5 of 7 (the full Other decision tree).

## Verbatim spec

**Catch-all category for everything not categorized above.**

1. Club Supervisor available (no time off + weekly availability)? → Assign @ **12:00 PM**.
2. Not available? → Primary Lead @ **12:00 PM**.

> ★ **Note: This is REVERSED from other flows — Club Supervisor is FIRST choice, not fallback.**

## Inputs

- `other_events` — all unscheduled events with `event_type == 'Other'` OR any `event_type` not already claimed by a prior category (catch-all interpretation). The cleanest implementation processes this category last and takes whatever remains in the unscheduled pool.
- `rotation_assignments` where `rotation_type == 'primary_lead'`.
- `employee_time_off`, `employee_weekly_availability`, `employee_availability_override`.
- `club_supervisor_employee`.

## Outputs

Per Other event: one PendingSchedule (proposal or manual review) at 12:00 PM.

## Pre-conditions

- Categories 1–5 have completed (Juicer Production, Juicer Survey, CORE + Supervisor, Freeosk, Digitals).
- `other_events` is sorted by `start_datetime` ascending.

## Post-conditions

- Every Other event has exactly one PendingSchedule.
- All successful Other assignments are @ 12:00 PM.
- Club Supervisor is consulted FIRST for every Other event (not as a fallback).

## Branches

| ID | Description |
|---|---|
| O1 | For each Other event, target_date = event.start_datetime.date() |
| O2 | Club Supervisor available on target_date? "Available" = not on approved time off AND passes weekly availability for the DoW. No "has primary event" check for CS. |
| O3 | CS available → assign Other to Club Supervisor @ 12:00 PM. Done. |
| O4 | CS unavailable → try Primary Lead (from rotation for target_date) |
| O5 | Primary Lead available on target_date → assign Other to Primary Lead @ 12:00 PM. NOTE: spec does NOT say "+ has primary event" for this branch — the Other category skips that check. |
| O6 | Primary Lead unavailable → manual review with reason "Other event: Club Supervisor on PTO and Primary Lead unavailable on <date>" |

## Edge cases

- **CS is on PTO but Primary Lead has no primary event on target_date:** The spec does not require Primary Lead to have a primary event in O5 (unlike Freeosk/Digitals). Still assign. This is a deliberate simplification of the catch-all category.
- **Neither CS nor Primary Lead available:** Manual review. No deeper fallback exists for Other.
- **No Primary Lead rotation for target_date's DoW:** `get_rotation_employee` returns (None, None). Primary Lead is "not available". Manual review.
- **CS is the Primary Lead:** Job-title-based routing picks the first match (CS, via O3). Primary Lead branch is unreachable.
- **Event type is e.g. "Supervisor" (a known category) but slipped past Phase 2 pairing because the matching CORE was dropped:** An orphan Supervisor would NOT land here — Phase 2 logs-and-skips unpaired Supervisors. But if a spec-violating path leaves one in the pool, treat it as Other and process accordingly.

## Do NOT

- Do NOT use the Primary Lead as the first choice for Other events. CS is FIRST.
- Do NOT require Primary Lead to have a primary event in the Other category.
- Do NOT schedule Other events at any time other than 12:00 PM.
- Do NOT apply "unconditional" CS assignment here — CS must pass its PTO + weekly availability check in O2. The "unconditional" CS fallback (from Key Concepts) applies to categories where CS is the LAST branch, not the FIRST. In Other, CS is the first branch and must pass availability checks; if it fails, the flow proceeds to Primary Lead.

## Traceability table

| Branch ID | Plan task | Test case | Implementation location |
|---|---|---|---|
| O1 | `07-other.md` T1 | `test_other_target_date_from_start` | TBD |
| O2, O3 | `07-other.md` T2 | `test_other_cs_first_choice_available` | TBD |
| O4, O5 | `07-other.md` T3 | `test_other_primary_lead_fallback` | TBD |
| O6 | `07-other.md` T4 | `test_other_manual_review_when_both_unavailable` | TBD |
