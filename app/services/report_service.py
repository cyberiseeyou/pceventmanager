"""
Report Service
Provides data queries for all reports in the Reports section.
"""
from datetime import date, datetime, timedelta
from collections import defaultdict
from sqlalchemy import func, and_, or_


class ReportService:
    """Service for computing report data."""

    def __init__(self, db_session, models):
        self.session = db_session
        self.Event = models['Event']
        self.Employee = models['Employee']
        self.Schedule = models['Schedule']
        self.EmployeeAttendance = models['EmployeeAttendance']
        self.EmployeeTimeOff = models['EmployeeTimeOff']
        self.LostDemo = models.get('LostDemo')

    def get_event_statistics(self, start_date, end_date):
        """Report 1: Event Statistics — summary stats, by-condition breakdown, weekly detail."""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        events = self.Event.query.filter(
            self.Event.start_datetime >= start_dt,
            self.Event.start_datetime <= end_dt
        ).order_by(self.Event.start_datetime.asc()).all()

        total = len(events)
        by_condition = {}
        for e in events:
            cond = e.condition or 'Unknown'
            by_condition[cond] = by_condition.get(cond, 0) + 1

        submitted = by_condition.get('Submitted', 0)
        scheduled_count = by_condition.get('Scheduled', 0) + by_condition.get('Staffed', 0)
        unstaffed = by_condition.get('Unstaffed', 0)
        completion_rate = round((submitted / total * 100), 1) if total > 0 else 0
        scheduled_pct = round((scheduled_count / total * 100), 1) if total > 0 else 0
        unstaffed_pct = round((unstaffed / total * 100), 1) if total > 0 else 0

        # Group by week (Sunday start)
        weeks = defaultdict(list)
        for event in events:
            event_date = event.start_datetime.date()
            days_since_sunday = (event_date.weekday() + 1) % 7
            week_start = event_date - timedelta(days=days_since_sunday)
            schedule = self.Schedule.query.filter_by(
                event_ref_num=event.project_ref_num
            ).first()
            emp_name = ''
            sched_date = ''
            if schedule:
                emp = self.session.get(self.Employee, schedule.employee_id)
                emp_name = emp.name if emp else ''
                sched_date = schedule.schedule_datetime.strftime('%m/%d/%Y') if schedule.schedule_datetime else ''

            days_available = (event.due_datetime.date() - event.start_datetime.date()).days

            weeks[week_start].append({
                'ref_num': event.project_ref_num,
                'name': event.project_name,
                'event_type': event.event_type,
                'condition': event.condition,
                'start_date': event.start_datetime.strftime('%m/%d/%Y'),
                'due_date': event.due_datetime.strftime('%m/%d/%Y'),
                'employee': emp_name,
                'schedule_date': sched_date,
                'days_available': days_available,
            })

        sorted_weeks = []
        for ws in sorted(weeks.keys()):
            we = ws + timedelta(days=6)
            sorted_weeks.append({
                'start': ws.strftime('%m/%d/%Y'),
                'end': we.strftime('%m/%d/%Y'),
                'count': len(weeks[ws]),
                'events': weeks[ws],
            })

        # Lost demo rate
        lost_count = 0
        if self.LostDemo:
            lost_count = self.LostDemo.query.filter(
                self.LostDemo.week_start_date >= start_date,
                self.LostDemo.week_start_date <= end_date,
            ).count()
        lost_rate = round((lost_count / total * 100), 1) if total > 0 else 0

        return {
            'total': total,
            'completion_rate': completion_rate,
            'scheduled_pct': scheduled_pct,
            'unstaffed_pct': unstaffed_pct,
            'by_condition': dict(sorted(by_condition.items())),
            'weeks': sorted_weeks,
            'lost_count': lost_count,
            'lost_rate': lost_rate,
        }

    def get_employee_schedules(self, start_date, end_date):
        """Report 2: Employee Schedule Details."""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        schedules = self.session.query(
            self.Schedule, self.Event, self.Employee
        ).join(
            self.Event, self.Event.project_ref_num == self.Schedule.event_ref_num
        ).join(
            self.Employee, self.Employee.id == self.Schedule.employee_id
        ).filter(
            self.Schedule.schedule_datetime >= start_dt,
            self.Schedule.schedule_datetime <= end_dt,
            self.Employee.is_active == True
        ).order_by(
            self.Employee.name,
            self.Schedule.schedule_datetime
        ).all()

        employees = {}
        for sched, event, emp in schedules:
            if emp.id not in employees:
                employees[emp.id] = {
                    'name': emp.name,
                    'events': [],
                    'event_count': 0,
                    'days_scheduled': set(),
                }
            employees[emp.id]['events'].append({
                'name': event.project_name,
                'event_type': event.event_type,
                'start_date': event.start_datetime.strftime('%m/%d/%Y'),
                'end_date': event.due_datetime.strftime('%m/%d/%Y'),
                'schedule_date': sched.schedule_datetime.strftime('%m/%d/%Y'),
            })
            employees[emp.id]['event_count'] += 1
            employees[emp.id]['days_scheduled'].add(
                sched.schedule_datetime.date()
            )

        result = []
        for emp_id, data in sorted(employees.items(), key=lambda x: x[1]['name']):
            result.append({
                'name': data['name'],
                'events': data['events'],
                'event_count': data['event_count'],
                'days_scheduled': len(data['days_scheduled']),
            })

        return result

    def get_event_type_breakdown(self, start_date, end_date):
        """Report 3: Event Type Breakdown — count and percentage per type."""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        rows = self.session.query(
            self.Event.event_type,
            func.count(self.Event.id).label('count')
        ).filter(
            self.Event.start_datetime >= start_dt,
            self.Event.start_datetime <= end_dt
        ).group_by(self.Event.event_type).all()

        total = sum(r.count for r in rows)
        types = []
        for r in sorted(rows, key=lambda x: x.count, reverse=True):
            types.append({
                'event_type': r.event_type,
                'count': r.count,
                'percentage': round((r.count / total * 100), 1) if total > 0 else 0,
            })

        return {'total': total, 'types': types}

    def get_employee_workload(self, start_date, end_date):
        """Report 4: Employee Workload — hours per employee."""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        rows = self.session.query(
            self.Employee.name,
            func.count(self.Schedule.id).label('event_count'),
            func.coalesce(func.sum(self.Event.estimated_time), 0).label('total_minutes')
        ).join(
            self.Schedule, self.Schedule.employee_id == self.Employee.id
        ).join(
            self.Event, self.Event.project_ref_num == self.Schedule.event_ref_num
        ).filter(
            self.Schedule.schedule_datetime >= start_dt,
            self.Schedule.schedule_datetime <= end_dt,
            self.Employee.is_active == True
        ).group_by(self.Employee.name).order_by(self.Employee.name).all()

        result = []
        for r in rows:
            hours = round(r.total_minutes / 60, 1)
            avg = round(hours / r.event_count, 1) if r.event_count > 0 else 0
            if r.event_count >= 19:
                status = 'Overloaded'
            elif r.event_count >= 13:
                status = 'High'
            else:
                status = 'Normal'
            result.append({
                'name': r.name,
                'event_count': r.event_count,
                'total_hours': hours,
                'avg_hours': avg,
                'status': status,
            })

        return result

    def get_attendance_report(self, start_date, end_date):
        """Report 5: Attendance Report."""
        rows = self.session.query(
            self.Employee.name,
            self.EmployeeAttendance.status,
            func.count(self.EmployeeAttendance.id).label('count')
        ).join(
            self.Employee, self.Employee.id == self.EmployeeAttendance.employee_id
        ).filter(
            self.EmployeeAttendance.attendance_date >= start_date,
            self.EmployeeAttendance.attendance_date <= end_date,
            self.Employee.is_active == True
        ).group_by(
            self.Employee.name,
            self.EmployeeAttendance.status
        ).all()

        employees = {}
        for r in rows:
            if r.name not in employees:
                employees[r.name] = {
                    'name': r.name,
                    'on_time': 0, 'late': 0, 'called_in': 0,
                    'no_call_no_show': 0, 'excused_absence': 0,
                    'total': 0,
                }
            employees[r.name][r.status] = r.count
            employees[r.name]['total'] += r.count

        result = []
        for name in sorted(employees.keys()):
            data = employees[name]
            on_time = data['on_time']
            rate = round((on_time / data['total'] * 100), 1) if data['total'] > 0 else 0
            data['attendance_rate'] = rate
            result.append(data)

        return result

    def get_scheduling_coverage(self, start_date, end_date):
        """Report 6: Scheduling Coverage — daily scheduled vs total."""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        events = self.Event.query.filter(
            self.Event.start_datetime >= start_dt,
            self.Event.start_datetime <= end_dt,
            self.Event.condition.notin_(['Canceled', 'Cancelled', 'Expired'])
        ).all()

        by_day = defaultdict(lambda: {'total': 0, 'scheduled': 0})
        for e in events:
            d = e.start_datetime.date()
            by_day[d]['total'] += 1
            if e.is_scheduled:
                by_day[d]['scheduled'] += 1

        days = []
        current = start_date
        while current <= end_date:
            data = by_day.get(current, {'total': 0, 'scheduled': 0})
            unscheduled = data['total'] - data['scheduled']
            coverage = round((data['scheduled'] / data['total'] * 100), 1) if data['total'] > 0 else 100
            days.append({
                'date': current.strftime('%m/%d/%Y'),
                'date_short': current.strftime('%m/%d'),
                'day_name': current.strftime('%a'),
                'total': data['total'],
                'scheduled': data['scheduled'],
                'unscheduled': unscheduled,
                'coverage': coverage,
            })
            current += timedelta(days=1)

        overall_total = sum(d['total'] for d in days)
        overall_sched = sum(d['scheduled'] for d in days)
        overall_pct = round((overall_sched / overall_total * 100), 1) if overall_total > 0 else 100
        days_with_events = [d for d in days if d['total'] > 0]
        best = max(days_with_events, key=lambda d: d['coverage']) if days_with_events else None
        worst = min(days_with_events, key=lambda d: d['coverage']) if days_with_events else None

        return {
            'days': days,
            'overall_coverage': overall_pct,
            'overall_total': overall_total,
            'overall_scheduled': overall_sched,
            'best_day': best,
            'worst_day': worst,
        }

    def get_time_off_summary(self, start_date, end_date):
        """Report 7: Time Off Summary."""
        records = self.session.query(
            self.EmployeeTimeOff, self.Employee
        ).join(
            self.Employee, self.Employee.id == self.EmployeeTimeOff.employee_id
        ).filter(
            self.EmployeeTimeOff.start_date <= end_date,
            self.EmployeeTimeOff.end_date >= start_date,
            self.Employee.is_active == True
        ).order_by(
            self.Employee.name,
            self.EmployeeTimeOff.start_date
        ).all()

        result = []
        total_days = 0
        for to, emp in records:
            # Clamp to report range
            eff_start = max(to.start_date, start_date)
            eff_end = min(to.end_date, end_date)
            days = (eff_end - eff_start).days + 1
            total_days += days
            result.append({
                'name': emp.name,
                'start_date': to.start_date.strftime('%m/%d/%Y'),
                'end_date': to.end_date.strftime('%m/%d/%Y'),
                'days': days,
                'reason': to.reason or '',
            })

        return {'records': result, 'total_days': total_days}

    def get_weekly_scheduled_hours(self, start_date, end_date):
        """Report 8: Weekly Scheduled Hours per employee (excluding Club Supervisors).

        Returns per-employee hours broken down by week, plus overall averages.
        Uses calculate_schedule_duration for accurate hours including lunch breaks.
        """
        from app.utils.event_helpers import calculate_schedule_duration

        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        rows = self.session.query(
            self.Employee, self.Schedule, self.Event
        ).join(
            self.Schedule, self.Schedule.employee_id == self.Employee.id
        ).join(
            self.Event, self.Event.project_ref_num == self.Schedule.event_ref_num
        ).filter(
            self.Schedule.schedule_datetime >= start_dt,
            self.Schedule.schedule_datetime <= end_dt,
            self.Employee.is_active == True,
            self.Employee.job_title != 'Club Supervisor',
        ).order_by(
            self.Schedule.schedule_datetime
        ).all()

        # Build weeks (Sun-Sat boundaries)
        weeks = []
        current = start_date - timedelta(days=(start_date.weekday() + 1) % 7)
        while current <= end_date:
            week_end = current + timedelta(days=6)
            weeks.append({
                'start': current,
                'end': min(week_end, end_date),
                'label': f"{current.strftime('%m/%d')} – {week_end.strftime('%m/%d')}",
            })
            current = week_end + timedelta(days=1)

        # Aggregate hours by employee and week
        emp_data = {}
        for emp, sched, event in rows:
            if emp.id not in emp_data:
                emp_data[emp.id] = {
                    'name': emp.name,
                    'job_title': emp.job_title,
                    'weeks': {i: 0.0 for i in range(len(weeks))},
                    'total_minutes': 0.0,
                    'event_count': 0,
                }

            duration = calculate_schedule_duration(event)
            sched_date = sched.schedule_datetime.date()

            for i, w in enumerate(weeks):
                if w['start'] <= sched_date <= w['end']:
                    emp_data[emp.id]['weeks'][i] += duration
                    break

            emp_data[emp.id]['total_minutes'] += duration
            emp_data[emp.id]['event_count'] += 1

        # Build result
        num_weeks = len(weeks) if weeks else 1
        employees = []
        for eid, d in sorted(emp_data.items(), key=lambda x: x[1]['name']):
            weekly_hours = [round(d['weeks'].get(i, 0) / 60, 1) for i in range(len(weeks))]
            total_hours = round(d['total_minutes'] / 60, 1)
            avg_weekly = round(total_hours / num_weeks, 1)

            employees.append({
                'name': d['name'],
                'job_title': d['job_title'],
                'weekly_hours': weekly_hours,
                'total_hours': total_hours,
                'avg_weekly_hours': avg_weekly,
                'event_count': d['event_count'],
            })

        # Team averages
        team_total = sum(e['total_hours'] for e in employees)
        team_avg_weekly = round(team_total / num_weeks, 1) if employees else 0
        per_employee_avg = round(team_avg_weekly / len(employees), 1) if employees else 0

        return {
            'weeks': [w['label'] for w in weeks],
            'employees': employees,
            'num_weeks': num_weeks,
            'team_total_hours': team_total,
            'team_avg_weekly': team_avg_weekly,
            'per_employee_avg_weekly': per_employee_avg,
            'employee_count': len(employees),
        }
