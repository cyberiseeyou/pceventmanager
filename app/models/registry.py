"""
Model Registry - Centralized model access using Flask extension pattern

Replaces the anti-pattern of storing models in app.config.
Provides clean, type-safe access to SQLAlchemy models throughout the application.

Usage:
    from models.registry import get_models

    def my_view():
        models = get_models()
        employee = models['Employee'].query.first()
"""
from flask import current_app
from typing import Dict, Any, Optional


class ModelRegistry:
    """
    Flask extension for centralized model management

    Provides a clean interface for accessing database models throughout
    the application, following Flask's extension pattern.
    """

    def __init__(self, app=None):
        """
        Initialize the model registry

        Args:
            app: Optional Flask app instance for immediate initialization
        """
        self.models: Dict[str, Any] = {}
        if app:
            self.init_app(app)

    def init_app(self, app):
        """
        Initialize extension with Flask app

        Args:
            app: Flask application instance
        """
        app.teardown_appcontext(self._teardown)
        app.extensions['models'] = self

    def register(self, models_dict: Dict[str, Any]):
        """
        Register all models with the registry

        Args:
            models_dict: Dictionary mapping model names to model classes
        """
        self.models = models_dict

    def get(self, model_name: str) -> Optional[Any]:
        """
        Get model class by name

        Args:
            model_name: Name of the model to retrieve

        Returns:
            Model class or None if not found
        """
        return self.models.get(model_name)

    def __getitem__(self, model_name: str) -> Any:
        """
        Allow dict-like access to models

        Args:
            model_name: Name of the model to retrieve

        Returns:
            Model class

        Raises:
            KeyError: If model name is not registered
        """
        return self.models[model_name]

    def all(self) -> Dict[str, Any]:
        """
        Get all registered models

        Returns:
            Dictionary of all registered models
        """
        return self.models.copy()

    def _teardown(self, exception):
        """
        Cleanup on request teardown

        Args:
            exception: Exception that occurred during request (if any)
        """
        pass


# Global instance
model_registry = ModelRegistry()


def get_models() -> Dict[str, Any]:
    """
    Helper to get all registered models from current app context

    This is a drop-in replacement for the old pattern:
        Employee = current_app.config['Employee']

    New pattern:
        models = get_models()
        Employee = models['Employee']

    Returns:
        Dictionary containing all registered models

    Raises:
        RuntimeError: If called outside application context
    """
    if 'models' not in current_app.extensions:
        raise RuntimeError(
            "ModelRegistry not initialized. "
            "Ensure model_registry.init_app(app) is called during app setup."
        )

    return current_app.extensions['models'].models


def get_db():
    """
    Helper to get SQLAlchemy database instance

    Returns:
        SQLAlchemy database instance

    Raises:
        RuntimeError: If called outside application context
    """
    return current_app.extensions['sqlalchemy']
