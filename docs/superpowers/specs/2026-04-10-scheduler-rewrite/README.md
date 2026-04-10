# Scheduler Rewrite — Spec Set (2026-04-10)

> **For every reader (human or agent):** This directory is the **single source of truth** for how the auto-scheduler must behave. If any implementation in the codebase disagrees with any rule in any file in this directory, the implementation is wrong, not the spec.

## Why this spec exists

On 2026-04-10, auto-scheduler run 192 failed 15 out of 17 events. Investigation showed that the CP-SAT constraint solver (`app/services/cpsat_scheduler.py`) cannot faithfully express the spec that the owner of this system gave us in 7 hand-authored images. The spec is a **sequential, deterministic, priority-ordered greedy algorithm with bumping and fallbacks** — a concept that is structurally incompatible with how CP-SAT's global-objective solver thinks about scheduling.

We chose **Option A — Greedy-first architecture**: refactor `app/services/scheduling_engine.py` (the older greedy wave-based scheduler that was already ~70% aligned with the spec) into full spec conformance, flip the `CPSAT_ENABLED` default off, and keep CP-SAT as an optional offline analyzer.

## The 7 source images

All seven images were uploaded on 2026-04-10 in the conversation that produced this spec set. They are the **original authority**. If this directory ever drifts from them, the images win.

| Image | Content | Spec file |
|---|---|---|
| 1 | Event Scheduling System Master Overview — Phases 1/2/3, category order, sort keys | `00-master-overview.md` |
| 2 | §1 Juicer Production + §2 Juicer Survey scheduling | `02-juicer-production.md`, `03-juicer-survey.md` |
| 3 | §3 CORE/Supervisor scheduling — date window, employee priority, time slots, Supervisor logic | `04-core-supervisor.md` |
| 4 | §4 Freeosk + §5 Digitals + §6 Other — subcategory tables, scheduling logic | `05-freeosk.md`, `06-digitals.md`, `07-other.md` (partial) |
| 5 | §6 Other catch-all conclusion — REVERSED priority note | `07-other.md` |
| 6 | Reference: Rotation tables + Key Concepts (Primary/Secondary, Bumping, CS Fallback) + Output section | `01-key-concepts.md` |
| 7 | Output section conclusion — All Events Scheduled vs Manual Review Pool | `01-key-concepts.md` |

## Reading order (for a fresh reader or subagent)

1. **`00-master-overview.md`** — the phases, the 6 categories, the sort keys. Without this nothing else makes sense.
2. **`01-key-concepts.md`** — definitions of Primary/Secondary, rotation table structure, bumping semantics, Club Supervisor fallback rules. Every other file assumes you know these terms.
3. **`99-data-model.md`** — how the spec's concepts ("Primary Lead", "Primary Juicer", "has a primary event", "week Sun–Sat") map to rows and columns in the existing database. Read this before writing any code; the spec talks about abstractions, this file tells you the concrete columns to query.
4. **`02-juicer-production.md`** through **`07-other.md`** — one file per category, in the order the scheduler processes them.

## Guarantees each spec file must satisfy

Every category spec file (02 through 07) MUST contain:

1. **A "Verbatim spec" section** that transcribes the corresponding image text exactly — green YES branches, red NO branches, blue assignments, brown annotations. Wording may be lightly normalized for Markdown but no rule or branch may be dropped, merged, or paraphrased.
2. **An "Inputs" section** listing the exact data needed to make scheduling decisions in this category (events to process, rotation lookups, availability checks, posted schedules).
3. **An "Outputs" section** listing the exact data the category produces (a PendingSchedule record with specific fields, state transitions on other events like bumped CORE going back to pool).
4. **A "Pre-conditions" section** listing what must already be true before this category runs (e.g., for CORE/Supervisor: "Phase 2 pairing has run; bumped CORE from Juicer Production has been returned to the pool").
5. **A "Post-conditions" section** listing the invariants that must hold after this category runs.
6. **A "Branches" section** enumerating every YES/NO decision point in the image as a numbered list, so tests and review gates can assert each branch is covered.
7. **An "Edge cases" section** calling out subtle cases the image doesn't explicitly draw but that follow logically from the rules (e.g., "what if the primary juicer is the same person as the backup?", "what if a Freeosk event's start date is in the past?").
8. **A "Do NOT" section** — explicit anti-requirements that capture common ways implementations drift from the spec.
9. **A "Traceability table" section** mapping each branch to: (a) the task in the corresponding plan file that implements it, (b) the test case that verifies it, (c) the function/line in the final implementation. This table is empty at spec-writing time and gets filled in during plan writing, implementation, and test authoring.

## Review gates

Every spec file must pass **Gate A — Spec Verification** before any corresponding plan work begins. Gate A is performed by a fresh subagent with the spec file and the source image loaded; the subagent must confirm every rule, branch, and time in the image appears verbatim in the spec file. The subagent's report is stored as a comment in the plan's Gate A checkpoint.

Gates B/C/D/E live in the plan directory (`docs/superpowers/plans/2026-04-10-scheduler-rewrite/review-gates.md`).

## Glossary (terms used throughout)

- **Primary event** — a CORE or Juicer Production event. At most one per employee per day (spec: "One Primary Event Per Employee Per Day").
- **Secondary event** — Juicer Survey, Supervisor, Freeosk (all subcategories), Digitals Setup, Digitals Refresh. Requires the assigned employee to also hold a primary event on the same day, UNLESS assigned via Club Supervisor fallback (see CS Fallback).
- **Primary Juicer** — for a given date (day-of-week), the `RotationAssignment` row with `rotation_type='juicer'` and matching `day_of_week`; `employee_id` is the Primary Juicer, `backup_employee_id` is the Backup Juicer.
- **Primary Lead** — same idea with `rotation_type='primary_lead'`.
- **Backup Lead / Backup Juicer** — the `backup_employee_id` field on the same `RotationAssignment` row.
- **Club Supervisor** — the employee whose `Employee.job_title == 'Club Supervisor'`. Only one such person exists per club in practice.
- **Primary event "has a primary event" check** — "employee X has a primary event on day D" means "there exists a posted Schedule (or PendingSchedule proposed in the same run) for X on D whose event_type is 'Core' or 'Juicer Production'".
- **Bumping** — removing a previously-posted Schedule (or a PendingSchedule proposed earlier in the same run) and returning its event to the processing pool. See §Bumping in `01-key-concepts.md`.
- **CS Fallback** — Club Supervisor unconditional fallback. When a category's logic reaches "nobody else available", the event is assigned to the Club Supervisor regardless of whether the CS has a primary event, is on time off, etc. CS Fallback means "assign no matter what". The only exception is the "Other" category, where CS is the FIRST choice rather than the last.
- **Manual review pool** — events that could not be scheduled even after all fallbacks. Represented as `PendingSchedule` rows with `failure_reason` set, `employee_id=None`, `schedule_datetime=None`. Shown to the supervisor as "Manual Intervention Required" in the UI.
- **Week (Sun–Sat)** — the scheduling week is Sunday through Saturday inclusive. Sunday is day 0 for week-boundary calculations (NOTE: Python's `date.weekday()` returns Mon=0, so conversions must be careful — see `99-data-model.md`).
- **Normal / Emergency mode** — Normal mode: CORE events are scheduled starting `today + 3 days`. Emergency mode: starting `today` (same day). Controlled by `scheduler.emergency_mode` flag on the run.
- **Posted Schedule** — a row in the `schedules` table (persistent, visible in the calendar). Distinguished from PendingSchedule (proposed, not yet approved).
- **Proposed PendingSchedule** — a row in the `pending_schedules` table produced by the current scheduler run, awaiting supervisor approval.

## Risk register (high-level — per-file risks live in each spec file)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Spec drift during transcription (image → Markdown) | High | Critical | Gate A subagent review before any plan work starts |
| Silent behavior loss during refactor (greedy code deletes a feature not in the spec) | Medium | High | Gate B audit lists every existing behavior; anything retained/removed is an explicit decision |
| Plan skips a spec branch | Medium | Critical | Gate C coverage review: every branch in spec traceability table must map to a plan task |
| Implementation drift from plan (code adds extras not in plan) | Medium | High | Gate D per-task diff review against spec |
| Tests pass but miss a spec branch | Medium | Critical | Gate E spec→test coverage matrix |
| Context window exhaustion in a subagent session | High | Medium | Files are kept small (<400 lines) and focused; subagents only load the files they need |
| Order-of-operations bug (e.g., running CORE before Juicer Production bumps are returned) | Medium | Critical | Execution DAG is fixed in the plan README and enforced by plan file numbering |
| Production regression during cutover | Low | Critical | Feature flag `CPSAT_ENABLED` stays as a kill switch; staged rollout; run 192 regression harness as gate |
| Loss of PR #5's unified-primary-cap logic | Low | Medium | Greedy engine already had Juicer-bumps-CORE in Wave 1; PR #5 was a CP-SAT fix, becomes dead code on cutover |
| Two schedulers running simultaneously | Low | High | Single entry point in `app/routes/auto_scheduler.py`; flag check happens once per run |

## What this spec does NOT cover (explicit out-of-scope)

- Manual scheduling via the UI (drag-drop, day-view override). This spec is only about the auto-scheduler.
- Approval workflow (PendingSchedule → Schedule). That's downstream of the scheduler.
- Notifications, push alerts, schedule-change emails. Those are separate services.
- External API sync (Crossmark, Walmart EDR, MVRetail). The scheduler produces PendingSchedule records; sync is a separate concern.
- Locked days, company holidays, shift blocks (as concepts outside the 4-slot CORE time model described in image 3). These are existing secondary safety rails and must continue to work, but are NOT modified by this rewrite.
- Weekly hours caps (40-hour limit). The spec doesn't describe this; current behavior (via `_add_weekly_hours_cap`) is preserved.
