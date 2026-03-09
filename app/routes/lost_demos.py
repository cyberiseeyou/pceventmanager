"""
Lost Demos Blueprint
API endpoints for confirming, undoing, and listing lost demos.
Also serves the weekly lost demos list page.
"""
from flask import Blueprint, jsonify, request, render_template, make_response
from datetime import datetime, date, timedelta
from app.models import get_models, get_db
import csv
import io

lost_demos_bp = Blueprint('lost_demos', __name__)


def _sunday_of(d):
    """Return the Sunday starting the week containing date d."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


@lost_demos_bp.route('/api/lost-demos/<int:ref_num>/confirm', methods=['POST'])
def confirm_lost(ref_num):
    """Confirm an event as a lost demo."""
    models = get_models()
    db = get_db()
    Event = models['Event']
    LostDemo = models['LostDemo']

    event = Event.query.filter_by(project_ref_num=ref_num).first()
    if not event:
        return jsonify({'status': 'error', 'error': 'Event not found'}), 404

    existing = LostDemo.query.filter_by(event_ref_num=ref_num).first()
    if existing:
        return jsonify({'status': 'error', 'error': 'Already confirmed as lost'}), 409

    data = request.get_json(silent=True) or {}
    week_start = _sunday_of(event.due_datetime.date())

    record = LostDemo(
        event_ref_num=ref_num,
        week_start_date=week_start,
        confirmed_at=datetime.utcnow(),
        notes=data.get('notes', ''),
    )
    db.session.add(record)
    db.session.commit()

    return jsonify({'status': 'success', 'data': {
        'event_ref_num': ref_num,
        'week_start_date': week_start.isoformat(),
    }})


@lost_demos_bp.route('/api/lost-demos/<int:ref_num>/confirm', methods=['DELETE'])
def undo_lost(ref_num):
    """Undo a lost demo confirmation."""
    models = get_models()
    db = get_db()
    LostDemo = models['LostDemo']

    record = LostDemo.query.filter_by(event_ref_num=ref_num).first()
    if not record:
        return jsonify({'status': 'error', 'error': 'Not found'}), 404

    db.session.delete(record)
    db.session.commit()
    return jsonify({'status': 'success'})


@lost_demos_bp.route('/api/lost-demos')
def list_lost_demos():
    """List lost demos for a given week."""
    models = get_models()
    Event = models['Event']
    LostDemo = models['LostDemo']

    week_str = request.args.get('week_start')
    if week_str:
        try:
            week_start = datetime.strptime(week_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'status': 'error', 'error': 'Invalid date format'}), 400
    else:
        today = date.today()
        week_start = _sunday_of(today)

    week_end = week_start + timedelta(days=6)

    records = LostDemo.query.filter(
        LostDemo.week_start_date >= week_start,
        LostDemo.week_start_date <= week_end,
    ).all()

    results = []
    for rec in records:
        event = Event.query.filter_by(project_ref_num=rec.event_ref_num).first()
        walmart_id = ''
        if event and event.walmart_event_id:
            walmart_id = event.walmart_event_id
        results.append({
            'event_ref_num': rec.event_ref_num,
            'walmart_event_id': walmart_id,
            'event_name': event.project_name if event else 'Unknown',
            'event_type': event.event_type if event else 'Unknown',
            'due_date': event.due_datetime.strftime('%m/%d/%Y') if event and event.due_datetime else '',
            'confirmed_at': rec.confirmed_at.strftime('%m/%d/%Y %I:%M %p') if rec.confirmed_at else '',
            'notes': rec.notes or '',
            'week_start_date': rec.week_start_date.isoformat(),
        })

    return jsonify({
        'status': 'success',
        'data': results,
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
    })


@lost_demos_bp.route('/api/lost-demos/confirmed-refs')
def confirmed_refs():
    """Return list of event_ref_nums that are confirmed lost."""
    models = get_models()
    LostDemo = models['LostDemo']
    refs = [r.event_ref_num for r in LostDemo.query.all()]
    return jsonify({'status': 'success', 'data': refs})


@lost_demos_bp.route('/api/lost-demos/export')
def export_lost_demos():
    """Export lost demos for a week as CSV."""
    models = get_models()
    Event = models['Event']
    LostDemo = models['LostDemo']

    week_str = request.args.get('week_start')
    if week_str:
        try:
            week_start = datetime.strptime(week_str, '%Y-%m-%d').date()
        except ValueError:
            week_start = _sunday_of(date.today())
    else:
        week_start = _sunday_of(date.today())

    week_end = week_start + timedelta(days=6)

    records = LostDemo.query.filter(
        LostDemo.week_start_date >= week_start,
        LostDemo.week_start_date <= week_end,
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Lost Demos', f'{week_start} to {week_end}'])
    writer.writerow(['Event #', 'Event Name', 'Event Type', 'Due Date', 'Confirmed At', 'Notes'])

    for rec in records:
        event = Event.query.filter_by(project_ref_num=rec.event_ref_num).first()
        display_id = event.walmart_event_id if event and event.walmart_event_id else rec.event_ref_num
        writer.writerow([
            display_id,
            event.project_name if event else 'Unknown',
            event.event_type if event else 'Unknown',
            event.due_datetime.strftime('%m/%d/%Y') if event and event.due_datetime else '',
            rec.confirmed_at.strftime('%m/%d/%Y %I:%M %p') if rec.confirmed_at else '',
            rec.notes or '',
        ])

    output.seek(0)
    resp = make_response(output.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename=lost_demos_{week_start}_{week_end}.csv'
    return resp


@lost_demos_bp.route('/events/lost-demos')
def lost_demos_page():
    """Weekly Lost Demos list page."""
    return render_template('lost_demos.html')
