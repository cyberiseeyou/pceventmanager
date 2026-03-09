"""Tests for ScheduleRebalancer service."""
import pytest
from datetime import datetime, date, timedelta
from app.models import get_models, get_db

# Actual shift block arrive times from ShiftBlockConfig
# Block 1,2: 10:15 | Block 3,4: 10:45 | Block 5,6: 11:15 | Block 7,8: 11:45
SLOT_1 = (10, 15)
SLOT_2 = (10, 45)
SLOT_3 = (11, 15)
SLOT_4 = (11, 45)


def _create_employee(db_session, models, emp_id, name, job_title='Event Specialist'):
    Employee = models['Employee']
    emp = Employee(id=emp_id, name=name, job_title=job_title, is_active=True)
    db_session.add(emp)
    db_session.flush()
    return emp


def _create_event(db_session, models, ref_num, event_type='Core', estimated_time=60):
    Event = models['Event']
    evt = Event(
        project_ref_num=ref_num,
        project_name=f'Test Event {ref_num}',
        event_type=event_type,
        start_datetime=datetime(2026, 3, 9, 0, 0),
        due_datetime=datetime(2026, 3, 13, 23, 59),
        estimated_time=estimated_time
    )
    db_session.add(evt)
    db_session.flush()
    return evt


def _create_schedule(db_session, models, event, employee, schedule_dt):
    Schedule = models['Schedule']
    sched = Schedule(
        event_ref_num=event.project_ref_num,
        employee_id=employee.id,
        employee_name=employee.name,
        schedule_datetime=schedule_dt
    )
    db_session.add(sched)
    db_session.flush()
    return sched


class TestTimeSlotRebalancing:
    """Phase 1: Time slot rebalancing within a day."""

    def test_rebalance_moves_events_from_overloaded_slot(self, app, db_session, models):
        """When one time slot has 3 Core events and another has 0, rebalance moves one."""
        from app.services.schedule_rebalancer import ScheduleRebalancer

        emp1 = _create_employee(db_session, models, 'E1', 'Alice')
        emp2 = _create_employee(db_session, models, 'E2', 'Bob')
        emp3 = _create_employee(db_session, models, 'E3', 'Carol')
        emp4 = _create_employee(db_session, models, 'E4', 'Dave')

        evt1 = _create_event(db_session, models, 1001)
        evt2 = _create_event(db_session, models, 1002)
        evt3 = _create_event(db_session, models, 1003)
        evt4 = _create_event(db_session, models, 1004)

        target_date = date(2026, 3, 9)  # Monday

        # Schedule 3 events at slot 1 (10:15) and 1 at slot 2 (10:45) — imbalanced
        _create_schedule(db_session, models, evt1, emp1, datetime(2026, 3, 9, *SLOT_1))
        _create_schedule(db_session, models, evt2, emp2, datetime(2026, 3, 9, *SLOT_1))
        _create_schedule(db_session, models, evt3, emp3, datetime(2026, 3, 9, *SLOT_1))
        _create_schedule(db_session, models, evt4, emp4, datetime(2026, 3, 9, *SLOT_2))
        db_session.commit()

        rebalancer = ScheduleRebalancer(db_session, models)
        result = rebalancer.rebalance_week(target_date)

        assert result['time_slot_moves'] >= 1
        assert result['moves_made'] >= 1

    def test_no_moves_when_already_balanced(self, app, db_session, models):
        """When time slots are already balanced, no moves are made."""
        from app.services.schedule_rebalancer import ScheduleRebalancer

        emp1 = _create_employee(db_session, models, 'E1', 'Alice')
        emp2 = _create_employee(db_session, models, 'E2', 'Bob')

        evt1 = _create_event(db_session, models, 1001)
        evt2 = _create_event(db_session, models, 1002)

        # One event per different slot — balanced
        _create_schedule(db_session, models, evt1, emp1, datetime(2026, 3, 9, *SLOT_1))
        _create_schedule(db_session, models, evt2, emp2, datetime(2026, 3, 9, *SLOT_2))
        db_session.commit()

        rebalancer = ScheduleRebalancer(db_session, models)
        result = rebalancer.rebalance_week(date(2026, 3, 9))

        assert result['time_slot_moves'] == 0

    def test_skips_locked_days(self, app, db_session, models):
        """Locked days are skipped entirely during rebalancing."""
        from app.services.schedule_rebalancer import ScheduleRebalancer

        LockedDay = models.get('LockedDay')
        if not LockedDay:
            pytest.skip('LockedDay model not available')

        target_date = date(2026, 3, 9)

        # Lock the day
        locked = LockedDay(locked_date=target_date, reason='Test lock')
        db_session.add(locked)

        emp1 = _create_employee(db_session, models, 'E1', 'Alice')
        emp2 = _create_employee(db_session, models, 'E2', 'Bob')
        emp3 = _create_employee(db_session, models, 'E3', 'Carol')

        evt1 = _create_event(db_session, models, 1001)
        evt2 = _create_event(db_session, models, 1002)
        evt3 = _create_event(db_session, models, 1003)

        # Imbalanced — 3 at slot 1, 0 elsewhere
        _create_schedule(db_session, models, evt1, emp1, datetime(2026, 3, 9, *SLOT_1))
        _create_schedule(db_session, models, evt2, emp2, datetime(2026, 3, 9, *SLOT_1))
        _create_schedule(db_session, models, evt3, emp3, datetime(2026, 3, 9, *SLOT_1))
        db_session.commit()

        rebalancer = ScheduleRebalancer(db_session, models)
        result = rebalancer.rebalance_week(target_date)

        # No moves because day is locked
        assert result['time_slot_moves'] == 0


class TestEmployeeWorkloadRebalancing:
    """Phase 2: Employee workload rebalancing across the week."""

    def test_rebalance_swaps_from_overloaded_to_underloaded(self, app, db_session, models):
        """Employee with 4 Core events should lose one to employee with 0."""
        from app.services.schedule_rebalancer import ScheduleRebalancer

        emp_heavy = _create_employee(db_session, models, 'E1', 'Alice')
        emp_light = _create_employee(db_session, models, 'E2', 'Bob')

        # 4 events all assigned to emp_heavy across different days
        for i, day_offset in enumerate([0, 1, 2, 3]):
            evt = _create_event(db_session, models, 2000 + i)
            dt = datetime(2026, 3, 9 + day_offset, *SLOT_1)
            _create_schedule(db_session, models, evt, emp_heavy, dt)

        db_session.commit()

        rebalancer = ScheduleRebalancer(db_session, models)
        week_start = date(2026, 3, 8)  # Sunday
        result = rebalancer.rebalance_week(week_start)

        assert result['employee_swaps'] >= 1

        # Verify distribution improved
        Schedule = models['Schedule']
        alice_count = db_session.query(Schedule).filter(
            Schedule.employee_id == 'E1'
        ).count()
        bob_count = db_session.query(Schedule).filter(
            Schedule.employee_id == 'E2'
        ).count()

        assert abs(alice_count - bob_count) <= 1

    def test_no_swaps_when_already_balanced(self, app, db_session, models):
        """When employees have equal Core counts, no swaps happen."""
        from app.services.schedule_rebalancer import ScheduleRebalancer

        emp1 = _create_employee(db_session, models, 'E1', 'Alice')
        emp2 = _create_employee(db_session, models, 'E2', 'Bob')

        evt1 = _create_event(db_session, models, 2001)
        evt2 = _create_event(db_session, models, 2002)

        _create_schedule(db_session, models, evt1, emp1, datetime(2026, 3, 9, *SLOT_1))
        _create_schedule(db_session, models, evt2, emp2, datetime(2026, 3, 9, *SLOT_2))
        db_session.commit()

        rebalancer = ScheduleRebalancer(db_session, models)
        result = rebalancer.rebalance_week(date(2026, 3, 8))

        assert result['employee_swaps'] == 0

    def test_respects_max_one_core_per_day(self, app, db_session, models):
        """Won't assign a second Core event to an employee on the same day."""
        from app.services.schedule_rebalancer import ScheduleRebalancer

        emp1 = _create_employee(db_session, models, 'E1', 'Alice')
        emp2 = _create_employee(db_session, models, 'E2', 'Bob')

        # Alice has 3 events on 3 different days
        for i in range(3):
            evt = _create_event(db_session, models, 3000 + i)
            _create_schedule(db_session, models, evt, emp1,
                             datetime(2026, 3, 9 + i, *SLOT_1))

        # Bob already has a Core event on day 0
        evt_bob = _create_event(db_session, models, 3010)
        _create_schedule(db_session, models, evt_bob, emp2,
                         datetime(2026, 3, 9, *SLOT_2))
        db_session.commit()

        rebalancer = ScheduleRebalancer(db_session, models)
        result = rebalancer.rebalance_week(date(2026, 3, 8))

        # Bob can receive events on days 1 and 2, but NOT day 0 (already has one)
        Schedule = models['Schedule']
        bob_day0 = db_session.query(Schedule).filter(
            Schedule.employee_id == 'E2',
            Schedule.schedule_datetime >= datetime(2026, 3, 9),
            Schedule.schedule_datetime < datetime(2026, 3, 10)
        ).count()
        assert bob_day0 <= 1  # Max 1 Core per day


class TestRebalanceWeekIntegration:
    """Integration tests for full rebalance_week flow."""

    def test_rebalance_returns_expected_structure(self, app, db_session, models):
        """Result dict has all required keys."""
        from app.services.schedule_rebalancer import ScheduleRebalancer

        rebalancer = ScheduleRebalancer(db_session, models)
        result = rebalancer.rebalance_week(date(2026, 3, 8))

        assert 'moves_made' in result
        assert 'time_slot_moves' in result
        assert 'employee_swaps' in result
        assert 'skipped_reasons' in result
        assert 'details' in result

    def test_only_core_events_are_moved(self, app, db_session, models):
        """Non-Core events should never be touched by the rebalancer."""
        from app.services.schedule_rebalancer import ScheduleRebalancer

        emp1 = _create_employee(db_session, models, 'E1', 'Alice')

        # Create a Juicer event at slot 1
        juicer_evt = _create_event(db_session, models, 5001, event_type='Juicer')
        _create_schedule(db_session, models, juicer_evt, emp1, datetime(2026, 3, 9, *SLOT_1))

        # Create 3 Core events at same slot to trigger imbalance
        for i in range(3):
            evt = _create_event(db_session, models, 5010 + i)
            emp = _create_employee(db_session, models, f'E{10+i}', f'Emp{10+i}')
            _create_schedule(db_session, models, evt, emp, datetime(2026, 3, 9, *SLOT_1))

        db_session.commit()

        rebalancer = ScheduleRebalancer(db_session, models)
        result = rebalancer.rebalance_week(date(2026, 3, 8))

        # Juicer event should still be at original time with original employee
        Schedule = models['Schedule']
        juicer_sched = db_session.query(Schedule).filter(
            Schedule.event_ref_num == 5001
        ).first()
        assert juicer_sched.employee_id == 'E1'
        assert juicer_sched.schedule_datetime.hour == SLOT_1[0]


class TestRebalanceAPI:
    """Test the /api/rebalance-week endpoint."""

    def test_rebalance_endpoint_returns_200(self, client, app, db_session, models):
        """POST /api/rebalance-week returns 200 with result summary."""
        response = client.post('/api/rebalance-week', json={
            'week_start': '2026-03-08'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'success'
        assert 'moves_made' in data['data']
        assert 'time_slot_moves' in data['data']
        assert 'employee_swaps' in data['data']

    def test_rebalance_endpoint_missing_date(self, client, app):
        """POST /api/rebalance-week without week_start returns 400."""
        response = client.post('/api/rebalance-week', json={})
        assert response.status_code == 400

    def test_rebalance_endpoint_invalid_date(self, client, app):
        """POST /api/rebalance-week with invalid date returns 400."""
        response = client.post('/api/rebalance-week', json={
            'week_start': 'not-a-date'
        })
        assert response.status_code == 400
