# Spec 01 — Key Concepts

> **Source images:** Image 6 ("Reference: Rotation Tables" + "Key Concepts") and Image 7 ("Output" — continuation). Every rule in this file must be traceable to those images.

This file is the glossary layer. It does not describe a *category* of processing; it describes the cross-cutting concepts every other spec file assumes. Read this file BEFORE reading any of the per-category specs (02–07).

## Verbatim spec

### Reference: Rotation Tables

| Rotation | Structure | Used For |
|---|---|---|
| **Primary Juicer** | Sun–Sat with optional backup per day | Juicer Production, Juicer Survey |
| **Primary Lead** | Sun–Sat with optional backup per day | CORE, Freeosk, Digitals, Supervisor |

### Key Concepts

#### Primary events
- CORE events
- Juicer Production events

#### Secondary events (require a primary event to be assigned)
- Juicer Survey
- Supervisor
- Freeosk (all subcategories)
- Digitals (Setup, Refresh)

> **Not listed as Secondary:** Digital Teardown is NOT listed as a secondary event in the spec. Teardown has its own unique logic (see `06-digitals.md`) and does not require the assignee to have a primary event. Teardown's rule is "find a Lead ≠ Primary Lead who is scheduled that day" — "scheduled that day" means already assigned to any event, not specifically a primary event.

#### Bumping
- Removes a scheduled event and returns it to the CORE/Supervisor pool.
- Events are re-sorted by due date when returned to the pool.
- Events can be bumped multiple times if necessary.
- When bumping, select event with the **LATEST** due date first.
- Juicer Production can bump CORE events.
- CORE can bump other CORE events (only if the other CORE has a later due date).

> **Derived rule:** CORE cannot bump a Juicer Production event. This follows from "Juicer Production can bump CORE" + the absence of "CORE can bump Juicer Production". The reverse is not allowed.
>
> **Derived rule:** Secondary events (Juicer Survey, Supervisor, Freeosk, Digitals, Other) cannot bump anything. Only primary events bump.
>
> **Derived rule:** "Returns it to the CORE/Supervisor pool" applies regardless of whether the bumped event was scheduled in the current run (as a PendingSchedule) or was previously posted (as a Schedule). In both cases the event re-enters category 3 processing, sorted alongside other CORE events by due date.

#### Club Supervisor Fallback
- Final fallback for most event types.
- **No primary event requirement** when assigned as fallback. (The "Club Supervisor" employee does not need to have a CORE or Juicer Production that day; the fallback assignment is unconditional.)
- Assignment is **unconditional** (no further checks — not even availability checks in the fallback branch; see note below).
- Exception: For 'Other' events, Club Supervisor is FIRST choice, Primary Lead is fallback.

> **Clarification — "unconditional" scope:** "Unconditional" in the spec means: when a category's decision tree reaches the CS fallback branch, the assignment happens regardless of whether the Club Supervisor has a primary event, regardless of whether other fallbacks were exhausted for a technical reason, and regardless of any secondary-event "requires primary" rule. However, the **Club Supervisor's own approved time off still blocks the assignment** — an employee on PTO cannot be assigned anything. A Club Supervisor on PTO with no alternative means the event falls to the **manual review pool**, not to another employee.
>
> **Clarification — "final fallback":** "Final" means the last branch in a category's decision tree, NOT the last resort across the whole scheduler. If even CS fallback fails (because the CS is on PTO), the event goes to manual review.

### Output

| Bucket | Meaning |
|---|---|
| **All Events Scheduled** | With assigned employee, date, and time. |
| **Manual Review Pool** | Events that could not be scheduled. |

## Inputs

This file has no inputs of its own; it defines terms used across all other spec files.

## Outputs

Concepts only — no outputs.

## Branches (conceptual — tested in the category where they apply)

| ID | Description |
|---|---|
| K1 | An event is a primary event iff `event_type IN ('Core', 'Juicer Production')` |
| K2 | An event is a secondary event iff `event_type IN ('Juicer Survey', 'Supervisor', 'Freeosk', 'Digital Setup', 'Digital Refresh', 'Digitals') AND NOT name_ends_with('Digital Demo Tear Down')` |
| K3 | Digital Teardown is its own bucket — not primary, not secondary |
| K4 | Bumping only moves primary events (Juicer Production can bump CORE; CORE can bump CORE with a later due date) |
| K5 | A bumped event re-enters category 3 (CORE + Supervisor) sorted by due date, regardless of its original category |
| K6 | Club Supervisor fallback is unconditional with respect to "requires primary event" and "requires other fallbacks exhausted" — but it still respects approved time off |
| K7 | For the Other category, Club Supervisor is FIRST choice, Primary Lead is FALLBACK (REVERSED from all other categories) |
| K8 | An employee "has a primary event" on day D iff there exists a posted Schedule OR a successful PendingSchedule in the current run for that employee on D with `event_type IN ('Core', 'Juicer Production')` |
| K9 | The scheduling week is Sunday through Saturday inclusive; "fewest primary events this week (Sun–Sat)" uses this bucket |

## Edge cases

- **Club Supervisor missing:** The spec assumes there is a Club Supervisor employee. If the club has no employee with `job_title == 'Club Supervisor'`, the CS fallback branch cannot fire. In that case the category's logic falls through to manual review. Test `test_cs_fallback_without_cs_employee_goes_to_manual_review` covers this.
- **Club Supervisor on long-term leave:** Same as above — CS on PTO for every day in the window means every category that reaches its CS fallback branch for those days produces a manual-review entry. This is correct behavior; the spec does not prescribe a "secondary fallback" beyond CS.
- **Primary Juicer rotation with no Primary Juicer for a day:** If `RotationAssignment` has no row for a given `(day_of_week, rotation_type='juicer')`, treat the Primary Juicer as "does not exist". The branch "Primary Juicer available?" evaluates as NO and the logic falls through to Backup Juicer.
- **Backup == Primary:** Data-entry error — `RotationAssignment.backup_employee_id == employee_id` for the same row. Treat as "no backup" (skip the backup step). Log a warning.
- **Multiple juicer-trained employees but only one in rotation:** The spec uses the rotation table exclusively for Primary/Backup Juicer. Other juicer-trained employees are NOT consulted. They may only receive Juicer Production or Juicer Survey assignments via the Club Supervisor fallback path for Juicer Survey (and only if they happen to be the Club Supervisor, which is unusual).
- **"Fewest primary events this week" ties:** If two employees have the same count, break the tie deterministically. Proposed tiebreakers (in order): (a) employee ID lexicographic, (b) name lexicographic. The spec doesn't prescribe this; the implementation chooses and documents it. Tests must use the documented tiebreaker.
- **Bumping cycles:** CORE A bumps CORE B; CORE B's re-attempt at scheduling could (in principle) want to bump CORE A back. Termination rule: the "bump event with LATEST due date" rule is monotonic (each bump strictly decreases the "latest due date among scheduled CORE" set), so cycles are impossible as long as the tiebreaker for equal due dates is stable (e.g., by event ID). Tests must exercise a 3-deep bump chain.

## Do NOT

- Do not treat Digital Teardown as a "secondary event requiring a primary event" — its logic is different (see `06-digitals.md`).
- Do not allow a secondary event to bump a primary event.
- Do not allow a CORE to bump another CORE with an earlier or equal due date.
- Do not skip the Club Supervisor's PTO check when assigning via CS fallback. "Unconditional" is about the decision logic, not about physically ignoring PTO.
- Do not assume Club Supervisor exists; always handle the case where no CS employee is found.
- Do not use Monday=0 for week-boundary math — the scheduling week is Sunday through Saturday, which requires a Sunday=0 remap (see `99-data-model.md` for the exact snippet).
- Do not consider other juicer-trained employees (outside the rotation table) as Primary Juicer candidates. The rotation table is the sole source of truth for who the Primary/Backup Juicer is on a given day.

## Traceability table

| Branch ID | Plan task | Test case | Implementation location |
|---|---|---|---|
| K1 | `01-phase-infrastructure.md` T8 | `test_primary_event_classifier` | TBD |
| K2 | `01-phase-infrastructure.md` T9 | `test_secondary_event_classifier` | TBD |
| K3 | `06-digitals.md` T5 | `test_digital_teardown_is_not_secondary` | TBD |
| K4 | `02-juicer-production.md` T8, `04-core-supervisor.md` T10 | `test_juicer_bumps_core`, `test_core_bumps_core_with_later_due_date` | TBD |
| K5 | `02-juicer-production.md` T14 | `test_bumped_event_rejoins_core_pool_sorted_by_due_date` | TBD |
| K6 | `04-core-supervisor.md` T12, `05-freeosk.md` T6, `06-digitals.md` T10, `07-other.md` T3 | `test_cs_fallback_unconditional_except_pto` | TBD |
| K7 | `07-other.md` T1 | `test_other_cs_first_primary_lead_fallback` | TBD |
| K8 | `01-phase-infrastructure.md` T10 | `test_has_primary_event_query` | TBD |
| K9 | `04-core-supervisor.md` T6 | `test_fewest_primaries_sun_sat_window` | TBD |
