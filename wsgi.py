"""
WSGI Entry Point for Production Deployment
Flask Schedule Webapp - Enterprise Production Configuration

This file serves as the entry point for WSGI servers (Gunicorn, uWSGI, etc.)
in production environments.

Usage with Gunicorn:
    gunicorn --config gunicorn_config.py wsgi:app

Usage with uWSGI:
    uwsgi --ini uwsgi.ini
"""
import os
import sys
from pathlib import Path

# Add the application directory to the Python path
base_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(base_dir))

# Set production environment if not already set
if 'FLASK_ENV' not in os.environ:
    os.environ['FLASK_ENV'] = 'production'

# Import the Flask application factory
from app import create_app, init_db

# Create the application instance
app = create_app()

# Initialize database if needed
try:
    init_db(app)
except Exception as e:
    app.logger.warning(f"Database initialization skipped or failed: {e}")

# This is the WSGI application object
application = app

if __name__ == "__main__":
    # This allows running the file directly for testing
    # In production, use a WSGI server like Gunicorn
    app.run(debug=True, host='0.0.0.0', port=5000)
