# Contributing

## Getting Started

1. Clone the repo and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and configure (see `CLAUDE.md` for env vars).
3. Run the dev server:
   ```bash
   FLASK_ENV=development python wsgi.py
   ```
4. Run the test suite to verify your setup:
   ```bash
   pytest -v
   ```

## Commit Standards

- **Max 500 lines per commit.** Keep changes atomic and focused on a single concern.
- Use **conventional commit** prefixes:
  - `feat:` -- new feature
  - `fix:` -- bug fix
  - `refactor:` -- code restructuring with no behavior change
  - `docs:` -- documentation only
  - `test:` -- adding or updating tests
  - `chore:` -- tooling, dependencies, config
- Write messages that explain **why**, not just what. Example:
  ```
  fix: prevent double-booking by checking overlap before schedule insert

  The constraint validator was not called for bulk schedule creation,
  allowing conflicting assignments to slip through.
  ```
- **Always run `pytest -v` before committing.** Do not push with failing tests.

## Code Style

### Python

- **Model access**: Always use the factory pattern. Never import models directly.
  ```python
  # Correct
  from app.models import get_models, get_db
  models = get_models()
  Employee = models['Employee']

  # Wrong -- causes circular imports
  from app.models.employee import Employee
  ```
- **Services**: Follow the service class pattern with explicit `db.session.commit()` and rollback on error. See `CLAUDE.md` for the full template.
- **Error handling**: Use custom exceptions from `app/error_handlers/exceptions.py`.
- **External APIs**: Always check feature flags first, always set timeouts.

### JavaScript

- Use ES6 module imports. Route all API calls through `app/static/js/utils/api.js`.
- Add JSDoc comments to all public functions.
- Use BEM naming for CSS classes (e.g., `schedule-card__header--active`).

### Templates

- Jinja2 templates should include a comment block at the top listing expected context variables:
  ```html
  {# Context: events (list[Event]), date (str), employee (Employee|None) #}
  ```

### CSS

- Use design tokens from `design-tokens.css`. Never hardcode color values.
- Prefer utility classes over inline styles.

## Database Changes

1. **Backup first**: `./backup_now.sh`
2. Edit the model in `app/models/`.
3. Generate migration: `flask db migrate -m "description"`
4. Review the generated migration file.
5. Test on the test database:
   ```bash
   DATABASE_URL=sqlite:///instance/scheduler_test.db flask db upgrade
   ```
6. Apply: `flask db upgrade`

## Merge Conflict Resolution Checklist

After resolving conflicts, verify each of the following before pushing:

- [ ] `requirements.txt` -- no duplicate or conflicting package versions
- [ ] `migrations/versions/` -- no two migrations share the same `down_revision`; re-generate if needed
- [ ] `app/constants.py` -- no duplicate or conflicting constant definitions
- [ ] No duplicate imports or function definitions introduced by the merge
- [ ] Full test suite passes: `pytest -v`
- [ ] If models changed, check the ripple effects table in `CLAUDE.md`

## Pull Request Guidelines

### Branch Naming

Use a prefix that matches the change type:
- `feature/short-description` -- new functionality
- `fix/short-description` -- bug fix
- `docs/short-description` -- documentation changes

### PR Requirements

- Reference the related issue number in the PR description (e.g., `Closes #42`).
- Include test coverage for new features or bug fixes.
- Keep PRs focused. If a refactor is needed alongside a feature, split them into separate PRs.
- Ensure `pytest -v` passes on your branch before requesting review.

### PR Description Template

```
## Summary
Brief description of what changed and why.

## Test Plan
- [ ] Unit tests added/updated
- [ ] Manual testing steps (if applicable)

Closes #<issue-number>
```
