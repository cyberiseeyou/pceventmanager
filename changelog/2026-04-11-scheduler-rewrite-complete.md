# 2026-04-11 — Scheduler rewrite complete (plans 00–08 + 99)

## Summary

The 2026-04-10 scheduler rewrite is complete. The auto-scheduler is
now a spec-conformant greedy engine
(`app/services/scheduling_engine.py`) that implements every branch of
the 7-image specification at
`docs/superpowers/specs/2026-04-10-scheduler-rewrite/`. CP-SAT is
retired from the production code path.

- PR: `cyberiseeyou/pceventmanager#8` (`refactor/scheduler-plan-02-juicer-production`)
- Test coverage: **100 scheduler conformance tests** + **run-192 regression harness** (17/17 events match spec-predicted outcomes)
- Full non-ML project suite: **351 pass**, 86 deselected (`optional` CP-SAT), 2 skipped
- Plans landed on this branch: **02, 03, 04, 05, 06, 07, 08, 99** (plans 00/01 were on the branch when the work began)

## Motivation

Auto-scheduler run 192 (2026-04-10 08:32:37) produced 15 manual-review
failures out of 17 events because CP-SAT's constraint model diverged
from the actual Crossmark scheduling policy in two ways:

1. **H13 symmetric mutual exclusion** made Juicer Production and Core
   mutually blocking on the same employee/day — neither could yield to
   the other, even though the spec says Juicer outranks Core.
2. **Bumpable-Core pinning** forbid a displaced Core from re-landing
   on any day other than its original posted day — which made "bump
   the Core out of the juicer's slot" a dead end.

The 2026-04-10 primary/secondary rules alignment patched CP-SAT to
approximate the policy, but the deeper issue was that CP-SAT's
all-at-once optimization can't faithfully express the spec's
sequential-with-bumping semantics. The rewrite replaces CP-SAT with a
greedy engine that walks the spec decision trees branch-by-branch.

## Changes

### New engine: `app/services/scheduling_engine.py`

The Phase 3 category dispatcher now delegates to six real category
handlers (all previously stubs):

- `_process_juicer_production` — spec 02 (JP1–JP19). Rotation lookup
  with `ScheduleException` override; primary available + CORE conflict
  → bump CORE into category 3; primary PTO → backup; retry-next-day
  loop within `[start, due)`; manual review on exhaustion; matching
  Juicer Survey auto-paired @ 5 PM.
- `_process_juicer_survey` — spec 03 (JS1–JS17 + K4). Paired surveys
  skipped (already placed by JP15); standalone chain: primary +
  `has_primary_event` → backup + `has_primary_event` → Club Supervisor
  unconditional (respecting PTO). Fixes the pre-existing silent-drop
  bug where standalone surveys were removed from `self.events` without
  a fallback (`cpsat_scheduler.py:770–774`).
- `_process_core_supervisor` — spec 04 (C1–C16 + S1–S8). New
  `core_slot_allocator` module with "fill 2 per slot before advancing,
  then +1 per slot per pass, always fill gaps first" logic (C9/C10/C11);
  date-window iteration with retry; Primary Lead @ 10:15 /
  Other Leads / fewest-primaries-this-week selection; CORE-to-CORE
  bumping with latest-due-date tiebreak; Supervisor decision tree: CS
  first → Primary Lead with CORE → Backup Lead with CORE → CS
  unconditional → manual review.
- `_process_freeosk` — spec 05 (F1–F11). Three subcategories
  (`daily_service`, `changeover`, `troubleshooting`) processed in
  strict order, each with fixed time and the shared Primary Lead →
  Backup Lead → CS unconditional chain.
- `_process_digitals` — spec 06 (D1–D15). Name-ends-with partitioning
  (Setup / Refresh / Teardown), Saturday-only Setup gate, +15 min
  offsets, Setup/Refresh shared employee chain, Teardown's unique
  "non-Primary Lead scheduled that day" logic.
- `_process_other` — spec 07 (O1–O6 + K7). REVERSED priority: CS
  first, Primary Lead fallback (no `has_primary_event` check for
  either branch per spec).

### Bumping model

`_bump_core_to_pool(core_row, run)` handles both directions:

- **Posted Schedule → PendingSchedule swap-marker**: the posted row is
  deleted, a new `PendingSchedule` is created with `is_swap=True`,
  `bumped_posted_schedule_id=<old>`, `employee_id=NULL`,
  `schedule_datetime=NULL`. The underlying Event is re-queued into the
  core_supervisor pool.
- **In-run PendingSchedule → in-place mutation**: the existing row's
  `employee_id` and `schedule_datetime` are cleared, `is_swap=True`,
  re-queued. No new row is created, so invariant 1 (exactly one
  PendingSchedule per event per run) holds.

`_assign_core(event, employee_id, d, slot_time, shift_block, run)`
detects a swap-marker row and UPDATES it in place rather than inserting
a duplicate. This cleanly bridges the plan 02 → plan 04 handoff: a
juicer-bumped CORE carries the `bumped_posted_schedule_id` metadata all
the way through to its final placement by the CORE handler.

### Helpers

New module-level helpers in `app/services/scheduler_helpers.py`:

- `lookup_rotation(db, models, target_date, rotation_type)` —
  ScheduleException overrides RotationAssignment.
- `classify_event(event_type)` — primary / secondary / teardown_bucket
  / other per key concepts K1–K3.
- `freeosk_subcategory(project_name)` — pure name classifier.
- `digital_subcategory(project_name)` — pure name classifier.

New helper in `app/services/scheduler_pairing.py`:

- `extract_six_digit_prefix(project_name)` — production/survey pairing
  by leading 6-digit event number (the production name doesn't end in
  CORE/SUPERVISOR so the pairing regex doesn't apply).

New module `app/services/core_slot_allocator.py` — pure, testable
time-slot packing logic with 6 unit tests covering every branch of
C5/C9/C10/C11.

### CP-SAT retirement (plan 08)

- `app/routes/auto_scheduler.py`: removed the `CPSAT_ENABLED` flag
  check, the per-request `?solver=` override, and the
  `CPSATSchedulingEngine` import / instantiation. The route now
  unconditionally instantiates `SchedulingEngine`.
- `app/config.py`: deleted `CPSAT_ENABLED` and `CPSAT_TIME_LIMIT`
  config keys.
- `app/templates/auto_scheduler_main.html`: removed the CP-SAT badge.
  The "Greedy Solver" badge is shown unconditionally.
- `app/services/cpsat_scheduler.py`: added a `DEPRECATED` docstring
  notice pointing at plan 08. The module still exists but must NOT be
  imported from production code.
- `tests/test_cpsat_stress.py`, `tests/test_cpsat_scheduler.py`,
  `tests/test_cpsat_double_booking.py`: added module-level
  `pytestmark = pytest.mark.optional` so CI skips them by default. Run
  explicitly with `pytest -m optional tests/test_cpsat_*`.
- `pytest.ini`: registered the `optional` marker and added
  `addopts = -m "not optional"`.
- Removed the stale `_force_cpsat` / `_auto_force_cpsat` autouse
  fixtures that existed only to toggle the now-deleted flag.

### Test coverage (new)

```
tests/scheduler_spec_conformance/
├── fixture_loader.py                      # run-192 regression loader
├── test_02_juicer_production.py           # 14 tests (JP1–JP19)
├── test_03_juicer_survey.py               # 11 tests (JS1–JS17 + K4)
├── test_04_core_slot_allocator.py         #  6 unit tests (C5/C9/C10/C11)
├── test_04_core_supervisor.py             # 12 integration tests
├── test_05_freeosk.py                     # 13 tests (5 unit + 8 integration)
├── test_06_digitals.py                    # 13 tests (4 unit + 9 integration)
├── test_07_other.py                       #  5 tests (O2/O3, K7, O4/O5, O6 ×2)
├── test_08_cpsat_retired.py               #  3 tests (flag absent, no import, deprecation)
└── test_99_run_192_regression.py          #  4 tests (loader, JPs, Cores, invariant 1)
```

Full scheduler conformance suite: **100 tests, all pass**.

### Expected-outcomes reconciliation (plan 99)

`tests/scheduler_spec_conformance/fixtures/run_192/expected.json` —
three May 8 MDay cores (31921484, 31922471, 31922475) were originally
predicted as `manual_review` under the old Pattern A (CP-SAT) weekly
core cap. The greedy engine has no such cap and the fixture has 12
active employees (3 Leads, 7 specialists, 2 juicers) — plenty for 3
MDay cores plus the bumped CORE from the May 8 Juicer Production.
Reconciled to `scheduled_success` per plan 99 T3 Step 2 guidance, with
notes recording the reconciliation rationale.

### Plan 02 test update (integrated into plan 04 commit)

The first iteration of `test_02_juicer_production.py` asserted that
bumped-CORE swap-marker rows had `employee_id=None` at end-of-run. This
was correct only against the plan 02 → plan 04 stub. Once plan 04
started re-placing those markers, the assertions needed to flip to
"re-placed with `is_swap=True` preserved". All three affected tests
(`test_jp6_jp17`, `test_jp10`, `test_jp19`) were updated in the plan
04 commit to assert the end-of-run invariants correctly.

### Plan 02 → plan 04 transitional stub

`_process_core_supervisor` had a hardened stub introduced in plan 02
that skipped events already carrying a PendingSchedule (so bumped
CORE swap-markers weren't duplicated). Plan 04 preserves the helper
(`_has_pending_schedule_in_run`) and reuses it in the paired-Supervisor
flow to avoid double-inserts.

## Not included (deferred)

- **Legacy Wave 1–5 scheduling methods**: `_schedule_juicer_events_wave1`,
  `_schedule_single_juicer_event_wave1`, `_bump_core_events`,
  `_try_juicer_fallback`, `_schedule_wave2_core_events`,
  `_schedule_freeosk_digital_events_wave3`,
  `_schedule_digital_events_wave4`, and related helpers remain in
  `scheduling_engine.py` as dead code — not invoked by
  `run_auto_scheduler` anymore. Deleting them is a follow-up cleanup
  that will shrink the engine file substantially but carries a small
  risk of removing a helper that's still referenced elsewhere.
- **Manual dev-mode smoke test**: plan 99 T5 Step 3 recommended
  triggering an auto-schedule run via the real UI against a dev DB
  after backing up. Not performed in this session; the run-192
  regression harness covers the input shape end-to-end but not the
  full Flask request/response path.

## Safety invariants

All 8 safety invariants from the plan README's "Safety invariants that
must never break" section are enforced by
`tests/scheduler_spec_conformance/test_00_invariants.py` and the
category-specific conformance tests:

1. ✅ Every event produces exactly one PendingSchedule (including
   bumped CORE events flowing plan 02 → plan 04).
2. ✅ `employee_id=None` ⇒ `failure_reason` set (manual-review rows
   pass through `_create_failed_pending_schedule` and
   `_upsert_core_manual_review`).
3. ✅ `employee_id` set ⇒ `schedule_datetime` and `schedule_time` set
   (enforced by `_create_pending_schedule`'s critical validation).
4. ✅ No two primary events on the same `(employee, date)` pair (the
   `has_primary_event` cache is consulted before every placement).
5. ✅ CS PTO never violated (every CS branch calls
   `cache.is_available` before placement).
6. ✅ Times are always spec-allowed per category (hardcoded in the
   handlers: JP @ 9 AM, JS @ 5 PM, CORE @ [10:15/10:45/11:15/11:45],
   Supervisor @ 12 PM, Freeosk A/B @ 10 AM + C @ 12 PM,
   Digitals per subcategory + offsets, Other @ 12 PM).
7. ✅ `SchedulerRunHistory.status` transitions only running →
   {completed, failed} (unchanged from the previous engine).
8. ✅ DB rollback on exception (existing commit/rollback boundary in
   `run_auto_scheduler` is untouched).

## Rollback

This change is on a feature branch and has not been merged to `main`
yet. If a post-merge issue surfaces:

1. **Immediate**: revert the PR (`gh pr merge --revert 8`). The
   previous CP-SAT-based scheduler returns immediately.
2. **Short term**: isolate which plan's commit introduced the issue
   (commits are one per plan), revert just that commit with `git
   revert`, re-land the rest.
3. **Long term**: add a conformance test that reproduces the failure,
   fix the code, re-land.

Note that plan 08 removed the `CPSAT_ENABLED` env-var rollback lever
— after the merge there is no "flip a flag" rollback, only a commit
revert.

## Related documents

- Spec source: `docs/superpowers/specs/2026-04-10-scheduler-rewrite/`
- Plans (each marked ✅ in the master README):
  `docs/superpowers/plans/2026-04-10-scheduler-rewrite/`
- Previous incremental CP-SAT patch:
  `changelog/2026-04-10-primary-secondary-rules-alignment.md`
- Pull request: `cyberiseeyou/pceventmanager#8`
