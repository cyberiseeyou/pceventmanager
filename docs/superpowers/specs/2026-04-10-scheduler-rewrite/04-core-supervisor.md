# Spec 04 — CORE/Supervisor Scheduling

> **Source image:** Image 3 of 7 (entire page). Depends on `00-master-overview.md`, `01-key-concepts.md`, and the bumped-event stream from `02-juicer-production.md`.

This is the largest spec in the set because it describes TWO interleaved flows: CORE event scheduling and Supervisor event scheduling (which runs once per CORE after the CORE is placed).

## Verbatim spec

### For each CORE/Supervisor pair (by due date, earliest first — INCLUDING bumped events):

#### CORE Event Scheduling

1. **Determine date window:**
   - Start: Event start date OR earliest in scope
     - Normal: current + 3 days
     - Emergency: current day
   - End: Event due date

2. **Employee selection priority:**
   - (a) **Primary Lead** (if no CORE yet) — always gets **10:15 AM**.
   - (b) Other Leads.
   - (c) Employee with **fewest primary events this week (Sun–Sat)**.

3. **Time slots:** 10:15, 10:45, 11:15, 11:45.
   - Fill 2 per slot before moving to next (up to 8), then +1 per slot in order.
   - **Always fill gaps first; don't count bumped person's old slot.**

4. **Nobody available?** → Bump event with **LATEST due date** → take their slot.

5. **Can't bump?** → Try next day (until past due → manual review pool).

#### Supervisor Event Scheduling (after CORE scheduled)

All Supervisor events scheduled @ **12:00 PM (Noon)**.

1. Club Supervisor available (no time off)? → Assign (no primary event required).
2. Primary Lead available + has CORE? → Assign @ 12:00 PM.
3. Backup Lead available + has CORE? → Assign @ 12:00 PM.
4. Neither available? → Club Supervisor **unconditionally** @ 12:00 PM.

## Inputs

- `core_pool` — all unscheduled CORE events (paired with their Supervisor from Phase 2), sorted by `due_datetime` ascending. Includes any CORE events that were bumped during Juicer Production processing.
- `rotation_assignments` where `rotation_type == 'primary_lead'`.
- `schedule_exceptions` where `rotation_type == 'primary_lead'`.
- `employees` — all active, with job_title to determine Leads vs Specialists vs Club Supervisor.
- `employee_time_off`, `employee_weekly_availability`, `employee_availability_override`.
- `posted_schedules` + `current_run_pending_schedules` — to compute "fewest primary events this week" and to detect already-assigned time slots on each day.
- `mode` — normal vs emergency (affects the date-window start).

## Outputs

For each CORE event, exactly one of:

1. **Successful proposal for CORE + successful proposal for paired Supervisor** — two PendingSchedule rows:
   - CORE: `employee_id`, `schedule_datetime`, `schedule_time` (one of 10:15, 10:45, 11:15, 11:45), `shift_block` set to the block number (1–8).
   - Supervisor (if paired): `employee_id`, `schedule_datetime` = same date @ 12:00 PM.

2. **Successful CORE proposal but Supervisor manual review** — rare; happens when CS is on PTO AND no Lead has a CORE to attach to AND there's no CS fallback.

3. **Successful CORE via bumping another CORE** — three PendingSchedule rows:
   - New CORE's successful proposal.
   - Bumped CORE's swap entry (`is_swap=True`, `bumped_event_ref_num`, `bumped_posted_schedule_id` if the bumped CORE was previously posted).
   - Bumped CORE re-enters the pool and gets a fresh proposal or manual-review entry.

4. **Manual review for CORE** — all days in `[start, due)` tried, no employee available, no bumpable CORE with a later due date.

## Pre-conditions

- Juicer Production category (spec 02) and Juicer Survey category (spec 03) have completed.
- `core_pool` is sorted by `due_datetime` ascending.
- Bumped CORE events from category 1 are included in the pool, with their prior posted Schedule rows already deleted (spec 02 JP17) and their PendingSchedule "reopened" state already set (spec 02 JP18).
- Phase 2 pairing has run; each CORE has its matching Supervisor in a lookup table (possibly None if unpaired).

## Post-conditions

- Every CORE has exactly one PendingSchedule (success or manual review) in the run.
- Every Supervisor has exactly one PendingSchedule (success or manual review) in the run, UNLESS it was an unpaired Supervisor logged and skipped in Phase 2.
- No two CORE events are assigned to the same `(employee_id, date)` pair.
- No CORE event is assigned to the same `(date, shift_block)` slot as another CORE.
- All assigned CORE times are one of {10:15, 10:45, 11:15, 11:45}.
- All assigned Supervisor times are 12:00 PM.
- If the Primary Lead was assigned a CORE, their assignment is at exactly 10:15 AM.

## Branches

### CORE scheduling

| ID | Description |
|---|---|
| C1 | Sort core_pool by `due_datetime` ascending |
| C2 | For each CORE event, compute date_window: start = max(event.start_datetime.date(), earliest_in_scope); end = event.due_datetime.date() |
| C3 | earliest_in_scope = (today + 3 days) in Normal mode, today in Emergency mode |
| C4 | Iterate candidate days from start to end - 1 inclusive. For each day, try to find an employee |
| C5 | On each day, first try Primary Lead (from rotation): if Primary Lead has no CORE yet that day AND is available AND target_day is in their workable days → assign to Primary Lead at 10:15 AM (slot 1, block 1) |
| C6 | If Primary Lead unavailable or already has a CORE that day: try Other Leads (job_title == 'Lead Event Specialist' and != Primary Lead) in order |
| C7 | If no Lead is available or all Leads already have CORE: try all eligible employees sorted by "fewest primary events this week (Sun–Sat) ascending", tiebreak by employee_id |
| C8 | "Fewest primary events this week" = count of posted Schedule + in-run PendingSchedule with event_type IN ('Core', 'Juicer Production') and date in the current Sunday–Saturday week of the candidate day |
| C9 | For the chosen employee, assign a time slot from [10:15, 10:45, 11:15, 11:45]. Fill 2 per slot before advancing (up to 8 total CORE per day), then +1 per slot in order. Always fill gaps first |
| C10 | "Fill gaps first" = if slot S1 currently has 1 event and S2 has 2 events, the next CORE goes into S1 (gap) not S3 |
| C11 | "Don't count bumped person's old slot" = when computing current slot occupancy for placement decisions, exclude slots freed by bumping within the current scheduling pass |
| C12 | If no employee is available on target_day AND there is at least one already-scheduled CORE on target_day with a LATER due date than the current event → bump that CORE, take its (date, block, employee) slot for the current event |
| C13 | If multiple existing CORE have later due dates, bump the one with the LATEST due date first (tiebreak: largest event ID) |
| C14 | If no employee available AND no bumpable CORE (all existing have earlier-or-equal due dates) → advance to target_day + 1 |
| C15 | If target_day + 1 >= date_window end → manual review entry |
| C16 | A bumped CORE is returned to the pool, re-sorted by due date, and processed later in the same category 3 pass |

### Supervisor scheduling

| ID | Description |
|---|---|
| S1 | For each successfully scheduled CORE, find the paired Supervisor (from Phase 2 pairing) |
| S2 | If paired Supervisor does not exist (CORE had no Supervisor pair), skip |
| S3 | target_date = CORE's assigned date; target_time = 12:00 PM |
| S4 | Is Club Supervisor available (no PTO, passes weekly availability) on target_date? → Assign Supervisor to Club Supervisor @ 12 PM. No "has primary event" check required for CS (spec: "no primary event required") |
| S5 | Club Supervisor unavailable → try Primary Lead: is Primary Lead available AND has a CORE on target_date? If both true → Assign Supervisor to Primary Lead @ 12 PM |
| S6 | Primary Lead unavailable or has no CORE → try Backup Lead: is Backup Lead (from rotation) available AND has a CORE on target_date? If both true → Assign Supervisor to Backup Lead @ 12 PM |
| S7 | Neither Primary nor Backup Lead qualifies → Assign Supervisor to Club Supervisor UNCONDITIONALLY @ 12 PM (even if CS is on PTO? NO — "unconditional" is w.r.t. primary event requirement, not PTO). If CS is on PTO, fall to S8 |
| S8 | CS is on PTO → manual review for this Supervisor event |

## Edge cases

- **"Has CORE on target_date" check for Supervisor assignment:** The Supervisor is being assigned to the day the CORE was placed on. By definition, that CORE was just placed by this category's logic earlier in the same loop iteration. So "Primary Lead has CORE on target_date" is true IFF Primary Lead was assigned the CORE in step C5. Keep a local lookup updated after each CORE placement.
- **Primary Lead has two CORE events due on the same day** (e.g., duplicate product key): first CORE placed on day D at 10:15 goes to Primary Lead. Second CORE on day D goes to Other Leads or fewest-primaries employee — Primary Lead already has a CORE that day.
- **Fill 2 per slot up to 8:** After 8 CORE events on a single day (2 in each of 4 slots), step 3 of the spec says "+1 per slot in order" — so the 9th CORE goes to slot 10:15 (now 3 events), 10th to 10:45 (now 3), etc. There is no hard cap at 8. In practice, saturating a day past 8 means the club is massively overbooked, but the spec is explicit.
- **"Fill gaps first":** If due to bumping, slot 10:45 on day D has only 1 event (instead of 2), and slot 11:15 has 2, the next CORE for day D goes into 10:45 (fills the gap). This is a *placement* rule, not a scheduling rule; it affects shift_block assignment on that day only.
- **Bumping a CORE on a different day:** When bumping, the bumped event's (old day, old slot) is freed. The current event takes that exact slot. The bumped event is returned to the pool for re-scheduling on any day in its own window.
- **Bumping cascade termination:** Proof: at each bump, the bumped event had a later due date than the current event. The current event takes the bumped event's slot. The bumped event re-enters the pool and may itself bump someone with an even later due date. The set of "latest CORE due dates still in the schedule" can only shrink or stay constant; since there are finitely many CORE events, bumping terminates.
- **Supervisor events with no paired CORE:** Phase 2 already logged-and-skipped these. Nothing to do in category 3.
- **Club Supervisor on PTO but is also a Primary Lead:** Not possible in practice (job titles are mutually exclusive), but if data allows it, follow job_title-based routing only.
- **A CORE event's due date is in the past (spec bug, shouldn't happen):** The date window has end = due, so the window is empty. Manual review.
- **Paired Supervisor has a different due date than its CORE:** Irrelevant. Supervisor inherits the CORE's scheduled date; its own due date is not consulted.

## Do NOT

- Do NOT assign Primary Lead to a CORE at any time other than 10:15 AM. The spec is explicit: "always gets 10:15 AM". In the greedy engine this must be hard-enforced, not a soft preference.
- Do NOT assign a Supervisor to a Primary or Backup Lead who does not have a CORE on the same day. The current greedy and CP-SAT code both fail to check this.
- Do NOT skip the Club Supervisor in Supervisor scheduling (they are the FIRST choice for Supervisor events, not a fallback).
- Do NOT bump a CORE with an earlier-or-equal due date. Bump only to break ties in favor of earlier deadlines.
- Do NOT count Juicer Production events toward the "fewest primaries this week" metric for anything EXCEPT the fairness metric itself. Juicer Production still counts — it's a primary event — but other fairness rules (e.g., weekly CORE cap) are per-type.
- Do NOT assign two CORE events to the same shift_block on the same day.
- Do NOT use a time other than {10:15, 10:45, 11:15, 11:45} for a CORE event.
- Do NOT use a time other than 12:00 PM for a Supervisor event.
- Do NOT require a Supervisor's Club Supervisor fallback to pass a "has CORE" check. CS can be assigned Supervisor without having any primary event that day.

## Traceability table

| Branch ID | Plan task | Test case | Implementation location |
|---|---|---|---|
| C1 | `04-core-supervisor.md` T1 | `test_core_pool_sorted_by_due_date` | TBD |
| C2, C3 | `04-core-supervisor.md` T2 | `test_date_window_normal_and_emergency` | TBD |
| C4 | `04-core-supervisor.md` T3 | `test_core_iterates_candidate_days` | TBD |
| C5 | `04-core-supervisor.md` T4 | `test_primary_lead_gets_core_at_1015` | TBD |
| C6 | `04-core-supervisor.md` T5 | `test_other_leads_tried_when_primary_unavailable` | TBD |
| C7, C8 | `04-core-supervisor.md` T6 | `test_fewest_primaries_this_week_tiebreaker` | TBD |
| C9 | `04-core-supervisor.md` T7 | `test_fill_2_per_slot_before_advancing` | TBD |
| C10 | `04-core-supervisor.md` T8 | `test_fill_gaps_first` | TBD |
| C11 | `04-core-supervisor.md` T9 | `test_bumped_persons_old_slot_excluded_from_count` | TBD |
| C12, C13 | `04-core-supervisor.md` T10 | `test_bump_core_with_latest_due_date` | TBD |
| C14, C15 | `04-core-supervisor.md` T11 | `test_no_bump_no_day_advances_manual_review` | TBD |
| C16 | `04-core-supervisor.md` T12 | `test_bumped_core_reenters_pool_sorted` | TBD |
| S1, S2 | `04-core-supervisor.md` T13 | `test_supervisor_paired_lookup` | TBD |
| S3 | `04-core-supervisor.md` T14 | `test_supervisor_scheduled_at_noon` | TBD |
| S4 | `04-core-supervisor.md` T15 | `test_supervisor_cs_first_no_primary_required` | TBD |
| S5 | `04-core-supervisor.md` T16 | `test_supervisor_primary_lead_requires_core` | TBD |
| S6 | `04-core-supervisor.md` T17 | `test_supervisor_backup_lead_requires_core` | TBD |
| S7 | `04-core-supervisor.md` T18 | `test_supervisor_cs_unconditional_fallback` | TBD |
| S8 | `04-core-supervisor.md` T19 | `test_supervisor_cs_pto_manual_review` | TBD |
