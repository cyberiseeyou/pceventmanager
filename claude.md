<default_to_action>
by default, implement changes rather than only suggesting them. If the user's intent is unclear, infer the most useful likely action and proceed, using toold to discover any missing details instead of guessing. Try to infer the user's intent about whether a tool call (e.g., file edit or read) is intended or not, and act accordingly.
</default_to_action>
# PCEventManager

## What This Is
Flask-based employee scheduling and demo event management app for Sam's Club Store #8135 (Product Connections / Acosta Group). Used by a Club Supervisor to schedule 10-20 demo event specialists and juice baristas.

## Stack
- **Backend:** Python/Flask, SQLite, SQLAlchemy
- **Frontend:** Jinja2 templates, Bootstrap (check current version), vanilla JS
- **Scheduling Engine:** Google OR-Tools CP-SAT solver
- **ML:** XGBoost model for schedule optimization
- **AI:** LLM integration for schedule review and natural language commands
- **Deployment:** Docker, Cloudflare tunnel for HTTPS

## Project Structure
- `app.py` or `run.py` — Flask app entry point
- `templates/` — Jinja2 HTML templates
- `static/` — CSS, JS, images
- `models/` — SQLAlchemy models
- `services/` — Business logic (scheduling engine, ML, AI)
- `config.py` — Configuration

## Commands
- `python app.py` or `flask run` — Start dev server
- `pip install -r requirements.txt` — Install dependencies
- `docker-compose up` — Run with Docker

## Current Mobile Optimization Task
We are converting this app to be mobile-optimized as a Progressive Web App (PWA). Key areas:
1. Responsive templates (mobile-first Bootstrap 5)
2. Touch-friendly UI (48px+ tap targets, swipe gestures for schedule views)
3. PWA manifest and service worker for installability
4. Offline schedule viewing via cache-first strategy
5. Bottom navigation bar for mobile (replacing desktop sidebar/top nav)

## Rules
- ALWAYS create a git branch before making changes (prefix: `mobile/`)
- ALWAYS back up files before modifying them
- Use Bootstrap 5 utility classes — no custom CSS frameworks
- Keep Jinja2 templating — do NOT convert to React/Vue
- Python code style: follow existing patterns in the codebase
- Test at mobile viewport (375px, 390px, 768px) after every template change
- Use Context7 MCP for current Flask and Bootstrap docs before implementing
- For complex changes spanning 3+ files, use plan mode first

## When Compacting
Always preserve: list of modified files, current branch name, which templates have been converted, and any test commands used.
