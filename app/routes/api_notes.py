"""
Notes and Tasks API Routes
Manages notes, tasks, reminders, and recurring reminders
"""
from flask import Blueprint, request, jsonify, current_app
from app.models import get_models
from datetime import datetime, date, time, timedelta
from app.routes.auth import require_authentication

api_notes_bp = Blueprint('api_notes', __name__, url_prefix='/api/notes')


@api_notes_bp.route('/', methods=['GET'])
@require_authentication()
def get_notes():
    """
    Get notes with optional filtering

    Query Parameters:
    - type: Filter by note_type (employee, event, task, followup, management)
    - completed: Filter by completion status (true/false)
    - employee_id: Get notes linked to specific employee
    - event_ref_num: Get notes linked to specific event
    - due_today: Get notes due today (true/false)
    - overdue: Get overdue notes (true/false)
    - limit: Maximum number of notes to return
    """
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Note = models['Note']

    try:
        query = db.session.query(Note)

        # Apply filters
        note_type = request.args.get('type')
        if note_type and note_type in Note.VALID_TYPES:
            query = query.filter(Note.note_type == note_type)

        completed = request.args.get('completed')
        if completed is not None:
            is_completed = completed.lower() == 'true'
            query = query.filter(Note.is_completed == is_completed)

        employee_id = request.args.get('employee_id')
        if employee_id:
            query = query.filter(Note.linked_employee_id == employee_id)

        event_ref_num = request.args.get('event_ref_num', type=int)
        if event_ref_num:
            query = query.filter(Note.linked_event_ref_num == event_ref_num)

        if request.args.get('due_today', '').lower() == 'true':
            today = date.today()
            query = query.filter(Note.due_date == today, Note.is_completed == False)

        if request.args.get('overdue', '').lower() == 'true':
            today = date.today()
            query = query.filter(Note.due_date < today, Note.is_completed == False)

        # Order by due date (nulls last), then priority, then created_at
        query = query.order_by(
            Note.is_completed,
            Note.due_date.asc().nullslast(),
            db.case(
                (Note.priority == 'urgent', 0),
                (Note.priority == 'high', 1),
                (Note.priority == 'normal', 2),
                (Note.priority == 'low', 3),
                else_=4
            ),
            Note.created_at.desc()
        )

        limit = request.args.get('limit', type=int)
        if limit:
            query = query.limit(limit)

        notes = query.all()

        return jsonify({
            'success': True,
            'notes': [n.to_dict() for n in notes],
            'count': len(notes)
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching notes: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_notes_bp.route('/', methods=['POST'])
@require_authentication()
def create_note():
    """Create a new note or task"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Note = models['Note']

    try:
        data = request.get_json()

        if not data.get('title'):
            return jsonify({'success': False, 'error': 'Title is required'}), 400

        note_type = data.get('note_type', 'task')
        if note_type not in Note.VALID_TYPES:
            return jsonify({
                'success': False,
                'error': f"Invalid note type. Must be one of: {', '.join(Note.VALID_TYPES)}"
            }), 400

        priority = data.get('priority', 'normal')
        if priority not in Note.VALID_PRIORITIES:
            return jsonify({
                'success': False,
                'error': f"Invalid priority. Must be one of: {', '.join(Note.VALID_PRIORITIES)}"
            }), 400

        # Parse due date if provided
        due_date = None
        if data.get('due_date'):
            try:
                due_date = datetime.strptime(data['due_date'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        # Parse due time if provided
        due_time = None
        if data.get('due_time'):
            try:
                due_time = datetime.strptime(data['due_time'], '%H:%M').time()
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid time format. Use HH:MM'}), 400

        note = Note(
            note_type=note_type,
            title=data['title'],
            content=data.get('content'),
            due_date=due_date,
            due_time=due_time,
            priority=priority,
            linked_employee_id=data.get('linked_employee_id'),
            linked_event_ref_num=data.get('linked_event_ref_num')
        )

        db.session.add(note)
        db.session.commit()

        current_app.logger.info(f"Created note: {note.title}")

        return jsonify({
            'success': True,
            'note': note.to_dict(),
            'message': 'Note created successfully'
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating note: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_notes_bp.route('/<int:note_id>', methods=['GET'])
@require_authentication()
def get_note(note_id):
    """Get a specific note"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Note = models['Note']

    try:
        note = db.session.query(Note).get(note_id)

        if not note:
            return jsonify({'success': False, 'error': 'Note not found'}), 404

        return jsonify({
            'success': True,
            'note': note.to_dict()
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching note: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_notes_bp.route('/<int:note_id>', methods=['PUT'])
@require_authentication()
def update_note(note_id):
    """Update a note"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Note = models['Note']

    try:
        note = db.session.query(Note).get(note_id)

        if not note:
            return jsonify({'success': False, 'error': 'Note not found'}), 404

        data = request.get_json()

        if 'title' in data:
            note.title = data['title']

        if 'content' in data:
            note.content = data['content']

        if 'note_type' in data:
            if data['note_type'] in Note.VALID_TYPES:
                note.note_type = data['note_type']

        if 'priority' in data:
            if data['priority'] in Note.VALID_PRIORITIES:
                note.priority = data['priority']

        if 'due_date' in data:
            if data['due_date']:
                try:
                    note.due_date = datetime.strptime(data['due_date'], '%Y-%m-%d').date()
                except ValueError:
                    return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
            else:
                note.due_date = None

        if 'due_time' in data:
            if data['due_time']:
                try:
                    note.due_time = datetime.strptime(data['due_time'], '%H:%M').time()
                except ValueError:
                    return jsonify({'success': False, 'error': 'Invalid time format. Use HH:MM'}), 400
            else:
                note.due_time = None

        if 'linked_employee_id' in data:
            note.linked_employee_id = data['linked_employee_id']

        if 'linked_event_ref_num' in data:
            note.linked_event_ref_num = data['linked_event_ref_num']

        db.session.commit()

        current_app.logger.info(f"Updated note: {note.title}")

        return jsonify({
            'success': True,
            'note': note.to_dict(),
            'message': 'Note updated successfully'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating note: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_notes_bp.route('/<int:note_id>', methods=['DELETE'])
@require_authentication()
def delete_note(note_id):
    """Delete a note"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Note = models['Note']

    try:
        note = db.session.query(Note).get(note_id)

        if not note:
            return jsonify({'success': False, 'error': 'Note not found'}), 404

        title = note.title
        db.session.delete(note)
        db.session.commit()

        current_app.logger.info(f"Deleted note: {title}")

        return jsonify({
            'success': True,
            'message': f"Note '{title}' deleted successfully"
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting note: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_notes_bp.route('/<int:note_id>/complete', methods=['POST'])
@require_authentication()
def complete_note(note_id):
    """Mark a note as complete"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Note = models['Note']

    try:
        note = db.session.query(Note).get(note_id)

        if not note:
            return jsonify({'success': False, 'error': 'Note not found'}), 404

        note.mark_complete()
        db.session.commit()

        current_app.logger.info(f"Completed note: {note.title}")

        return jsonify({
            'success': True,
            'note': note.to_dict(),
            'message': 'Note marked as complete'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error completing note: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_notes_bp.route('/<int:note_id>/reopen', methods=['POST'])
@require_authentication()
def reopen_note(note_id):
    """Mark a note as incomplete"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Note = models['Note']

    try:
        note = db.session.query(Note).get(note_id)

        if not note:
            return jsonify({'success': False, 'error': 'Note not found'}), 404

        note.mark_incomplete()
        db.session.commit()

        current_app.logger.info(f"Reopened note: {note.title}")

        return jsonify({
            'success': True,
            'note': note.to_dict(),
            'message': 'Note reopened'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error reopening note: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_notes_bp.route('/summary', methods=['GET'])
@require_authentication()
def get_notes_summary():
    """Get summary counts of notes by status and type"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Note = models['Note']

    try:
        today = date.today()

        # Get counts
        total = db.session.query(Note).count()
        completed = db.session.query(Note).filter(Note.is_completed == True).count()
        pending = db.session.query(Note).filter(Note.is_completed == False).count()
        due_today = db.session.query(Note).filter(
            Note.due_date == today,
            Note.is_completed == False
        ).count()
        overdue = db.session.query(Note).filter(
            Note.due_date < today,
            Note.is_completed == False
        ).count()

        # Counts by type
        type_counts = {}
        for note_type in Note.VALID_TYPES:
            type_counts[note_type] = db.session.query(Note).filter(
                Note.note_type == note_type,
                Note.is_completed == False
            ).count()

        return jsonify({
            'success': True,
            'summary': {
                'total': total,
                'completed': completed,
                'pending': pending,
                'due_today': due_today,
                'overdue': overdue,
                'by_type': type_counts
            }
        })

    except Exception as e:
        current_app.logger.error(f"Error getting notes summary: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_notes_bp.route('/employee/<employee_id>', methods=['GET'])
@require_authentication()
def get_employee_notes(employee_id):
    """Get all active notes for a specific employee"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Note = models['Note']

    try:
        notes = db.session.query(Note).filter(
            Note.linked_employee_id == employee_id,
            Note.note_type == 'employee'
        ).order_by(
            Note.is_completed,
            Note.due_date.asc().nullslast(),
            Note.created_at.desc()
        ).all()

        return jsonify({
            'success': True,
            'notes': [n.to_dict() for n in notes],
            'employee_id': employee_id
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching employee notes: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_notes_bp.route('/event/<int:event_ref_num>', methods=['GET'])
@require_authentication()
def get_event_notes(event_ref_num):
    """Get all notes for a specific event"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Note = models['Note']

    try:
        notes = db.session.query(Note).filter(
            Note.linked_event_ref_num == event_ref_num,
            Note.note_type == 'event'
        ).order_by(Note.created_at.desc()).all()

        return jsonify({
            'success': True,
            'notes': [n.to_dict() for n in notes],
            'event_ref_num': event_ref_num
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching event notes: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_notes_bp.route('/notifications/pending', methods=['GET'])
@require_authentication()
def get_pending_notifications():
    """Get notes that need browser notifications (due soon, not sent)"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Note = models['Note']

    try:
        now = datetime.now()
        today = now.date()
        current_time = now.time()

        # Get notes due today that haven't had notifications sent
        pending_notes = db.session.query(Note).filter(
            Note.due_date <= today,
            Note.is_completed == False,
            Note.reminder_sent == False
        ).all()

        # Filter to only include notes that are due now or past due
        notifications = []
        for note in pending_notes:
            should_notify = False

            if note.due_date < today:
                # Overdue - always notify
                should_notify = True
            elif note.due_date == today:
                if note.due_time:
                    # Has specific time - notify if past that time
                    should_notify = current_time >= note.due_time
                else:
                    # No specific time - notify in morning
                    should_notify = True

            if should_notify:
                notifications.append(note.to_dict())

        return jsonify({
            'success': True,
            'notifications': notifications,
            'count': len(notifications)
        })

    except Exception as e:
        current_app.logger.error(f"Error getting pending notifications: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_notes_bp.route('/<int:note_id>/notification-sent', methods=['POST'])
@require_authentication()
def mark_notification_sent(note_id):
    """Mark that notification was sent for a note"""
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Note = models['Note']

    try:
        note = db.session.query(Note).get(note_id)

        if not note:
            return jsonify({'success': False, 'error': 'Note not found'}), 404

        note.reminder_sent = True
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Notification marked as sent'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error marking notification: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# Recurring Reminders Routes

@api_notes_bp.route('/reminders', methods=['GET'])
@require_authentication()
def get_recurring_reminders():
    """Get all recurring reminders"""
    db = current_app.extensions['sqlalchemy']
    RecurringReminder = current_app.config['RecurringReminder']

    try:
        reminders = db.session.query(RecurringReminder).order_by(
            RecurringReminder.is_active.desc(),
            RecurringReminder.title
        ).all()

        return jsonify({
            'success': True,
            'reminders': [r.to_dict() for r in reminders]
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching reminders: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_notes_bp.route('/reminders', methods=['POST'])
@require_authentication()
def create_recurring_reminder():
    """Create a recurring reminder"""
    db = current_app.extensions['sqlalchemy']
    RecurringReminder = current_app.config['RecurringReminder']

    try:
        data = request.get_json()

        if not data.get('title'):
            return jsonify({'success': False, 'error': 'Title is required'}), 400

        frequency = data.get('frequency', 'weekly')
        if frequency not in RecurringReminder.VALID_FREQUENCIES:
            return jsonify({
                'success': False,
                'error': f"Invalid frequency. Must be one of: {', '.join(RecurringReminder.VALID_FREQUENCIES)}"
            }), 400

        # Parse time if provided
        time_of_day = None
        if data.get('time_of_day'):
            try:
                time_of_day = datetime.strptime(data['time_of_day'], '%H:%M').time()
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid time format. Use HH:MM'}), 400

        reminder = RecurringReminder(
            title=data['title'],
            description=data.get('description'),
            frequency=frequency,
            day_of_week=data.get('day_of_week'),
            day_of_month=data.get('day_of_month'),
            time_of_day=time_of_day,
            is_active=data.get('is_active', True)
        )

        db.session.add(reminder)
        db.session.commit()

        current_app.logger.info(f"Created recurring reminder: {reminder.title}")

        return jsonify({
            'success': True,
            'reminder': reminder.to_dict(),
            'message': 'Recurring reminder created successfully'
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating reminder: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_notes_bp.route('/reminders/<int:reminder_id>', methods=['PUT'])
@require_authentication()
def update_recurring_reminder(reminder_id):
    """Update a recurring reminder"""
    db = current_app.extensions['sqlalchemy']
    RecurringReminder = current_app.config['RecurringReminder']

    try:
        reminder = db.session.query(RecurringReminder).get(reminder_id)

        if not reminder:
            return jsonify({'success': False, 'error': 'Reminder not found'}), 404

        data = request.get_json()

        if 'title' in data:
            reminder.title = data['title']

        if 'description' in data:
            reminder.description = data['description']

        if 'frequency' in data:
            if data['frequency'] in RecurringReminder.VALID_FREQUENCIES:
                reminder.frequency = data['frequency']

        if 'day_of_week' in data:
            reminder.day_of_week = data['day_of_week']

        if 'day_of_month' in data:
            reminder.day_of_month = data['day_of_month']

        if 'time_of_day' in data:
            if data['time_of_day']:
                try:
                    reminder.time_of_day = datetime.strptime(data['time_of_day'], '%H:%M').time()
                except ValueError:
                    return jsonify({'success': False, 'error': 'Invalid time format. Use HH:MM'}), 400
            else:
                reminder.time_of_day = None

        if 'is_active' in data:
            reminder.is_active = data['is_active']

        db.session.commit()

        return jsonify({
            'success': True,
            'reminder': reminder.to_dict(),
            'message': 'Reminder updated successfully'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating reminder: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_notes_bp.route('/reminders/<int:reminder_id>', methods=['DELETE'])
@require_authentication()
def delete_recurring_reminder(reminder_id):
    """Delete a recurring reminder"""
    db = current_app.extensions['sqlalchemy']
    RecurringReminder = current_app.config['RecurringReminder']

    try:
        reminder = db.session.query(RecurringReminder).get(reminder_id)

        if not reminder:
            return jsonify({'success': False, 'error': 'Reminder not found'}), 404

        title = reminder.title
        db.session.delete(reminder)
        db.session.commit()

        current_app.logger.info(f"Deleted reminder: {title}")

        return jsonify({
            'success': True,
            'message': f"Reminder '{title}' deleted successfully"
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting reminder: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_notes_bp.route('/reminders/trigger', methods=['POST'])
@require_authentication()
def trigger_due_reminders():
    """
    Check and trigger any due recurring reminders.
    Creates Note entries for reminders that should trigger.
    """
    db = current_app.extensions['sqlalchemy']
    models = get_models()
    Note = models['Note']
    RecurringReminder = current_app.config['RecurringReminder']

    try:
        now = datetime.now()
        triggered = []

        reminders = db.session.query(RecurringReminder).filter(
            RecurringReminder.is_active == True
        ).all()

        for reminder in reminders:
            if reminder.should_trigger(now):
                # Create a task note from this reminder
                note = Note(
                    note_type='task',
                    title=reminder.title,
                    content=reminder.description,
                    due_date=now.date(),
                    due_time=reminder.time_of_day,
                    priority='normal'
                )
                db.session.add(note)

                # Update last triggered
                reminder.last_triggered = now
                triggered.append(reminder.title)

        db.session.commit()

        return jsonify({
            'success': True,
            'triggered': triggered,
            'count': len(triggered)
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error triggering reminders: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
