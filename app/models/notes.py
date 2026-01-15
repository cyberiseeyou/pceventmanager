"""
Notes and Tasks model for tracking reminders, employee notes, and follow-ups
Supports both general tasks and notes linked to employees or events
"""
from datetime import datetime


def create_notes_models(db):
    """Factory function to create Note and Task models with db instance"""

    class Note(db.Model):
        """
        Note model for tracking various types of notes and tasks

        Note Types:
        - employee: Notes attached to specific employees (vacation, schedule preferences)
        - event: Notes attached to specific events (special instructions)
        - task: General to-do items
        - followup: Follow-up reminders
        - management: Management requests

        Attributes:
            id: Unique identifier
            note_type: Type of note (employee, event, task, followup, management)
            title: Short summary/title
            content: Full note content
            due_date: Optional due date for tasks/reminders
            due_time: Optional time component for due date
            is_completed: Whether task is completed
            priority: Priority level (low, normal, high, urgent)
            linked_employee_id: Optional link to employee
            linked_event_ref_num: Optional link to event
            created_at: When note was created
            completed_at: When note was marked complete
            reminder_sent: Whether browser notification was sent
        """
        __tablename__ = 'notes'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        note_type = db.Column(db.String(20), nullable=False, default='task')
        title = db.Column(db.String(200), nullable=False)
        content = db.Column(db.Text, nullable=True)
        due_date = db.Column(db.Date, nullable=True)
        due_time = db.Column(db.Time, nullable=True)
        is_completed = db.Column(db.Boolean, nullable=False, default=False)
        priority = db.Column(db.String(20), nullable=False, default='normal')

        # Optional links to other entities
        linked_employee_id = db.Column(db.String(50), nullable=True)
        linked_event_ref_num = db.Column(db.Integer, nullable=True)

        # Timestamps
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
        completed_at = db.Column(db.DateTime, nullable=True)

        # Notification tracking
        reminder_sent = db.Column(db.Boolean, nullable=False, default=False)

        __table_args__ = (
            # Index for querying by type
            db.Index('idx_notes_type', 'note_type'),

            # Index for incomplete tasks
            db.Index('idx_notes_incomplete', 'is_completed'),

            # Index for due date queries
            db.Index('idx_notes_due_date', 'due_date'),

            # Index for employee-linked notes
            db.Index('idx_notes_employee', 'linked_employee_id'),

            # Index for event-linked notes
            db.Index('idx_notes_event', 'linked_event_ref_num'),

            # Composite index for common query: incomplete tasks due soon
            db.Index('idx_notes_pending_tasks', 'is_completed', 'due_date'),
        )

        # Valid note types
        VALID_TYPES = ['employee', 'event', 'task', 'followup', 'management']
        VALID_PRIORITIES = ['low', 'normal', 'high', 'urgent']

        @property
        def is_overdue(self):
            """Check if note is overdue"""
            if not self.due_date or self.is_completed:
                return False
            today = datetime.now().date()
            return self.due_date < today

        @property
        def is_due_today(self):
            """Check if note is due today"""
            if not self.due_date or self.is_completed:
                return False
            today = datetime.now().date()
            return self.due_date == today

        @property
        def display_type(self):
            """Get display-friendly type name"""
            type_names = {
                'employee': 'Employee Note',
                'event': 'Event Note',
                'task': 'Task',
                'followup': 'Follow-up',
                'management': 'Management Request'
            }
            return type_names.get(self.note_type, 'Note')

        @property
        def type_icon(self):
            """Get icon for note type"""
            icons = {
                'employee': 'fa-user',
                'event': 'fa-calendar',
                'task': 'fa-check-square',
                'followup': 'fa-bell',
                'management': 'fa-briefcase'
            }
            return icons.get(self.note_type, 'fa-sticky-note')

        @property
        def priority_color(self):
            """Get color for priority level"""
            colors = {
                'low': '#6b7280',      # gray
                'normal': '#0071ce',   # blue
                'high': '#f59e0b',     # yellow/orange
                'urgent': '#dc2626'    # red
            }
            return colors.get(self.priority, '#0071ce')

        def mark_complete(self):
            """Mark note as completed"""
            self.is_completed = True
            self.completed_at = datetime.utcnow()

        def mark_incomplete(self):
            """Mark note as incomplete"""
            self.is_completed = False
            self.completed_at = None

        def to_dict(self):
            """Convert note to dictionary for JSON serialization"""
            return {
                'id': self.id,
                'note_type': self.note_type,
                'display_type': self.display_type,
                'type_icon': self.type_icon,
                'title': self.title,
                'content': self.content,
                'due_date': self.due_date.isoformat() if self.due_date else None,
                'due_time': self.due_time.strftime('%H:%M') if self.due_time else None,
                'is_completed': self.is_completed,
                'is_overdue': self.is_overdue,
                'is_due_today': self.is_due_today,
                'priority': self.priority,
                'priority_color': self.priority_color,
                'linked_employee_id': self.linked_employee_id,
                'linked_event_ref_num': self.linked_event_ref_num,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'completed_at': self.completed_at.isoformat() if self.completed_at else None,
                'reminder_sent': self.reminder_sent
            }

        def __repr__(self):
            return f'<Note {self.id}: {self.title[:30]}...>'

    class RecurringReminder(db.Model):
        """
        Recurring reminder configuration for scheduled tasks

        Used for things like:
        - Weekly inventory count reminders
        - Daily check-in prompts
        - End-of-week reports

        Attributes:
            id: Unique identifier
            title: Reminder title
            description: Optional description
            frequency: daily, weekly, monthly
            day_of_week: For weekly (0=Monday, 6=Sunday)
            day_of_month: For monthly (1-31)
            time_of_day: When to show reminder
            is_active: Whether reminder is active
            last_triggered: When reminder last created a note
        """
        __tablename__ = 'recurring_reminders'

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        title = db.Column(db.String(200), nullable=False)
        description = db.Column(db.Text, nullable=True)
        frequency = db.Column(db.String(20), nullable=False)  # daily, weekly, monthly
        day_of_week = db.Column(db.Integer, nullable=True)  # 0-6 for weekly
        day_of_month = db.Column(db.Integer, nullable=True)  # 1-31 for monthly
        time_of_day = db.Column(db.Time, nullable=True)
        is_active = db.Column(db.Boolean, nullable=False, default=True)
        last_triggered = db.Column(db.DateTime, nullable=True)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

        # Valid frequencies
        VALID_FREQUENCIES = ['daily', 'weekly', 'monthly']

        def should_trigger(self, current_datetime=None):
            """Check if reminder should trigger based on current time"""
            if not self.is_active:
                return False

            now = current_datetime or datetime.now()
            today = now.date()

            # Check if already triggered today
            if self.last_triggered and self.last_triggered.date() == today:
                return False

            if self.frequency == 'daily':
                return True

            elif self.frequency == 'weekly':
                # Check if today is the configured day
                return now.weekday() == self.day_of_week

            elif self.frequency == 'monthly':
                # Check if today is the configured day of month
                return now.day == self.day_of_month

            return False

        def to_dict(self):
            """Convert to dictionary for JSON"""
            return {
                'id': self.id,
                'title': self.title,
                'description': self.description,
                'frequency': self.frequency,
                'day_of_week': self.day_of_week,
                'day_of_month': self.day_of_month,
                'time_of_day': self.time_of_day.strftime('%H:%M') if self.time_of_day else None,
                'is_active': self.is_active,
                'last_triggered': self.last_triggered.isoformat() if self.last_triggered else None,
                'created_at': self.created_at.isoformat() if self.created_at else None
            }

        def __repr__(self):
            return f'<RecurringReminder {self.id}: {self.title}>'

    return Note, RecurringReminder
