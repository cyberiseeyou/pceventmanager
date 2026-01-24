# AGENTS.md

📖 **For comprehensive codebase documentation, see [docs/CODEBASE_MAP.md](docs/CODEBASE_MAP.md)**

## Commands
```bash
pytest                           # run all tests
pytest tests/test_file.py        # single file
pytest tests/test_file.py::test_func  # single test
pytest -v --cov=app              # verbose with coverage
python wsgi.py                   # dev server
flask db upgrade                 # apply migrations
```

## Code Style
- **Imports**: stdlib, third-party, local (relative within app/)
- **Types**: Use type hints on all functions (`def foo(x: str) -> int:`)
- **Naming**: snake_case functions/vars, PascalCase classes, UPPER_SNAKE constants
- **Docstrings**: Google style with Args/Returns/Raises sections
- **Errors**: Use custom exceptions from `app/error_handlers/exceptions.py` (ValidationException, ResourceNotFoundException, etc.)
- **Decorators**: Use `@handle_errors` for routes, `@with_db_transaction` for DB ops

## Architecture
- **Models**: Access via `from app.models import get_models; models = get_models()`
- **Services**: Business logic in `app/services/`, accept `db_session` and `models` in `__init__`
- **Routes**: Blueprints in `app/routes/` with `*_bp` naming (e.g., `api_bp`)
- **Config**: `app/config.py` - DevelopmentConfig, TestingConfig, ProductionConfig
