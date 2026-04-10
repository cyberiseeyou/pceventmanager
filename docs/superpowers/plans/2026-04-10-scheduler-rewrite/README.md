# Scheduler Rewrite — Master Plan (2026-04-10)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to execute this plan task-by-task. DO NOT execute inline — each task must be a fresh subagent session to prevent context pollution and drift. See `review-gates.md` for the review gates every task must pass.

**Goal:** Refactor the Flask auto-scheduler so that it follows the 7-image spec at `docs/superpowers/specs/2026-04-10-scheduler-rewrite/` exactly. This is a multi-week refactor of the core scheduling engine that powers production.

**Architecture:** Greedy-first. The existing CP-SAT constraint solver (`cpsat_scheduler.py`) is retired from the production code path because it cannot faithfully express the spec's sequential-with-bumping semantics. The greedy `scheduling_engine.py` is refactored to match the spec 1:1 and becomes the production scheduler. CP-SAT stays in the repo as a dead-code module that may be resurrected as an offline analyzer if needed.

**Tech Stack:** Flask 2.0+, SQLAlchemy, Python 3.12, pytest for TDD, no new dependencies.

---

## Execution DAG

Plans must be executed in this exact order. Each plan produces a set of passing tests that the next plan's tests rely on. Each plan ends in a commit and a PR.

```
00-foundation              — feature flag flip, test infra, conformance harness
       │
       ▼
01-phase-infrastructure    — Phase 1/2/3 skeleton: category order, sort keys, helpers
       │
       ▼
02-juicer-production       — Wave 1 Juicer Production spec conformance
       │
       ▼
03-juicer-survey           — Wave 1 Juicer Survey + standalone fallback fix
       │
       ▼
04-core-supervisor         — Wave 2 CORE + Supervisor spec conformance (biggest)
       │
       ├─▶ 05-freeosk      ┐
       ├─▶ 06-digitals     ├── sequential for review simplicity (no data dependency)
       └─▶ 07-other        ┘
                │
                ▼
       08-retire-cpsat     — remove CP-SAT from production path
                │
                ▼
       99-acceptance-harness — run-192 regression replay, full conformance sweep
```

## Feature flag strategy

- **Before plan 00 runs:** `CPSAT_ENABLED=True` (default). CP-SAT is the production scheduler.
- **After plan 00 lands:** `CPSAT_ENABLED=False` (new default). Greedy is the production scheduler. CP-SAT remains reachable by setting the env var `CPSAT_ENABLED=true`.
- **After plans 01–07 land:** The greedy engine has been fully refactored to match the spec.
- **After plan 08 lands:** `CPSAT_ENABLED` flag is removed entirely. The `cpsat_scheduler.py` module is marked `@deprecated` and its only callers are the stress test suite (marked `@pytest.mark.optional`).
- **After plan 99 lands:** The run-192 regression harness is part of CI; any change to `scheduling_engine.py` must pass it.

At any point during plans 01–07 a supervisor can roll back to CP-SAT in production by setting `CPSAT_ENABLED=true` in the env. This is the primary rollback mechanism.

## Rollback plan

If production breaks during rollout:
1. **Immediate:** set `CPSAT_ENABLED=true` env var, restart the Flask worker. Previous scheduler returns in <1 minute.
2. **Short term:** revert the offending plan's PR. All plans are independent commits so reverting one does not destabilize the others.
3. **Long term:** investigate failure, add a conformance test that reproduces the failure, fix the code, re-land.

## Conformance test harness (defined in plan 00)

All test files live at `tests/scheduler_spec_conformance/`:

```
tests/scheduler_spec_conformance/
├── __init__.py
├── conftest.py                         — scheduler setup fixtures
├── test_00_master_overview.py          — Phase 1/2/3 + ordering tests
├── test_01_key_concepts.py             — primary/secondary/bumping tests
├── test_02_juicer_production.py        — every JP1..JP19 branch
├── test_03_juicer_survey.py            — every JS1..JS17 branch
├── test_04_core_supervisor.py          — every C1..C16 + S1..S8 branch
├── test_05_freeosk.py                  — every F1..F11 branch
├── test_06_digitals.py                 — every D1..D15 branch
├── test_07_other.py                    — every O1..O6 branch
├── test_99_run_192_regression.py       — full replay of run 192 input data
└── fixtures/
    ├── run_192_events.json             — captured event data from run 192
    ├── run_192_rotations.json          — rotation snapshot at run 192
    └── run_192_expected_schedule.json  — the schedule the spec predicts
```

Every test name maps to a branch ID in the corresponding spec file's traceability table. If a branch ID has no test, that's a spec gap (caught by Gate C) or a test gap (caught by Gate E).

## Review gates

See `review-gates.md` for the 5 gates (A–E) and their subagent prompt templates. Every task in every plan goes through:
- **Gate A (Spec Verification):** once per spec file, before any plan work starts.
- **Gate B (Pre-Impl Audit):** once per plan file, before the first task runs.
- **Gate C (Plan Coverage):** once per plan file, after the plan is written.
- **Gate D (Implementation Drift):** once per plan task, after the code change commits.
- **Gate E (Test Adequacy):** once per plan file, after all test tasks are written.

Gates are **blocking**: a plan task cannot move to the next step until the gate for the current step has passed.

## Plan file conventions

Every plan file follows the writing-plans skill template:

```markdown
# Plan N — <Title> Implementation Plan

**Goal:** <one sentence>
**Architecture:** <2–3 sentences>
**Tech Stack:** Flask 2.0+, pytest, SQLAlchemy (inherited from project)
**Source spec:** docs/superpowers/specs/2026-04-10-scheduler-rewrite/<N>-<name>.md
**Depends on:** <previous plan files, if any>

---

## Pre-flight (Gate B — Pre-Impl Audit)

Subagent prompt for the audit gate. Must complete and return PASS before Task 1.

## Task 1 — <...>

Files:
- Create / Modify / Test

- [ ] Step 1: Write the failing test
      <actual code>
- [ ] Step 2: Run to verify it fails
      Command, expected output
- [ ] Step 3: Write minimal implementation
      <actual code>
- [ ] Step 4: Run to verify it passes
      Command, expected output
- [ ] Step 5: Commit
      <commit message>
- [ ] Step 6: Gate D review (subagent)
      <subagent prompt>

## Task 2 — <...>

... (same structure) ...

## Post-flight (Gate C + Gate E review)

... (subagent prompts) ...
```

All tasks are numbered sequentially within the plan file (T1, T2, ...). Task IDs in the spec traceability tables must match these exactly.

## Context budget per task

Every plan task must be executable in a fresh subagent session with the following loaded:
1. The task description (the part of the plan file for that task).
2. The corresponding spec file (up to 400 lines).
3. The specific source file(s) being modified (typically one file, up to 3000 lines).
4. The test file being written (new or up to 1000 lines of existing content).
5. The output of `git diff HEAD~1` for the most recent commit (for context continuity with the prior task).

Total loaded context budget per task: **<20k tokens**. This is enforced by keeping plan tasks small (2–5 minutes of work) and files focused.

## Glossary (quick reference — full definitions in `specs/01-key-concepts.md`)

- **Primary event** — CORE, Juicer Production.
- **Secondary event** — Juicer Survey, Supervisor, Freeosk, Digitals Setup, Digitals Refresh.
- **Digital Teardown** — Its own bucket. Not primary, not secondary.
- **Bumping** — Primary events only. Juicer Prod bumps CORE; CORE bumps CORE with later due date.
- **CS Fallback** — Unconditional w.r.t. has-primary-event; still respects PTO.
- **Manual review pool** — `PendingSchedule` rows with `employee_id=None`, `failure_reason` set.
- **Week (Sun–Sat)** — Scheduling week for "fewest primaries this week" math.

## Safety invariants that must never break

These are spec-independent safety properties. Every plan task that touches the scheduler must not violate any of these. They are enforced by conftest.py fixtures in the conformance test suite.

1. **Every event produces exactly one PendingSchedule** per run. No silent drops, no duplicates.
2. **A PendingSchedule with `employee_id=None` MUST have `failure_reason` set.** No invalid states.
3. **A PendingSchedule with `employee_id` set MUST have `schedule_datetime` AND `schedule_time` set.**
4. **No two primary events are assigned to the same `(employee_id, date)` pair in a single run.**
5. **Club Supervisor PTO is never violated.** Even in "unconditional" fallback branches.
6. **No scheduled time is outside the spec's allowed times for its category** (e.g., CORE at 13:00 is invalid).
7. **`SchedulerRunHistory.status` transitions only: running → completed OR running → failed.** No other states.
8. **Database rollback on exception:** if any task raises during scheduling, the run's PendingSchedule records AND the SchedulerRunHistory row are rolled back atomically.

## Dependency between plans (read carefully)

- Plan 01 depends on 00 (test harness must exist).
- Plan 02 depends on 00, 01 (phase infra must exist before Juicer Production category can be implemented).
- Plan 03 depends on 00, 01, 02 (standalone Juicer Survey handling needs the pairing logic from 02).
- Plan 04 depends on 00, 01, 02 (CORE category must process Juicer-bumped events).
- Plans 05, 06, 07 depend on 00, 01, 04 (secondary categories need the "has primary event" query which is built in 04).
- Plan 08 depends on 01, 02, 03, 04, 05, 06, 07 (cannot retire CP-SAT until the greedy engine fully replaces it).
- Plan 99 depends on everything (final acceptance).

## What to do when a plan fails a gate

- **Gate A fails (spec mismatch with image):** Update the spec file to match the image. Do NOT update the image to match the spec. The image is authoritative.
- **Gate B fails (audit finds existing behavior that the plan will silently break):** Add a task to the plan file to explicitly preserve or explicitly remove the behavior, with a decision note in the changelog.
- **Gate C fails (plan doesn't cover a spec branch):** Add the missing task to the plan file; re-run Gate C.
- **Gate D fails (implementation drifted from spec):** Revert the task's commit; re-do the implementation with the subagent briefed on the specific drift.
- **Gate E fails (test doesn't cover a spec branch):** Add the missing test; do not merge until all branches are covered.

## Tracking

Use `TaskCreate` to track progress at the plan-file level (one task per plan file). Within each plan file, use checkboxes (`- [ ]`) to track task-level progress. Update TaskList weekly at minimum.
