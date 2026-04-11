# Flask Schedule Webapp

Employee scheduling system for Crossmark event specialists at Sam's Club,
with auto-scheduling, approval workflows, Walmart EDR / MVRetail
integration, and an optional RAG-based AI assistant.

## What it does

- **Auto-scheduler** — assigns Juicer Production, Core, Supervisor,
  Freeosk, Digitals, and Other events to employees per a spec-conformant
  greedy engine (`app/services/scheduling_engine.py`). Supervisors
  approve proposed schedules before they post to the external API.
- **Rotations & availability** — weekly primary-lead and juicer
  rotations, per-day exceptions, approved time off, weekly availability
  per employee.
- **Approval workflow** — every auto-scheduler run produces
  `PendingSchedule` rows for human review; approval pushes them to
  `Schedule` and syncs to MVRetail.
- **Schedule change notifications** — web push + in-app alerts when a
  lead or specialist's schedule changes within 7 days.
- **Walmart EDR integration** — generate / update Event Detail Reports
  with per-event shift block assignments.
- **AI assistant** — opt-in RAG panel backed by a local Ollama model.
- **Calloffs, attendance, inventory** — auxiliary modules for
  day-to-day supervisor operations.

## Tech stack

| Layer | Choice |
|-------|--------|
| Web framework | Flask 2.0+ |
| ORM | SQLAlchemy (factory pattern — use `get_models()`) |
| Database | SQLite in dev, PostgreSQL in production |
| Queue | Celery + Redis |
| Auth | Redis-backed sessions, WebAuthn + PIN app lock |
| Tests | pytest |
| Linting | ruff |
| AI | Ollama (local), optional |

## Quick start

```bash
# 1. Python 3.12+ and a virtualenv
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Create a .env (see app/config.py for the full list)
cat > .env <<EOF
FLASK_ENV=development
SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
DATABASE_URL=sqlite:///instance/scheduler.db
REDIS_URL=redis://localhost:6379/0
EOF

# 3. Run migrations
flask db upgrade

# 4. Start the dev server
python wsgi.py
```

The app listens on `http://localhost:5000` by default. A Redis server
must be reachable for sessions and Celery tasks to work.

## Running tests

```bash
pytest -v                                        # full suite
pytest tests/scheduler_spec_conformance/ -v      # scheduler conformance suite
pytest -m optional tests/test_cpsat_*            # legacy CP-SAT tests (opt-in)
pytest --cov=app                                 # with coverage
ruff check app/                                  # lint
```

Known issue: the ML test files (`tests/test_ml_*`) fail with a
pre-existing schema mismatch and are excluded from CI. The CP-SAT
tests are opted out of default runs via the `optional` pytest marker
(the scheduler rewrite retired CP-SAT from the production path; see
`docs/superpowers/plans/2026-04-10-scheduler-rewrite/08-retire-cpsat.md`).

## Production

```bash
gunicorn --config gunicorn_config.py wsgi:app
celery -A celery_worker:celery_app worker --loglevel=info
```

Database must be backed up before any migration:

```bash
./backup_now.sh                    # safe, always run first
flask db migrate -m "description"
flask db upgrade
```

## Project structure

```
app/
├── models/          # Factory-pattern SQLAlchemy models
├── routes/          # Flask blueprints
├── services/        # Scheduling engine, integrations, AI
├── integrations/    # Walmart EDR, MVRetail sync
├── ai/              # RAG assistant
├── templates/       # Jinja2
├── static/          # JS + CSS
├── error_handlers/
└── utils/

tests/               # pytest suite
migrations/          # Alembic migrations
instance/            # scheduler.db (gitignored)
docs/                # Architecture + specs + plans
  ├── CODEBASE_MAP.md
  ├── scheduling_validation_rules.md
  └── superpowers/
      ├── specs/     # Source-of-truth specifications
      └── plans/     # Executed and in-progress refactor plans
changelog/           # Dated notes on major changes
```

## Architecture & docs

| Document | Purpose |
|----------|---------|
| [`CLAUDE.md`](CLAUDE.md) | AI-assistant / contributor runbook — style rules, ripple effects, API tour |
| [`docs/CODEBASE_MAP.md`](docs/CODEBASE_MAP.md) | Codebase architecture walkthrough |
| [`docs/scheduling_validation_rules.md`](docs/scheduling_validation_rules.md) | Business rules enforced by the scheduler |
| [`docs/component-patterns.md`](docs/component-patterns.md) | Model / service / test patterns |
| [`docs/design-system-guide.md`](docs/design-system-guide.md) | UI tokens + components |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contribution + review flow |
| [`docs/superpowers/specs/2026-04-10-scheduler-rewrite/`](docs/superpowers/specs/2026-04-10-scheduler-rewrite/) | 7-image scheduler spec (source of truth for plans 00–99) |

## Contributing

Pull requests should pass:

1. `pytest -v` (excluding known-broken ML tests; see above)
2. `ruff check app/`
3. CLAUDE.md's "Change Ripple Effects" checklist (run through the table
   of model/service/route dependencies when you touch any of those)
4. A backup via `./backup_now.sh` if the change includes a migration

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full flow.

## Security & safety

- Never commit `.env` or credentials. `app/config.py` reads from env vars.
- External integrations (MVRetail, Walmart EDR) are feature-flag-gated
  and no-op unless the corresponding flag is enabled.
- Schema changes require a migration **and** a `./backup_now.sh` before
  running `flask db upgrade`.
- Auth sessions are 30-day persistent for all roles; a 5-minute app lock
  (PIN or WebAuthn biometric) kicks in on inactivity.

## License

Private — internal use only.
