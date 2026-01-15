import pytest
from app import create_app
from app.extensions import db as _db
from app.models import get_models
import os

@pytest.fixture(scope='session')
def app():
    """Create and configure a new app instance for each test session."""
    os.environ['FLASK_ENV'] = 'testing'
    app = create_app('testing')
    
    # Create application context
    ctx = app.app_context()
    ctx.push()

    yield app

    ctx.pop()

@pytest.fixture(scope='session')
def db(app):
    """Create a database for the test session."""
    _db.create_all()
    yield _db
    _db.drop_all()

@pytest.fixture(scope='function')
def db_session(db):
    """
    Creates a new database session for a test.
    """
    # Create tables for this test
    db.create_all()
    
    yield db.session
    
    # Cleanup
    db.session.remove()
    db.drop_all()

@pytest.fixture(scope='function')
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture(scope='function')
def runner(app):
    """A test runner for the app's CLI commands."""
    return app.test_cli_runner()

@pytest.fixture(scope='function')
def models(app):
    """Get models from registry."""
    return get_models()
