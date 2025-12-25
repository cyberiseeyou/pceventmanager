"""
Gunicorn Configuration for Production Deployment
Flask Schedule Webapp - Enterprise Production Settings

This configuration file provides production-ready settings for Gunicorn WSGI server.

Usage:
    gunicorn --config gunicorn_config.py wsgi:app
"""
import multiprocessing
import os

# Server Socket
bind = os.getenv('GUNICORN_BIND', '0.0.0.0:8000')
backlog = int(os.getenv('GUNICORN_BACKLOG', '2048'))

# Worker Processes
workers = int(os.getenv('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = os.getenv('GUNICORN_WORKER_CLASS', 'gevent')  # gevent for async I/O
worker_connections = int(os.getenv('GUNICORN_WORKER_CONNECTIONS', '1000'))
max_requests = int(os.getenv('GUNICORN_MAX_REQUESTS', '10000'))
max_requests_jitter = int(os.getenv('GUNICORN_MAX_REQUESTS_JITTER', '1000'))
timeout = int(os.getenv('GUNICORN_TIMEOUT', '120'))
keepalive = int(os.getenv('GUNICORN_KEEPALIVE', '5'))

# Server Mechanics
daemon = False  # Don't daemonize in production (use systemd/supervisor instead)
pidfile = os.getenv('GUNICORN_PIDFILE', None)
umask = int(os.getenv('GUNICORN_UMASK', '0'))
user = os.getenv('GUNICORN_USER', None)
group = os.getenv('GUNICORN_GROUP', None)
tmp_upload_dir = os.getenv('GUNICORN_TMP_UPLOAD_DIR', None)

# Logging
accesslog = os.getenv('GUNICORN_ACCESS_LOG', '-')  # '-' for stdout
errorlog = os.getenv('GUNICORN_ERROR_LOG', '-')    # '-' for stderr
loglevel = os.getenv('GUNICORN_LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process Naming
proc_name = 'flask_schedule_webapp'

# Server Hooks
def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Starting Flask Schedule Webapp")

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    server.log.info("Reloading Flask Schedule Webapp")

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("Flask Schedule Webapp is ready. Listening on: %s", bind)

def worker_int(worker):
    """Called when a worker receives the SIGINT or SIGQUIT signal."""
    worker.log.info("Worker received SIGINT or SIGQUIT")

def worker_abort(worker):
    """Called when a worker receives the SIGABRT signal."""
    worker.log.info("Worker received SIGABRT")

# Security
limit_request_line = int(os.getenv('GUNICORN_LIMIT_REQUEST_LINE', '4096'))
limit_request_fields = int(os.getenv('GUNICORN_LIMIT_REQUEST_FIELDS', '100'))
limit_request_field_size = int(os.getenv('GUNICORN_LIMIT_REQUEST_FIELD_SIZE', '8190'))

# SSL (if using Gunicorn for SSL termination)
keyfile = os.getenv('GUNICORN_KEYFILE', None)
certfile = os.getenv('GUNICORN_CERTFILE', None)
ssl_version = os.getenv('GUNICORN_SSL_VERSION', 'TLSv1_2')
cert_reqs = int(os.getenv('GUNICORN_CERT_REQS', '0'))
ca_certs = os.getenv('GUNICORN_CA_CERTS', None)

# Graceful Timeout
graceful_timeout = int(os.getenv('GUNICORN_GRACEFUL_TIMEOUT', '30'))

# Environment Variables
raw_env = [
    f"FLASK_ENV={os.getenv('FLASK_ENV', 'production')}",
]
