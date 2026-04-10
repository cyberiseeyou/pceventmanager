# 2026-04-10 — Primary/secondary rules alignment

## Summary

Reframed the CP-SAT auto-scheduler around the user-stated **primary vs. secondary** policy:

- **Primary events** are `Core` and `Juicer Production`. Each employee may hold at most **one primary per day**.
- **Secondary events** (Digitals, Freeosk, Supervisor, Juicer Survey, Other) are unlimited per day but require the same employee to also hold a primary that day.
- **Juicer Production strictly outranks Core.** When the primary rotation juicer already has a Core posted on the day a Juicer Production needs to run, the Core is **bumped** to another day inside its own window — instead of blocking the Juicer.
- **Core is window-flexible** even when bumpable: it may re-land on any day in `[start_datetime, due_datetime)`, not just its current posted day.
- **Backup juicers are used only when the primary juicer has approved PTO**, not when the primary merely has a Core conflict.

## Motivation

Auto-scheduler run 192 (2026-04-10 08:32:37) produced 15 manual-intervention failures out of 17 events, split as:

- **5 Core** events failed with `Post-review: conflicts with 1 existing posted Core event(s)`.
- **10 ESI Juicer Production** events failed with the generic `Solver could not schedule within constraints`.

The failures traced back to two interacting CP-SAT behaviors that diverged from the user's actual policy:

1. **H13** (`_add_mutual_exclusion_per_day`) treated Juicer Production and Core as a symmetric hard-excluded pair on the same employee/day. Since the constraint was symmetric, neither event could yield to the other — even though the user wants the Core to step aside for the Juicer.
2. **Bumpable-Core pinning**: `_valid_days_for_event` pinned bumpable events to their currently-posted day(s), so a displaced Core had nowhere to go. Comment on cpsat_scheduler.py:877 read *"Bumpable events are pinned to their currently-scheduled day(s) ONLY"* — this was correct for Juicer types (pinned to start date) but wrong for Core (window-flexible).

The combined effect: on every day where the primary rotation juicer (CLAUDIA or THOMAS per the Crossmark juicer rotation) already had a Core posted, the Juicer Production was silently blocked.

## Changes

### `app/services/cpsat_scheduler.py`

**New constant** (`PRIMARY_EVENT_TYPES = {'Core'} | JUICER_PRODUCTION_TYPES`) — the canonical set of primary event types.

**Unified primary cap.** Replaced H11 (`≤1 Core/emp/day`) + H13 (`Core⊥JuicerProd same emp-day`) + H22 (`≤1 JuicerProd/emp/day`) with a single `_add_emp_day_limits(primary_events, 1, existing_counts=existing_primary_count_by_emp_day)` call. The objective function's type-priority weight (Juicer = 1, Core = 6) decides which primary wins when both compete for the same slot.

Removed the dead `_add_mutual_exclusion_per_day` helper.

**Bumpable Core is now window-flexible.** `_valid_days_for_event` now returns the full event window for bumpable Core events instead of only the posted day(s). Other bumpable types (Juicer Production, Juicer Survey, etc.) remain pinned because of `JUICER_START_DATE_PINNED`.

**Existing-count tracking.** Added `existing_primary_count_by_emp_day` (populated alongside `existing_core_count` and `existing_juicer_count`) in:
- `_compute_existing_core_counts` — reads posted schedules
- `_inject_pending_as_existing` — adds Phase 2 proposals to Phase 3 state

**Post-solve review** now enforces the primary cap (instead of Core-only). `_post_solve_review` scans all primary pending schedules, detects cross-run conflicts against `existing_primary_count_by_emp_day`, and surfaces them with a clarified failure reason: *"Post-review: conflicts with N existing posted primary event(s) (Core or Juicer Production)."* Check 3 (weekly excess) stays Core-specific because the weekly cap is still per-type.

### `docs/scheduling_validation_rules.md`

- **RULE-001** reworded from "Single Core/Juicer Production Limit" to "One Primary Event Per Employee Per Day" (explicit primary/secondary language).
- **RULE-006** clarified to reference RULE-001 and RULE-022 (no longer a standalone exclusion).
- **RULE-022** added: "Juicer Production Outranks Core (Bump-the-Core)."
- **RULE-023** added: "Backup Juicer Only on Approved PTO."

### `tests/test_cpsat_stress.py`

Added `TestScenarioPrimarySecondaryRules` with three scenarios:

1. **`test_juicer_bumps_core_on_same_day`** — Pre-post a wide-window Core to the primary juicer on day D, then run the scheduler with a Juicer Production on D. Expect the Juicer on the juicer, the Core re-landed on a different day (or at least not sharing day D with the same juicer).
2. **`test_juicer_falls_back_to_backup_only_on_pto`** — Put the primary juicer on PTO for day D. Expect the Juicer Production to fall through to the rotation backup.
3. **`test_juicer_bumps_core_with_no_room_core_fails`** — Pre-post a narrow-window Core (start=D, due=D+1) to the primary juicer. The Juicer should still win, and the Core should fail gracefully (nowhere to move).

## Testing

- `pytest tests/test_cpsat_stress.py -v` — **41 passed** (38 original + 3 new).
- `pytest -v` — **339 passed**, 2 skipped, 1 pre-existing unrelated failure in `test_reports.py::test_export_with_date_params` (CSV filename date-handling bug; verified failing on unmodified code).

## Expected operational impact

Re-running auto-scheduler on the same input set as run 192 should:

- Schedule all 10 failing ESI Juicer Production events. Primary rotation juicer gets the slot; where the juicer had a Core, the Core is moved to another day in its window.
- Resolve the 2 wide-window Core failures (Tuna Burger May 2–15, Creative Gummies Mar 28–Apr 11).
- Leave 3 narrow-window Core failures on the May 8–10 MDay batch as **legitimate capacity exhaustion** — the fix cannot create slots that don't exist.

## Out of scope

- **Generic-failure-message diagnostics** (`_create_pending_failure` upgrade to walk eligible employees × days and report first hard-blocker). Only needed if the rule fix leaves residual unexplained failures.
- **Secondary-requires-primary** extension for Juicer Survey and "Other" event types (RULE-005 currently only covers Freeosk/Digital/Supervisor). Audit deferred.
- **H17 pairing** behavior when an already-posted Juicer Survey is bound to employee A and a new Juicer Production needs employee B — requires its own spec.
- **Data-staleness audit** of `_inject_pending_as_existing` for cross-phase updates — separate follow-up.
