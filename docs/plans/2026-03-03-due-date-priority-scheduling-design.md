# Due-Date Priority Scheduling Design

**Date**: 2026-03-03
**Status**: Approved
**File**: `app/services/cpsat_scheduler.py`

## Problem

The CP-SAT auto-scheduler does not guarantee that events with the earliest due dates are scheduled first. A later-due-date event may occupy a slot that an earlier-due-date event could use, leaving the urgent event unscheduled.

Additionally, bumpable events that the solver reassigns to different slots are marked with `bumped_event_ref_num=event.project_ref_num` (self-reference), causing the UI to display "bumping event X for event X" and inflating the swap count.

## Solution: 4-Phase Scheduling

Modify `run_auto_scheduler()` to execute in 4 phases:

### Phase 1: Due-Date Priority Pre-Pass

**Method**: `_due_date_priority_pass(run)`

Before the solver runs, scan posted schedules and swap later-due-date events for earlier-due-date unscheduled events of the same type.

**Algorithm**:
1. Load all posted schedules grouped by event type
2. Load all unscheduled events sorted by `due_datetime` ascending
3. For each event type:
   - Sort posted schedules by event `due_datetime` descending (latest first = most swappable)
   - For each unscheduled event (earliest due first):
     - Find a posted schedule where:
       - Posted event's `due_datetime` > unscheduled event's `due_datetime`
       - Scheduled date is within unscheduled event's `[start_datetime, due_datetime)` range
       - Employee is eligible for the unscheduled event (same type eligibility rules)
       - Scheduled date is not locked or a holiday
     - If found:
       - Create PendingSchedule for unscheduled event (same employee, date, time, block)
       - Create PendingSchedule failure/displacement record for the posted event
       - Mark posted event's schedule for deletion on approval
       - The displaced event becomes available for the solver in Phase 2/3
4. Remove swapped-in events from the unscheduled pool (they're now pending)

**Swap constraints** (same-type only):
- Core <-> Core (preserves block assignment)
- Digitals <-> Digitals
- Juicer Production <-> Juicer Production
- Juicer Survey <-> Juicer Survey
- Freeosk <-> Freeosk
- Digital Setup <-> Digital Setup
- Digital Refresh <-> Digital Refresh
- Digital Teardown <-> Digital Teardown

**Employee eligibility check**:
- Juicer types: employee must have `job_title in JUICER_TITLES` or `juicer_trained=True`
- Lead-only types: employee must have `job_title in LEAD_TITLES`
- Core: any active employee

### Phase 2: Solver Run Without Bumping

Run the CP-SAT solver for remaining unscheduled events with bumping disabled.

**Implementation**: Add `self.allow_bumping` flag. In `_load_data()`, skip bumpable event loading (lines 286-320) when `allow_bumping=False`.

The solver uses all hard constraints (availability, weekly limits, block uniqueness, etc.) but cannot displace any existing posted schedules.

### Phase 3: Solver Run With Bumping (Conditional)

If Phase 2 left events unscheduled, re-run the solver WITH bumping enabled for only those failed events.

**Implementation**:
1. Collect failed event refs from Phase 2
2. Re-initialize with `allow_bumping=True`
3. Filter events to only the failed ones
4. Run solver — bumpable events are loaded and can be displaced
5. Merge results into the same run record

### Phase 4: Due-Date Verification Post-Pass

**Method**: `_due_date_verification_pass(run)`

After all scheduling, verify due-date ordering across the combined posted + pending schedules.

**Algorithm**: Same as Phase 1, but operates on the union of:
- Existing posted schedules (excluding those displaced in earlier phases)
- Newly-created PendingSchedule records from this run

If a swap is needed, create additional PendingSchedule records. Log any remaining violations that couldn't be resolved (e.g., no valid swap target).

## Self-Bump Fix (Included)

Fix the existing bug where bumpable events reassigned by the solver are marked with `bumped_event_ref_num=event.project_ref_num`.

**Change in `_extract_solution`** (lines 1837-1863):
- For reassigned bumpable events: set `is_swap=False`, `bumped_event_ref_num=None`
- Store `bumped_posted_schedule_id` to track the old schedule to replace
- Use `swap_reason='Solver rescheduled'` for informational purposes
- Do NOT increment `swap_count` — these aren't real bumps

**Change in approval code** (`auto_scheduler.py`):
- Add handling for PendingSchedules with `bumped_posted_schedule_id` but no `bumped_event_ref_num`
- Delete only the specific posted schedule by ID (not all schedules for the event ref)

## PendingSchedule Records

### Phase 1/4 swap records:
```
PendingSchedule(
    event_ref_num=<earlier-due-date event>,
    employee_id=<same as displaced>,
    schedule_datetime=<same as displaced>,
    is_swap=True,
    bumped_event_ref_num=<later-due-date event ref>,
    bumped_posted_schedule_id=<posted schedule ID>,
    swap_reason='Due date priority swap',
)
```

### Phase 2/3 solver records:
Same as current behavior, but with self-bump fix applied.

## Run Flow in `run_auto_scheduler()`

```python
def run_auto_scheduler(self, run_type='manual'):
    run = self._create_run(run_type)

    # Phase 1: Pre-pass — swap posted schedules for due-date priority
    phase1_swaps = self._due_date_priority_pass(run)

    # Phase 2: Solver without bumping
    self.allow_bumping = False
    self._load_data()
    # ... exclude events already handled in Phase 1
    self._build_model()
    scheduled_2, failed_2, _ = self._solve_and_extract(run)

    # Phase 3: Solver with bumping (only for Phase 2 failures)
    if failed_2 > 0:
        self.allow_bumping = True
        # ... reload with only failed events
        scheduled_3, failed_3, swaps_3 = self._solve_and_extract(run)

    # Phase 4: Post-pass — verify due-date ordering
    phase4_swaps = self._due_date_verification_pass(run)

    # Aggregate counts
    run.events_scheduled = phase1_swaps + scheduled_2 + scheduled_3
    run.events_failed = failed_3  # Only final failures count
    run.events_requiring_swaps = swaps_3 + phase4_swaps
    return run
```

## Logging

Each phase logs its activity:
- `Phase 1: Due-date priority pre-pass — N swaps`
- `Phase 2: Solver (no bumping) — scheduled N, failed M`
- `Phase 3: Solver (with bumping) — scheduled N, failed M, swaps K`
- `Phase 4: Due-date verification — N additional swaps`

## Testing

- Test Phase 1 swap logic with mock posted schedules and unscheduled events
- Test that same-type constraint is enforced
- Test that date validity is checked
- Test that employee eligibility is checked
- Test Phase 2/3 solver split (no bumping then bumping)
- Test Phase 4 catches remaining due-date violations
- Test self-bump fix: reassigned bumpable events don't show as self-bumps
- Test approval flow with new PendingSchedule records from all phases
