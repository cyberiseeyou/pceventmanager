# Due-Date Priority Scheduling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 4-phase scheduling to the CP-SAT auto-scheduler that guarantees events with earliest due dates are scheduled first, and fix the self-bump bug.

**Architecture:** Add two greedy pre/post-pass methods to `CPSATSchedulingEngine`, split the existing single solver run into a no-bump phase then a bump phase, and fix the self-bump in `_extract_solution`.

**Tech Stack:** Python, OR-Tools CP-SAT, SQLAlchemy, pytest

---

### Task 1: Fix the Self-Bump Bug

**Files:**
- Modify: `app/services/cpsat_scheduler.py:1837-1863` (first-pass self-bump)
- Modify: `app/services/cpsat_scheduler.py:1934-1942` (second-pass self-bump)
- Test: `tests/test_cpsat_scheduler.py`

**Step 1: Write the failing test**

Add to `tests/test_cpsat_scheduler.py`:

```python
class TestSelfBumpFix:
    """Verify that reassigned bumpable events don't create self-bumps."""

    def test_reassigned_bumpable_event_not_self_bump(self, db_session, models):
        """When solver moves a bumpable event to a new slot, is_swap should be False
        and bumped_event_ref_num should be None (not the event's own ref)."""
        Schedule = models['Schedule']

        # Create employee and a 'Scheduled' event with a posted schedule
        emp = _make_employee(models, db_session, 'emp1', 'Alice')
        event = _make_event(models, db_session, 300001, 'Core',
                            condition='Scheduled', start_days=3, due_days=20)
        event.is_scheduled = True
        db_session.flush()

        # Create the posted schedule (on a day within range)
        posted_date = _future(5)
        sched = Schedule(
            event_ref_num=300001,
            employee_id='emp1',
            schedule_datetime=posted_date,
            shift_block=1,
        )
        db_session.add(sched)

        # Create a second employee so solver has reason to reassign
        _make_employee(models, db_session, 'emp2', 'Bob')
        # Create several other events to create scheduling pressure
        for i in range(3):
            _make_event(models, db_session, 300010 + i, 'Core', start_days=3, due_days=14)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.status == 'completed'

        # Check that no pending schedule has bumped_event_ref_num == its own ref
        pending = _get_pending(db_session, models, run.id)
        for p in pending:
            if p.event_ref_num == 300001 and p.bumped_event_ref_num:
                assert p.bumped_event_ref_num != 300001, \
                    f"Self-bump detected: event 300001 bumped_event_ref_num points to itself"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cpsat_scheduler.py::TestSelfBumpFix::test_reassigned_bumpable_event_not_self_bump -v`
Expected: FAIL with "Self-bump detected"

**Step 3: Fix the first-pass self-bump (lines 1837-1863)**

In `app/services/cpsat_scheduler.py`, replace lines 1837-1863 (the `else` block for reassigned bumpable events):

```python
                    else:
                        # Reassigned to different slot — NOT a bump, just a rescheduling
                        assigned_block = None
                        if etype == 'Core':
                            for b in range(1, NUM_CORE_BLOCKS + 1):
                                if (eid, b) in self.v_assign_block and solver.Value(self.v_assign_block[(eid, b)]):
                                    assigned_block = b
                                    break
                        schedule_time_val = self._get_schedule_time(event, etype, assigned_block)
                        schedule_dt = datetime.combine(assigned_day, schedule_time_val)

                        # Find the posted schedule being replaced
                        posted_id = None
                        for s in self.bumpable_schedule_map.get(event.project_ref_num, []):
                            posted_id = s.id
                            break

                        ps = self._create_pending_schedule(
                            run, event, assigned_emp, schedule_dt,
                            is_swap=False,
                            bumped_event_ref_num=None,
                            swap_reason='Solver rescheduled',
                            shift_block=assigned_block,
                        )
                        # Store the posted schedule ID so approval knows what to replace
                        if posted_id and ps:
                            ps.bumped_posted_schedule_id = posted_id

                        scheduled_count += 1
                        logger.info(
                            f"CP-SAT reschedule: {event.project_name} ({etype}) "
                            f"moved to {assigned_day} emp={assigned_emp}"
                        )
                        continue
```

**Step 4: Fix the second-pass self-bump (lines 1934-1942)**

Remove the self-reassignment detection block entirely:

```python
            # REMOVED: old-style self-reassignment detection that caused self-bumps.
            # New events should not have existing posted schedules. If they do,
            # the solver's assignment is authoritative.
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_cpsat_scheduler.py::TestSelfBumpFix -v`
Expected: PASS

**Step 6: Run full test suite to verify no regressions**

Run: `pytest tests/test_cpsat_scheduler.py -v`
Expected: All existing tests PASS

**Step 7: Commit**

```bash
git add app/services/cpsat_scheduler.py tests/test_cpsat_scheduler.py
git commit -m "fix: remove self-bump when solver reassigns bumpable events

Bumpable events reassigned by the solver were setting
bumped_event_ref_num to their own ref, causing the UI to show
'bumping event X for event X' and inflating swap counts.

Now: reassigned events get is_swap=False, bumped_event_ref_num=None,
and use bumped_posted_schedule_id to track the old schedule to replace."
```

---

### Task 2: Add Approval Handling for `bumped_posted_schedule_id`

**Files:**
- Modify: `app/routes/auto_scheduler.py:574-682` (approval bump processing)
- Test: `tests/test_cpsat_scheduler.py`

**Step 1: Write the failing test**

```python
class TestApprovalRescheduledEvents:
    """Verify approval correctly handles rescheduled events with bumped_posted_schedule_id."""

    def test_approval_deletes_old_schedule_for_rescheduled_event(self, client, db_session, models):
        """When approving a rescheduled event (bumped_posted_schedule_id set, no bumped_event_ref_num),
        the old posted schedule should be deleted and the new one created."""
        Schedule = models['Schedule']
        PendingSchedule = models['PendingSchedule']
        SchedulerRunHistory = models['SchedulerRunHistory']

        emp = _make_employee(models, db_session, 'emp1', 'Alice')
        event = _make_event(models, db_session, 400001, 'Core',
                            condition='Scheduled', start_days=0, due_days=20)
        event.is_scheduled = True
        db_session.flush()

        # Old posted schedule
        old_date = _future(5)
        old_sched = Schedule(
            event_ref_num=400001,
            employee_id='emp1',
            schedule_datetime=old_date,
            shift_block=1,
        )
        db_session.add(old_sched)
        db_session.flush()
        old_sched_id = old_sched.id

        # Create run + pending schedule (rescheduled, not a bump)
        run = SchedulerRunHistory(run_type='manual', status='completed', solver_type='cpsat')
        db_session.add(run)
        db_session.flush()

        new_date = _future(7)
        ps = PendingSchedule(
            scheduler_run_id=run.id,
            event_ref_num=400001,
            employee_id='emp1',
            schedule_datetime=new_date,
            schedule_time=new_date.time(),
            status='proposed',
            is_swap=False,
            bumped_event_ref_num=None,
            bumped_posted_schedule_id=old_sched_id,
        )
        db_session.add(ps)
        db_session.commit()

        # Approve
        response = client.post(f'/auto-schedule/approve?run_id={run.id}')
        assert response.status_code == 200

        # Old schedule should be deleted
        assert db_session.query(Schedule).get(old_sched_id) is None

        # New schedule should exist
        new_scheds = db_session.query(Schedule).filter_by(event_ref_num=400001).all()
        assert len(new_scheds) == 1
        assert new_scheds[0].schedule_datetime.date() == new_date.date()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cpsat_scheduler.py::TestApprovalRescheduledEvents -v`
Expected: FAIL — old schedule not deleted

**Step 3: Add rescheduled-event handling to approval code**

In `app/routes/auto_scheduler.py`, after the existing bump processing block (after line 682), add:

```python
    # Handle rescheduled events (bumped_posted_schedule_id set, no bumped_event_ref_num)
    # These are events the solver moved to a different slot — delete the old posted schedule
    try:
        rescheduled = [ps for ps in pending_schedules
                       if ps.bumped_posted_schedule_id and not ps.bumped_event_ref_num]
        if rescheduled:
            current_app.logger.info(f"Processing {len(rescheduled)} rescheduled events")
            for ps in rescheduled:
                old_sched = db.session.query(models['Schedule']).get(ps.bumped_posted_schedule_id)
                if old_sched:
                    current_app.logger.info(
                        f"  Deleting old schedule {old_sched.id} for rescheduled event {ps.event_ref_num}"
                    )
                    db.session.delete(old_sched)
            db.session.flush()
    except Exception as resched_error:
        db.session.rollback()
        current_app.logger.error(f"Failed to process rescheduled events: {resched_error}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Failed to process rescheduled events: {str(resched_error)}'
        }), 500
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cpsat_scheduler.py::TestApprovalRescheduledEvents -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `pytest tests/test_cpsat_scheduler.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add app/routes/auto_scheduler.py tests/test_cpsat_scheduler.py
git commit -m "feat: handle rescheduled events in approval flow

When a solver-rescheduled event is approved, delete the old posted
schedule via bumped_posted_schedule_id before creating the new one."
```

---

### Task 3: Add `_due_date_priority_pass` Method

**Files:**
- Modify: `app/services/cpsat_scheduler.py` (add new method)
- Test: `tests/test_cpsat_scheduler.py`

**Step 1: Write the failing tests**

```python
class TestDueDatePriorityPass:
    """Test the pre-pass that swaps posted schedules for earlier-due-date events."""

    def test_earlier_due_date_swaps_later(self, db_session, models):
        """An unscheduled Core event due sooner should take the slot of a scheduled
        Core event due later, same employee/date/time."""
        Schedule = models['Schedule']

        emp = _make_employee(models, db_session, 'emp1', 'Alice')

        # Scheduled event with later due date
        later_event = _make_event(models, db_session, 500001, 'Core',
                                  condition='Scheduled', start_days=3, due_days=30)
        later_event.is_scheduled = True
        db_session.flush()

        sched_date = _future(5)
        sched = Schedule(
            event_ref_num=500001, employee_id='emp1',
            schedule_datetime=sched_date, shift_block=1,
        )
        db_session.add(sched)

        # Unscheduled event with earlier due date — valid for same date
        earlier_event = _make_event(models, db_session, 500002, 'Core',
                                    start_days=3, due_days=10)
        db_session.commit()

        from app.services.cpsat_scheduler import CPSATSchedulingEngine
        engine = CPSATSchedulingEngine(db_session, models)
        run = engine.SchedulerRunHistory(run_type='manual', status='running', solver_type='cpsat')
        db_session.add(run)
        db_session.flush()

        engine._load_time_settings()
        swaps = engine._due_date_priority_pass(run, db_session)
        db_session.flush()

        assert swaps >= 1
        # Should have created a PendingSchedule for the earlier event
        pending = _get_pending(db_session, models, run.id)
        swap_pending = [p for p in pending if p.event_ref_num == 500002]
        assert len(swap_pending) == 1
        assert swap_pending[0].is_swap is True
        assert swap_pending[0].bumped_event_ref_num == 500001

    def test_no_swap_when_types_differ(self, db_session, models):
        """A Digitals event should not swap with a Core event."""
        Schedule = models['Schedule']

        emp = _make_employee(models, db_session, 'emp1', 'Alice',
                             job_title='Lead Event Specialist')

        later_core = _make_event(models, db_session, 500010, 'Core',
                                 condition='Scheduled', start_days=3, due_days=30)
        later_core.is_scheduled = True
        db_session.flush()

        sched_date = _future(5)
        sched = Schedule(
            event_ref_num=500010, employee_id='emp1',
            schedule_datetime=sched_date, shift_block=1,
        )
        db_session.add(sched)

        # Earlier due date but different type
        earlier_digitals = _make_event(models, db_session, 500011, 'Digitals',
                                       start_days=3, due_days=10)
        db_session.commit()

        from app.services.cpsat_scheduler import CPSATSchedulingEngine
        engine = CPSATSchedulingEngine(db_session, models)
        run = engine.SchedulerRunHistory(run_type='manual', status='running', solver_type='cpsat')
        db_session.add(run)
        db_session.flush()

        engine._load_time_settings()
        swaps = engine._due_date_priority_pass(run, db_session)
        assert swaps == 0

    def test_no_swap_when_date_outside_event_range(self, db_session, models):
        """Don't swap if the scheduled date is outside the earlier event's valid range."""
        Schedule = models['Schedule']

        emp = _make_employee(models, db_session, 'emp1', 'Alice')

        later_event = _make_event(models, db_session, 500020, 'Core',
                                  condition='Scheduled', start_days=3, due_days=30)
        later_event.is_scheduled = True
        db_session.flush()

        # Schedule on day 15 — but earlier event's due_date is day 10
        sched_date = _future(15)
        sched = Schedule(
            event_ref_num=500020, employee_id='emp1',
            schedule_datetime=sched_date, shift_block=1,
        )
        db_session.add(sched)

        earlier_event = _make_event(models, db_session, 500021, 'Core',
                                    start_days=3, due_days=10)
        db_session.commit()

        from app.services.cpsat_scheduler import CPSATSchedulingEngine
        engine = CPSATSchedulingEngine(db_session, models)
        run = engine.SchedulerRunHistory(run_type='manual', status='running', solver_type='cpsat')
        db_session.add(run)
        db_session.flush()

        engine._load_time_settings()
        swaps = engine._due_date_priority_pass(run, db_session)
        assert swaps == 0

    def test_employee_eligibility_respected(self, db_session, models):
        """Don't swap if the employee isn't eligible for the earlier event type."""
        Schedule = models['Schedule']

        # Regular Event Specialist — not juicer trained
        emp = _make_employee(models, db_session, 'emp1', 'Alice')

        # Scheduled Juicer event (employee is Juicer Barista via override or title)
        later_juicer = _make_event(models, db_session, 500030, 'Core',
                                   condition='Scheduled', start_days=3, due_days=30)
        later_juicer.is_scheduled = True
        db_session.flush()

        sched_date = _future(5)
        sched = Schedule(
            event_ref_num=500030, employee_id='emp1',
            schedule_datetime=sched_date, shift_block=1,
        )
        db_session.add(sched)

        # Earlier Juicer Production event — employee not eligible
        earlier_juicer = _make_event(models, db_session, 500031, 'Juicer Production',
                                     start_days=3, due_days=10)
        db_session.commit()

        from app.services.cpsat_scheduler import CPSATSchedulingEngine
        engine = CPSATSchedulingEngine(db_session, models)
        run = engine.SchedulerRunHistory(run_type='manual', status='running', solver_type='cpsat')
        db_session.add(run)
        db_session.flush()

        engine._load_time_settings()
        swaps = engine._due_date_priority_pass(run, db_session)
        assert swaps == 0  # Can't swap — employee not Juicer eligible
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cpsat_scheduler.py::TestDueDatePriorityPass -v`
Expected: FAIL with "CPSATSchedulingEngine has no attribute _due_date_priority_pass"

**Step 3: Implement `_due_date_priority_pass`**

Add this method to `CPSATSchedulingEngine` class in `app/services/cpsat_scheduler.py`, before `run_auto_scheduler`:

```python
    def _due_date_priority_pass(self, run, db_session):
        """Pre-pass: swap posted schedules to prioritize earlier due dates.

        For each event type, find posted schedules holding later-due-date events
        and swap them for unscheduled events with earlier due dates.

        Only swaps same-type events. Keeps employee, date, time, and block unchanged.

        Returns:
            int: number of swaps performed
        """
        from sqlalchemy import and_
        from app.constants import INACTIVE_CONDITIONS

        swap_count = 0
        today = date.today()

        # Load unscheduled events (same query as _load_data)
        unscheduled_events = self.Event.query.filter(
            self.Event.is_scheduled == False,
            ~self.Event.condition.in_(list(INACTIVE_CONDITIONS)),
            self.Event.due_datetime > today,
        ).order_by(self.Event.due_datetime.asc()).all()

        if not unscheduled_events:
            logger.info("Phase 1: No unscheduled events — skipping due-date priority pass")
            return 0

        # Load all posted schedules with their events
        posted_schedules = db_session.query(self.Schedule).all()
        if not posted_schedules:
            logger.info("Phase 1: No posted schedules — skipping due-date priority pass")
            return 0

        # Build lookup: event_ref -> event object for posted events
        posted_event_refs = {s.event_ref_num for s in posted_schedules}
        posted_events = {
            e.project_ref_num: e
            for e in self.Event.query.filter(
                self.Event.project_ref_num.in_(posted_event_refs)
            ).all()
        }

        # Load locked days and holidays for validation
        locked_set = set()
        if self.LockedDay:
            for ld in self.LockedDay.query.all():
                locked_set.add(ld.locked_date)

        holiday_set = set()
        if self.CompanyHoliday:
            try:
                horizon = max(s.schedule_datetime.date() if isinstance(s.schedule_datetime, datetime)
                              else s.schedule_datetime for s in posted_schedules)
                holiday_set = set(self.CompanyHoliday.get_holidays_in_range(today, horizon))
            except Exception:
                pass

        # Load EventSchedulingOverride to skip excluded events
        skip_refs = set()
        if self.EventSchedulingOverride:
            for ov in self.EventSchedulingOverride.query.filter_by(allow_auto_schedule=False).all():
                skip_refs.add(ov.event_ref_num)

        # Load EventTypeOverride for correct type detection
        type_overrides = {}
        if self.EventTypeOverride:
            for ov in self.EventTypeOverride.query.all():
                type_overrides[ov.project_ref_num] = ov.override_event_type

        # Group posted schedules by event type
        def get_etype(event):
            return type_overrides.get(event.project_ref_num, None) or event.event_type

        posted_by_type = defaultdict(list)  # event_type -> [(schedule, event)]
        for s in posted_schedules:
            event = posted_events.get(s.event_ref_num)
            if not event:
                continue
            if event.project_ref_num in skip_refs:
                continue
            etype = get_etype(event)
            if etype == 'Supervisor':
                continue  # Don't swap Supervisor events
            posted_by_type[etype].append((s, event))

        # Sort posted schedules by due_datetime descending (latest first = most swappable)
        for etype in posted_by_type:
            posted_by_type[etype].sort(key=lambda x: x[1].due_datetime, reverse=True)

        # Group unscheduled events by type, sorted by due_datetime ascending
        unscheduled_by_type = defaultdict(list)
        for e in unscheduled_events:
            if e.project_ref_num in skip_refs:
                continue
            etype = get_etype(e)
            if etype == 'Supervisor':
                continue
            unscheduled_by_type[etype].append(e)

        # Track which events have been swapped (to avoid double-swapping)
        swapped_schedule_ids = set()
        swapped_event_refs = set()

        # Load employees for eligibility checks
        employees = {e.id: e for e in self.Employee.query.filter(
            self.Employee.is_active == True
        ).all()}

        for etype, posted_list in posted_by_type.items():
            unscheduled_list = unscheduled_by_type.get(etype, [])
            if not unscheduled_list:
                continue

            for unsched_event in list(unscheduled_list):
                if unsched_event.project_ref_num in swapped_event_refs:
                    continue

                for sched, posted_event in posted_list:
                    if sched.id in swapped_schedule_ids:
                        continue

                    # Must have later due date than the unscheduled event
                    if posted_event.due_datetime <= unsched_event.due_datetime:
                        continue

                    # Get the scheduled date
                    sched_date = (sched.schedule_datetime.date()
                                  if isinstance(sched.schedule_datetime, datetime)
                                  else sched.schedule_datetime)

                    # Scheduled date must be within unscheduled event's valid range
                    unsched_start = (unsched_event.start_datetime.date()
                                     if hasattr(unsched_event.start_datetime, 'date')
                                     else unsched_event.start_datetime)
                    unsched_due = (unsched_event.due_datetime.date()
                                   if hasattr(unsched_event.due_datetime, 'date')
                                   else unsched_event.due_datetime)

                    if not (unsched_start <= sched_date < unsched_due):
                        continue

                    # Date must not be locked or holiday
                    if sched_date in locked_set or sched_date in holiday_set:
                        continue

                    # Employee must be eligible for the unscheduled event
                    emp = employees.get(sched.employee_id)
                    if not emp:
                        continue

                    unsched_etype = get_etype(unsched_event)
                    if unsched_etype in JUICER_EVENT_TYPES:
                        if emp.job_title not in JUICER_TITLES and not emp.juicer_trained:
                            continue
                    elif unsched_etype in LEAD_ONLY_EVENT_TYPES:
                        if emp.job_title not in LEAD_TITLES:
                            continue

                    # Valid swap found — create PendingSchedule records
                    logger.info(
                        f"Phase 1: Swapping {unsched_event.project_name} (due {unsched_due}) "
                        f"into slot of {posted_event.project_name} (due "
                        f"{posted_event.due_datetime.date() if hasattr(posted_event.due_datetime, 'date') else posted_event.due_datetime}) "
                        f"on {sched_date} with {emp.name}"
                    )

                    # Create pending schedule for the earlier-due event (takes the slot)
                    ps = self._create_pending_schedule(
                        run, unsched_event, sched.employee_id,
                        sched.schedule_datetime,
                        is_swap=True,
                        bumped_event_ref_num=posted_event.project_ref_num,
                        swap_reason='Due date priority swap',
                        shift_block=getattr(sched, 'shift_block', None),
                    )
                    if ps:
                        ps.bumped_posted_schedule_id = sched.id

                    swapped_schedule_ids.add(sched.id)
                    swapped_event_refs.add(unsched_event.project_ref_num)
                    swap_count += 1
                    break  # Move to next unscheduled event

        logger.info(f"Phase 1: Due-date priority pre-pass — {swap_count} swaps")
        return swap_count
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cpsat_scheduler.py::TestDueDatePriorityPass -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add app/services/cpsat_scheduler.py tests/test_cpsat_scheduler.py
git commit -m "feat: add due-date priority pre-pass method

Scans posted schedules and swaps later-due-date events for unscheduled
events with earlier due dates. Same type only, preserves employee/date/
time/block. Creates PendingSchedule swap records for approval workflow."
```

---

### Task 4: Add `_due_date_verification_pass` Method

**Files:**
- Modify: `app/services/cpsat_scheduler.py` (add new method)
- Test: `tests/test_cpsat_scheduler.py`

**Step 1: Write the failing test**

```python
class TestDueDateVerificationPass:
    """Test the post-pass that verifies due-date ordering after solver runs."""

    def test_post_pass_catches_remaining_violation(self, db_session, models):
        """If solver scheduled a later-due event while an earlier-due event
        of same type is in a posted schedule, post-pass should swap them."""
        Schedule = models['Schedule']
        PendingSchedule = models['PendingSchedule']

        emp = _make_employee(models, db_session, 'emp1', 'Alice')

        # Posted schedule with later due date (not touched by solver)
        later_event = _make_event(models, db_session, 600001, 'Core',
                                  condition='Scheduled', start_days=3, due_days=30)
        later_event.is_scheduled = True
        db_session.flush()

        sched_date = _future(5)
        sched = Schedule(
            event_ref_num=600001, employee_id='emp1',
            schedule_datetime=sched_date, shift_block=1,
        )
        db_session.add(sched)

        # Solver failed to schedule this earlier-due event
        earlier_event = _make_event(models, db_session, 600002, 'Core',
                                    start_days=3, due_days=10)
        db_session.commit()

        from app.services.cpsat_scheduler import CPSATSchedulingEngine
        engine = CPSATSchedulingEngine(db_session, models)
        run = engine.SchedulerRunHistory(run_type='manual', status='running', solver_type='cpsat')
        db_session.add(run)
        db_session.flush()

        # Simulate: solver created a failure record for earlier_event
        fail_ps = PendingSchedule(
            scheduler_run_id=run.id,
            event_ref_num=600002,
            failure_reason='Solver could not schedule within constraints',
            status='proposed',
        )
        db_session.add(fail_ps)
        db_session.flush()

        engine._load_time_settings()
        swaps = engine._due_date_verification_pass(run, db_session)
        db_session.flush()

        assert swaps >= 1
        # The earlier event should now have a swap pending
        pending = _get_pending(db_session, models, run.id)
        swap_pending = [p for p in pending
                        if p.event_ref_num == 600002 and p.is_swap]
        assert len(swap_pending) == 1
        assert swap_pending[0].bumped_event_ref_num == 600001
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cpsat_scheduler.py::TestDueDateVerificationPass -v`
Expected: FAIL with "has no attribute _due_date_verification_pass"

**Step 3: Implement `_due_date_verification_pass`**

Add this method after `_due_date_priority_pass`:

```python
    def _due_date_verification_pass(self, run, db_session):
        """Post-pass: verify due-date ordering and fix remaining violations.

        Checks the combined set of posted schedules + pending schedules from
        this run. If a later-due-date event occupies a slot that an unscheduled
        (or failed) earlier-due-date event of the same type could use, swap them.

        Returns:
            int: number of additional swaps performed
        """
        from app.constants import INACTIVE_CONDITIONS

        swap_count = 0
        today = date.today()

        # Get events that failed scheduling in this run (or are still unscheduled)
        failed_pending = db_session.query(self.PendingSchedule).filter(
            self.PendingSchedule.scheduler_run_id == run.id,
            self.PendingSchedule.failure_reason.isnot(None),
        ).all()
        failed_refs = {fp.event_ref_num for fp in failed_pending}

        # Also check for unscheduled events not in this run at all
        run_refs = {ps.event_ref_num for ps in
                    db_session.query(self.PendingSchedule).filter_by(scheduler_run_id=run.id).all()}

        unscheduled_events = self.Event.query.filter(
            self.Event.is_scheduled == False,
            ~self.Event.condition.in_(list(INACTIVE_CONDITIONS)),
            self.Event.due_datetime > today,
        ).order_by(self.Event.due_datetime.asc()).all()

        # Include failed events + events not in this run
        candidate_events = [e for e in unscheduled_events
                            if e.project_ref_num in failed_refs
                            or e.project_ref_num not in run_refs]

        if not candidate_events:
            logger.info("Phase 4: No failed/unscheduled events — skipping verification pass")
            return 0

        # Reuse pre-pass logic but with combined schedule view
        # For now, posted schedules that weren't displaced are still valid targets
        displaced_refs = set()
        for ps in db_session.query(self.PendingSchedule).filter(
            self.PendingSchedule.scheduler_run_id == run.id,
            self.PendingSchedule.is_swap == True,
            self.PendingSchedule.bumped_event_ref_num.isnot(None),
        ).all():
            displaced_refs.add(ps.bumped_event_ref_num)

        posted_schedules = db_session.query(self.Schedule).all()
        posted_schedules = [s for s in posted_schedules
                            if s.event_ref_num not in displaced_refs]

        if not posted_schedules:
            logger.info("Phase 4: No remaining posted schedules to check")
            return 0

        # Load context (same as pre-pass)
        posted_event_refs = {s.event_ref_num for s in posted_schedules}
        posted_events = {
            e.project_ref_num: e
            for e in self.Event.query.filter(
                self.Event.project_ref_num.in_(posted_event_refs)
            ).all()
        }

        locked_set = set()
        if self.LockedDay:
            for ld in self.LockedDay.query.all():
                locked_set.add(ld.locked_date)

        holiday_set = set()
        if self.CompanyHoliday:
            try:
                horizon = max(s.schedule_datetime.date() if isinstance(s.schedule_datetime, datetime)
                              else s.schedule_datetime for s in posted_schedules)
                holiday_set = set(self.CompanyHoliday.get_holidays_in_range(today, horizon))
            except Exception:
                pass

        skip_refs = set()
        if self.EventSchedulingOverride:
            for ov in self.EventSchedulingOverride.query.filter_by(allow_auto_schedule=False).all():
                skip_refs.add(ov.event_ref_num)

        type_overrides = {}
        if self.EventTypeOverride:
            for ov in self.EventTypeOverride.query.all():
                type_overrides[ov.project_ref_num] = ov.override_event_type

        def get_etype(event):
            return type_overrides.get(event.project_ref_num, None) or event.event_type

        employees = {e.id: e for e in self.Employee.query.filter(
            self.Employee.is_active == True
        ).all()}

        # Group posted by type
        posted_by_type = defaultdict(list)
        for s in posted_schedules:
            event = posted_events.get(s.event_ref_num)
            if not event or event.project_ref_num in skip_refs:
                continue
            etype = get_etype(event)
            if etype == 'Supervisor':
                continue
            posted_by_type[etype].append((s, event))

        for etype in posted_by_type:
            posted_by_type[etype].sort(key=lambda x: x[1].due_datetime, reverse=True)

        # Group candidates by type
        candidates_by_type = defaultdict(list)
        for e in candidate_events:
            if e.project_ref_num in skip_refs:
                continue
            etype = get_etype(e)
            if etype == 'Supervisor':
                continue
            candidates_by_type[etype].append(e)

        swapped_schedule_ids = set()
        swapped_event_refs = set()

        for etype, posted_list in posted_by_type.items():
            candidates = candidates_by_type.get(etype, [])
            if not candidates:
                continue

            for candidate in candidates:
                if candidate.project_ref_num in swapped_event_refs:
                    continue

                for sched, posted_event in posted_list:
                    if sched.id in swapped_schedule_ids:
                        continue
                    if posted_event.due_datetime <= candidate.due_datetime:
                        continue

                    sched_date = (sched.schedule_datetime.date()
                                  if isinstance(sched.schedule_datetime, datetime)
                                  else sched.schedule_datetime)

                    cand_start = (candidate.start_datetime.date()
                                  if hasattr(candidate.start_datetime, 'date')
                                  else candidate.start_datetime)
                    cand_due = (candidate.due_datetime.date()
                                if hasattr(candidate.due_datetime, 'date')
                                else candidate.due_datetime)

                    if not (cand_start <= sched_date < cand_due):
                        continue
                    if sched_date in locked_set or sched_date in holiday_set:
                        continue

                    emp = employees.get(sched.employee_id)
                    if not emp:
                        continue

                    cand_etype = get_etype(candidate)
                    if cand_etype in JUICER_EVENT_TYPES:
                        if emp.job_title not in JUICER_TITLES and not emp.juicer_trained:
                            continue
                    elif cand_etype in LEAD_ONLY_EVENT_TYPES:
                        if emp.job_title not in LEAD_TITLES:
                            continue

                    logger.info(
                        f"Phase 4: Swapping {candidate.project_name} (due {cand_due}) "
                        f"into slot of {posted_event.project_name} on {sched_date}"
                    )

                    # Delete the failure record if one exists
                    fail_record = db_session.query(self.PendingSchedule).filter(
                        self.PendingSchedule.scheduler_run_id == run.id,
                        self.PendingSchedule.event_ref_num == candidate.project_ref_num,
                        self.PendingSchedule.failure_reason.isnot(None),
                    ).first()
                    if fail_record:
                        db_session.delete(fail_record)

                    ps = self._create_pending_schedule(
                        run, candidate, sched.employee_id,
                        sched.schedule_datetime,
                        is_swap=True,
                        bumped_event_ref_num=posted_event.project_ref_num,
                        swap_reason='Due date priority verification swap',
                        shift_block=getattr(sched, 'shift_block', None),
                    )
                    if ps:
                        ps.bumped_posted_schedule_id = sched.id

                    swapped_schedule_ids.add(sched.id)
                    swapped_event_refs.add(candidate.project_ref_num)
                    swap_count += 1
                    break

        logger.info(f"Phase 4: Due-date verification — {swap_count} additional swaps")
        return swap_count
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cpsat_scheduler.py::TestDueDateVerificationPass -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/cpsat_scheduler.py tests/test_cpsat_scheduler.py
git commit -m "feat: add due-date verification post-pass method

After the solver runs, checks remaining unscheduled/failed events and
swaps them into posted schedule slots occupied by later-due-date events
of the same type."
```

---

### Task 5: Refactor `run_auto_scheduler` into 4-Phase Flow

**Files:**
- Modify: `app/services/cpsat_scheduler.py:2299-2421` (run_auto_scheduler)
- Test: `tests/test_cpsat_scheduler.py`

**Step 1: Write the failing test**

```python
class TestFourPhaseScheduling:
    """Test the complete 4-phase scheduling flow."""

    def test_full_flow_prioritizes_earlier_due_date(self, db_session, models):
        """End-to-end: earlier-due-date event should be scheduled even when
        a later-due-date event already occupies the only viable slot."""
        Schedule = models['Schedule']

        emp = _make_employee(models, db_session, 'emp1', 'Alice')

        # Later-due Core event already scheduled
        later = _make_event(models, db_session, 700001, 'Core',
                            condition='Scheduled', start_days=3, due_days=30)
        later.is_scheduled = True
        db_session.flush()

        sched_date = _future(5)
        sched = Schedule(
            event_ref_num=700001, employee_id='emp1',
            schedule_datetime=sched_date, shift_block=1,
        )
        db_session.add(sched)

        # Earlier-due Core event — unscheduled, valid for same date
        earlier = _make_event(models, db_session, 700002, 'Core',
                              start_days=3, due_days=10)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.status == 'completed'

        # Earlier event should be scheduled (via pre-pass swap or solver)
        pending = _get_pending(db_session, models, run.id)
        earlier_pending = [p for p in pending if p.event_ref_num == 700002
                           and p.employee_id is not None]
        assert len(earlier_pending) >= 1, "Earlier-due event should be scheduled"

    def test_no_bumping_phase_schedules_into_empty_slots(self, db_session, models):
        """Phase 2 should schedule events into empty slots without bumping."""
        _make_employee(models, db_session, 'emp1', 'Alice')
        _make_employee(models, db_session, 'emp2', 'Bob')

        # Two events, plenty of open slots
        _make_event(models, db_session, 700010, 'Core', start_days=3, due_days=14)
        _make_event(models, db_session, 700011, 'Core', start_days=3, due_days=14)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.status == 'completed'
        assert run.events_scheduled >= 2

        # No swaps should be needed
        pending = _get_pending(db_session, models, run.id)
        swaps = [p for p in pending if p.is_swap]
        assert len(swaps) == 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cpsat_scheduler.py::TestFourPhaseScheduling -v`
Expected: The first test may fail (earlier event not scheduled)

**Step 3: Refactor `run_auto_scheduler`**

Replace the `run_auto_scheduler` method (lines 2299-2421) with the 4-phase flow:

```python
    def run_auto_scheduler(self, run_type='manual', time_limit_seconds=60):
        """
        Run the CP-SAT auto-scheduler in 4 phases:

        Phase 1: Due-date priority pre-pass (swap posted schedules)
        Phase 2: Solver without bumping (schedule into empty slots)
        Phase 3: Solver with bumping (only for Phase 2 failures)
        Phase 4: Due-date verification post-pass

        Args:
            run_type: 'manual' or 'automatic'
            time_limit_seconds: Maximum solver time per phase (default 60s)

        Returns:
            SchedulerRunHistory record with results
        """
        run = self.SchedulerRunHistory(
            run_type=run_type,
            status='running',
            solver_type='cpsat',
        )
        self.db.add(run)
        self.db.flush()

        total_scheduled = 0
        total_failed = 0
        total_swaps = 0
        total_events = 0

        try:
            # ============================================================
            # Phase 1: Due-date priority pre-pass
            # ============================================================
            logger.info("=== PHASE 1: Due-date priority pre-pass ===")
            phase1_swaps = self._due_date_priority_pass(run, self.db)
            total_swaps += phase1_swaps
            total_scheduled += phase1_swaps
            self.db.flush()

            # ============================================================
            # Phase 2: Solver WITHOUT bumping
            # ============================================================
            logger.info("=== PHASE 2: Solver (no bumping) ===")
            self.allow_bumping = False
            self._load_data()

            # Exclude events already handled in Phase 1
            phase1_refs = set()
            for ps in self.db.query(self.PendingSchedule).filter(
                self.PendingSchedule.scheduler_run_id == run.id,
                self.PendingSchedule.employee_id.isnot(None),
            ).all():
                phase1_refs.add(ps.event_ref_num)

            if phase1_refs:
                self.events = [e for e in self.events
                               if e.project_ref_num not in phase1_refs]
                # Recompute eligibility/pairings after filtering
                self._compute_pairings()
                self._compute_eligibility()
                self._compute_product_groups()

            phase2_events = len(self.events)
            total_events += phase2_events

            if phase2_events == 0:
                logger.info("Phase 2: No events to schedule")
                scheduled_2 = 0
                failed_2 = 0
            else:
                paired_sup = len(self.core_sup_pairs)
                paired_survey = len(getattr(self, 'juicer_prod_survey_pairs', {}))
                bumpable_count = len(self.bumpable_event_ids)
                logger.info(
                    f"CP-SAT Scheduler: {phase2_events} events to schedule "
                    f"({bumpable_count} bumpable), "
                    f"{len(self.employee_ids)} employees, "
                    f"{len(self.valid_days)} valid days, "
                    f"{paired_sup} Core-Supervisor pairs, "
                    f"{paired_survey} Juicer Prod-Survey pairs"
                )

                model = self._build_model()
                solver, status = self._solve(model, time_limit_seconds)

                if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                    scheduled_2, failed_2, swaps_2 = self._extract_solution(solver, run)
                    self._log_solution_explanations(solver)
                    removed = self._post_solve_review(run)
                    if removed > 0:
                        scheduled_2 -= removed
                        failed_2 += removed
                    total_swaps += swaps_2
                else:
                    logger.warning(f"Phase 2 solver status: {status}")
                    scheduled_2 = 0
                    failed_2 = phase2_events

            total_scheduled += scheduled_2
            total_failed += failed_2
            self.db.flush()

            # ============================================================
            # Phase 3: Solver WITH bumping (only for Phase 2 failures)
            # ============================================================
            if failed_2 > 0:
                logger.info(f"=== PHASE 3: Solver (with bumping) for {failed_2} failed events ===")

                # Collect failed event refs from Phase 2
                failed_refs = set()
                for ps in self.db.query(self.PendingSchedule).filter(
                    self.PendingSchedule.scheduler_run_id == run.id,
                    self.PendingSchedule.failure_reason.isnot(None),
                ).all():
                    failed_refs.add(ps.event_ref_num)

                if failed_refs:
                    # Delete the failure records — we'll re-attempt them
                    self.db.query(self.PendingSchedule).filter(
                        self.PendingSchedule.scheduler_run_id == run.id,
                        self.PendingSchedule.failure_reason.isnot(None),
                        self.PendingSchedule.event_ref_num.in_(failed_refs),
                    ).delete(synchronize_session='fetch')
                    self.db.flush()

                    self.allow_bumping = True
                    self._load_data()

                    # Filter to only the failed events
                    self.events = [e for e in self.events
                                   if e.project_ref_num in failed_refs
                                   or e.id in self.bumpable_event_ids]

                    # Recompute after filtering
                    self._compute_pairings()
                    self._compute_eligibility()
                    self._compute_product_groups()

                    phase3_events = len([e for e in self.events
                                         if e.id not in self.bumpable_event_ids])

                    if phase3_events > 0:
                        bumpable_count = len(self.bumpable_event_ids)
                        logger.info(
                            f"Phase 3: {phase3_events} events to retry "
                            f"({bumpable_count} bumpable targets)"
                        )

                        model = self._build_model()
                        solver, status = self._solve(model, time_limit_seconds)

                        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                            scheduled_3, failed_3, swaps_3 = self._extract_solution(solver, run)
                            self._log_solution_explanations(solver)
                            removed = self._post_solve_review(run)
                            if removed > 0:
                                scheduled_3 -= removed
                                failed_3 += removed

                            # Adjust totals (Phase 2 failures resolved)
                            total_scheduled += scheduled_3
                            total_failed = total_failed - len(failed_refs) + failed_3
                            total_swaps += swaps_3
                        else:
                            logger.warning(f"Phase 3 solver status: {status}")
                    else:
                        logger.info("Phase 3: No events to retry")

                self.db.flush()
            else:
                logger.info("=== PHASE 3: Skipped (no Phase 2 failures) ===")

            # ============================================================
            # Phase 4: Due-date verification post-pass
            # ============================================================
            logger.info("=== PHASE 4: Due-date verification post-pass ===")
            phase4_swaps = self._due_date_verification_pass(run, self.db)
            total_swaps += phase4_swaps
            total_scheduled += phase4_swaps
            # Reduce failed count by events rescued in Phase 4
            total_failed = max(0, total_failed - phase4_swaps)

            # ============================================================
            # Finalize
            # ============================================================
            run.status = 'completed'
            run.completed_at = datetime.utcnow()
            run.total_events_processed = total_events + phase1_swaps
            run.events_scheduled = total_scheduled
            run.events_failed = total_failed
            run.events_requiring_swaps = total_swaps
            self.db.commit()

            logger.info(
                f"CP-SAT Scheduler: Done. "
                f"Phase1Swaps={phase1_swaps}, Phase2={scheduled_2}/{failed_2}, "
                f"Phase3={'skipped' if failed_2 == 0 else f'{total_scheduled - scheduled_2 - phase1_swaps - phase4_swaps}'}, "
                f"Phase4Swaps={phase4_swaps}, "
                f"Total: Scheduled={total_scheduled}, Failed={total_failed}, Swaps={total_swaps}"
            )

        except Exception as e:
            logger.exception(f"CP-SAT Scheduler: Error - {e}")
            run.status = 'crashed'
            run.completed_at = datetime.utcnow()
            run.error_message = str(e)
            run.total_events_processed = 0
            run.events_scheduled = 0
            run.events_failed = 0
            run.events_requiring_swaps = 0
            self.db.commit()
            raise

        return run
```

**Step 4: Add `allow_bumping` guard to `_load_data`**

In `_load_data` (around line 286), wrap the bumpable events loading:

```python
        # --- Bumpable events: already-scheduled events that can be displaced ---
        if getattr(self, 'allow_bumping', True):
            # Load "Scheduled" condition events that have posted schedules...
            # (existing code lines 291-320)
        else:
            logger.info("Phase 2: Bumping disabled — skipping bumpable event loading")
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cpsat_scheduler.py::TestFourPhaseScheduling -v`
Expected: PASS

**Step 6: Run full test suite**

Run: `pytest tests/test_cpsat_scheduler.py -v`
Expected: All tests PASS (existing tests should still work since the 4-phase flow
produces the same results when there are no posted schedules to swap)

**Step 7: Commit**

```bash
git add app/services/cpsat_scheduler.py tests/test_cpsat_scheduler.py
git commit -m "feat: refactor auto-scheduler into 4-phase due-date priority flow

Phase 1: Pre-pass swaps posted schedules for earlier-due-date events
Phase 2: Solver run without bumping (fill empty slots)
Phase 3: Solver run with bumping (only for Phase 2 failures)
Phase 4: Post-pass verification of due-date ordering

This ensures events with earliest due dates are always scheduled first."
```

---

### Task 6: Integration Test with Realistic Data

**Files:**
- Test: `tests/test_cpsat_scheduler.py`

**Step 1: Write integration test**

```python
class TestDueDateIntegration:
    """Integration tests with realistic multi-employee, multi-event scenarios."""

    def test_multiple_types_due_date_ordering(self, db_session, models):
        """Multiple event types should each independently respect due-date ordering."""
        Schedule = models['Schedule']

        # Create employees with various roles
        _make_employee(models, db_session, 'emp1', 'Alice', job_title='Lead Event Specialist')
        _make_employee(models, db_session, 'emp2', 'Bob', job_title='Event Specialist')
        _make_employee(models, db_session, 'emp3', 'Carol', job_title='Juicer Barista')

        # Scheduled Core event with later due date
        later_core = _make_event(models, db_session, 800001, 'Core',
                                 condition='Scheduled', start_days=3, due_days=25)
        later_core.is_scheduled = True
        db_session.flush()

        sched_date = _future(5)
        sched = Schedule(
            event_ref_num=800001, employee_id='emp1',
            schedule_datetime=sched_date, shift_block=1,
        )
        db_session.add(sched)

        # Unscheduled Core event with earlier due date
        _make_event(models, db_session, 800002, 'Core', start_days=3, due_days=8)

        # Unscheduled Digitals event (should NOT swap with Core)
        _make_event(models, db_session, 800003, 'Digitals', start_days=3, due_days=8)

        # Several more unscheduled events
        _make_event(models, db_session, 800004, 'Core', start_days=3, due_days=14)
        _make_event(models, db_session, 800005, 'Core', start_days=3, due_days=20)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.status == 'completed'
        assert run.events_scheduled >= 3

        # Verify: earlier Core event (800002) should be scheduled
        pending = _get_pending(db_session, models, run.id)
        earlier_core = [p for p in pending if p.event_ref_num == 800002
                        and p.employee_id is not None]
        assert len(earlier_core) >= 1, "Earlier-due Core event must be scheduled"

    def test_phase3_bumping_only_when_needed(self, db_session, models):
        """Bumping should only happen in Phase 3 when Phase 2 can't schedule."""
        Schedule = models['Schedule']

        # One employee, all slots taken by posted schedules
        emp = _make_employee(models, db_session, 'emp1', 'Alice')

        # Fill up slots with posted schedules (8 core events = 1 per day for 8 days)
        for i in range(6):
            evt = _make_event(models, db_session, 900001 + i, 'Core',
                              condition='Scheduled', start_days=3, due_days=30)
            evt.is_scheduled = True
            db_session.flush()
            sched = Schedule(
                event_ref_num=900001 + i, employee_id='emp1',
                schedule_datetime=_future(4 + i), shift_block=(i % 8) + 1,
            )
            db_session.add(sched)

        # New event that should need bumping to schedule
        _make_event(models, db_session, 900010, 'Core', start_days=3, due_days=12)
        db_session.commit()

        run = _run_cpsat(db_session, models)
        assert run.status == 'completed'
        # Event should be scheduled (either via Phase 1 swap or Phase 3 bump)
        pending = _get_pending(db_session, models, run.id)
        new_event_pending = [p for p in pending if p.event_ref_num == 900010
                             and p.employee_id is not None]
        assert len(new_event_pending) >= 1, \
            "New event should be scheduled (via Phase 1 swap or Phase 3 bump)"
```

**Step 2: Run integration tests**

Run: `pytest tests/test_cpsat_scheduler.py::TestDueDateIntegration -v`
Expected: PASS

**Step 3: Run full test suite**

Run: `pytest tests/test_cpsat_scheduler.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add tests/test_cpsat_scheduler.py
git commit -m "test: add integration tests for 4-phase due-date scheduling"
```

---

### Task 7: Final Verification and Cleanup

**Step 1: Run complete test suite**

Run: `pytest -v`
Expected: All tests PASS

**Step 2: Verify logging output format**

Run the scheduler manually in a test instance and verify logs show:
```
=== PHASE 1: Due-date priority pre-pass ===
Phase 1: Due-date priority pre-pass — N swaps
=== PHASE 2: Solver (no bumping) ===
CP-SAT Scheduler: X events to schedule...
=== PHASE 3: Solver (with bumping) for M failed events ===
=== PHASE 4: Due-date verification post-pass ===
CP-SAT Scheduler: Done. Phase1Swaps=N, Phase2=X/Y, Phase3=..., Phase4Swaps=K
```

**Step 3: Final commit with all changes**

```bash
git add -A
git commit -m "feat: complete 4-phase due-date priority scheduling

- Phase 1: Pre-pass swaps posted schedules for earlier-due-date events
- Phase 2: Solver run without bumping (fill empty slots only)
- Phase 3: Solver run with bumping (only for Phase 2 failures)
- Phase 4: Post-pass verification of due-date ordering
- Fix: Self-bump bug where reassigned events showed as bumping themselves
- Fix: Approval handles rescheduled events via bumped_posted_schedule_id"
```
