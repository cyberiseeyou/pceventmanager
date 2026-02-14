# Review Scope

## Target

Review UI/UX structure to ensure it is optimized for usability and ease-of-use, and that the layout follows UI/UX best practices. This is a Flask scheduling webapp (Crossmark employee scheduling) with 108 UI/UX files.

## Files

### Templates (48 files)
- `app/templates/base.html` - Master layout template
- `app/templates/login.html` - Login page (standalone, no base.html)
- `app/templates/index.html` - Dashboard landing page
- `app/templates/daily_view.html` - Daily schedule view with inline modal styles
- `app/templates/calendar.html` - Calendar view
- `app/templates/schedule.html` - Main schedule page
- `app/templates/schedule_verification.html` - Verification interface (inline styles)
- `app/templates/unscheduled.html` - Events view with condition tabs
- `app/templates/unreported_events.html` - Unreported events
- `app/templates/auto_scheduler_main.html` - Auto-scheduler interface (inline styles)
- `app/templates/auto_schedule_review.html` - Review auto-schedule proposals
- `app/templates/employees.html` - Employee management
- `app/templates/employees/add.html` - Add employee form
- `app/templates/employees/import_selection.html` - Import employees
- `app/templates/attendance.html` - Attendance tracking
- `app/templates/time_off_requests.html` - Time-off requests
- `app/templates/shift_blocks.html` - Shift blocks
- `app/templates/rotations.html` - Rotation assignments
- `app/templates/event_times.html` - Event times config
- `app/templates/settings.html` - Settings page
- `app/templates/printing.html` - PDF reports
- `app/templates/scheduler_history.html` - Scheduler history
- `app/templates/employee_analytics.html` - Employee analytics
- `app/templates/workload_dashboard.html` - Workload analytics
- `app/templates/api_tester.html` - API testing utility
- `app/templates/sync_admin.html` - Sync admin
- `app/templates/dashboard/command_center.html` (27KB)
- `app/templates/dashboard/daily_validation.html` (57KB)
- `app/templates/dashboard/weekly_validation.html` (68KB)
- `app/templates/dashboard/approved_events.html` (73KB)
- `app/templates/inventory/index.html` (37KB)
- `app/templates/inventory/orders.html`
- `app/templates/inventory/order_detail.html`
- `app/templates/help/` (11 help pages)
- `app/templates/components/modal_base.html` - Reusable modal macro
- `app/templates/components/ai_chat_bubble.html` - AI chat widget
- `app/templates/components/ai_panel.html` - AI panel
- `app/templates/components/quick_note_widget.html` - Quick notes
- `app/templates/components/floating_verification_widget.html` - Verification widget
- `app/templates/auth/loading.html` - Loading state

### CSS (23 files)
- Core: `design-tokens.css`, `style.css`, `responsive.css`
- Pages: `pages/index.css`, `pages/daily-view.css`, `pages/dashboard.css`, `pages/employees.css`, `pages/auto-schedule-review.css`, `pages/unscheduled.css`, `pages/attendance-calendar.css`, `pages/workload-dashboard.css`
- Components: `components/modal.css`, `components/schedule-modal.css`, `components/notification-modal.css`, `components/ai-chat.css`
- Functional: `modals.css`, `login.css`, `validation.css`, `form-validation.css`, `loading.css`, `loading-states.css`, `keyboard-shortcuts.css`, `help.css`

### JavaScript (37 files)
- Core: `main.js`, `csrf_helper.js`, `notifications.js`, `navigation.js`, `search.js`, `user_dropdown.js`, `database-refresh.js`, `login.js`, `loading-progress.js`
- Utils: `utils/api-client.js`, `utils/debounce.js`, `utils/cache-manager.js`, `utils/loading-state.js`, `utils/focus-trap.js`, `utils/sr-announcer.js`
- Modules: `modules/focus-trap.js`, `modules/aria-announcer.js`, `modules/state-manager.js`, `modules/toast-notifications.js`, `modules/validation-engine.js`
- Components: `components/modal.js`, `components/schedule-modal.js`, `components/reschedule-modal.js`, `components/change-employee-modal.js`, `components/notification-modal.js`, `components/trade-modal.js`, `components/conflict-validator.js`, `components/ai-chat.js`, `components/ai-assistant.js`
- Pages: `pages/daily-view.js`, `pages/daily-view-attendance-methods.js`, `pages/dashboard.js`, `pages/schedule-verification.js`, `pages/schedule-form.js`, `pages/attendance-calendar.js`, `pages/workload-dashboard.js`
- Standalone: `employees.js`

## Flags

- Security Focus: no
- Performance Critical: no
- Strict Mode: no
- Framework: Flask/Jinja2 with vanilla JS, CSS custom properties design system

## Review Phases

1. Code Quality & Architecture
2. Security & Performance
3. Testing & Documentation
4. Best Practices & Standards
5. Consolidated Report

## Key Architectural Observations

- **Design System**: Centralized `design-tokens.css` with CSS custom properties
- **Template Inheritance**: `base.html` → all content pages
- **Component Pattern**: Jinja2 macros for reusable modals
- **Accessibility**: Dedicated ARIA/focus-trap modules
- **Mixed Patterns**: Some pages use inline CSS (daily_view, auto_scheduler_main, schedule_verification) while most use external files
- **Large Templates**: Dashboard validation templates are 57-73KB - potential maintainability concern
- **BEM Naming**: CSS uses BEM convention for components
