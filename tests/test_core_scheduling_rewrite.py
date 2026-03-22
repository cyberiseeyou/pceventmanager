import pytest
from datetime import datetime, date, time, timedelta


class TestScheduleNotificationModel:
    """Test the ScheduleNotification model CRUD operations."""

    def test_create_schedule_notification(self, db_session, models):
        """ScheduleNotification can be created with required fields."""
        ScheduleNotification = models['ScheduleNotification']
        Employee = models['Employee']
        Event = models['Event']
        SchedulerRunHistory = models['SchedulerRunHistory']

        emp = Employee(id="emp1", name="Test Employee", job_title="Event Specialist")
        db_session.add(emp)

        today = datetime.now()
        event = Event(
            project_ref_num=99999,
            project_name="Test Core Event",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=today,
            due_datetime=today + timedelta(days=14),
            estimated_time=60,
        )
        db_session.add(event)

        run = SchedulerRunHistory(
            run_type='manual',
            started_at=datetime.utcnow(),
            status='running',
            solver_type='greedy',
        )
        db_session.add(run)
        db_session.flush()

        notification = ScheduleNotification(
            scheduler_run_id=run.id,
            event_ref_num=99999,
            employee_id="emp1",
            schedule_date=today.date() + timedelta(days=5),
            schedule_time=time(10, 15),
            days_notice=5,
        )
        db_session.add(notification)
        db_session.commit()

        saved = db_session.query(ScheduleNotification).first()
        assert saved is not None
        assert saved.event_ref_num == 99999
        assert saved.employee_id == "emp1"
        assert saved.days_notice == 5
        assert saved.notified is False
        assert saved.notified_at is None

    def test_mark_notification_as_notified(self, db_session, models):
        """Notification can be marked as acknowledged by supervisor."""
        ScheduleNotification = models['ScheduleNotification']
        Employee = models['Employee']
        Event = models['Event']
        SchedulerRunHistory = models['SchedulerRunHistory']

        emp = Employee(id="emp2", name="Test Employee 2", job_title="Lead Event Specialist")
        db_session.add(emp)

        today = datetime.now()
        event = Event(
            project_ref_num=99998,
            project_name="Test Core Event 2",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=today,
            due_datetime=today + timedelta(days=14),
            estimated_time=60,
        )
        db_session.add(event)

        run = SchedulerRunHistory(
            run_type='manual',
            started_at=datetime.utcnow(),
            status='running',
            solver_type='greedy',
        )
        db_session.add(run)
        db_session.flush()

        notification = ScheduleNotification(
            scheduler_run_id=run.id,
            event_ref_num=99998,
            employee_id="emp2",
            schedule_date=today.date() + timedelta(days=4),
            schedule_time=time(10, 15),
            days_notice=4,
        )
        db_session.add(notification)
        db_session.commit()

        notification.notified = True
        notification.notified_at = datetime.utcnow()
        notification.notified_by = "supervisor"
        db_session.commit()

        saved = db_session.query(ScheduleNotification).first()
        assert saved.notified is True
        assert saved.notified_at is not None
        assert saved.notified_by == "supervisor"


class TestCoreSchedulingWave2:
    """Test the rewritten Wave 2 Core scheduling logic."""

    def _setup_basic(self, db_session, models):
        """Helper: create a Lead, a Specialist, and an engine."""
        Employee = models['Employee']
        RotationAssignment = models['RotationAssignment']

        lead = Employee(
            id="lead1", name="Lead One",
            job_title="Lead Event Specialist", is_active=True
        )
        specialist = Employee(
            id="spec1", name="Specialist One",
            job_title="Event Specialist", is_active=True
        )
        db_session.add_all([lead, specialist])
        db_session.flush()

        # Make lead the primary lead for all weekdays
        for day in range(5):
            ra = RotationAssignment(
                day_of_week=day,
                rotation_type='primary_lead',
                employee_id="lead1",
            )
            db_session.add(ra)
        db_session.flush()

        from app.services.scheduling_engine import SchedulingEngine
        engine = SchedulingEngine(db_session, models)
        return engine, lead, specialist

    def test_empty_slot_tried_before_bump(self, db_session, models):
        """When an unscheduled employee exists, should fill empty slot, never bump."""
        engine, lead, specialist = self._setup_basic(db_session, models)
        Event = models['Event']
        SchedulerRunHistory = models['SchedulerRunHistory']
        PendingSchedule = models['PendingSchedule']

        today = datetime.now()
        start = today + timedelta(days=5)
        event = Event(
            project_ref_num=10001,
            project_name="Test Core",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=start,
            due_datetime=start + timedelta(days=9),
            estimated_time=60,
        )
        db_session.add(event)
        db_session.flush()

        run = SchedulerRunHistory(
            run_type='manual', started_at=datetime.utcnow(),
            status='running', solver_type='greedy',
        )
        db_session.add(run)
        db_session.flush()
        engine.validator.set_current_run(run.id)

        failed = engine._schedule_core_events_wave2_new(run, [event])
        assert len(failed) == 0
        assert event.is_scheduled is True

        pending = db_session.query(PendingSchedule).filter(
            PendingSchedule.scheduler_run_id == run.id,
            PendingSchedule.event_ref_num == 10001,
            PendingSchedule.failure_reason.is_(None),
        ).first()
        assert pending is not None
        assert pending.is_swap is False  # Filled empty slot, not a bump

    def test_3day_buffer_respected(self, db_session, models):
        """Events within 3 days should NOT be scheduled unless emergency mode."""
        engine, lead, specialist = self._setup_basic(db_session, models)
        Event = models['Event']
        SchedulerRunHistory = models['SchedulerRunHistory']

        today = datetime.now()
        event = Event(
            project_ref_num=10002,
            project_name="Urgent Core",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=today + timedelta(days=1),
            due_datetime=today + timedelta(days=3),
            estimated_time=60,
        )
        db_session.add(event)
        db_session.flush()

        run = SchedulerRunHistory(
            run_type='manual', started_at=datetime.utcnow(),
            status='running', solver_type='greedy',
        )
        db_session.add(run)
        db_session.flush()
        engine.validator.set_current_run(run.id)

        engine.emergency_mode = False
        failed = engine._schedule_core_events_wave2_new(run, [event])
        assert len(failed) == 1

    def test_3day_buffer_bypassed_in_emergency(self, db_session, models):
        """In emergency mode, 3-day buffer is ignored."""
        engine, lead, specialist = self._setup_basic(db_session, models)
        Event = models['Event']
        SchedulerRunHistory = models['SchedulerRunHistory']

        today = datetime.now()
        event = Event(
            project_ref_num=10003,
            project_name="Emergency Core",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=today + timedelta(days=1),
            due_datetime=today + timedelta(days=3),
            estimated_time=60,
        )
        db_session.add(event)
        db_session.flush()

        run = SchedulerRunHistory(
            run_type='manual', started_at=datetime.utcnow(),
            status='running', solver_type='greedy',
        )
        db_session.add(run)
        db_session.flush()
        engine.validator.set_current_run(run.id)

        engine.emergency_mode = True
        failed = engine._schedule_core_events_wave2_new(run, [event])
        assert len(failed) == 0

    def test_7day_notification_created(self, db_session, models):
        """Scheduling within 7 days should create a ScheduleNotification."""
        engine, lead, specialist = self._setup_basic(db_session, models)
        Event = models['Event']
        SchedulerRunHistory = models['SchedulerRunHistory']
        ScheduleNotification = models['ScheduleNotification']

        today = datetime.now()
        start = today + timedelta(days=4)
        event = Event(
            project_ref_num=10004,
            project_name="Short Notice Core",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=start,
            due_datetime=start + timedelta(days=3),
            estimated_time=60,
        )
        db_session.add(event)
        db_session.flush()

        run = SchedulerRunHistory(
            run_type='manual', started_at=datetime.utcnow(),
            status='running', solver_type='greedy',
        )
        db_session.add(run)
        db_session.flush()
        engine.validator.set_current_run(run.id)

        failed = engine._schedule_core_events_wave2_new(run, [event])
        assert len(failed) == 0

        notif = db_session.query(ScheduleNotification).filter(
            ScheduleNotification.event_ref_num == 10004,
        ).first()
        assert notif is not None
        assert notif.days_notice <= 7
        assert notif.notified is False

    def test_search_starts_from_event_start_not_tomorrow(self, db_session, models):
        """Search should start from event start date, not always tomorrow."""
        engine, lead, specialist = self._setup_basic(db_session, models)
        Event = models['Event']
        SchedulerRunHistory = models['SchedulerRunHistory']
        PendingSchedule = models['PendingSchedule']

        today = datetime.now()
        start = today + timedelta(days=10)
        event = Event(
            project_ref_num=10030,
            project_name="Future Core",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=start,
            due_datetime=start + timedelta(days=5),
            estimated_time=60,
        )
        db_session.add(event)
        db_session.flush()

        run = SchedulerRunHistory(
            run_type='manual', started_at=datetime.utcnow(),
            status='running', solver_type='greedy',
        )
        db_session.add(run)
        db_session.flush()
        engine.validator.set_current_run(run.id)

        failed = engine._schedule_core_events_wave2_new(run, [event])
        assert len(failed) == 0

        pending = db_session.query(PendingSchedule).filter(
            PendingSchedule.scheduler_run_id == run.id,
            PendingSchedule.event_ref_num == 10030,
            PendingSchedule.failure_reason.is_(None),
        ).first()
        assert pending is not None
        assert pending.schedule_datetime.date() >= start.date()

    def test_primary_lead_gets_first_time_slot(self, db_session, models):
        """Primary lead for the day should be assigned the first Core time slot (10:15)."""
        engine, lead, specialist = self._setup_basic(db_session, models)
        Event = models['Event']
        SchedulerRunHistory = models['SchedulerRunHistory']
        PendingSchedule = models['PendingSchedule']

        today = datetime.now()
        start = today + timedelta(days=5)
        event = Event(
            project_ref_num=10040,
            project_name="Primary Lead Core",
            event_type="Core",
            condition="Unstaffed",
            start_datetime=start,
            due_datetime=start + timedelta(days=9),
            estimated_time=60,
        )
        db_session.add(event)
        db_session.flush()

        run = SchedulerRunHistory(
            run_type='manual', started_at=datetime.utcnow(),
            status='running', solver_type='greedy',
        )
        db_session.add(run)
        db_session.flush()
        engine.validator.set_current_run(run.id)

        failed = engine._schedule_core_events_wave2_new(run, [event])
        assert len(failed) == 0

        pending = db_session.query(PendingSchedule).filter(
            PendingSchedule.scheduler_run_id == run.id,
            PendingSchedule.event_ref_num == 10040,
            PendingSchedule.failure_reason.is_(None),
        ).first()
        assert pending is not None
        # lead1 is the primary lead for all weekdays (set up in _setup_basic)
        assert pending.employee_id == "lead1"
        assert pending.schedule_time == time(10, 15)
