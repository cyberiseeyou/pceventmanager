# 2026-02-18: CLAUDE.md Audit & Claude Code Automations

## Summary

Audited and improved the project CLAUDE.md for accuracy, then implemented a full suite of Claude Code automations (hooks, skills, MCP server, subagent).

---

## Part 1: CLAUDE.md Audit & Improvements

### Broken References Fixed
- `app/static/js/utils/api.js` → `app/static/js/utils/api-client.js` (file didn't exist)
- Removed nonexistent `app/static/js/modules/auto-scheduler.js`
- Fixed auto-scheduler API endpoint prefix: `/auto-scheduler` → `/auto-schedule` (matches actual blueprint)

### Bloat Reduced (480 → 428 lines)
- Removed "Creating New Models" tutorial section (23 lines) — linked to `docs/component-patterns.md` instead
- Removed "Service Pattern" tutorial section (24 lines) — same link
- Removed duplicate model factory example from Common Pitfalls (already in dedicated section)
- Removed stale token count annotations from Key Files table ("42k tokens", etc.)
- Condensed Migrations common patterns to a one-liner

### Updated for Currency
- **Key Files table**: Added 7 services: `cpsat_scheduler.py`, `constraint_modifier.py`, `fix_wizard.py`, `weekly_validation.py`, `ai_assistant.py`, `database_refresh_service.py`
- **Blueprint Routes table**: Expanded from 8 → 23 blueprints with correct prefixes verified against source code
- **Model Relationships**: Added missing model groups (auto-scheduler, system, content, inventory)
- **JS files**: Added `fix-wizard.js` and `ai-assistant.js` references
- **Last updated date**: 2026-01-28 → 2026-02-18

### Score Change
- Before: 68/100 (C+)
- After: ~85/100 (B+)

---

## Part 2: Claude Code Automations

### Hooks (`.claude/settings.json`)

Three hooks added to enforce project standards automatically:

| Hook | Event | What It Does |
|------|-------|--------------|
| Protected file guard | PreToolUse (Edit/Write) | Blocks edits to `.env`, `.env.local`, `.env.test`, `instance/scheduler.db`, `instance/scheduler_test.db` |
| Ruff auto-lint | PostToolUse (Edit/Write) | Auto-fixes lint errors and formats Python files after every edit |
| Model import checker | PostToolUse (Edit/Write) | Warns when a `.py` file contains `from app.models.xxx import` (direct import anti-pattern) |

**Technical note**: Hook commands use `bash -c '...'` wrapper because Claude Code runs hooks under `/bin/sh`, not bash. The original implementation used bash arrays which failed with a syntax error.

### Skills (`.claude/skills/`)

Three project-specific skills created:

| Skill | File | Invocation | Purpose |
|-------|------|-----------|---------|
| `/backup-and-migrate` | `.claude/skills/backup-and-migrate/SKILL.md` | User-only | Automates the full migration safety workflow: backup → generate → review → test on test DB → apply |
| `/run-tests` | `.claude/skills/run-tests/SKILL.md` | Both (user + Claude) | Runs pytest with ML test exclusions baked in, accepts extra args |
| `/deploy` | `.claude/skills/deploy/SKILL.md` | User-only | Docker Compose production deployment with pre-checks (tests, git status, backup, health check, rollback) |

### MCP Server (`.mcp.json`)

Created project-level `.mcp.json` with SQLite MCP server:

```json
{
  "mcpServers": {
    "sqlite": {
      "command": "uvx",
      "args": ["mcp-server-sqlite", "--db-path", "./instance/scheduler.db"]
    }
  }
}
```

Enables direct SQL queries on the schedule database for debugging without writing Python code. Requires session restart to load.

### Subagent (`.claude/agents/scheduling-reviewer.md`)

Domain-specific code reviewer that enforces:
- Event priority order (Juicer → Digital Setup → ... → Other)
- ConstraintValidator usage before schedule creation
- Model factory pattern (`get_models()`)
- Double-booking conflict checks
- Supervisor/Core event pairing
- LockedDay, TimeOff, and Availability respect
- External API safety (feature flags, timeouts)

### Other Changes
- Installed `ruff` (v0.15.1) in `.venv` — was previously only installed ad-hoc in CI

---

## Files Created

```
.claude/settings.json              # Updated - added hooks
.claude/skills/backup-and-migrate/SKILL.md  # New
.claude/skills/run-tests/SKILL.md           # New
.claude/skills/deploy/SKILL.md              # New
.claude/agents/scheduling-reviewer.md       # New
.mcp.json                                   # New
```

## Files Modified

```
CLAUDE.md                          # Audit fixes, bloat reduction, currency updates
```
