/**
 * ATTENDANCE METHODS FOR DAILY VIEW (Story 4.2)
 *
 * These methods should be added to the DailyView class in daily-view.js
 * Add them BEFORE the closing brace of the class (before line 710)
 */

/* ===================================================================
   Story 4.2 Methods - Attendance Quick Entry
   =================================================================== */

/**
 * Render attendance dropdown for recording attendance
 *
 * @param {number} scheduleId - Schedule ID
 * @returns {string} HTML for attendance dropdown
 */
renderAttendanceDropdown(scheduleId) {
    return `
        <div class="attendance-dropdown" data-schedule-id="${scheduleId}">
            <button class="btn btn-attendance dropdown-toggle"
                    aria-label="Record attendance"
                    aria-haspopup="true"
                    aria-expanded="false">
                Record Attendance ▼
            </button>
            <div class="dropdown-menu" role="menu">
                <button class="dropdown-item attendance-option"
                        role="menuitem"
                        data-schedule-id="${scheduleId}"
                        data-status="on_time">
                    🟢 On-Time
                </button>
                <button class="dropdown-item attendance-option"
                        role="menuitem"
                        data-schedule-id="${scheduleId}"
                        data-status="late">
                    🟡 Late
                </button>
                <button class="dropdown-item attendance-option"
                        role="menuitem"
                        data-schedule-id="${scheduleId}"
                        data-status="called_in">
                    📞 Called-In
                </button>
                <button class="dropdown-item attendance-option"
                        role="menuitem"
                        data-schedule-id="${scheduleId}"
                        data-status="no_call_no_show">
                    🔴 No-Call-No-Show
                </button>
            </div>
        </div>
    `;
}

/**
 * Render recorded attendance status
 *
 * @param {string} status - Attendance status
 * @param {string} notes - Attendance notes
 * @param {number} scheduleId - Schedule ID for edit button
 * @returns {string} HTML for recorded attendance
 */
renderAttendanceRecorded(status, notes, scheduleId) {
    const statusLabels = {
        'on_time': '🟢 On-Time',
        'late': '🟡 Late',
        'called_in': '📞 Called-In',
        'no_call_no_show': '🔴 No-Call-No-Show'
    };

    const statusLabel = statusLabels[status] || status;
    const notesPreview = notes ? `<span class="attendance-notes-preview" title="${this.escapeHtml(notes)}">📝 ${this.truncate(notes, 30)}</span>` : '';

    return `
        <div class="attendance-recorded">
            <span class="attendance-badge attendance-badge--${status}">${statusLabel}</span>
            ${notesPreview}
            <button class="btn-link btn-edit-attendance"
                    data-schedule-id="${scheduleId}"
                    aria-label="Edit attendance">
                Edit
            </button>
        </div>
    `;
}

/**
 * Truncate text to specified length
 *
 * @param {string} text - Text to truncate
 * @param {number} maxLength - Maximum length
 * @returns {string} Truncated text
 */
truncate(text, maxLength) {
    if (!text || text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

/**
 * Toggle attendance dropdown
 *
 * @param {HTMLElement} dropdown - Attendance dropdown element
 */
toggleAttendanceDropdown(dropdown) {
    const isOpen = dropdown.classList.contains('dropdown-open');

    // Close all dropdowns (actions and attendance)
    this.closeAllDropdowns();
    this.closeAllAttendanceDropdowns();

    // Toggle this dropdown
    if (!isOpen) {
        dropdown.classList.add('dropdown-open');
        const toggle = dropdown.querySelector('.dropdown-toggle');
        if (toggle) {
            toggle.setAttribute('aria-expanded', 'true');
        }
    }
}

/**
 * Close all attendance dropdowns
 */
closeAllAttendanceDropdowns() {
    document.querySelectorAll('.attendance-dropdown').forEach(dropdown => {
        dropdown.classList.remove('dropdown-open');
        const toggle = dropdown.querySelector('.dropdown-toggle');
        if (toggle) {
            toggle.setAttribute('aria-expanded', 'false');
        }
    });
}

/**
 * Handle attendance recording (Story 4.2)
 *
 * @param {number} scheduleId - Schedule ID
 * @param {string} status - Attendance status
 */
async handleAttendanceRecord(scheduleId, status) {
    console.log(`Recording attendance: schedule=${scheduleId}, status=${status}`);

    // Close dropdown
    this.closeAllAttendanceDropdowns();

    // Show note modal
    const notes = await this.showAttendanceNoteModal(status);

    // User cancelled
    if (notes === null) {
        console.log('Attendance recording cancelled');
        return;
    }

    // Send to API
    try {
        const response = await fetch('/api/attendance', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': this.getCsrfToken()
            },
            body: JSON.stringify({
                schedule_id: scheduleId,
                status: status,
                notes: notes
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            this.showNotification(
                `Attendance recorded: ${data.attendance.status_label}`,
                'success'
            );

            // Reload events to show updated attendance
            await this.loadDailyEvents();
        } else {
            throw new Error(data.error || 'Failed to record attendance');
        }

    } catch (error) {
        console.error('Failed to record attendance:', error);
        this.showNotification(
            error.message || 'Failed to record attendance. Please try again.',
            'error'
        );
    }
}

/**
 * Handle attendance edit (Story 4.2)
 *
 * @param {number} scheduleId - Schedule ID
 */
async handleAttendanceEdit(scheduleId) {
    console.log(`Editing attendance for schedule: ${scheduleId}`);

    // Get event card and replace recorded attendance with dropdown
    const eventCard = document.querySelector(`[data-schedule-id="${scheduleId}"]`);
    const attendanceSection = eventCard?.querySelector('.event-card__attendance');

    if (attendanceSection) {
        // Replace recorded attendance with dropdown
        attendanceSection.innerHTML = `
            <label class="attendance-label">Attendance:</label>
            ${this.renderAttendanceDropdown(scheduleId)}
        `;

        // Reattach listeners
        this.attachEventCardListeners();
    }
}

/**
 * Show attendance note modal (Story 4.2)
 *
 * @param {string} status - Attendance status being recorded
 * @returns {Promise<string|null>} - Resolves to notes string or null if cancelled
 */
showAttendanceNoteModal(status) {
    return new Promise((resolve) => {
        const statusLabels = {
            'on_time': '🟢 On-Time',
            'late': '🟡 Late',
            'called_in': '📞 Called-In',
            'no_call_no_show': '🔴 No-Call-No-Show'
        };

        const statusLabel = statusLabels[status] || status;

        const modalHTML = `
            <div class="modal modal-open" id="attendance-note-modal" role="dialog" aria-modal="true" aria-labelledby="attendance-modal-title">
                <div class="modal-overlay" aria-hidden="true"></div>
                <div class="modal-container modal-container--medium">
                    <div class="modal-header">
                        <h2 class="modal-title" id="attendance-modal-title">Record Attendance - ${statusLabel}</h2>
                        <button class="modal-close" aria-label="Close" data-action="cancel">✕</button>
                    </div>
                    <div class="modal-body">
                        <div class="form-group">
                            <label for="attendance-notes" class="form-label">
                                Notes (optional):
                            </label>
                            <textarea id="attendance-notes"
                                      class="form-control"
                                      rows="4"
                                      placeholder="Add context (e.g., 'Traffic delay, arrived 15 min late')"></textarea>
                            <small class="form-help">Provide additional details about the attendance status</small>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" data-action="cancel">Cancel</button>
                        <button class="btn btn-primary" data-action="save">Save</button>
                    </div>
                </div>
            </div>
        `;

        // Insert modal
        document.body.insertAdjacentHTML('beforeend', modalHTML);

        const modal = document.getElementById('attendance-note-modal');
        const textarea = document.getElementById('attendance-notes');
        const saveBtn = modal.querySelector('[data-action="save"]');
        const cancelBtns = modal.querySelectorAll('[data-action="cancel"]');
        const overlay = modal.querySelector('.modal-overlay');

        // Focus textarea
        textarea.focus();

        // Prevent body scroll
        document.body.style.overflow = 'hidden';

        // Handle save
        const handleSave = () => {
            const notes = textarea.value.trim();
            cleanup();
            resolve(notes);
        };

        // Handle cancel
        const handleCancel = () => {
            cleanup();
            resolve(null);
        };

        // Cleanup
        const cleanup = () => {
            modal.remove();
            document.body.style.overflow = '';
        };

        // Attach listeners
        saveBtn.addEventListener('click', handleSave);
        cancelBtns.forEach(btn => btn.addEventListener('click', handleCancel));
        overlay.addEventListener('click', handleCancel);

        // Handle Escape key
        const handleKeyDown = (e) => {
            if (e.key === 'Escape') {
                handleCancel();
                document.removeEventListener('keydown', handleKeyDown);
            } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                // Ctrl+Enter or Cmd+Enter to save
                handleSave();
            }
        };
        document.addEventListener('keydown', handleKeyDown);
    });
}
