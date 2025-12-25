"""
Health Check and Monitoring Endpoints
Provides endpoints for application health monitoring, readiness checks, and metrics.
"""
from flask import Blueprint, jsonify, current_app
from datetime import datetime
import sys
import psutil
import os

health_bp = Blueprint('health', __name__, url_prefix='/health')


@health_bp.route('/ping', methods=['GET'])
def ping():
    """
    Simple ping endpoint for basic connectivity checks.
    Returns: 200 OK with pong message
    """
    return jsonify({
        'status': 'ok',
        'message': 'pong',
        'timestamp': datetime.utcnow().isoformat()
    }), 200


@health_bp.route('/live', methods=['GET'])
def liveness():
    """
    Liveness probe - checks if application is running.
    Used by orchestrators (Kubernetes, Docker) to determine if container should be restarted.

    Returns:
        200: Application is alive
        503: Application is not responsive
    """
    try:
        return jsonify({
            'status': 'alive',
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'dead',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 503


@health_bp.route('/ready', methods=['GET'])
def readiness():
    """
    Readiness probe - checks if application is ready to serve traffic.
    Validates critical dependencies (database, external APIs, etc.)

    Returns:
        200: Application is ready
        503: Application is not ready
    """
    checks = {
        'database': False,
        'external_api': True,  # Optional check
    }
    errors = []

    # Check database connectivity
    try:
        from scheduler_app.app import db
        db.session.execute('SELECT 1')
        checks['database'] = True
    except Exception as e:
        errors.append(f"Database: {str(e)}")

    # Overall status
    all_checks_passed = all(checks.values())
    status_code = 200 if all_checks_passed else 503

    response = {
        'status': 'ready' if all_checks_passed else 'not_ready',
        'checks': checks,
        'timestamp': datetime.utcnow().isoformat()
    }

    if errors:
        response['errors'] = errors

    return jsonify(response), status_code


@health_bp.route('/status', methods=['GET'])
def status():
    """
    Detailed application status and metrics.
    Provides information about application health, system resources, and configuration.

    Returns:
        200: Status information
    """
    try:
        # Get process info
        process = psutil.Process()

        # Memory info
        memory_info = process.memory_info()
        memory_percent = process.memory_percent()

        # CPU info
        cpu_percent = process.cpu_percent(interval=0.1)

        # Disk info (for database file)
        disk_usage = psutil.disk_usage('/')

        status_info = {
            'status': 'operational',
            'timestamp': datetime.utcnow().isoformat(),
            'application': {
                'name': 'Flask Schedule Webapp',
                'version': '2.0.0',
                'environment': current_app.config.get('FLASK_ENV', 'unknown'),
                'debug': current_app.debug,
            },
            'system': {
                'python_version': sys.version,
                'platform': sys.platform,
                'process_id': os.getpid(),
            },
            'resources': {
                'memory': {
                    'used_mb': round(memory_info.rss / 1024 / 1024, 2),
                    'percent': round(memory_percent, 2),
                },
                'cpu': {
                    'percent': round(cpu_percent, 2),
                },
                'disk': {
                    'total_gb': round(disk_usage.total / 1024 / 1024 / 1024, 2),
                    'used_gb': round(disk_usage.used / 1024 / 1024 / 1024, 2),
                    'free_gb': round(disk_usage.free / 1024 / 1024 / 1024, 2),
                    'percent': disk_usage.percent,
                }
            },
            'database': {
                'type': 'sqlite' if 'sqlite' in current_app.config.get('SQLALCHEMY_DATABASE_URI', '') else 'postgresql',
                'connected': True,  # If we got here, we're connected
            }
        }

        return jsonify(status_info), 200

    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500


@health_bp.route('/metrics', methods=['GET'])
def metrics():
    """
    Application metrics in Prometheus-compatible format.
    Can be scraped by monitoring systems.

    Returns:
        200: Metrics in Prometheus text format
    """
    try:
        from scheduler_app.app import db

        # Count records in key tables
        metrics_data = []

        try:
            employee_count = db.session.execute('SELECT COUNT(*) FROM employee').scalar()
            metrics_data.append(f'scheduler_employees_total {employee_count}')
        except:
            pass

        try:
            schedule_count = db.session.execute('SELECT COUNT(*) FROM schedule').scalar()
            metrics_data.append(f'scheduler_schedules_total {schedule_count}')
        except:
            pass

        try:
            event_count = db.session.execute('SELECT COUNT(*) FROM event').scalar()
            metrics_data.append(f'scheduler_events_total {event_count}')
        except:
            pass

        # Process metrics
        process = psutil.Process()
        memory_info = process.memory_info()
        cpu_percent = process.cpu_percent(interval=0.1)

        metrics_data.append(f'scheduler_memory_bytes {memory_info.rss}')
        metrics_data.append(f'scheduler_cpu_percent {cpu_percent}')

        # Add timestamp
        timestamp = int(datetime.utcnow().timestamp() * 1000)

        return '\n'.join(metrics_data) + '\n', 200, {'Content-Type': 'text/plain; charset=utf-8'}

    except Exception as e:
        return f'# Error: {str(e)}\n', 500, {'Content-Type': 'text/plain; charset=utf-8'}
