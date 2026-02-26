// static/js/pages/daily-view.js

/**
 * Convert a string to Title Case for consistent name display
 */
function toTitleCase(text) {
    if (text == null) return '';
    return String(text).toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
}

/**
 * Daily View Page Controller
 *
 * Manages daily schedule view including summary, timeslots, and event cards.
 * Extended for Story 3.3 to include event cards display and interactions.
 */

class DailyView {
    constructor(date) {
        // Ensure date is set - fallback to DOM if not provided
        if (!date) {
            const dateElement = document.querySelector('[data-selected-date]');
            date = dateElement ? dateElement.getAttribute('data-selected-date') : null;
            if (!date) {
                console.error('DailyView: Unable to determine date from constructor or DOM');
            }
        }
        this.date = date;

        // Get today's date from DOM for reissue logic
        const container = document.querySelector('.daily-view-container');
        this.today = container ? container.getAttribute('data-today') : null;

        this.summaryContainer = document.getElementById('daily-summary');
        this.timeslotContainer = document.getElementById('timeslot-blocks');
        this.eventsContainer = document.getElementById('event-cards-container');  // NEW for Story 3.3
        this.attendanceContainer = document.getElementById('attendance-list-container');  // NEW for attendance
        this.typeFilter = document.getElementById('event-type-filter');  // Type filter dropdown
        this.employeeFilter = document.getElementById('event-employee-filter');  // Employee filter dropdown
        this.allEvents = [];  // Store all events for filtering
        this.viewMode = localStorage.getItem('dailyViewMode') || 'list';  // default to list view, persist preference
        this.init();
    }

    async init() {
        // PERFORMANCE: Parallel API calls instead of sequential (3x faster)
        // Previously: 3 sequential awaits creating waterfall (~600ms)
        // Now: All 3 requests start simultaneously (~200ms)
        await Promise.all([
            this.loadDailySummary(),   // From Story 3.2
            this.loadAttendance(),     // For attendance
            this.loadDailyEvents(),    // From Story 3.3
            this.checkLockStatus(),    // Check if day is locked
            this.loadDailyNotes()      // Load contextual notes for this date
        ]);
        this.setupTypeFilter();        // Setup filter listener
        this.setupEmployeeFilter();   // Setup employee filter listener
        this.setupViewToggle();        // Setup view mode toggle
        this.setupLockButton();        // Setup lock/unlock button
        this.setupKeyboardShortcuts(); // Setup keyboard navigation
    }

    /**
     * Setup type filter event listener
     */
    setupTypeFilter() {
        if (this.typeFilter) {
            this.typeFilter.addEventListener('change', () => {
                this.filterAndRenderEvents();
            });
        }
    }

    /**
     * Setup employee filter event listener
     */
    setupEmployeeFilter() {
        if (this.employeeFilter) {
            this.employeeFilter.addEventListener('change', () => {
                this.filterAndRenderEvents();
            });
        }
    }

    /**
     * Populate employee filter dropdown from loaded events
     */
    populateEmployeeFilter() {
        if (!this.employeeFilter) return;

        // Extract unique employees from events
        const employeeMap = new Map();
        this.allEvents.forEach(event => {
            if (event.employee_id && event.employee_name) {
                employeeMap.set(event.employee_id, event.employee_name);
            }
        });

        // Sort by name
        const employees = Array.from(employeeMap.entries())
            .sort((a, b) => a[1].localeCompare(b[1]));

        // Rebuild options keeping current selection
        const currentValue = this.employeeFilter.value;
        this.employeeFilter.innerHTML = '<option value="all">All Employees</option>';
        employees.forEach(([id, name]) => {
            const option = document.createElement('option');
            option.value = id;
            option.textContent = toTitleCase(name);
            this.employeeFilter.appendChild(option);
        });

        // Restore selection if still valid
        if (currentValue !== 'all' && employeeMap.has(currentValue)) {
            this.employeeFilter.value = currentValue;
        }
    }

    /**
     * Setup view toggle button listeners
     */
    setupViewToggle() {
        const toggleButtons = document.querySelectorAll('.view-toggle-btn');

        // Set initial active state from persisted preference
        toggleButtons.forEach(b => {
            const isActive = b.getAttribute('data-view') === this.viewMode;
            b.classList.toggle('active', isActive);
            b.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });

        toggleButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const newView = e.currentTarget.getAttribute('data-view');
                if (newView !== this.viewMode) {
                    this.viewMode = newView;
                    localStorage.setItem('dailyViewMode', newView);
                    // Update button states
                    toggleButtons.forEach(b => {
                        const isActive = b.getAttribute('data-view') === newView;
                        b.classList.toggle('active', isActive);
                        b.setAttribute('aria-pressed', isActive ? 'true' : 'false');
                    });
                    // Re-render with new view mode
                    this.filterAndRenderEvents();
                }
            });
        });
    }

    /**
     * Get the display category for an event type
     * Maps specific event types to their display categories
     */
    getEventTypeCategory(eventType) {
        const juicerTypes = ['Juicer Production', 'Juicer Survey', 'Juicer Deep Clean'];
        const digitalTypes = ['Digital Setup', 'Digital Refresh', 'Digital Teardown', 'Digitals'];

        if (juicerTypes.includes(eventType)) {
            return 'Juicer';
        } else if (digitalTypes.includes(eventType)) {
            return 'Digital';
        } else if (['Core', 'Supervisor', 'Freeosk', 'Other'].includes(eventType)) {
            return eventType;
        }
        return 'Other';
    }

    /**
     * Filter events by type and re-render based on view mode
     */
    filterAndRenderEvents() {
        const selectedType = this.typeFilter ? this.typeFilter.value : 'all';
        const selectedEmployee = this.employeeFilter ? this.employeeFilter.value : 'all';
        let filteredEvents = this.allEvents;

        if (selectedType !== 'all') {
            filteredEvents = filteredEvents.filter(event => {
                const category = this.getEventTypeCategory(event.event_type);
                return category === selectedType;
            });
        }

        if (selectedEmployee !== 'all') {
            filteredEvents = filteredEvents.filter(event => event.employee_id === selectedEmployee);
        }

        // Render based on view mode
        if (this.viewMode === 'list') {
            this.renderEventList(filteredEvents);
        } else {
            this.renderEventCards(filteredEvents);
        }
    }

    /* ===================================================================
       Story 3.2 Methods - Event Type Summary & Timeslot Coverage
       =================================================================== */

    /**
     * Load daily summary data from API
     */
    async loadDailySummary() {
        try {
            const response = await fetch(`/api/daily-summary/${this.date}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            this.renderEventTypeSummary(data.event_types, data.total_events);

            // Use 4-slot timeslot coverage (for external API compatibility)
            // The 8-block shift system is used for EDR printing only
            this.renderTimeslotCoverage(data.timeslot_coverage, data.timeslot_metadata);
        } catch (error) {
            console.error('Failed to load daily summary:', error);
            this.showError('Failed to load daily summary. Please refresh the page.');
        }
    }

    /**
     * Render 8-block shift blocks (NEW system)
     * Each block shows: Block number, times, and employees with their events
     */
    renderShiftBlocks(shiftBlocks) {
        if (!this.timeslotContainer) return;

        const html = shiftBlocks.map(block => {
            const hasEmployees = block.employees && block.employees.length > 0;
            const statusClass = hasEmployees ? 'shift-block--filled' : 'shift-block--empty';

            // Format times for display
            const arriveTime = this.formatTime12h(block.arrive);
            const onFloorTime = this.formatTime12h(block.on_floor);
            const lunchTime = `${this.formatTime12h(block.lunch_begin)} - ${this.formatTime12h(block.lunch_end)}`;
            const departTime = this.formatTime12h(block.depart);

            // Build employee list with expandable events
            let employeeHtml = '';
            if (hasEmployees) {
                employeeHtml = block.employees.map(emp => {
                    const eventsHtml = emp.events.map(evt => `
                        <div class="shift-block__event-detail" style="display: none;">
                            <div class="event-detail__row"><span class="event-detail__label">Event:</span> ${this.escapeHtml(evt.event_name)}</div>
                            <div class="event-detail__row"><span class="event-detail__label">Start Date:</span> ${evt.start_date}</div>
                            <div class="event-detail__row"><span class="event-detail__label">Due Date:</span> ${evt.due_date}</div>
                            <div class="event-detail__row"><span class="event-detail__label">Status:</span> <span class="status-badge status-badge--${evt.status.toLowerCase()}">${evt.status}</span></div>
                        </div>
                    `).join('');

                    return `
                        <div class="shift-block__employee" data-schedule-id="${emp.events[0]?.schedule_id || ''}">
                            <span class="shift-block__employee-name toggle-event-details" title="Click to see event details">${this.escapeHtml(emp.name)}</span>
                            ${eventsHtml}
                        </div>
                    `;
                }).join('');
            } else {
                employeeHtml = '<div class="shift-block__no-employees">No employees scheduled</div>';
            }

            return `
                <div class="shift-block ${statusClass}" data-block="${block.block}">
                    <div class="shift-block__header">
                        <span class="shift-block__number">Block ${block.block}</span>
                        <span class="shift-block__time-primary">${onFloorTime}</span>
                    </div>
                    <div class="shift-block__times">
                        <div class="shift-block__time-row">
                            <span class="shift-block__time-label">Arrive:</span>
                            <span class="shift-block__time-value">${arriveTime}</span>
                        </div>
                        <div class="shift-block__time-row">
                            <span class="shift-block__time-label">Lunch:</span>
                            <span class="shift-block__time-value">${lunchTime}</span>
                        </div>
                        <div class="shift-block__time-row">
                            <span class="shift-block__time-label">Depart:</span>
                            <span class="shift-block__time-value">${departTime}</span>
                        </div>
                    </div>
                    <div class="shift-block__employees-section">
                        ${employeeHtml}
                    </div>
                </div>
            `;
        }).join('');

        this.timeslotContainer.innerHTML = html;

        // Add click event listeners for expandable event details
        this.setupEventDetailsToggle();
    }

    /**
     * Setup click handlers for expandable event details
     */
    setupEventDetailsToggle() {
        const toggleElements = document.querySelectorAll('.toggle-event-details');
        toggleElements.forEach(el => {
            el.addEventListener('click', (e) => {
                const employeeDiv = e.target.closest('.shift-block__employee');
                if (employeeDiv) {
                    const detailDiv = employeeDiv.querySelector('.shift-block__event-detail');
                    if (detailDiv) {
                        const isVisible = detailDiv.style.display !== 'none';
                        detailDiv.style.display = isVisible ? 'none' : 'block';
                        e.target.classList.toggle('expanded', !isVisible);
                    }
                }
            });
        });
    }

    /**
     * Render event type summary section
     * Groups event types by category and displays in priority order:
     * Juicer, Core, Supervisor, Freeosk, Digital, Other
     */
    renderEventTypeSummary(eventTypes, totalEvents) {
        if (!this.summaryContainer) return;

        // Group event types by category
        const categoryCounts = {};
        Object.entries(eventTypes).forEach(([type, count]) => {
            const category = this.getEventTypeCategory(type);
            categoryCounts[category] = (categoryCounts[category] || 0) + count;
        });

        // Define display order
        const displayOrder = ['Juicer', 'Core', 'Supervisor', 'Freeosk', 'Digital', 'Other'];

        // Build sorted array with only types that have events
        const sortedCategories = displayOrder
            .filter(category => categoryCounts[category] > 0)
            .map(category => [category, categoryCounts[category]]);

        const html = `
            <div class="event-summary">
                <h3 class="event-summary__title">Events Summary</h3>
                <div class="event-summary__total">
                    <span class="event-summary__count">${totalEvents}</span>
                    <span class="event-summary__label">Total Events</span>
                </div>
                <div class="event-summary__types">
                    ${sortedCategories.map(([category, count]) => `
                        <div class="event-type-item">
                            <span class="event-type-item__icon">${this.getEventIcon(category)}</span>
                            <span class="event-type-item__label">${category}</span>
                            <span class="event-type-item__count">${count}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;

        this.summaryContainer.innerHTML = html;
    }

    /**
     * Render timeslot coverage blocks
     * Now uses timeslot metadata from settings instead of hardcoded values
     * Shows employee names instead of just counts
     */
    renderTimeslotCoverage(timeslotCoverage, timeslotMetadata = null) {
        if (!this.timeslotContainer) return;

        // Build timeslots from metadata if available, otherwise use defaults
        let timeslots;
        if (timeslotMetadata && Object.keys(timeslotMetadata).length > 0) {
            // Use times from settings
            timeslots = Object.entries(timeslotMetadata).map(([timeKey, meta]) => ({
                time: timeKey,
                label: meta.label,
                slot: meta.slot,
                lunchBegin: meta.lunch_begin,
                lunchEnd: meta.lunch_end,
                end: meta.end
            })).sort((a, b) => a.slot - b.slot);
        } else {
            // Fallback to default hardcoded times if settings not available
            timeslots = [
                { time: '09:45:00', label: '9:45 AM', slot: 1 },
                { time: '10:30:00', label: '10:30 AM', slot: 2 },
                { time: '11:00:00', label: '11:00 AM', slot: 3 },
                { time: '11:30:00', label: '11:30 AM', slot: 4 }
            ];
        }

        const html = timeslots.map(slot => {
            // Handle both old format (number) and new format (object with count and employees)
            const coverageData = timeslotCoverage[slot.time];
            let count = 0;
            let employees = [];

            if (typeof coverageData === 'object' && coverageData !== null) {
                count = coverageData.count || 0;
                employees = coverageData.employees || [];
            } else {
                count = coverageData || 0;
            }

            const status = this.getTimeslotStatus(count);
            const statusClass = `timeslot-block--${status}`;

            // Build tooltip with shift details if available
            let tooltip = `Employees starting at ${slot.label}:\n${employees.length > 0 ? employees.join(', ') : 'None'}`;
            if (slot.end) {
                tooltip += `\nShift ends at ${this.formatTime12h(slot.end)}`;
            }
            if (slot.lunchBegin && slot.lunchEnd) {
                tooltip += `\nLunch: ${this.formatTime12h(slot.lunchBegin)} - ${this.formatTime12h(slot.lunchEnd)}`;
            }

            // Build employee list HTML
            const employeeListHtml = employees.length > 0
                ? employees.map(name => `<div class="timeslot-block__employee">${this.escapeHtml(name)}</div>`).join('')
                : '<div class="timeslot-block__empty">No employees</div>';

            return `
                <div class="timeslot-block ${statusClass}"
                     title="${tooltip}"
                     aria-label="${count} employees starting at ${slot.label}">
                    <div class="timeslot-block__time">${slot.label}</div>
                    <div class="timeslot-block__employees">
                        ${employeeListHtml}
                    </div>
                </div>
            `;
        }).join('');

        this.timeslotContainer.innerHTML = html;
    }

    /**
     * Format 24h time (HH:MM) to 12h format
     */
    formatTime12h(timeStr) {
        if (!timeStr) return '';
        const [hour, minute] = timeStr.split(':').map(Number);
        if (hour === 0) return `12:${minute.toString().padStart(2, '0')} AM`;
        if (hour < 12) return `${hour}:${minute.toString().padStart(2, '0')} AM`;
        if (hour === 12) return `12:${minute.toString().padStart(2, '0')} PM`;
        return `${hour - 12}:${minute.toString().padStart(2, '0')} PM`;
    }

    /**
     * Get timeslot status based on employee count
     *
     * @param {number} count - Number of employees
     * @returns {string} Status: 'optimal', 'low', or 'empty'
     */
    getTimeslotStatus(count) {
        if (count >= 3) return 'optimal';
        if (count >= 1) return 'low';
        return 'empty';
    }

    /**
     * Get Material Symbol icon HTML for event type
     */
    getEventIcon(eventType) {
        const icons = {
            'Setup': '<span class="material-symbols-outlined">inventory_2</span>',
            'Demo': '<span class="material-symbols-outlined">target</span>',
            'Juicer': '<span class="material-symbols-outlined">blender</span>',
            'Other': '<span class="material-symbols-outlined">description</span>',
            'Core': '<span class="material-symbols-outlined">target</span>',
            'Supervisor': '<span class="material-symbols-outlined">admin_panel_settings</span>',
            'Freeosk': '<span class="material-symbols-outlined">redeem</span>',
            'Digital': '<span class="material-symbols-outlined">devices</span>',
            'Digitals': '<span class="material-symbols-outlined">devices</span>'
        };
        return icons[eventType] || '<span class="material-symbols-outlined">event</span>';
    }

    /**
     * Check if a time is a Core event time slot
     * Core times are: 10:15, 10:45, 11:15, 11:45 AM
     *
     * @param {string} time12h - Time in 12-hour format (e.g., "10:15 AM")
     * @returns {boolean} True if this is a Core time slot
     */
    isCoreTime(time12h) {
        if (!time12h) return false;
        const coreTimes = ['10:15 AM', '10:45 AM', '11:15 AM', '11:45 AM'];
        // Normalize the time string and check if it matches
        const normalized = time12h.trim().toUpperCase();
        return coreTimes.some(ct => normalized.startsWith(ct.toUpperCase()));
    }

    /**
     * Get Core badge HTML if the time is a Core time slot
     *
     * @param {string} startTime - Start time in 12-hour format
     * @returns {string} HTML for Core badge or empty string
     */
    getCoreBadge(startTime) {
        if (this.isCoreTime(startTime)) {
            return '<span class="badge-core">CORE</span>';
        }
        return '';
    }

    /**
     * Show error message
     */
    showError(message) {
        const container = this.summaryContainer || this.timeslotContainer;
        if (container) {
            container.innerHTML = `<div class="error-message" role="alert">${message}</div>`;
        }
    }

    /* ===================================================================
       Employee Attendance Methods - Separate from Events
       =================================================================== */

    /**
     * Load attendance data for scheduled employees
     */
    async loadAttendance() {
        try {
            const response = await fetch(`/api/attendance/scheduled-employees/${this.date}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            this.renderAttendanceList(data.scheduled_employees);
        } catch (error) {
            console.error('Failed to load attendance:', error);
            this.showAttendanceError('Failed to load attendance. Please refresh the page.');
        }
    }

    /**
     * Render attendance list
     */
    renderAttendanceList(employees) {
        if (!this.attendanceContainer) return;

        if (employees.length === 0) {
            this.attendanceContainer.innerHTML = `
                <div class="empty-state" role="status">
                    <p class="empty-state__message">No employees scheduled for this date</p>
                </div>
            `;
            return;
        }

        const html = employees.map(emp => this.createAttendanceRow(emp)).join('');
        this.attendanceContainer.innerHTML = `
            <div class="attendance-table">
                ${html}
            </div>
        `;

        // Attach event listeners
        this.attachAttendanceListeners();
    }

    /**
     * Create attendance row for an employee
     */
    createAttendanceRow(employee) {
        const hasAttendance = employee.attendance_status !== null;
        const statusBadge = hasAttendance
            ? this.getAttendanceBadge(employee.attendance_status, employee.status_label)
            : '<span class="attendance-badge attendance-badge--no-record">⚪ No Record</span>';

        const notesPreview = employee.attendance_notes
            ? `<span class="attendance-notes" title="${this.escapeHtml(employee.attendance_notes)}"><span class="material-symbols-outlined">notes</span> ${this.truncate(employee.attendance_notes, 40)}</span>`
            : '';

        const startTime = employee.earliest_start_time
            ? `<span class="employee-start-time"> - ${employee.earliest_start_time}</span>`
            : '';

        return `
            <div class="attendance-row" data-employee-id="${employee.employee_id}">
                <div class="attendance-row__employee">
                    <span class="employee-icon">👤</span>
                    <span class="employee-name">${employee.employee_name}${startTime}</span>
                </div>
                <div class="attendance-row__status">
                    ${statusBadge}
                    ${notesPreview}
                </div>
                <div class="attendance-row__actions">
                    ${hasAttendance
                ? `<button class="btn btn-secondary btn-sm btn-edit-attendance-row"
                                   data-employee-id="${employee.employee_id}"
                                   aria-label="Edit attendance for ${employee.employee_name}">
                               Edit
                           </button>`
                : `<div class="attendance-dropdown" data-employee-id="${employee.employee_id}">
                               <button class="btn btn-primary btn-sm dropdown-toggle"
                                       aria-label="Record attendance for ${employee.employee_name}"
                                       aria-haspopup="true"
                                       aria-expanded="false">
                                   Record Attendance ▼
                               </button>
                               <div class="dropdown-menu" role="menu">
                                   <button class="dropdown-item attendance-option"
                                           role="menuitem"
                                           data-employee-id="${employee.employee_id}"
                                           data-status="on_time">
                                       🟢 On-Time
                                   </button>
                                   <button class="dropdown-item attendance-option"
                                           role="menuitem"
                                           data-employee-id="${employee.employee_id}"
                                           data-status="late">
                                       🟡 Late
                                   </button>
                                   <button class="dropdown-item attendance-option"
                                           role="menuitem"
                                           data-employee-id="${employee.employee_id}"
                                           data-status="called_in">
                                       📞 Called-In
                                   </button>
                                   <button class="dropdown-item attendance-option"
                                           role="menuitem"
                                           data-employee-id="${employee.employee_id}"
                                           data-status="no_call_no_show">
                                       🔴 No-Call-No-Show
                                   </button>
                                   <button class="dropdown-item attendance-option"
                                           role="menuitem"
                                           data-employee-id="${employee.employee_id}"
                                           data-status="excused_absence">
                                       🔵 Excused Absence
                                   </button>
                               </div>
                           </div>`
            }
                </div>
            </div>
        `;
    }

    /**
     * Get attendance badge HTML
     */
    getAttendanceBadge(status, statusLabel) {
        return `<span class="attendance-badge attendance-badge--${status}">${statusLabel}</span>`;
    }

    /**
     * Attach event listeners to attendance section
     */
    attachAttendanceListeners() {
        // Record attendance dropdowns
        document.querySelectorAll('.attendance-dropdown .dropdown-toggle').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const dropdown = e.currentTarget.closest('.attendance-dropdown');
                this.toggleAttendanceDropdown(dropdown);
            });
        });

        // Attendance status options
        document.querySelectorAll('.attendance-option').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const employeeId = e.currentTarget.getAttribute('data-employee-id');
                const status = e.currentTarget.getAttribute('data-status');
                this.handleAttendanceRecordForEmployee(employeeId, status);
            });
        });

        // Edit attendance buttons
        document.querySelectorAll('.btn-edit-attendance-row').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const employeeId = e.currentTarget.getAttribute('data-employee-id');
                this.handleAttendanceEditForEmployee(employeeId);
            });
        });

        // Close dropdowns when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.attendance-dropdown')) {
                this.closeAllAttendanceDropdowns();
            }
        });
    }

    /**
     * Handle attendance recording for employee
     */
    async handleAttendanceRecordForEmployee(employeeId, status) {
        this.closeAllAttendanceDropdowns();
        const notes = await this.showAttendanceNoteModal(status);
        if (notes === null) return;

        try {
            const response = await fetch('/api/attendance', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': this.getCsrfToken()
                },
                body: JSON.stringify({
                    employee_id: employeeId,
                    attendance_date: this.date,
                    status,
                    notes
                })
            });

            const data = await response.json();
            if (response.ok && data.success) {
                this.showNotification(`Attendance recorded: ${data.attendance.status_label}`, 'success');
                await this.loadAttendance();  // Reload attendance list

                // Trigger Call-Off Wizard for absence statuses
                if (status === 'called_in' || status === 'no_call_no_show') {
                    this.showCallOffWizard(employeeId, status);
                }
            } else {
                throw new Error(data.error || 'Failed to record attendance');
            }
        } catch (error) {
            this.showNotification(error.message || 'Failed to record attendance', 'error');
        }
    }

    /**
     * Handle attendance edit for employee
     */
    async handleAttendanceEditForEmployee(employeeId) {
        const row = document.querySelector(`[data-employee-id="${employeeId}"]`);
        if (row) {
            // Replace edit button with record dropdown
            const actionsCell = row.querySelector('.attendance-row__actions');
            actionsCell.innerHTML = `
                <div class="attendance-dropdown" data-employee-id="${employeeId}">
                    <button class="btn btn-primary btn-sm dropdown-toggle"
                            aria-label="Update attendance"
                            aria-haspopup="true"
                            aria-expanded="false">
                        Update Attendance ▼
                    </button>
                    <div class="dropdown-menu" role="menu">
                        <button class="dropdown-item attendance-option"
                                role="menuitem"
                                data-employee-id="${employeeId}"
                                data-status="on_time">
                            🟢 On-Time
                        </button>
                        <button class="dropdown-item attendance-option"
                                role="menuitem"
                                data-employee-id="${employeeId}"
                                data-status="late">
                            🟡 Late
                        </button>
                        <button class="dropdown-item attendance-option"
                                role="menuitem"
                                data-employee-id="${employeeId}"
                                data-status="called_in">
                            📞 Called-In
                        </button>
                        <button class="dropdown-item attendance-option"
                                role="menuitem"
                                data-employee-id="${employeeId}"
                                data-status="no_call_no_show">
                            🔴 No-Call-No-Show
                        </button>
                        <button class="dropdown-item attendance-option"
                                role="menuitem"
                                data-employee-id="${employeeId}"
                                data-status="excused_absence">
                            🔵 Excused Absence
                        </button>
                    </div>
                </div>
            `;
            this.attachAttendanceListeners();
        }
    }

    /**
     * Show attendance error
     */
    showAttendanceError(message) {
        if (this.attendanceContainer) {
            this.attendanceContainer.innerHTML = `
                <div class="error-message" role="alert">${message}</div>
            `;
        }
    }

    /* ===================================================================
       Story 3.3 Methods - Event Cards Display
       =================================================================== */

    /**
     * Load daily events from API
     */
    async loadDailyEvents() {
        try {
            const response = await fetch(`/api/daily-events/${this.date}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            this.allEvents = data.events;  // Store for filtering
            this.populateEmployeeFilter(); // Populate employee dropdown
            this.filterAndRenderEvents();  // Render with current filter
        } catch (error) {
            console.error('Failed to load daily events:', error);
            this.showEventsError('Failed to load events. Please refresh the page.');
        }
    }

    /**
     * Load contextual notes for today's events and employees
     */
    async loadDailyNotes() {
        try {
            const response = await fetch(`/api/daily-notes/${this.date}`);
            if (!response.ok) return;
            const data = await response.json();
            if (data.success && data.count > 0) {
                this.renderNotesBanner(data.notes);
            }
        } catch (error) {
            console.error('Failed to load daily notes:', error);
        }
    }

    renderNotesBanner(notes) {
        const banner = document.createElement('div');
        banner.className = 'daily-notes-banner';
        banner.style.cssText = 'background: linear-gradient(135deg, #fefce8, #fef9c3); border: 1px solid #fde68a; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;';

        const header = document.createElement('div');
        header.style.cssText = 'display: flex; justify-content: space-between; align-items: center; cursor: pointer;';
        header.innerHTML = `<span style="font-weight: 600; font-size: 14px; color: #92400e;">📝 ${notes.length} note${notes.length !== 1 ? 's' : ''} for today</span><span style="color: #92400e; font-size: 12px;">Click to expand</span>`;

        const list = document.createElement('div');
        list.style.cssText = 'display: none; margin-top: 8px; border-top: 1px solid #fde68a; padding-top: 8px;';

        notes.forEach(function(note) {
            var item = document.createElement('div');
            item.style.cssText = 'padding: 6px 0; font-size: 13px; border-bottom: 1px solid #fef3c7;';
            var linked = '';
            if (note.linked_event_ref_num) linked += ' <span style="color:#6b7280;">📋 Event #' + note.linked_event_ref_num + '</span>';
            if (note.linked_employee_id) linked += ' <span style="color:#6b7280;">👤 ' + note.linked_employee_id + '</span>';
            item.innerHTML = '<strong>' + escapeHtml(note.title) + '</strong>' + linked +
                (note.content ? '<div style="color:#78716c; font-size:12px; margin-top:2px;">' + escapeHtml(note.content) + '</div>' : '');
            list.appendChild(item);
        });

        header.addEventListener('click', function() {
            list.style.display = list.style.display === 'none' ? '' : 'none';
        });

        banner.appendChild(header);
        banner.appendChild(list);

        // Insert before the events section
        var eventsSection = this.eventsContainer;
        if (eventsSection && eventsSection.parentNode) {
            eventsSection.parentNode.insertBefore(banner, eventsSection);
        }
    }

    /**
     * Group events by category
     * @param {Array} events - Array of event objects
     * @returns {Object} Events grouped by category
     */
    groupEventsByCategory(events) {
        const grouped = {
            'Juicer': [],
            'Core': [],
            'Supervisor': [],
            'Freeosk': [],
            'Digital': [],
            'Other': []
        };

        events.forEach(event => {
            const category = this.getEventTypeCategory(event.event_type);
            if (grouped[category]) {
                grouped[category].push(event);
            } else {
                grouped['Other'].push(event);
            }
        });

        // Sort each group by time
        Object.keys(grouped).forEach(category => {
            grouped[category].sort((a, b) => a.start_time.localeCompare(b.start_time));
        });

        return grouped;
    }

    /**
     * Pair Core and Supervisor events for display
     * Core always on left, Supervisor on right
     */
    pairCoreSupervisorEvents(coreEvents, supervisorEvents) {
        const paired = [];
        const usedSupervisors = new Set();

        coreEvents.forEach(coreEvent => {
            const match = coreEvent.event_name.match(/^(\d{6})/);
            let pairedSupervisor = null;

            if (match) {
                const eventNumber = match[1];
                pairedSupervisor = supervisorEvents.find(supEvent => {
                    const supMatch = supEvent.event_name.match(/^(\d{6})/);
                    return supMatch && supMatch[1] === eventNumber && !usedSupervisors.has(supEvent.schedule_id);
                });

                if (pairedSupervisor) {
                    usedSupervisors.add(pairedSupervisor.schedule_id);
                }
            }

            paired.push({ core: coreEvent, supervisor: pairedSupervisor });
        });

        const unpairedSupervisors = supervisorEvents.filter(s => !usedSupervisors.has(s.schedule_id));
        return { paired, unpairedSupervisors };
    }

    /**
     * Create paired Core-Supervisor display
     */
    createCoreSupervisorPair(pair) {
        const coreHTML = pair.core ? this.createEventCard(pair.core) : '<div class="event-card-placeholder"></div>';
        const supervisorHTML = pair.supervisor ? this.createEventCard(pair.supervisor) : '<div class="event-card-placeholder"></div>';

        return `
            <div class="core-supervisor-pair">
                <div class="pair-core">${coreHTML}</div>
                <div class="pair-supervisor">${supervisorHTML}</div>
            </div>
        `;
    }

    /**
     * Render event cards into container
     * Groups events by category with Core-Supervisor pairing
     *
     * @param {Array} events - Array of event objects from API
     */
    renderEventCards(events) {
        if (!this.eventsContainer) return;

        // Remove list-view class if present
        this.eventsContainer.classList.remove('list-view');

        if (events.length === 0) {
            this.eventsContainer.innerHTML = `
                <div class="empty-state" role="status">
                    <p class="empty-state__message">No events scheduled for this date</p>
                </div>
            `;
            return;
        }

        // Check for cancelled events
        const cancelledEvents = events.filter(e => e.is_cancelled || e.reporting_status === 'cancelled');
        const cancelledBannerHTML = cancelledEvents.length > 0
            ? this.createCancelledEventsBanner(cancelledEvents)
            : '';

        // Group events by category
        const grouped = this.groupEventsByCategory(events);
        const categoryOrder = ['Juicer', 'Core', 'Supervisor', 'Freeosk', 'Digital', 'Other'];
        let cardsHTML = '';

        categoryOrder.forEach(category => {
            if (category === 'Core') {
                const pairingResult = this.pairCoreSupervisorEvents(grouped['Core'], grouped['Supervisor']);

                if (pairingResult.paired.length > 0) {
                    cardsHTML += `
                        <div class="event-category-section event-category-section--paired">
                            <h3 class="event-category-header">
                                <span class="category-icon">${this.getEventIcon('Core')}</span>
                                Core & Supervisor Events
                            </h3>
                            <div class="event-category-content">
                                ${pairingResult.paired.map(pair => this.createCoreSupervisorPair(pair)).join('')}
                            </div>
                        </div>
                    `;
                }

                if (pairingResult.unpairedSupervisors.length > 0) {
                    cardsHTML += `
                        <div class="event-category-section">
                            <h3 class="event-category-header">
                                <span class="category-icon">${this.getEventIcon('Supervisor')}</span>
                                Unpaired Supervisor Events
                            </h3>
                            <div class="event-category-content">
                                ${pairingResult.unpairedSupervisors.map(event => this.createEventCard(event)).join('')}
                            </div>
                        </div>
                    `;
                }
            } else if (category === 'Supervisor') {
                return; // Handled with Core
            } else {
                const categoryEvents = grouped[category];
                if (categoryEvents.length > 0) {
                    cardsHTML += `
                        <div class="event-category-section">
                            <h3 class="event-category-header">
                                <span class="category-icon">${this.getEventIcon(category)}</span>
                                ${category} Events
                            </h3>
                            <div class="event-category-content">
                                ${categoryEvents.map(event => this.createEventCard(event)).join('')}
                            </div>
                        </div>
                    `;
                }
            }
        });

        this.eventsContainer.innerHTML = cancelledBannerHTML + cardsHTML;
        this.attachEventCardListeners();
    }

    /**
     * Create notification banner for cancelled events
     *
     * @param {Array} cancelledEvents - Array of cancelled event objects
     * @returns {string} HTML string for banner
     */
    createCancelledEventsBanner(cancelledEvents) {
        const eventDetails = cancelledEvents.map(e =>
            `<li><strong>${e.event_id}</strong>: ${e.event_name} (${e.employee_name})</li>`
        ).join('');

        return `
            <div class="cancelled-events-banner" role="alert">
                <div class="cancelled-events-banner__header">
                    <span class="cancelled-events-banner__icon"><span class="material-symbols-outlined">cancel</span></span>
                    <strong>Action Required: ${cancelledEvents.length} Cancelled Event${cancelledEvents.length > 1 ? 's' : ''} Detected</strong>
                </div>
                <p class="cancelled-events-banner__message">
                    The following event${cancelledEvents.length > 1 ? 's have' : ' has'} been <strong>CANCELLED</strong> in the Walmart EDR system.
                    You cannot generate paperwork until these are unscheduled.
                </p>
                <ul class="cancelled-events-banner__list">
                    ${eventDetails}
                </ul>
                <p class="cancelled-events-banner__action">
                    Please <strong>unschedule</strong> these events and notify the assigned employee(s) of the schedule change.
                </p>
            </div>
        `;
    }

    /**
     * Render events in list/table view
     * Groups events by category with Core-Supervisor pairing
     *
     * @param {Array} events - Array of event objects from API
     */
    renderEventList(events) {
        if (!this.eventsContainer) return;

        // Add list-view class
        this.eventsContainer.classList.add('list-view');

        if (events.length === 0) {
            this.eventsContainer.innerHTML = `
                <div class="empty-state" role="status">
                    <p class="empty-state__message">No events scheduled for this date</p>
                </div>
            `;
            return;
        }

        // Group events by category
        const grouped = this.groupEventsByCategory(events);
        const categoryOrder = ['Juicer', 'Core', 'Supervisor', 'Freeosk', 'Digital', 'Other'];
        let listHTML = '';

        categoryOrder.forEach(category => {
            if (category === 'Core') {
                const pairingResult = this.pairCoreSupervisorEvents(grouped['Core'], grouped['Supervisor']);

                if (pairingResult.paired.length > 0 || pairingResult.unpairedSupervisors.length > 0) {
                    listHTML += `
                        <div class="event-category-section event-category-section--paired">
                            <h3 class="event-category-header">
                                <span class="category-icon">${this.getEventIcon('Core')}</span>
                                Core & Supervisor Events
                            </h3>
                            <div class="event-category-content">
                                <div class="event-list-header">
                                    <div>Time</div>
                                    <div>Event</div>
                                    <div>Employee</div>
                                    <div>Type</div>
                                    <div>Actions</div>
                                </div>
                    `;

                    // Add paired Core events first
                    pairingResult.paired.forEach(pair => {
                        if (pair.core) {
                            listHTML += this.createEventListRow(pair.core);
                        }
                        if (pair.supervisor) {
                            listHTML += this.createEventListRow(pair.supervisor);
                        }
                    });

                    // Add unpaired supervisors
                    pairingResult.unpairedSupervisors.forEach(event => {
                        listHTML += this.createEventListRow(event);
                    });

                    listHTML += '</div></div>';
                }
            } else if (category === 'Supervisor') {
                return; // Handled with Core
            } else {
                const categoryEvents = grouped[category];
                if (categoryEvents.length > 0) {
                    listHTML += `
                        <div class="event-category-section">
                            <h3 class="event-category-header">
                                <span class="category-icon">${this.getEventIcon(category)}</span>
                                ${category} Events
                            </h3>
                            <div class="event-category-content">
                                <div class="event-list-header">
                                    <div>Time</div>
                                    <div>Event</div>
                                    <div>Employee</div>
                                    <div>Type</div>
                                    <div>Actions</div>
                                </div>
                                ${categoryEvents.map(event => this.createEventListRow(event)).join('')}
                            </div>
                        </div>
                    `;
                }
            }
        });

        this.eventsContainer.innerHTML = listHTML;

        // Attach event listeners
        this.attachEventListListeners();
    }

    /**
     * Create HTML for a single event list row
     *
     * @param {Object} event - Event object from API
     * @returns {string} HTML string for event list row
     */
    createEventListRow(event) {
        return `
            <div class="event-list-row"
                 data-schedule-id="${event.schedule_id}"
                 data-event-id="${event.event_id}"
                 data-event-type="${event.event_type}"
                 data-employee-id="${event.employee_id}"
                 data-event-name="${this.escapeHtml(event.event_name)}">
                <div class="event-list-row__time">${event.start_time}</div>
                <div class="event-list-row__name" title="${this.escapeHtml(event.event_name)}">${event.event_name}</div>
                <div class="event-list-row__employee">${toTitleCase(event.employee_name)}</div>
                <div class="event-list-row__type">${event.event_type} ${this.getUrgencyBadge(event)}</div>
                <div class="event-list-row__actions">
                    <button class="btn btn-primary btn-sm btn-reschedule-list"
                            data-schedule-id="${event.schedule_id}"
                            title="Reschedule"><span class="material-symbols-outlined">edit_calendar</span></button>
                    <button class="btn btn-secondary btn-sm btn-more-list"
                            data-schedule-id="${event.schedule_id}"
                            title="More actions"><span class="material-symbols-outlined">more_vert</span></button>
                </div>
            </div>
        `;
    }

    /**
     * Attach event listeners to list view buttons
     */
    attachEventListListeners() {
        // Reschedule buttons in list view
        document.querySelectorAll('.btn-reschedule-list').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const scheduleId = e.currentTarget.getAttribute('data-schedule-id');
                this.handleReschedule(scheduleId);
            });
        });

        // More actions buttons in list view
        document.querySelectorAll('.btn-more-list').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const scheduleId = e.currentTarget.getAttribute('data-schedule-id');
                // For now, just open reschedule - could expand to dropdown later
                this.handleReschedule(scheduleId);
            });
        });
    }

    /**
     * Get urgency badge HTML based on days remaining until event due date
     *
     * @param {Object} event - Event object with due_datetime (YYYY-MM-DD)
     * @returns {string} HTML string for urgency badge, or empty string
     */
    getUrgencyBadge(event) {
        if (!event.due_datetime) return '';

        const today = new Date(this.date || new Date().toISOString().split('T')[0]);
        const dueDate = new Date(event.due_datetime);
        const diffMs = dueDate - today;
        // due_datetime means work must be completed BEFORE that day,
        // so subtract 1: if due 2/22 and today is 2/21, that's due today
        const daysRemaining = Math.ceil(diffMs / (1000 * 60 * 60 * 24)) - 1;

        if (daysRemaining < 0) {
            return '<span class="badge-urgency badge-urgency--critical">OVERDUE</span>';
        } else if (daysRemaining === 0) {
            return '<span class="badge-urgency badge-urgency--critical">DUE TODAY</span>';
        } else if (daysRemaining === 1) {
            return '<span class="badge-urgency badge-urgency--high">1 DAY LEFT</span>';
        } else if (daysRemaining <= 3) {
            return `<span class="badge-urgency badge-urgency--medium">${daysRemaining} DAYS LEFT</span>`;
        } else {
            return `<span class="badge-urgency badge-urgency--low">${daysRemaining} DAYS LEFT</span>`;
        }
    }

    /**
     * Create HTML for a single event card
     *
     * @param {Object} event - Event object from API
     * @returns {string} HTML string for event card
     */
    createEventCard(event) {
        // Check for cancelled status from either is_cancelled flag or reporting_status
        const isCancelled = event.is_cancelled || event.reporting_status === 'cancelled';
        const statusBadge = this.getStatusBadge(event.reporting_status, isCancelled);
        const overdueBadge = event.is_overdue ? '<span class="badge-overdue"><span class="material-symbols-outlined">warning</span> OVERDUE</span>' : '';
        const urgencyBadge = this.getUrgencyBadge(event);
        const salesToolLink = event.sales_tool_url
            ? `<a href="${event.sales_tool_url}"
                   target="_blank"
                   rel="noopener noreferrer"
                   class="link-sales-tool"
                   aria-label="View event details in sales tool (opens new tab)">
                 <span class="material-symbols-outlined">open_in_new</span> View Event Details
               </a>`
            : '';

        // Add cancelled class for special styling
        const cancelledClass = isCancelled ? 'event-card--cancelled' : '';

        // Determine if this should be Reissue or Reschedule
        const isReissue = this.shouldShowReissue(event);
        const buttonLabel = isReissue ? 'Reissue' : 'Reschedule';
        const buttonClass = isReissue ? 'btn-reissue' : 'btn-reschedule';

        // Generate unique ID for ARIA labeling
        const cardId = `event-${event.schedule_id}`;

        return `
            <article class="event-card ${cancelledClass}"
                     data-schedule-id="${event.schedule_id}"
                     data-event-id="${event.event_id}"
                     data-event-type="${event.event_type}"
                     data-employee-id="${event.employee_id}"
                     data-event-name="${this.escapeHtml(event.event_name)}"
                     data-is-cancelled="${isCancelled}"
                     data-event-condition="${event.condition || ''}"
                     data-due-datetime="${event.due_datetime || ''}"
                     role="article"
                     aria-labelledby="${cardId}-title"
                     aria-describedby="${cardId}-details">
                <header class="event-card__header">
                    <h3 class="employee-name" id="${cardId}-title">
                        <span class="material-symbols-outlined" aria-hidden="true">person</span>
                        <span class="sr-only">Assigned to </span>
                        ${toTitleCase(event.employee_name)}
                    </h3>
                    ${urgencyBadge}
                    ${overdueBadge}
                </header>

                <div class="event-card__body" id="${cardId}-details">
                    <div class="event-card__details">
                        <div class="event-time" role="text">
                            <span class="material-symbols-outlined" aria-hidden="true">schedule</span>
                            <span class="sr-only">Time: </span>
                            <time datetime="${event.start_time}">${event.start_time}</time> - <time datetime="${event.end_time}">${event.end_time}</time> ${this.getCoreBadge(event.start_time)}
                        </div>
                        <div class="event-info">
                            <span aria-hidden="true">${this.getEventIcon(event.event_type)}</span>
                            <span class="sr-only">Event: </span>
                            ${event.walmart_event_id ? `<span class="walmart-event-id" title="Walmart Event #${event.walmart_event_id}">${event.walmart_event_id}</span> ` : ''}${event.event_name}
                        </div>
                        <div class="event-type-display">
                            <span class="material-symbols-outlined" aria-hidden="true">label</span>
                            <span class="sr-only">Type: </span>
                            ${event.event_type}
                        </div>
                        ${event.start_date ? `<div class="event-dates"><span class="material-symbols-outlined" aria-hidden="true">date_range</span> <span class="sr-only">Event dates: </span>${event.start_date} - ${event.due_date}</div>` : ''}
                        ${salesToolLink}
                    </div>

                    ${this.renderWalmartItems(event, cardId)}

                    <div class="event-divider"></div>

                    <div class="event-card__status" role="status" aria-live="polite">
                        <span class="sr-only">Status: </span>
                        ${statusBadge}
                    </div>

                    <div class="event-divider"></div>
                </div>

                <footer class="event-card__actions">
                    <button class="btn btn-primary ${buttonClass}"
                            data-schedule-id="${event.schedule_id}"
                            aria-label="${buttonLabel} event for ${event.employee_name} at ${event.start_time}">
                        <span aria-hidden="true">${isReissue ? '🔄' : '📅'}</span> ${buttonLabel}
                    </button>
                    <div class="dropdown">
                        <button class="btn btn-secondary dropdown-toggle"
                                aria-label="Additional actions for ${event.employee_name}'s ${event.event_type} event"
                                aria-haspopup="true"
                                aria-expanded="false">
                            <span class="material-symbols-outlined" aria-hidden="true">more_vert</span> More
                        </button>
                        <div class="dropdown-menu" role="menu">
                            <button class="dropdown-item btn-change-employee"
                                    role="menuitem"
                                    data-schedule-id="${event.schedule_id}">
                                Change Employee
                            </button>
                            <button class="dropdown-item btn-change-event-type"
                                    role="menuitem"
                                    data-schedule-id="${event.schedule_id}"
                                    data-event-ref="${event.event_id}"
                                    data-current-type="${event.event_type}"
                                    data-event-name="${event.event_name}">
                                Change Event Type
                            </button>
                            ${event.event_type === 'Core' ? `
                            <button class="dropdown-item btn-trade-event"
                                    role="menuitem"
                                    data-schedule-id="${event.schedule_id}">
                                Trade Event
                            </button>
                            ` : ''}
                            <button class="dropdown-item btn-unschedule"
                                    role="menuitem"
                                    data-schedule-id="${event.schedule_id}">
                                Unschedule
                            </button>
                        </div>
                    </div>
                </footer>
            </article>
        `;
    }

    /**
     * Determine if event should show Reissue button vs Reschedule button
     *
     * Business logic:
     * - Show "Reissue" if event.condition === 'Submitted'
     * - Show "Reissue" if today >= event.due_datetime
     * - Show "Reschedule" otherwise
     *
     * Uses string comparison to avoid timezone issues with Date objects
     *
     * @param {Object} event - Event object with condition and due_datetime
     * @returns {boolean} True to show Reissue, false to show Reschedule
     */
    shouldShowReissue(event) {
        // Check if event has been submitted
        if (event.condition === 'Submitted') {
            return true;
        }

        // Check if today is on or after the due date
        // Use string comparison (YYYY-MM-DD format) to avoid timezone issues
        if (event.due_datetime && this.today) {
            // String comparison works for YYYY-MM-DD format
            // "2026-01-28" >= "2026-01-26" → true
            return this.today >= event.due_datetime;
        }

        // Default to Reschedule
        return false;
    }

    /**
     * Get status badge HTML for reporting status
     *
     * @param {string} status - Reporting status (scheduled, submitted, cancelled)
     * @param {boolean} isCancelled - Whether the event is cancelled in EDR (legacy support)
     * @returns {string} HTML string for status badge
     */
    getStatusBadge(status, isCancelled = false) {
        // Support both the new reporting_status='cancelled' and legacy is_cancelled flag
        if (status === 'cancelled' || isCancelled) {
            return '<span class="status-badge status-cancelled">🔴 CANCELLED</span>';
        }

        const badges = {
            'submitted': '<span class="status-badge status-submitted">🟢 SUBMITTED</span>',
            'scheduled': '<span class="status-badge status-scheduled">🟡 SCHEDULED (Not Reported)</span>'
        };
        return badges[status] || badges['scheduled'];
    }

    renderWalmartItems(event, cardId) {
        if (!event.walmart_items) return '';

        let items;
        try {
            items = JSON.parse(event.walmart_items);
        } catch (e) {
            return '';
        }
        if (!items || items.length === 0) return '';

        const itemRows = items.map(item =>
            `<tr>
                <td>${this.escapeHtml(item.itemNumber || '-')}</td>
                <td>${this.escapeHtml(item.itemDesc || '-')}</td>
                <td>${this.escapeHtml(item.vendorNbr || '-')}</td>
            </tr>`
        ).join('');

        return `
            <div class="event-divider"></div>
            <div class="walmart-items-section">
                <button class="walmart-items-toggle" aria-expanded="false" aria-controls="${cardId}-items"
                        type="button">
                    <span class="material-symbols-outlined" aria-hidden="true">inventory_2</span>
                    Items (${items.length})
                    <span class="material-symbols-outlined toggle-icon" aria-hidden="true">expand_more</span>
                </button>
                <div class="walmart-items-list" id="${cardId}-items" hidden>
                    <table class="walmart-items-table">
                        <thead><tr><th>Item #</th><th>Description</th><th>Vendor</th></tr></thead>
                        <tbody>${itemRows}</tbody>
                    </table>
                </div>
            </div>`;
    }

    /**
     * Attach event listeners to event card buttons
     */
    attachEventCardListeners() {
        // Walmart items toggle
        document.querySelectorAll('.walmart-items-toggle').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const section = e.currentTarget.closest('.walmart-items-section');
                const list = section.querySelector('.walmart-items-list');
                const expanded = e.currentTarget.getAttribute('aria-expanded') === 'true';
                e.currentTarget.setAttribute('aria-expanded', !expanded);
                list.hidden = expanded;
            });
        });

        // Reschedule buttons
        document.querySelectorAll('.btn-reschedule').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const scheduleId = e.currentTarget.getAttribute('data-schedule-id');
                this.handleReschedule(scheduleId);
            });
        });

        // Reissue buttons
        document.querySelectorAll('.btn-reissue').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const scheduleId = e.currentTarget.getAttribute('data-schedule-id');
                this.handleReissue(scheduleId);
            });
        });

        // Dropdown toggles
        document.querySelectorAll('.dropdown-toggle').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const dropdown = e.currentTarget.closest('.dropdown');
                this.toggleDropdown(dropdown);
            });
        });

        // Change employee buttons
        document.querySelectorAll('.btn-change-employee').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const scheduleId = e.currentTarget.getAttribute('data-schedule-id');
                this.handleChangeEmployee(scheduleId);
            });
        });

        // Change event type buttons
        document.querySelectorAll('.btn-change-event-type').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const scheduleId = e.currentTarget.getAttribute('data-schedule-id');
                const eventRef = e.currentTarget.getAttribute('data-event-ref');
                const currentType = e.currentTarget.getAttribute('data-current-type');
                const eventName = e.currentTarget.getAttribute('data-event-name');
                this.handleChangeEventType(scheduleId, eventRef, currentType, eventName);
            });
        });

        // Trade event buttons
        document.querySelectorAll('.btn-trade-event').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const scheduleId = parseInt(e.currentTarget.getAttribute('data-schedule-id'));
                this.handleTradeEvent(scheduleId);
            });
        });

        // Unschedule buttons
        document.querySelectorAll('.btn-unschedule').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const scheduleId = e.currentTarget.getAttribute('data-schedule-id');
                this.handleUnschedule(scheduleId);
            });
        });

        // Close dropdowns when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.dropdown')) {
                this.closeAllDropdowns();
            }
        });

        // Keyboard accessibility for dropdowns
        document.querySelectorAll('.dropdown-toggle').forEach(btn => {
            btn.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    this.closeAllDropdowns();
                }
            });
        });
    }

    /**
     * Toggle dropdown menu open/closed
     *
     * @param {HTMLElement} dropdown - Dropdown container element
     */
    toggleDropdown(dropdown) {
        const isOpen = dropdown.classList.contains('dropdown-open');

        // Close all other dropdowns
        this.closeAllDropdowns();

        // Toggle this dropdown
        if (!isOpen) {
            dropdown.classList.add('dropdown-open');
            const toggle = dropdown.querySelector('.dropdown-toggle');
            toggle.setAttribute('aria-expanded', 'true');
        }
    }

    /**
     * Close all open dropdowns
     */
    closeAllDropdowns() {
        document.querySelectorAll('.dropdown').forEach(dropdown => {
            dropdown.classList.remove('dropdown-open');
            const toggle = dropdown.querySelector('.dropdown-toggle');
            toggle.setAttribute('aria-expanded', 'false');
        });
    }

    /**
     * Handle reschedule button click
     *
     * @param {number} scheduleId - Schedule ID
     */
    async handleReschedule(scheduleId) {
        console.log('Reschedule event:', scheduleId);

        // Get event card to extract event details
        const eventCard = document.querySelector(`[data-schedule-id="${scheduleId}"]`);
        if (!eventCard) {
            this.showNotification('Event not found', 'error');
            return;
        }

        const eventId = eventCard.getAttribute('data-event-id');
        // Use data attributes for reliable data extraction
        const eventName = eventCard.getAttribute('data-event-name') ||
            eventCard.querySelector('.event-info')?.textContent?.trim()?.replace(/^[^\s]+\s/, '') ||
            'Unknown Event';
        const eventType = eventCard.getAttribute('data-event-type') || 'Unknown';
        const currentEmployeeName = eventCard.querySelector('.employee-name')?.textContent?.replace(/person|Assigned to|👤/g, '').trim() || 'Unknown';
        const currentEmployeeId = eventCard.getAttribute('data-employee-id');

        // Get event start time from the <time> element inside event-time
        const startTime = eventCard.querySelector('.event-time time')?.textContent?.trim() || '';

        console.log('Reschedule data:', { eventId, eventName, eventType, currentEmployeeName, currentEmployeeId, startTime });

        // Fetch schedule details to get date constraints (start_date, due_date)
        try {
            const response = await fetch(`/api/schedule/${scheduleId}`);
            if (response.ok) {
                const scheduleDetails = await response.json();

                // Store date constraints for the reschedule modal
                this.currentScheduleConstraints = {
                    startDate: scheduleDetails.start_date,
                    dueDate: scheduleDetails.due_date
                };

                console.log('Schedule constraints:', this.currentScheduleConstraints);
            } else {
                console.warn('Could not fetch schedule details, date constraints will not be applied');
                this.currentScheduleConstraints = null;
            }
        } catch (error) {
            console.error('Error fetching schedule details:', error);
            this.currentScheduleConstraints = null;
        }

        // Open reschedule modal
        await this.openRescheduleModal(scheduleId, eventId, eventName, eventType, startTime, currentEmployeeName, currentEmployeeId, this.date);
    }

    /**
     * Open reschedule modal
     *
     * @param {number} scheduleId - Schedule ID
     * @param {number} eventId - Event ID
     * @param {string} eventName - Event name
     * @param {string} eventType - Event type
     * @param {string} currentTime - Current scheduled time (12-hour format)
     * @param {string} employeeName - Current employee name
     * @param {string} employeeId - Current employee ID
     * @param {string} currentDate - Current date (YYYY-MM-DD)
     */
    async openRescheduleModal(scheduleId, eventId, eventName, eventType, currentTime, employeeName, employeeId, currentDate) {
        try {
            // Store current reschedule context
            this.rescheduleContext = {
                scheduleId,
                eventId,
                eventType,
                eventName,
                currentEmployeeId: employeeId
            };

            document.getElementById('reschedule-schedule-id').value = scheduleId;
            document.getElementById('reschedule-event-info').innerHTML = `
                <strong>${this.escapeHtml(eventName)}</strong> (${this.escapeHtml(eventType)})<br>
                <small>Current: ${currentDate} at ${currentTime} with ${employeeName}</small>
            `;

            // Pre-populate date field with current date
            const dateInput = document.getElementById('reschedule-date');
            if (dateInput) {
                dateInput.value = currentDate;

                // Apply date constraints from schedule details (start_date/due_date)
                if (this.currentScheduleConstraints) {
                    if (this.currentScheduleConstraints.startDate) {
                        dateInput.min = this.currentScheduleConstraints.startDate;
                    }
                    if (this.currentScheduleConstraints.dueDate) {
                        dateInput.max = this.currentScheduleConstraints.dueDate;
                    }
                    console.log('Applied date constraints:', dateInput.min, 'to', dateInput.max);
                } else {
                    // No constraints - remove any existing min/max
                    dateInput.removeAttribute('min');
                    dateInput.removeAttribute('max');
                }
            }

            // Convert displayed time to 24-hour format
            const time24 = this.convertTo24Hour(currentTime);

            // Pre-populate time field with current time
            const timeInput = document.getElementById('reschedule-time');
            if (timeInput && time24) {
                timeInput.value = time24;
            }

            // IMPORTANT: Reset override checkbox BEFORE setting up restrictions
            // This ensures the checkbox state matches the UI behavior
            const overrideCheckbox = document.getElementById('reschedule-override-constraints');
            if (overrideCheckbox) {
                overrideCheckbox.checked = false;
            }

            // Set up time restrictions for event type (async - fetches from API)
            await this.setupTimeRestrictions('reschedule', eventType, time24, eventName);

            // Load available employees and pre-select current employee
            await this.loadAvailableEmployeesForReschedule('reschedule-employee', currentDate, eventType, employeeId);

            document.getElementById('reschedule-modal').style.display = 'flex';
        } catch (error) {
            console.error('Error opening reschedule modal:', error);
            this.showNotification('Error opening reschedule modal', 'error');
        }
    }

    /**
     * Close reschedule modal
     */
    closeRescheduleModal() {
        document.getElementById('reschedule-modal').style.display = 'none';
    }

    /* ===================================================================
       Reissue Event Methods
       =================================================================== */

    /**
     * Handle reissue event button click
     *
     * @param {number} scheduleId - Schedule ID
     */
    async handleReissue(scheduleId) {
        console.log('Reissue event:', scheduleId);

        // Get event card to extract event details
        const eventCard = document.querySelector(`[data-schedule-id="${scheduleId}"]`);
        if (!eventCard) {
            this.showNotification('Event not found', 'error');
            return;
        }

        const eventId = eventCard.getAttribute('data-event-id');
        const eventName = eventCard.getAttribute('data-event-name') ||
            eventCard.querySelector('.event-info')?.textContent?.trim()?.replace(/^[^\s]+\s/, '') ||
            'Unknown Event';
        const eventType = eventCard.getAttribute('data-event-type') || 'Unknown';
        const currentEmployeeName = eventCard.querySelector('.employee-name')?.textContent?.replace(/👤|person/g, '').trim() || 'Unknown';
        const currentEmployeeId = eventCard.getAttribute('data-employee-id');

        // Get event datetime from card
        const timeText = eventCard.querySelector('.event-time')?.textContent || '';
        const timeMatch = timeText.match(/(\d{1,2}:\d{2}\s[AP]M)/);
        const startTime = timeMatch ? timeMatch[1] : '';

        console.log('Reissue data:', { eventId, eventName, eventType, currentEmployeeName, currentEmployeeId, startTime });

        // Open reissue modal
        await this.openReissueModal(scheduleId, eventId, eventName, eventType, startTime, currentEmployeeName, currentEmployeeId, this.date);
    }

    /**
     * Open reissue modal
     *
     * @param {number} scheduleId - Schedule ID
     * @param {number} eventId - Event ID
     * @param {string} eventName - Event name
     * @param {string} eventType - Event type
     * @param {string} currentTime - Current scheduled time (12-hour format)
     * @param {string} employeeName - Current employee name
     * @param {string} employeeId - Current employee ID
     * @param {string} currentDate - Current date (YYYY-MM-DD)
     */
    async openReissueModal(scheduleId, eventId, eventName, eventType, currentTime, employeeName, employeeId, currentDate) {
        try {
            // Store current reissue context
            this.reissueContext = {
                scheduleId,
                eventId,
                eventType,
                eventName,
                currentEmployeeId: employeeId
            };

            document.getElementById('reissue-schedule-id').value = scheduleId;
            document.getElementById('reissue-event-info').innerHTML = `
                <strong>${this.escapeHtml(eventName)}</strong> (${this.escapeHtml(eventType)})<br>
                <small>Current: ${currentDate} at ${currentTime} with ${employeeName}</small>
            `;

            // Set default date and time to current schedule
            document.getElementById('reissue-date').value = currentDate;

            // Convert 12-hour to 24-hour format for time input
            const time24 = this.convertTo24Hour(currentTime);
            document.getElementById('reissue-time').value = time24;

            // Load available employees
            await this.loadEmployeesForReissue();

            // Pre-select current employee if available
            if (employeeId) {
                document.getElementById('reissue-employee').value = employeeId;
            }

            // Show modal
            document.getElementById('reissue-modal').style.display = 'flex';
            document.body.style.overflow = 'hidden';
        } catch (error) {
            console.error('Error opening reissue modal:', error);
            this.showNotification('Failed to open reissue modal', 'error');
        }
    }

    /**
     * Close reissue modal
     */
    closeReissueModal() {
        document.getElementById('reissue-modal').style.display = 'none';
        document.body.style.overflow = '';
    }

    /**
     * Load employees for reissue dropdown
     */
    async loadEmployeesForReissue() {
        try {
            const response = await fetch('/api/employees/active');
            if (response.ok) {
                const employees = await response.json();
                const select = document.getElementById('reissue-employee');
                select.innerHTML = '<option value="">Select employee...</option>';

                employees.forEach(emp => {
                    const option = document.createElement('option');
                    option.value = emp.id;
                    option.textContent = `${emp.name} (${emp.job_title})`;
                    select.appendChild(option);
                });
            }
        } catch (error) {
            console.error('Error loading employees for reissue:', error);
        }
    }

    /* ===================================================================
       Bulk Reassign Supervisor Events Methods
       =================================================================== */

    /**
     * Open bulk reassign supervisor events modal
     */
    openBulkReassignModal() {
        const modal = document.getElementById('bulk-reassign-modal');
        if (modal) {
            modal.style.display = 'flex';
            document.body.style.overflow = 'hidden';
        }
    }

    /**
     * Close bulk reassign supervisor events modal
     */
    closeBulkReassignModal() {
        const modal = document.getElementById('bulk-reassign-modal');
        const errorDiv = document.getElementById('bulk-reassign-error');
        const previewDiv = document.getElementById('bulk-reassign-preview');

        if (modal) {
            modal.style.display = 'none';
            document.body.style.overflow = '';
        }

        // Clear any errors
        if (errorDiv) {
            errorDiv.style.display = 'none';
            errorDiv.textContent = '';
        }

        // Clear preview
        if (previewDiv) {
            previewDiv.style.display = 'none';
        }

        // Reset form
        const form = document.getElementById('bulk-reassign-form');
        if (form) {
            form.reset();
        }
    }

    /**
     * Submit bulk reassignment of supervisor events
     */
    async submitBulkReassign(event) {
        event.preventDefault();

        const employeeSelect = document.getElementById('bulk-reassign-employee');
        const errorDiv = document.getElementById('bulk-reassign-error');
        const newEmployeeId = employeeSelect ? employeeSelect.value : '';

        // Validate employee selection - check for empty string
        if (!newEmployeeId || newEmployeeId.trim() === '') {
            errorDiv.textContent = 'Please select an employee';
            errorDiv.style.display = 'block';
            return;
        }

        // Ensure we have a valid date - fallback to DOM if this.date is not set
        let dateToUse = this.date;
        if (!dateToUse) {
            const dateElement = document.querySelector('[data-selected-date]');
            dateToUse = dateElement ? dateElement.getAttribute('data-selected-date') : null;
        }

        if (!dateToUse) {
            errorDiv.textContent = 'Unable to determine the date for reassignment';
            errorDiv.style.display = 'block';
            return;
        }

        // Clear any previous errors
        errorDiv.style.display = 'none';

        // Show loading state
        const submitBtn = event.target.querySelector('button[type="submit"]');
        const originalText = submitBtn.textContent;
        submitBtn.disabled = true;
        submitBtn.textContent = 'Reassigning...';

        try {
            // Get CSRF token
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';

            // Get override checkbox value
            const overrideCheckbox = document.getElementById('bulk-reassign-override');
            const overrideConstraints = overrideCheckbox ? overrideCheckbox.checked : false;

            // Call bulk reassignment API
            const response = await fetch('/api/bulk-reassign-supervisor-events', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': csrfToken
                },
                body: JSON.stringify({
                    date: dateToUse,
                    new_employee_id: newEmployeeId,
                    override_constraints: overrideConstraints
                })
            });

            const data = await response.json();

            if (!response.ok) {
                // Handle error
                const errorMessage = data.error || 'Failed to reassign supervisor events';
                errorDiv.textContent = errorMessage;
                errorDiv.style.display = 'block';
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
                return;
            }

            // Success
            this.showNotification(data.message, 'success');
            this.closeBulkReassignModal();

            // Reload the daily view data
            await this.init();

        } catch (error) {
            console.error('Failed to bulk reassign supervisor events:', error);
            errorDiv.textContent = 'Failed to reassign supervisor events. Please try again.';
            errorDiv.style.display = 'block';
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
        }
    }

    /**
     * Setup time restrictions based on event type (fetches from settings API)
     *
     * @param {string} prefix - Form field prefix
     * @param {string} eventType - Event type
     * @param {string} currentTime - Current time in 24-hour format
     * @param {string} eventName - Optional event name for teardown detection
     */
    async setupTimeRestrictions(prefix, eventType, currentTime, eventName = null) {
        const timeInput = document.getElementById(`${prefix}-time`);
        const timeDropdown = document.getElementById(`${prefix}-time-dropdown`);
        const overrideCheckbox = document.getElementById('reschedule-override-constraints');

        // Check if override is active
        if (overrideCheckbox && overrideCheckbox.checked) {
            // Override active: Show free-form time input
            timeInput.style.display = 'block';
            timeInput.required = true;
            timeDropdown.style.display = 'none';
            timeDropdown.required = false;
            timeDropdown.classList.add('hidden');

            if (currentTime) {
                timeInput.value = currentTime;
            }
            return; // Skip fetching restrictions
        }

        try {
            // Fetch allowed times from settings API with date for schedule counts
            const dateInput = document.getElementById(`${prefix}-date`);
            const selectedDate = dateInput ? dateInput.value : '';
            let url = `/api/event-allowed-times/${encodeURIComponent(eventType)}`;
            const params = [];
            if (selectedDate) {
                params.push(`date=${encodeURIComponent(selectedDate)}`);
            }
            if (eventName) {
                params.push(`event_name=${encodeURIComponent(eventName)}`);
            }
            if (params.length > 0) {
                url += '?' + params.join('&');
            }
            const response = await fetch(url);
            const data = await response.json();

            if (data.success && data.has_restrictions && data.allowed_times.length > 0) {
                // Show dropdown with restricted times
                timeInput.style.display = 'none';
                timeInput.required = false;
                timeDropdown.style.display = 'block';
                timeDropdown.required = true;
                timeDropdown.classList.remove('hidden');

                timeDropdown.innerHTML = '<option value="">Select a time</option>';

                // Use time_details if available (includes schedule counts)
                if (data.time_details && data.time_details.length > 0) {
                    data.time_details.forEach(detail => {
                        const option = document.createElement('option');
                        option.value = detail.value;
                        option.textContent = detail.label; // e.g. "9:15 AM (2 scheduled)"
                        if (currentTime && detail.value === currentTime) {
                            option.selected = true;
                        }
                        timeDropdown.appendChild(option);
                    });
                } else {
                    // Fallback to plain times
                    data.allowed_times.forEach(time => {
                        const option = document.createElement('option');
                        option.value = time;
                        option.textContent = this.formatTime(time);
                        if (currentTime && time === currentTime) {
                            option.selected = true;
                        }
                        timeDropdown.appendChild(option);
                    });
                }

                // If current time not in allowed times, select the first allowed time
                if (currentTime && !data.allowed_times.includes(currentTime) && data.allowed_times.length > 0) {
                    timeDropdown.value = data.allowed_times[0];
                }
            } else {
                // No restrictions - show free-form time input
                timeInput.style.display = 'block';
                timeInput.required = true;
                timeDropdown.style.display = 'none';
                timeDropdown.required = false;
                timeDropdown.classList.add('hidden');

                // Set current time if available
                if (currentTime) {
                    timeInput.value = currentTime;
                }
            }
        } catch (error) {
            console.error('Error fetching time restrictions:', error);
            // Fallback: show free-form time input
            timeInput.style.display = 'block';
            timeInput.required = true;
            timeDropdown.style.display = 'none';
            timeDropdown.required = false;
            timeDropdown.classList.add('hidden');

            if (currentTime) {
                timeInput.value = currentTime;
            }
        }
    }

    /**
     * Format time from 24-hour to 12-hour format
     *
     * @param {string} time24 - Time in 24-hour format (HH:MM)
     * @returns {string} Time in 12-hour format
     */
    formatTime(time24) {
        const [hours, minutes] = time24.split(':');
        const hour = parseInt(hours);
        const ampm = hour >= 12 ? 'PM' : 'AM';
        const displayHour = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
        return `${displayHour}:${minutes} ${ampm}`;
    }

    /**
     * Convert 12-hour time to 24-hour format
     *
     * @param {string} time12 - Time in 12-hour format
     * @returns {string} Time in 24-hour format
     */
    convertTo24Hour(time12) {
        if (!time12 || !time12.includes(':')) {
            return time12;
        }

        const [time, modifier] = time12.split(' ');
        if (!modifier) {
            return time12; // Already in 24-hour format
        }

        const [hours, minutes] = time.split(':');
        let hour = parseInt(hours);

        if (modifier.toUpperCase() === 'PM' && hour !== 12) {
            hour += 12;
        } else if (modifier.toUpperCase() === 'AM' && hour === 12) {
            hour = 0;
        }

        return `${hour.toString().padStart(2, '0')}:${minutes}`;
    }

    /**
     * Load available employees for rescheduling
     *
     * @param {string} selectId - Select element ID
     * @param {string} date - Date for availability check
     * @param {string} eventType - Event type
     * @param {number} currentEmployeeId - Current employee ID
     */
    async loadAvailableEmployeesForReschedule(selectId, date, eventType, currentEmployeeId) {
        const select = document.getElementById(selectId);
        select.innerHTML = '<option value="">Loading...</option>';

        try {
            let apiUrl = `/api/available_employees_for_change/${date}/${eventType}`;
            let params = [];

            if (currentEmployeeId) {
                params.push(`current_employee_id=${currentEmployeeId}`);
                params.push(`current_date=${date}`);
            }

            // Check override status
            const overrideCheckbox = document.getElementById('reschedule-override-constraints');
            if (overrideCheckbox && overrideCheckbox.checked) {
                params.push('override=true');
            }

            if (params.length > 0) {
                apiUrl += '?' + params.join('&');
            }

            const response = await fetch(apiUrl);
            const employees = await response.json();

            select.innerHTML = '<option value="">Select an employee</option>';
            employees.forEach(employee => {
                const option = document.createElement('option');
                option.value = employee.id;
                option.textContent = `${employee.name} (${employee.job_title})`;
                // Pre-select current employee
                if (currentEmployeeId && employee.id === currentEmployeeId) {
                    option.selected = true;
                }
                select.appendChild(option);
            });

            // If current employee wasn't in the list, ensure we still have them selected
            if (currentEmployeeId && !select.value) {
                console.log('Current employee not in available list, adding to dropdown');
            }
        } catch (error) {
            console.error('Error loading employees:', error);
            select.innerHTML = '<option value="">Error loading employees</option>';
        }
    }

    /**
     * Handle change employee button click (Story 3.7)
     *
     * Opens a modal with available employees dropdown and handles
     * the employee change with conflict validation.
     *
     * @param {number} scheduleId - Schedule ID
     */
    async handleChangeEmployee(scheduleId) {
        console.log('Change employee:', scheduleId);

        // Get event card to extract event details
        const eventCard = document.querySelector(`[data-schedule-id="${scheduleId}"]`);
        if (!eventCard) {
            this.showNotification('Event not found', 'error');
            return;
        }

        const eventId = eventCard.getAttribute('data-event-id');
        const currentEmployeeName = eventCard.querySelector('.employee-name')?.textContent?.replace(/person|Assigned to|👤/g, '').trim() || 'Unknown';

        // Get event start time from the <time> element inside event-time
        const startTime = eventCard.querySelector('.event-time time')?.textContent?.trim() || '';

        // Open change employee modal
        await this.openChangeEmployeeModal(scheduleId, eventId, currentEmployeeName, this.date, startTime);
    }

    /**
     * Open change employee modal (Story 3.7)
     *
     * @param {number} scheduleId - Schedule ID
     * @param {number} eventId - Event ID
     * @param {string} currentEmployeeName - Current employee name
     * @param {string} date - Event date (YYYY-MM-DD)
     * @param {string} time - Event time (e.g., "10:00 AM")
     */
    async openChangeEmployeeModal(scheduleId, eventId, currentEmployeeName, date, time) {
        // Create modal HTML
        const modalHtml = `
            <div class="modal modal-open" id="change-employee-modal" role="dialog" aria-labelledby="change-employee-title" aria-modal="true">
                <div class="modal-overlay"></div>
                <div class="modal-container modal-container--medium">
                    <div class="modal-header">
                        <h2 id="change-employee-title" class="modal-title">Change Employee Assignment</h2>
                        <button class="modal-close" aria-label="Close modal">✕</button>
                    </div>
                    <div class="modal-body">
                        <div class="current-assignment">
                            <label class="form-label">Current Assignment:</label>
                            <div class="current-employee-display">
                                <span class="employee-icon">👤</span>
                                <strong>${this.escapeHtml(currentEmployeeName)}</strong>
                            </div>
                        </div>

                        <div class="form-group">
                            <label for="new-employee-select" class="form-label">New Employee:</label>
                            <select id="new-employee-select" class="form-select" required>
                                <option value="">Loading available employees...</option>
                            </select>
                            <div class="form-help">Only showing employees with no conflicts at this time</div>
                        </div>

                        <div id="conflict-error" class="error-message" style="display: none;" role="alert"></div>

                        <div class="loading-spinner" id="loading-employees" role="status">
                            <span class="sr-only">Loading available employees...</span>
                            Loading...
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary modal-cancel">Cancel</button>
                        <button type="button" class="btn btn-primary modal-submit" disabled>Change Employee</button>
                    </div>
                </div>
            </div>
        `;

        // Insert modal into DOM
        const existingModal = document.getElementById('change-employee-modal');
        if (existingModal) {
            existingModal.remove();
        }
        document.body.insertAdjacentHTML('beforeend', modalHtml);

        const modal = document.getElementById('change-employee-modal');

        // Load available employees
        await this.loadAvailableEmployees(date, time, modal);

        // Prevent body scroll
        document.body.style.overflow = 'hidden';

        // Setup event listeners
        this.setupChangeEmployeeModalListeners(modal, scheduleId);

        // Focus first focusable element
        const firstInput = modal.querySelector('#new-employee-select');
        if (firstInput) {
            firstInput.focus();
        }
    }

    /**
     * Load available employees into dropdown (Story 3.7)
     *
     * @param {string} date - Event date (YYYY-MM-DD)
     * @param {string} time - Event time (e.g., "10:00 AM")
     * @param {HTMLElement} modal - Modal element
     */
    async loadAvailableEmployees(date, time, modal) {
        const select = modal.querySelector('#new-employee-select');
        const loadingSpinner = modal.querySelector('#loading-employees');

        try {
            // Convert time from "10:00 AM" to "10:00" (24-hour format)
            const time24 = this.convertTo24Hour(time);

            const response = await fetch(
                `/api/available-employees?date=${date}&time=${time24}&duration=120`,
                {
                    method: 'GET',
                    headers: {
                        'X-CSRF-Token': this.getCsrfToken()
                    }
                }
            );

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();

            // Hide loading spinner
            loadingSpinner.style.display = 'none';

            // Populate dropdown
            if (data.available_employees.length === 0) {
                select.innerHTML = '<option value="">No available employees</option>';
                select.disabled = true;
            } else {
                select.innerHTML = '<option value="">-- Select an employee --</option>';
                data.available_employees.forEach(emp => {
                    const option = document.createElement('option');
                    option.value = emp.employee_id;
                    option.textContent = emp.employee_name;
                    select.appendChild(option);
                });
                select.disabled = false;
            }

        } catch (error) {
            console.error('Failed to load available employees:', error);
            loadingSpinner.style.display = 'none';
            select.innerHTML = '<option value="">Error loading employees</option>';
            select.disabled = true;
            this.showModalError(modal, 'Failed to load available employees. Please try again.');
        }
    }

    /**
     * Setup change employee modal event listeners (Story 3.7)
     *
     * @param {HTMLElement} modal - Modal element
     * @param {number} scheduleId - Schedule ID
     */
    setupChangeEmployeeModalListeners(modal, scheduleId) {
        const closeBtn = modal.querySelector('.modal-close');
        const cancelBtn = modal.querySelector('.modal-cancel');
        const submitBtn = modal.querySelector('.modal-submit');
        const overlay = modal.querySelector('.modal-overlay');
        const select = modal.querySelector('#new-employee-select');

        // Close handlers
        const closeModal = () => this.closeChangeEmployeeModal(modal);

        closeBtn.addEventListener('click', closeModal);
        cancelBtn.addEventListener('click', closeModal);
        overlay.addEventListener('click', closeModal);

        // Escape key handler
        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                closeModal();
            }
        };
        document.addEventListener('keydown', handleEscape);
        modal._escapeHandler = handleEscape; // Store for cleanup

        // Enable submit button when employee selected
        select.addEventListener('change', () => {
            submitBtn.disabled = !select.value;
        });

        // Submit handler
        submitBtn.addEventListener('click', async () => {
            const newEmployeeId = select.value;
            if (!newEmployeeId) return;

            await this.submitChangeEmployee(scheduleId, newEmployeeId, modal);
        });
    }

    /**
     * Submit change employee request (Story 3.7)
     *
     * @param {number} scheduleId - Schedule ID
     * @param {string} newEmployeeId - New employee ID
     * @param {HTMLElement} modal - Modal element
     * @param {boolean} overrideConflicts - Whether to override conflicts
     */
    async submitChangeEmployee(scheduleId, newEmployeeId, modal, overrideConflicts = false) {
        const submitBtn = modal.querySelector('.modal-submit');
        const originalText = submitBtn.textContent;

        try {
            // Show loading state
            submitBtn.disabled = true;
            submitBtn.textContent = 'Changing...';

            const response = await fetch(`/api/event/${scheduleId}/change-employee`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': this.getCsrfToken()
                },
                body: JSON.stringify({
                    new_employee_id: newEmployeeId,
                    override_conflicts: overrideConflicts
                })
            });

            const result = await response.json();

            if (response.status === 409) {
                // Conflict detected - show conflicts with override option
                this.showModalConflictsWithOverride(
                    modal,
                    'Employee Change Conflicts',
                    result.conflicts,
                    () => this.submitChangeEmployee(scheduleId, newEmployeeId, modal, true)
                );
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
                return;
            }

            if (!response.ok) {
                throw new Error(result.error || 'Failed to change employee');
            }

            // Success
            const warningMsg = overrideConflicts ? ' (conflicts overridden)' : '';
            this.showNotification(
                `Employee changed from ${result.old_employee_name} to ${result.new_employee_name}${warningMsg}`,
                overrideConflicts ? 'warning' : 'success'
            );

            // Update event card UI with new employee name
            this.updateEventCardEmployee(scheduleId, result.new_employee_name);

            // Close modal
            this.closeChangeEmployeeModal(modal);

            // Optionally reload daily summary if needed
            // await this.loadDailySummary();

        } catch (error) {
            console.error('Failed to change employee:', error);
            this.showModalError(modal, error.message);
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
        }
    }

    /**
     * Update event card with new employee name (Story 3.7)
     *
     * @param {number} scheduleId - Schedule ID
     * @param {string} newEmployeeName - New employee name
     */
    updateEventCardEmployee(scheduleId, newEmployeeName) {
        const eventCard = document.querySelector(`[data-schedule-id="${scheduleId}"]`);
        if (!eventCard) return;

        const employeeNameEl = eventCard.querySelector('.employee-name');
        if (employeeNameEl) {
            employeeNameEl.textContent = `👤 ${newEmployeeName.toUpperCase()}`;
        }
    }

    /**
     * Show error in modal (Story 3.7)
     *
     * @param {HTMLElement} modal - Modal element
     * @param {string} message - Error message
     * @param {Array} conflicts - Optional array of conflict objects
     */
    showModalError(modal, message, conflicts = null) {
        const errorDiv = modal.querySelector('#conflict-error');
        if (!errorDiv) return;

        errorDiv.style.display = 'block';

        if (conflicts && conflicts.length > 0) {
            const conflictList = conflicts.map(c =>
                `<li class="conflict-${c.severity}">
                    <span class="icon">${c.severity === 'error' ? '✕' : '⚠️'}</span>
                    ${this.escapeHtml(c.message)}
                </li>`
            ).join('');

            errorDiv.innerHTML = `
                <strong>${this.escapeHtml(message)}</strong>
                <ul class="conflict-list">
                    ${conflictList}
                </ul>
            `;
        } else {
            errorDiv.innerHTML = `<span class="icon">✕</span> ${this.escapeHtml(message)}`;
        }
    }

    /**
     * Show modal conflicts with override option
     *
     * @param {HTMLElement} modal - Modal element
     * @param {string} title - Conflict title
     * @param {Array} conflicts - Array of conflicts
     * @param {Function} overrideCallback - Function to call when override is clicked
     */
    showModalConflictsWithOverride(modal, title, conflicts, overrideCallback) {
        const errorDiv = modal.querySelector('#conflict-error');
        if (!errorDiv) return;

        errorDiv.style.display = 'block';

        const conflictList = conflicts.map(c =>
            `<li class="conflict-${c.severity}">
                <span class="icon">${c.severity === 'hard' ? '✕' : '⚠️'}</span>
                ${this.escapeHtml(c.message)}
            </li>`
        ).join('');

        errorDiv.innerHTML = `
            <div class="conflict-warning">
                <strong>${this.escapeHtml(title)}</strong>
                <ul class="conflict-list">
                    ${conflictList}
                </ul>
                <div class="conflict-actions" style="margin-top: 15px; display: flex; gap: 10px; justify-content: flex-end;">
                    <button class="btn btn-secondary conflict-cancel" style="padding: 8px 16px;">Cancel</button>
                    <button class="btn btn-warning conflict-override" style="padding: 8px 16px; background: #ff9800; border-color: #ff9800;">
                        ⚠️ Override and Continue
                    </button>
                </div>
            </div>
        `;

        // Setup event listeners for override buttons
        const cancelBtn = errorDiv.querySelector('.conflict-cancel');
        const overrideBtn = errorDiv.querySelector('.conflict-override');

        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => {
                errorDiv.style.display = 'none';
                errorDiv.innerHTML = '';
            });
        }

        if (overrideBtn) {
            overrideBtn.addEventListener('click', () => {
                errorDiv.style.display = 'none';
                errorDiv.innerHTML = '';
                if (overrideCallback) {
                    overrideCallback();
                }
            });
        }
    }

    /**
     * Close change employee modal (Story 3.7)
     *
     * @param {HTMLElement} modal - Modal element
     */
    closeChangeEmployeeModal(modal) {
        if (!modal) return;

        // Remove escape key handler
        if (modal._escapeHandler) {
            document.removeEventListener('keydown', modal._escapeHandler);
        }

        // Hide modal
        modal.classList.remove('modal-open');
        modal.setAttribute('aria-hidden', 'true');

        // Restore body scroll
        document.body.style.overflow = '';

        // Remove modal from DOM after animation
        setTimeout(() => {
            modal.remove();
        }, 200);
    }

    /**
     * Convert 12-hour time to 24-hour format (Story 3.7)
     *
     * @param {string} time12 - Time in 12-hour format (e.g., "10:00 AM")
     * @returns {string} Time in 24-hour format (e.g., "10:00")
     */
    convertTo24Hour(time12) {
        const [time, period] = time12.split(' ');
        let [hours, minutes] = time.split(':');
        hours = parseInt(hours);

        if (period === 'PM' && hours !== 12) {
            hours += 12;
        } else if (period === 'AM' && hours === 12) {
            hours = 0;
        }

        return `${hours.toString().padStart(2, '0')}:${minutes}`;
    }

    /**
     * Handle change event type button click
     *
     * Opens a modal to change the event type with persistence through database refreshes.
     *
     * @param {number} scheduleId - Schedule ID
     * @param {number} eventRef - Event reference number (project_ref_num)
     * @param {string} currentType - Current event type
     * @param {string} eventName - Event name
     */
    handleChangeEventType(scheduleId, eventRef, currentType, eventName) {
        const modal = document.getElementById('change-event-type-modal');
        if (!modal) {
            console.error('Change event type modal not found');
            return;
        }

        document.getElementById('change-type-event-ref').value = eventRef;
        document.getElementById('change-type-schedule-id').value = scheduleId;
        document.getElementById('change-type-event-info').textContent = eventName;
        document.getElementById('change-type-current').textContent = currentType;
        document.getElementById('change-type-new-type').value = '';
        document.getElementById('change-type-reason').value = '';
        modal.style.display = 'flex';
    }

    /**
     * Submit event type change to backend
     */
    async submitEventTypeChange() {
        const eventRef = document.getElementById('change-type-event-ref').value;
        const newType = document.getElementById('change-type-new-type').value;
        const reason = document.getElementById('change-type-reason').value;

        if (!newType) {
            window.toaster.warning('Please select a new event type');
            return;
        }

        try {
            const response = await fetch(`/api/event/${eventRef}/change-type`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({new_event_type: newType, reason: reason})
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to change event type');
            }

            const result = await response.json();
            this.closeChangeEventTypeModal();
            this.showSuccessMessage(`Event type changed to ${newType}`);
            await this.loadDailyEvents();  // Reload to show changes
        } catch (error) {
            window.toaster.error(`Error: ${error.message}`);
        }
    }

    /**
     * Close the change event type modal
     */
    closeChangeEventTypeModal() {
        const modal = document.getElementById('change-event-type-modal');
        if (modal) {
            modal.style.display = 'none';
        }
    }

    /**
     * Show a success notification toast
     */
    showSuccessMessage(message) {
        const toast = document.createElement('div');
        toast.className = 'toast-notification';
        toast.textContent = message;
        toast.style.cssText = 'position:fixed;top:20px;right:20px;background:#28a745;color:white;padding:15px 20px;border-radius:8px;z-index:10000;';
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }

    /**
     * Handle trade event button click (Story 3.8)
     *
     * Opens a modal to trade employee assignments with another event on the same day.
     * Uses ConflictValidator to validate both employees before swapping.
     *
     * @param {number} scheduleId - Schedule ID
     */
    async handleTradeEvent(scheduleId) {
        console.log('Trade event:', scheduleId);

        // Get event card to extract details
        const eventCard = document.querySelector(`[data-schedule-id="${scheduleId}"]`);
        if (!eventCard) {
            this.showNotification('Event not found', 'error');
            return;
        }

        // Validate that this is a Core event (only Core events can be traded)
        const eventType = eventCard.getAttribute('data-event-type');
        if (eventType !== 'Core') {
            this.showNotification('Only Core events can be traded', 'error');
            return;
        }

        const eventId = eventCard.getAttribute('data-event-id');
        const employeeName = eventCard.querySelector('.employee-name')?.textContent?.replace(/person|Assigned to|👤/g, '').trim() || 'Unknown';
        const eventName = eventCard.querySelector('.event-info')?.textContent;

        // Extract start/end times from <time> elements inside event-time
        const timeElements = eventCard.querySelectorAll('.event-time time');
        const startTime = timeElements[0]?.textContent?.trim() || '';
        const endTime = timeElements[1]?.textContent?.trim() || '';
        const datetime = `${this.date} ${this.convertTo24Hour(startTime)}`;

        // Open trade modal
        await this.openTradeEventModal({
            schedule_id: scheduleId,
            event_id: eventId,
            employee_name: employeeName,
            event_name: eventName,
            event_type: eventType,
            datetime: datetime,
            start_time: startTime,
            end_time: endTime,
            date: this.date
        });
    }

    /**
     * Open trade event modal (Story 3.8)
     *
     * @param {Object} sourceEvent - Source event data
     */
    async openTradeEventModal(sourceEvent) {
        const modalHtml = `
            <div class="modal modal-open" id="trade-event-modal" role="dialog" aria-labelledby="trade-modal-title" aria-modal="true">
                <div class="modal-overlay"></div>
                <div class="modal-container modal-container--large">
                    <div class="modal-header">
                        <h2 id="trade-modal-title" class="modal-title">Trade Event Assignment</h2>
                        <button class="modal-close" aria-label="Close modal">✕</button>
                    </div>
                    <div class="modal-body">
                        <!-- Source Event Display -->
                        <div class="trade-source-event">
                            <h3 class="trade-section-title">Current Event:</h3>
                            <div class="trade-event-card trade-event-card--source">
                                <div class="trade-event-employee">👤 ${this.escapeHtml(sourceEvent.employee_name)}</div>
                                <div class="trade-event-time">⏰ ${sourceEvent.start_time} - ${sourceEvent.end_time}</div>
                                <div class="trade-event-name">${this.escapeHtml(sourceEvent.event_name || 'Event')}</div>
                            </div>
                        </div>

                        <div class="trade-divider">
                            <span class="trade-divider-text">Trade with</span>
                        </div>

                        <!-- Target Events List -->
                        <div class="trade-target-events">
                            <h3 class="trade-section-title">Select Event to Trade With:</h3>
                            <div id="trade-events-list" class="trade-events-list">
                                <div class="loading-spinner" role="status">
                                    <span class="sr-only">Loading events...</span>
                                    Loading events...
                                </div>
                            </div>
                        </div>

                        <!-- Error Display -->
                        <div id="trade-error" class="error-message" style="display: none;" role="alert"></div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary modal-cancel">Cancel</button>
                        <button type="button" class="btn btn-primary modal-submit" id="btn-execute-trade" disabled>Execute Trade</button>
                    </div>
                </div>
            </div>
        `;

        // Insert modal into DOM
        const existingModal = document.getElementById('trade-event-modal');
        if (existingModal) {
            existingModal.remove();
        }
        document.body.insertAdjacentHTML('beforeend', modalHtml);

        const modal = document.getElementById('trade-event-modal');

        // Load available events to trade with
        await this.loadTradeableEvents(sourceEvent.schedule_id, modal);

        // Prevent body scroll
        document.body.style.overflow = 'hidden';

        // Setup event listeners
        this.setupTradeEventModalListeners(modal, sourceEvent.schedule_id);
    }

    /**
     * Load events available for trading (Story 3.8)
     *
     * @param {number} sourceScheduleId - Source schedule ID to exclude
     * @param {HTMLElement} modal - Modal element
     */
    async loadTradeableEvents(sourceScheduleId, modal) {
        const eventsList = modal.querySelector('#trade-events-list');
        const executeBtn = modal.querySelector('#btn-execute-trade');

        try {
            // Fetch events for the same date
            const response = await fetch(`/api/daily-events/${this.date}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();

            // Filter out source event and empty events
            const tradeableEvents = data.events.filter(event =>
                event.schedule_id !== sourceScheduleId
            );

            if (tradeableEvents.length === 0) {
                // No other events available
                eventsList.innerHTML = `
                    <div class="empty-state" role="status">
                        <p class="empty-state__message">No other events available to trade on this date</p>
                    </div>
                `;
                executeBtn.disabled = true;
            } else {
                // Render event cards
                this.renderTradeableEvents(tradeableEvents, eventsList);
            }

        } catch (error) {
            console.error('Failed to load tradeable events:', error);
            eventsList.innerHTML = `
                <div class="error-message" role="alert">
                    <span class="icon">✕</span>
                    Failed to load events. Please try again.
                </div>
            `;
            executeBtn.disabled = true;
        }
    }

    /**
     * Render tradeable events list (Story 3.8)
     *
     * @param {Array} events - Array of event objects
     * @param {HTMLElement} container - Container element
     */
    renderTradeableEvents(events, container) {
        const eventsHtml = events.map(event => `
            <div class="trade-event-card"
                 data-schedule-id="${event.schedule_id}"
                 role="radio"
                 aria-checked="false"
                 tabindex="0">
                <div class="trade-event-employee">👤 ${this.escapeHtml(event.employee_name)}</div>
                <div class="trade-event-time">⏰ ${event.start_time} - ${event.end_time}</div>
                <div class="trade-event-name">${this.escapeHtml(event.event_name)}</div>
                <div class="trade-event-check" aria-hidden="true">✓</div>
            </div>
        `).join('');

        container.innerHTML = eventsHtml;

        // Attach selection handlers
        this.attachTradeEventSelectionHandlers(container);
    }

    /**
     * Attach selection handlers to tradeable event cards (Story 3.8)
     *
     * @param {HTMLElement} container - Container element
     */
    attachTradeEventSelectionHandlers(container) {
        const eventCards = container.querySelectorAll('.trade-event-card');
        const executeBtn = document.querySelector('#btn-execute-trade');

        eventCards.forEach(card => {
            // Click handler
            card.addEventListener('click', () => {
                this.selectTradeEvent(card, executeBtn);
            });

            // Keyboard handler
            card.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    this.selectTradeEvent(card, executeBtn);
                }
            });
        });
    }

    /**
     * Select a trade event (Story 3.8)
     *
     * @param {HTMLElement} card - Selected event card
     * @param {HTMLElement} executeBtn - Execute trade button
     */
    selectTradeEvent(card, executeBtn) {
        // Deselect all cards
        const allCards = document.querySelectorAll('.trade-event-card');
        allCards.forEach(c => {
            c.classList.remove('trade-event-card--selected');
            c.setAttribute('aria-checked', 'false');
        });

        // Select this card
        card.classList.add('trade-event-card--selected');
        card.setAttribute('aria-checked', 'true');

        // Enable execute button
        executeBtn.disabled = false;

        // Store selected schedule ID
        this.selectedTradeScheduleId = parseInt(card.getAttribute('data-schedule-id'));
    }

    /**
     * Setup trade event modal listeners (Story 3.8)
     *
     * @param {HTMLElement} modal - Modal element
     * @param {number} sourceScheduleId - Source schedule ID
     */
    setupTradeEventModalListeners(modal, sourceScheduleId) {
        const closeBtn = modal.querySelector('.modal-close');
        const cancelBtn = modal.querySelector('.modal-cancel');
        const executeBtn = modal.querySelector('#btn-execute-trade');
        const overlay = modal.querySelector('.modal-overlay');

        // Close handlers
        const closeModal = () => this.closeTradeEventModal(modal);

        closeBtn.addEventListener('click', closeModal);
        cancelBtn.addEventListener('click', closeModal);
        overlay.addEventListener('click', closeModal);

        // Escape key handler
        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                closeModal();
            }
        };
        document.addEventListener('keydown', handleEscape);
        modal._escapeHandler = handleEscape;

        // Execute trade handler
        executeBtn.addEventListener('click', async () => {
            if (!this.selectedTradeScheduleId) return;

            await this.executeTradeEvent(sourceScheduleId, this.selectedTradeScheduleId, modal);
        });
    }

    /**
     * Execute trade between two events (Story 3.8)
     *
     * @param {number} schedule1Id - First schedule ID
     * @param {number} schedule2Id - Second schedule ID
     * @param {HTMLElement} modal - Modal element
     */
    async executeTradeEvent(schedule1Id, schedule2Id, modal) {
        const executeBtn = modal.querySelector('#btn-execute-trade');
        const originalText = executeBtn.textContent;

        try {
            // Show loading state
            executeBtn.disabled = true;
            executeBtn.textContent = 'Trading...';

            const response = await fetch('/api/trade-events', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': this.getCsrfToken()
                },
                body: JSON.stringify({
                    schedule_1_id: schedule1Id,
                    schedule_2_id: schedule2Id
                })
            });

            const result = await response.json();

            if (response.status === 409) {
                // Conflict detected
                this.showTradeModalError(modal, 'Trade would create conflicts:', result.conflicts);
                executeBtn.disabled = false;
                executeBtn.textContent = originalText;
                return;
            }

            if (!response.ok) {
                throw new Error(result.error || 'Failed to execute trade');
            }

            // Success
            this.showNotification('Events traded successfully', 'success');

            // Close modal
            this.closeTradeEventModal(modal);

            // Reload events to show swapped assignments
            await this.loadDailyEvents();
            await this.loadDailySummary();

        } catch (error) {
            console.error('Failed to execute trade:', error);
            this.showTradeModalError(modal, error.message || 'Failed to execute trade. Please try again.');
            executeBtn.disabled = false;
            executeBtn.textContent = originalText;
        }
    }

    /**
     * Show error in trade modal (Story 3.8)
     *
     * @param {HTMLElement} modal - Modal element
     * @param {string} message - Error message
     * @param {Array} conflicts - Optional array of conflict objects
     */
    showTradeModalError(modal, message, conflicts = null) {
        const errorDiv = modal.querySelector('#trade-error');
        if (!errorDiv) return;

        errorDiv.style.display = 'block';

        if (conflicts && conflicts.length > 0) {
            const conflictList = conflicts.map(c =>
                `<li class="conflict-${c.severity}">
                    <span class="icon">${c.severity === 'error' ? '✕' : '⚠️'}</span>
                    ${this.escapeHtml(c.message)}
                </li>`
            ).join('');

            errorDiv.innerHTML = `
                <strong>${this.escapeHtml(message)}</strong>
                <ul class="conflict-list">
                    ${conflictList}
                </ul>
            `;
        } else {
            errorDiv.innerHTML = `<span class="icon">✕</span> ${this.escapeHtml(message)}`;
        }
    }

    /**
     * Close trade event modal (Story 3.8)
     *
     * @param {HTMLElement} modal - Modal element
     */
    closeTradeEventModal(modal) {
        if (!modal) return;

        // Remove escape key handler
        if (modal._escapeHandler) {
            document.removeEventListener('keydown', modal._escapeHandler);
        }

        // Hide modal
        modal.classList.remove('modal-open');
        modal.setAttribute('aria-hidden', 'true');

        // Restore body scroll
        document.body.style.overflow = '';

        // Clear selected trade ID
        this.selectedTradeScheduleId = null;

        // Remove modal from DOM after animation
        setTimeout(() => {
            modal.remove();
        }, 200);
    }

    /**
     * Handle unschedule button click (Story 3.5)
     *
     * Displays confirmation modal, checks for attendance warnings,
     * and unschedules event via API if confirmed.
     *
     * @param {number} scheduleId - Schedule ID to unschedule
     */
    async handleUnschedule(scheduleId) {
        console.log('Unschedule event:', scheduleId);

        // Get event card for context
        const eventCard = document.querySelector(`[data-schedule-id="${scheduleId}"]`);
        const employeeName = eventCard?.querySelector('.employee-name')?.textContent?.replace(/person|Assigned to|👤/g, '').trim() || 'this employee';
        const eventInfo = eventCard?.querySelector('.event-info')?.textContent || 'this event';

        // Show confirmation modal
        const confirmed = await this.showConfirmationModal(
            'Unschedule Event',
            `Are you sure you want to unschedule ${eventInfo} for ${employeeName}? This will remove the employee assignment.`
        );

        if (!confirmed) {
            console.log('Unschedule cancelled by user');
            return;
        }

        // Close any open dropdowns
        this.closeAllDropdowns();

        // Show loading state on button
        const unscheduleBtn = eventCard?.querySelector('.btn-unschedule');
        if (unscheduleBtn) {
            unscheduleBtn.disabled = true;
            unscheduleBtn.textContent = 'Unscheduling...';
        }

        try {
            // Call API to unschedule
            const response = await fetch(`/api/event/${scheduleId}/unschedule`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': this.getCsrfToken()
                }
            });

            const data = await response.json();

            if (response.ok && data.success) {
                // Show appropriate notification
                if (data.unscheduled_supervisor_id) {
                    this.showNotification(
                        'Core event unscheduled. Paired Supervisor event also unscheduled.',
                        'success'
                    );
                } else if (data.had_attendance) {
                    this.showNotification(
                        'Event unscheduled. Attendance record was also removed.',
                        'warning'
                    );
                } else {
                    this.showNotification('Event unscheduled successfully', 'success');
                }

                // Remove card from UI with animation
                if (eventCard) {
                    eventCard.style.transition = 'opacity 300ms ease, transform 300ms ease';
                    eventCard.style.opacity = '0';
                    eventCard.style.transform = 'translateX(20px)';

                    setTimeout(() => {
                        eventCard.remove();

                        // Check if no more events, show empty state
                        const remainingCards = this.eventsContainer?.querySelectorAll('.event-card');
                        if (remainingCards?.length === 0) {
                            this.eventsContainer.innerHTML = `
                                <div class="empty-state" role="status">
                                    <p class="empty-state__message">No events scheduled for this date</p>
                                </div>
                            `;
                        }
                    }, 300);
                }

                // Also remove Supervisor card if it was unscheduled
                if (data.unscheduled_supervisor_id) {
                    const supervisorCard = document.querySelector(`[data-schedule-id="${data.unscheduled_supervisor_id}"]`);
                    if (supervisorCard) {
                        supervisorCard.style.transition = 'opacity 300ms ease, transform 300ms ease';
                        supervisorCard.style.opacity = '0';
                        supervisorCard.style.transform = 'translateX(20px)';

                        setTimeout(() => {
                            supervisorCard.remove();
                        }, 300);
                    }
                }

                // Reload summary stats (event count may have changed)
                await this.loadDailySummary();

            } else {
                // API returned error
                throw new Error(data.error || 'Failed to unschedule event');
            }

        } catch (error) {
            console.error('Failed to unschedule event:', error);
            this.showNotification(
                error.message || 'Failed to unschedule event. Please try again.',
                'error'
            );

            // Re-enable button
            if (unscheduleBtn) {
                unscheduleBtn.disabled = false;
                unscheduleBtn.textContent = 'Unschedule';
            }
        }
    }

    /**
     * Show confirmation modal (Story 3.5)
     *
     * Displays a modal dialog with title, message, and confirm/cancel buttons.
     * Returns a promise that resolves to true if confirmed, false if cancelled.
     *
     * @param {string} title - Modal title
     * @param {string} message - Confirmation message
     * @returns {Promise<boolean>} - Resolves to true if confirmed
     */
    showConfirmationModal(title, message) {
        return new Promise((resolve) => {
            // Create modal HTML
            const modalHTML = `
                <div class="modal modal-open" id="confirmation-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
                    <div class="modal-overlay" aria-hidden="true"></div>
                    <div class="modal-container modal-container--small">
                        <div class="modal-header">
                            <h2 class="modal-title" id="modal-title">${this.escapeHtml(title)}</h2>
                            <button class="modal-close" aria-label="Close" data-action="cancel">✕</button>
                        </div>
                        <div class="modal-body">
                            <p class="modal-message">${this.escapeHtml(message)}</p>
                        </div>
                        <div class="modal-footer">
                            <button class="btn btn-secondary" data-action="cancel">Cancel</button>
                            <button class="btn btn-primary" data-action="confirm">Confirm</button>
                        </div>
                    </div>
                </div>
            `;

            // Insert modal into DOM
            document.body.insertAdjacentHTML('beforeend', modalHTML);

            const modal = document.getElementById('confirmation-modal');
            const overlay = modal.querySelector('.modal-overlay');
            const confirmBtn = modal.querySelector('[data-action="confirm"]');
            const cancelBtns = modal.querySelectorAll('[data-action="cancel"]');

            // Focus first button (cancel for accessibility)
            cancelBtns[0]?.focus();

            // Prevent body scroll
            document.body.style.overflow = 'hidden';

            // Handle confirm
            const handleConfirm = () => {
                cleanup();
                resolve(true);
            };

            // Handle cancel
            const handleCancel = () => {
                cleanup();
                resolve(false);
            };

            // Cleanup function
            const cleanup = () => {
                modal.remove();
                document.body.style.overflow = '';
            };

            // Attach event listeners
            confirmBtn.addEventListener('click', handleConfirm);
            cancelBtns.forEach(btn => btn.addEventListener('click', handleCancel));
            overlay.addEventListener('click', handleCancel);

            // Handle Escape key
            const handleKeyDown = (e) => {
                if (e.key === 'Escape') {
                    handleCancel();
                    document.removeEventListener('keydown', handleKeyDown);
                }
            };
            document.addEventListener('keydown', handleKeyDown);

            // Handle Tab key for focus trap
            modal.addEventListener('keydown', (e) => {
                if (e.key === 'Tab') {
                    const focusableElements = modal.querySelectorAll(
                        'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
                    );
                    const firstFocusable = focusableElements[0];
                    const lastFocusable = focusableElements[focusableElements.length - 1];

                    if (e.shiftKey && document.activeElement === firstFocusable) {
                        e.preventDefault();
                        lastFocusable.focus();
                    } else if (!e.shiftKey && document.activeElement === lastFocusable) {
                        e.preventDefault();
                        firstFocusable.focus();
                    }
                }
            });
        });
    }

    /**
     * Show toast notification (Story 3.5)
     *
     * Displays a temporary toast notification at the top right of the page.
     *
     * @param {string} message - Notification message
     * @param {string} type - Notification type (success, error, warning, info)
     */
    showNotification(message, type = 'info') {
        // Use global toast manager if available
        if (window.toast) {
            window.toast.show(message, type);
            return;
        }

        // Fallback: simple notification
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        notification.setAttribute('role', 'alert');
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 24px;
            background: ${this.getNotificationColor(type)};
            color: white;
            border-radius: 4px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            z-index: 9999;
            animation: slideInRight 200ms ease-out;
        `;

        document.body.appendChild(notification);

        // Auto-remove after 3 seconds
        setTimeout(() => {
            notification.style.animation = 'slideOutRight 200ms ease-in';
            setTimeout(() => notification.remove(), 200);
        }, 3000);
    }

    /**
     * Get notification background color based on type (Story 3.5)
     *
     * @param {string} type - Notification type
     * @returns {string} CSS color value
     */
    getNotificationColor(type) {
        const colors = {
            success: '#10B981',  // Green
            error: '#DC2626',    // Red
            warning: '#F59E0B',  // Amber
            info: '#3B82F6'      // Blue
        };
        return colors[type] || colors.info;
    }

    /**
     * Get CSRF token from meta tag (Story 3.5)
     *
     * @returns {string} CSRF token
     */
    getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.content || '';
    }

    /**
     * Escape HTML to prevent XSS (Story 3.5)
     *
     * @param {string} text - Text to escape
     * @returns {string} Escaped text
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Show error message for events container
     *
     * @param {string} message - Error message to display
     */
    showEventsError(message) {
        if (this.eventsContainer) {
            this.eventsContainer.innerHTML = `
                <div class="error-message" role="alert">${message}</div>
            `;
        }
    }

    /* ===================================================================
       Shared Utility Methods
       =================================================================== */

    /**
     * Truncate text to specified length
     */
    truncate(text, maxLength) {
        if (!text || text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    }

    /**
     * Toggle attendance dropdown
     */
    toggleAttendanceDropdown(dropdown) {
        const isOpen = dropdown.classList.contains('dropdown-open');
        this.closeAllDropdowns();
        this.closeAllAttendanceDropdowns();
        if (!isOpen) {
            dropdown.classList.add('dropdown-open');
            const toggle = dropdown.querySelector('.dropdown-toggle');
            if (toggle) toggle.setAttribute('aria-expanded', 'true');
        }
    }

    /**
     * Close all attendance dropdowns
     */
    closeAllAttendanceDropdowns() {
        document.querySelectorAll('.attendance-dropdown').forEach(dropdown => {
            dropdown.classList.remove('dropdown-open');
            const toggle = dropdown.querySelector('.dropdown-toggle');
            if (toggle) toggle.setAttribute('aria-expanded', 'false');
        });
    }

    /**
     * Show attendance note modal
     */
    showAttendanceNoteModal(status) {
        return new Promise((resolve) => {
            const statusLabels = {
                'on_time': '🟢 On-Time',
                'late': '🟡 Late',
                'called_in': '📞 Called-In',
                'no_call_no_show': '🔴 No-Call-No-Show',
                'excused_absence': '🔵 Excused Absence'
            };
            const modalHTML = `
                <div class="modal modal-open" id="attendance-note-modal">
                    <div class="modal-overlay"></div>
                    <div class="modal-container modal-container--medium">
                        <div class="modal-header">
                            <h2 class="modal-title">Record Attendance - ${statusLabels[status]}</h2>
                            <button class="modal-close" data-action="cancel">✕</button>
                        </div>
                        <div class="modal-body">
                            <div class="form-group">
                                <label for="attendance-notes" class="form-label">Notes (optional):</label>
                                <textarea id="attendance-notes" class="form-control" rows="4"
                                          placeholder="Add context (e.g., 'Traffic delay, arrived 15 min late')"></textarea>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button class="btn btn-secondary" data-action="cancel">Cancel</button>
                            <button class="btn btn-primary" data-action="save">Save</button>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', modalHTML);
            const modal = document.getElementById('attendance-note-modal');
            const textarea = document.getElementById('attendance-notes');
            textarea.focus();
            document.body.style.overflow = 'hidden';

            const cleanup = () => { modal.remove(); document.body.style.overflow = ''; };
            const handleSave = () => { cleanup(); resolve(textarea.value.trim()); };
            const handleCancel = () => { cleanup(); resolve(null); };

            modal.querySelector('[data-action="save"]').addEventListener('click', handleSave);
            modal.querySelectorAll('[data-action="cancel"]').forEach(btn => btn.addEventListener('click', handleCancel));
            modal.querySelector('.modal-overlay').addEventListener('click', handleCancel);

            const handleKeyDown = (e) => {
                if (e.key === 'Escape') { handleCancel(); document.removeEventListener('keydown', handleKeyDown); }
                else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleSave();
            };
            document.addEventListener('keydown', handleKeyDown);
        });
    }

    /* ===================================================================
       Lock/Unlock Day Methods
       =================================================================== */

    /**
     * Check if the current day is locked
     */
    async checkLockStatus() {
        try {
            const response = await fetch(`/api/locked-days/${this.date}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            this.isLocked = data.is_locked;
            this.lockInfo = data.locked_day || null;
        } catch (error) {
            console.error('Error checking lock status:', error);
            this.isLocked = false;
            this.lockInfo = null;
        }
    }

    /**
     * Setup lock/unlock button listener
     */
    setupLockButton() {
        const lockBtn = document.getElementById('btn-lock-day');
        if (!lockBtn) return;

        // Update button state based on lock status
        this.updateLockButtonState();

        // Add click handler
        lockBtn.addEventListener('click', () => {
            this.toggleDayLock();
        });
    }

    /**
     * Update the lock button UI based on current state
     */
    updateLockButtonState() {
        const lockBtn = document.getElementById('btn-lock-day');
        const lockIcon = document.getElementById('lock-icon');
        const lockText = document.getElementById('lock-text');

        if (!lockBtn || !lockIcon || !lockText) return;

        if (this.isLocked) {
            lockIcon.innerHTML = '<span class="material-symbols-outlined">lock</span>';
            lockText.textContent = 'Unlock Day';
            lockBtn.classList.add('btn-locked');
            lockBtn.classList.remove('btn-unlocked');
            lockBtn.setAttribute('aria-label', 'Unlock this day');
            lockBtn.title = this.lockInfo ?
                `Locked by ${this.lockInfo.locked_by}${this.lockInfo.reason ? ': ' + this.lockInfo.reason : ''}` :
                'Day is locked';
        } else {
            lockIcon.innerHTML = '<span class="material-symbols-outlined">lock_open</span>';
            lockText.textContent = 'Lock Day';
            lockBtn.classList.add('btn-unlocked');
            lockBtn.classList.remove('btn-locked');
            lockBtn.setAttribute('aria-label', 'Lock this day');
            lockBtn.title = 'Lock this day to prevent schedule changes';
        }
    }

    /**
     * Toggle the lock state of the current day
     */
    async toggleDayLock() {
        if (this.isLocked) {
            await this.unlockDay();
        } else {
            await this.lockDay();
        }
    }

    /**
     * Lock the current day
     */
    async lockDay() {
        const reason = prompt('Enter a reason for locking this day (optional):', 'Schedule finalized');

        // User cancelled the prompt
        if (reason === null) return;

        try {
            const response = await fetch('/api/locked-days', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    date: this.date,
                    reason: reason || 'Schedule finalized',
                    locked_by: 'User'
                })
            });

            const data = await response.json();

            if (data.success) {
                this.isLocked = true;
                this.lockInfo = data.locked_day;
                this.updateLockButtonState();
                this.showNotification(`Day locked: ${this.date}`, 'success');
            } else {
                this.showNotification(`Failed to lock day: ${data.error}`, 'error');
            }
        } catch (error) {
            console.error('Error locking day:', error);
            this.showNotification('Failed to lock day', 'error');
        }
    }

    /**
     * Unlock the current day
     */
    async unlockDay() {
        if (!confirm('Are you sure you want to unlock this day? This will allow schedule modifications.')) {
            return;
        }

        try {
            const response = await fetch(`/api/locked-days/${this.date}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                }
            });

            const data = await response.json();

            if (data.success) {
                this.isLocked = false;
                this.lockInfo = null;
                this.updateLockButtonState();
                this.showNotification(`Day unlocked: ${this.date}`, 'success');
            } else {
                this.showNotification(`Failed to unlock day: ${data.error}`, 'error');
            }
        } catch (error) {
            console.error('Error unlocking day:', error);
            this.showNotification('Failed to unlock day', 'error');
        }
    }

    /* ===================================================================
       KEYBOARD SHORTCUTS
       ================================================================ */

    /**
     * Setup keyboard shortcuts for daily view navigation
     *
     * Shortcuts:
     * - Arrow Left (←): Navigate to previous day
     * - Arrow Right (→): Navigate to next day
     * - T: Go to today
     * - ?: Show keyboard shortcuts help modal
     * - Esc: Close modals
     *
     * Features:
     * - Smart detection: Doesn't trigger in input fields
     * - Modal awareness: Respects open modals (Esc only)
     * - Accessible: Works with screen readers
     */
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Don't trigger shortcuts when typing in input fields
            const isInputActive = ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName);

            // Check if any modal is open
            const isModalOpen = this.isAnyModalOpen();

            // ESC key - Close modals (works even in input fields)
            if (e.key === 'Escape' && isModalOpen) {
                this.closeAllModals();
                return;
            }

            // Don't process other shortcuts if typing in an input or modal is open
            if (isInputActive || isModalOpen) {
                return;
            }

            // Handle keyboard shortcuts
            switch(e.key) {
                case 'ArrowLeft':
                    e.preventDefault();
                    this.navigateToPreviousDay();
                    break;

                case 'ArrowRight':
                    e.preventDefault();
                    this.navigateToNextDay();
                    break;

                case 't':
                case 'T':
                    e.preventDefault();
                    this.navigateToToday();
                    break;

                case '?':
                    e.preventDefault();
                    this.showKeyboardShortcutsHelp();
                    break;
            }
        });
    }

    /**
     * Check if any modal is currently open
     */
    isAnyModalOpen() {
        const modals = [
            'reschedule-modal',
            'bulk-reassign-modal',
            'change-event-type-modal',
            'change-employee-modal',
            'trade-event-modal',
            'confirmation-modal',
            'attendance-note-modal',
            'keyboard-shortcuts-modal'
        ];

        return modals.some(modalId => {
            const modal = document.getElementById(modalId);
            return modal && modal.style.display !== 'none';
        });
    }

    /**
     * Close all open modals
     */
    closeAllModals() {
        // Close known modals
        this.closeRescheduleModal();
        this.closeBulkReassignModal();
        this.closeChangeEventTypeModal();

        // Close keyboard shortcuts help
        const helpModal = document.getElementById('keyboard-shortcuts-modal');
        if (helpModal) {
            helpModal.style.display = 'none';
        }

        // Close any dynamically created modals
        const modals = document.querySelectorAll('.modal-backdrop');
        modals.forEach(modal => {
            modal.style.display = 'none';
        });

        // Restore body scroll
        document.body.style.overflow = '';
    }

    /**
     * Navigate to previous day
     */
    navigateToPreviousDay() {
        const prevDayLink = document.querySelector('.btn-nav-prev');
        if (prevDayLink) {
            // Show loading overlay with date info
            const currentDate = new Date(this.date);
            currentDate.setDate(currentDate.getDate() - 1);
            const formattedDate = currentDate.toLocaleDateString('en-US', {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            });

            if (window.loadingState) {
                window.loadingState.showOverlay(`Loading events for ${formattedDate}...`);
            }

            // Navigate
            window.location.href = prevDayLink.href;
        }
    }

    /**
     * Navigate to next day
     */
    navigateToNextDay() {
        const nextDayLink = document.querySelector('.btn-nav-next');
        if (nextDayLink) {
            // Show loading overlay with date info
            const currentDate = new Date(this.date);
            currentDate.setDate(currentDate.getDate() + 1);
            const formattedDate = currentDate.toLocaleDateString('en-US', {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            });

            if (window.loadingState) {
                window.loadingState.showOverlay(`Loading events for ${formattedDate}...`);
            }

            // Navigate
            window.location.href = nextDayLink.href;
        }
    }

    /**
     * Navigate to today's date
     */
    navigateToToday() {
        const today = new Date();
        const todayStr = today.toISOString().split('T')[0];

        // Don't navigate if already on today
        if (this.date === todayStr) {
            if (window.toaster) {
                window.toaster.info('Already viewing today\'s schedule');
            }
            return;
        }

        // Show loading overlay
        const formattedDate = today.toLocaleDateString('en-US', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });

        if (window.loadingState) {
            window.loadingState.showOverlay(`Loading events for ${formattedDate}...`);
        }

        // Navigate to today
        window.location.href = `/daily-schedule/${todayStr}`;
    }

    /**
     * Show keyboard shortcuts help modal
     */
    showKeyboardShortcutsHelp() {
        let modal = document.getElementById('keyboard-shortcuts-modal');

        // Create modal if it doesn't exist
        if (!modal) {
            const modalHtml = `
                <div class="modal-backdrop" id="keyboard-shortcuts-modal" style="display: none;">
                    <div class="modal-dialog" role="dialog" aria-labelledby="shortcuts-title" aria-modal="true">
                        <div class="modal-header">
                            <h2 id="shortcuts-title" class="modal-title">Keyboard Shortcuts</h2>
                            <button type="button" class="btn-close" aria-label="Close">&times;</button>
                        </div>
                        <div class="modal-body">
                            <div class="keyboard-shortcuts-help">
                                <dl class="shortcuts-list">
                                    <dt><kbd>←</kbd> Arrow Left</dt>
                                    <dd>Navigate to previous day</dd>

                                    <dt><kbd>→</kbd> Arrow Right</dt>
                                    <dd>Navigate to next day</dd>

                                    <dt><kbd>T</kbd></dt>
                                    <dd>Go to today's schedule</dd>

                                    <dt><kbd>?</kbd></dt>
                                    <dd>Show this help dialog</dd>

                                    <dt><kbd>Esc</kbd></dt>
                                    <dd>Close open modals</dd>

                                    <dt><kbd>Tab</kbd></dt>
                                    <dd>Navigate forward through elements</dd>

                                    <dt><kbd>Shift</kbd> + <kbd>Tab</kbd></dt>
                                    <dd>Navigate backward through elements</dd>
                                </dl>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-primary btn-close-modal">Got it!</button>
                        </div>
                    </div>
                </div>
            `;

            document.body.insertAdjacentHTML('beforeend', modalHtml);
            modal = document.getElementById('keyboard-shortcuts-modal');

            // Setup close handlers
            const closeBtn = modal.querySelector('.btn-close');
            const closeModalBtn = modal.querySelector('.btn-close-modal');
            const backdrop = modal;

            const closeModal = () => {
                modal.style.display = 'none';
                document.body.style.overflow = '';
            };

            closeBtn.addEventListener('click', closeModal);
            closeModalBtn.addEventListener('click', closeModal);
            backdrop.addEventListener('click', (e) => {
                if (e.target === backdrop) {
                    closeModal();
                }
            });
        }

        // Show modal
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';

        // Focus first focusable element
        const firstButton = modal.querySelector('.btn-close-modal');
        if (firstButton) {
            firstButton.focus();
        }
    }

    /* ===================================================================
       Call-Off Wizard - Manages absent employee's events (Feature 3.3)
       =================================================================== */

    /**
     * Show the Call-Off Wizard for managing an absent employee's events.
     *
     * Triggered when an employee is marked as "Called-In" or "No-Call-No-Show".
     * Displays a modal with each of the employee's scheduled events and provides
     * Reassign, Reschedule, and Unschedule actions for each.
     *
     * @param {number} employeeId - Employee ID
     * @param {string} status - Attendance status ('called_in' or 'no_call_no_show')
     */
    async showCallOffWizard(employeeId, status) {
        // Find this employee's events from loaded data
        const employeeEvents = this.allEvents.filter(e => e.employee_id === employeeId);

        if (employeeEvents.length === 0) {
            this.showNotification('No events found for this employee today.', 'info');
            return;
        }

        const employeeName = toTitleCase(employeeEvents[0].employee_name);
        const statusLabel = status === 'called_in' ? 'Called-In' : 'No-Call-No-Show';

        const modal = document.getElementById('calloff-wizard-modal');
        const title = document.getElementById('calloff-wizard-title');
        const content = document.getElementById('calloff-wizard-content');

        title.textContent = `Manage ${employeeName}'s Events`;

        // Build event list with actions
        let html = `
            <div class="calloff-wizard-info" style="background: #FEF3C7; padding: 12px; border-radius: 8px; margin-bottom: 16px;">
                <strong>${this.escapeHtml(employeeName)}</strong> marked as <strong>${statusLabel}</strong>.
                They have <strong>${employeeEvents.length} event${employeeEvents.length > 1 ? 's' : ''}</strong> scheduled today.
            </div>
            <div class="calloff-wizard-events">
        `;

        employeeEvents.forEach(event => {
            const urgencyBadge = this.getUrgencyBadge(event);
            html += `
                <div class="calloff-event-row" id="calloff-event-${event.schedule_id}"
                     style="border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <strong>${this.escapeHtml(event.event_name)}</strong>
                        ${urgencyBadge}
                    </div>
                    <div style="color: #666; font-size: 13px; margin-bottom: 8px;">
                        ${this.escapeHtml(event.event_type)} &bull; ${event.start_time} - ${event.end_time}
                    </div>
                    <div class="calloff-actions" style="display: flex; gap: 8px; flex-wrap: wrap;">
                        <button class="btn btn-primary btn-sm calloff-btn-reassign"
                                data-schedule-id="${event.schedule_id}">
                            Reassign
                        </button>
                        <button class="btn btn-secondary btn-sm calloff-btn-reschedule"
                                data-schedule-id="${event.schedule_id}">
                            Reschedule
                        </button>
                        <button class="btn btn-secondary btn-sm calloff-btn-unschedule"
                                style="color: #dc2626;"
                                data-schedule-id="${event.schedule_id}">
                            Unschedule
                        </button>
                    </div>
                    <div class="calloff-action-result" style="display: none; margin-top: 8px;"></div>
                </div>
            `;
        });

        html += '</div>';
        content.innerHTML = html;

        // Attach action listeners - Reassign
        content.querySelectorAll('.calloff-btn-reassign').forEach(btn => {
            btn.addEventListener('click', () => {
                const scheduleId = btn.getAttribute('data-schedule-id');
                this.closeCallOffWizard();
                this.handleChangeEmployee(scheduleId);
            });
        });

        // Attach action listeners - Reschedule
        content.querySelectorAll('.calloff-btn-reschedule').forEach(btn => {
            btn.addEventListener('click', () => {
                const scheduleId = btn.getAttribute('data-schedule-id');
                this.closeCallOffWizard();
                this.handleReschedule(scheduleId);
            });
        });

        // Attach action listeners - Unschedule
        content.querySelectorAll('.calloff-btn-unschedule').forEach(btn => {
            btn.addEventListener('click', async () => {
                const scheduleId = btn.getAttribute('data-schedule-id');
                if (confirm('Are you sure you want to unschedule this event?')) {
                    try {
                        const response = await fetch(`/api/event/${scheduleId}/unschedule`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRF-Token': this.getCsrfToken()
                            }
                        });
                        const data = await response.json();
                        if (response.ok && data.success) {
                            const row = document.getElementById(`calloff-event-${scheduleId}`);
                            if (row) {
                                row.style.opacity = '0.5';
                                row.querySelector('.calloff-actions').style.display = 'none';
                                const result = row.querySelector('.calloff-action-result');
                                result.style.display = 'block';
                                result.innerHTML = '<span style="color: #059669; font-weight: 500;">Unscheduled</span>';
                            }
                            // Also remove the event card from the main view
                            const eventCard = document.querySelector(`[data-schedule-id="${scheduleId}"]`);
                            if (eventCard) {
                                eventCard.style.transition = 'opacity 300ms ease, transform 300ms ease';
                                eventCard.style.opacity = '0';
                                eventCard.style.transform = 'translateX(20px)';
                                setTimeout(() => eventCard.remove(), 300);
                            }
                            // Reload summary stats
                            await this.loadDailySummary();
                        } else {
                            throw new Error(data.error || 'Failed to unschedule event');
                        }
                    } catch (error) {
                        this.showNotification(error.message || 'Failed to unschedule event', 'error');
                    }
                }
            });
        });

        modal.style.display = 'flex';
    }

    /**
     * Close the Call-Off Wizard modal
     */
    closeCallOffWizard() {
        const modal = document.getElementById('calloff-wizard-modal');
        if (modal) modal.style.display = 'none';
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    const dateElement = document.querySelector('[data-selected-date]');
    if (dateElement) {
        const date = dateElement.getAttribute('data-selected-date');
        window.dailyView = new DailyView(date);
    }

    // Setup reschedule form submission handler
    const rescheduleForm = document.getElementById('reschedule-form');
    if (rescheduleForm) {
        // Helper function to submit reschedule with optional override
        const submitReschedule = async (overrideConflicts = false) => {
            const scheduleId = document.getElementById('reschedule-schedule-id').value;
            const date = document.getElementById('reschedule-date').value;
            const timeInput = document.getElementById('reschedule-time');
            const timeDropdown = document.getElementById('reschedule-time-dropdown');
            const time = timeDropdown.style.display !== 'none' ? timeDropdown.value : timeInput.value;
            const employeeId = document.getElementById('reschedule-employee').value;

            if (!date || !time || !employeeId) {
                window.toaster.warning('Please fill in all fields');
                return;
            }

            try {
                const response = await fetch('/api/event/' + scheduleId + '/reschedule', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        new_date: date,
                        new_time: time,
                        employee_id: employeeId,
                        override_conflicts: overrideConflicts // Fixed: API expects 'override_conflicts'
                    })
                });

                const data = await response.json();

                if (response.status === 409) {
                    // Check if this is a locked day error (no conflicts array)
                    if (!data.conflicts && data.error) {
                        // Locked day error - show clear message with unlock instructions
                        if (data.error.includes('locked')) {
                            window.toaster.warning(`🔒 Day is Locked - ${data.error} - To reschedule this event, first unlock the day using the "Lock Day" button.`);
                        } else {
                            window.toaster.error('Error: ' + data.error);
                        }
                        return;
                    }

                    // Conflict detected - show override option
                    const conflictList = data.conflicts.map(c =>
                        `<li class="conflict-${c.severity}">
                            <span class="icon">${c.severity === 'hard' ? '✕' : '⚠️'}</span>
                            ${c.message}
                        </li>`
                    ).join('');

                    const confirmOverride = confirm(
                        `Reschedule Conflicts Detected:\n\n` +
                        data.conflicts.map(c => `• ${c.message}`).join('\n') +
                        `\n\nDo you want to override these conflicts and reschedule anyway?`
                    );

                    if (confirmOverride) {
                        // Retry with override flag
                        await submitReschedule(true);
                    }
                    return;
                }

                if (data.success) {
                    const warningMsg = overrideConflicts ? ' (conflicts overridden)' : '';
                    if (window.dailyView) {
                        window.dailyView.showNotification(data.message + warningMsg, overrideConflicts ? 'warning' : 'success');
                        window.dailyView.closeRescheduleModal();
                        // Reload the daily view data
                        window.dailyView.init();
                    } else {
                        if (overrideConflicts) {
                            window.toaster.warning(data.message + warningMsg);
                        } else {
                            window.toaster.success(data.message + warningMsg);
                        }
                        location.reload();
                    }
                } else {
                    window.toaster.error('Error: ' + data.error);
                }
            } catch (error) {
                console.error('Error:', error);
                window.toaster.error('Error rescheduling event');
            }
        };

        rescheduleForm.addEventListener('submit', async function (e) {
            e.preventDefault();
            // Check manual override checkbox
            const overrideCheckbox = document.getElementById('reschedule-override-constraints');
            const manualOverride = overrideCheckbox ? overrideCheckbox.checked : false;
            await submitReschedule(manualOverride);
        });

        // Add listener for override checkbox to toggle constraints
        const overrideCheckbox = document.getElementById('reschedule-override-constraints');
        if (overrideCheckbox) {
            overrideCheckbox.addEventListener('change', function () {
                const dateInput = document.getElementById('reschedule-date');
                const timeInput = document.getElementById('reschedule-time');
                const timeDropdown = document.getElementById('reschedule-time-dropdown');
                const isChecked = this.checked;

                if (isChecked) {
                    // ENABLE OVERRIDE
                    if (dateInput) {
                        dateInput.removeAttribute('min');
                        dateInput.removeAttribute('max');
                    }
                    if (timeInput && timeDropdown) {
                        timeInput.style.display = 'block';
                        timeInput.required = true;
                        timeDropdown.style.display = 'none';
                        timeDropdown.classList.add('hidden');
                        timeDropdown.required = false;
                        if (timeDropdown.value) timeInput.value = timeDropdown.value;
                    }
                    // Refresh employees
                    if (dateInput && dateInput.value && window.dailyView) {
                        const eventType = document.getElementById('reschedule-form').dataset.eventType || 'Core'; // fallback
                        const empId = document.getElementById('reschedule-employee').value;
                        window.dailyView.loadAvailableEmployeesForReschedule('reschedule-employee', dateInput.value, eventType, empId);
                    }
                } else {
                    // DISABLE OVERRIDE - restore all constraints
                    if (window.dailyView) {
                        const eventType = document.getElementById('reschedule-form').dataset.eventType || 'Core';

                        // Restore date constraints
                        if (window.dailyView.currentScheduleConstraints && dateInput) {
                            if (window.dailyView.currentScheduleConstraints.startDate) {
                                dateInput.min = window.dailyView.currentScheduleConstraints.startDate;
                            }
                            if (window.dailyView.currentScheduleConstraints.dueDate) {
                                dateInput.max = window.dailyView.currentScheduleConstraints.dueDate;
                            }
                        }

                        // Restore time restrictions
                        const eventName = window.dailyView.rescheduleContext ? window.dailyView.rescheduleContext.eventName : null;
                        window.dailyView.setupTimeRestrictions('reschedule', eventType, timeInput.value, eventName);

                        // Restore employee restrictions
                        const empId = document.getElementById('reschedule-employee').value;
                        const dateVal = dateInput ? dateInput.value : null;
                        if (dateVal) window.dailyView.loadAvailableEmployeesForReschedule('reschedule-employee', dateVal, eventType, empId);
                    }
                }
            });
        }
    }

    // Setup reissue form submission
    const reissueForm = document.getElementById('reissue-form');
    if (reissueForm) {
        reissueForm.addEventListener('submit', async function (e) {
            e.preventDefault();

            const scheduleId = document.getElementById('reissue-schedule-id').value;
            const date = document.getElementById('reissue-date').value;
            const time = document.getElementById('reissue-time').value;
            const employeeId = document.getElementById('reissue-employee').value;
            const includeResponses = document.getElementById('reissue-include-responses').checked;

            if (!scheduleId || !date || !time || !employeeId) {
                window.toaster.warning('Please fill in all required fields');
                return;
            }

            try {
                const response = await fetch('/api/reissue-event', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        schedule_id: parseInt(scheduleId),
                        employee_id: employeeId,
                        schedule_date: date,
                        schedule_time: time,
                        include_responses: includeResponses
                    })
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    if (window.dailyView) {
                        window.dailyView.showNotification(data.message || 'Event reissued successfully', 'success');
                        window.dailyView.closeReissueModal();
                        // Reload the daily view data
                        window.dailyView.init();
                    } else {
                        window.toaster.success(data.message || 'Event reissued successfully');
                        location.reload();
                    }
                } else {
                    window.toaster.error('Error: ' + (data.error || 'Failed to reissue event'));
                }
            } catch (error) {
                console.error('Error reissuing event:', error);
                window.toaster.error('Error reissuing event');
            }
        });
    }

    // Setup bulk reassign supervisor events button
    const bulkReassignBtn = document.getElementById('btn-bulk-reassign-supervisor');
    if (bulkReassignBtn && window.dailyView) {
        bulkReassignBtn.addEventListener('click', () => {
            window.dailyView.openBulkReassignModal();
        });
    }

    // Setup bulk reassign form submission
    const bulkReassignForm = document.getElementById('bulk-reassign-form');
    if (bulkReassignForm && window.dailyView) {
        bulkReassignForm.addEventListener('submit', (e) => {
            window.dailyView.submitBulkReassign(e);
        });
    }
});
