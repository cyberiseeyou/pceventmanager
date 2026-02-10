/**
 * ATTENDANCE CALENDAR VIEW (Story 4.3)
 *
 * JavaScript for the employee attendance calendar view.
 * Displays monthly attendance calendar with color-coded dates.
 */

class AttendanceCalendar {
    constructor() {
        this.container = document.querySelector('.attendance-calendar-container');
        if (!this.container) {
            console.error('Attendance calendar container not found');
            return;
        }

        this.selectedDate = this.container.getAttribute('data-selected-date');
        this.selectedEmployeeId = this.getSelectedEmployeeId();
        this.attendanceData = {};
        this.statisticsData = {};

        this.init();
    }

    /**
     * Initialize the calendar
     */
    async init() {
        console.log('[AttendanceCalendar] Initializing...');

        // Attach event listeners
        this.attachEventListeners();

        // Load attendance data and render calendar
        await this.loadAttendanceData();
        this.renderCalendar();
        this.renderStatistics();

        console.log('[AttendanceCalendar] Initialized successfully');
    }

    /**
     * Attach event listeners
     */
    attachEventListeners() {
        // Employee selector change
        const employeeSelector = document.getElementById('employee-selector');
        if (employeeSelector) {
            employeeSelector.addEventListener('change', (e) => {
                this.handleEmployeeChange(e.target.value);
            });
        }

        // Close detail panel when clicking outside
        document.addEventListener('click', (e) => {
            const detailContainer = document.getElementById('date-detail-container');
            const calendarGrid = document.getElementById('calendar-grid');

            if (detailContainer &&
                detailContainer.style.display !== 'none' &&
                !detailContainer.contains(e.target) &&
                !calendarGrid.contains(e.target)) {
                this.closeDateDetail();
            }
        });
    }

    /**
     * Get selected employee ID from URL or selector
     */
    getSelectedEmployeeId() {
        const urlParams = new URLSearchParams(window.location.search);
        const employeeId = urlParams.get('employee_id');
        return employeeId || null;
    }

    /**
     * Handle employee selector change
     */
    handleEmployeeChange(employeeId) {
        console.log(`[AttendanceCalendar] Employee changed: ${employeeId}`);

        // Build URL with employee filter
        let url = window.location.pathname;
        const params = new URLSearchParams(window.location.search);

        if (employeeId) {
            params.set('employee_id', employeeId);
        } else {
            params.delete('employee_id');
        }

        // Navigate to new URL
        if (params.toString()) {
            window.location.href = `${url}?${params.toString()}`;
        } else {
            window.location.href = url;
        }
    }

    /**
     * Parse the selected date string into {year, month} without timezone issues
     */
    parseSelectedDate() {
        const parts = this.selectedDate.split('-');
        return {
            year: parseInt(parts[0], 10),
            month: parseInt(parts[1], 10) - 1 // 0-indexed for JS Date compatibility
        };
    }

    /**
     * Load attendance data from API
     */
    async loadAttendanceData() {
        console.log('[AttendanceCalendar] Loading attendance data...');

        try {
            // Parse selected date without timezone conversion
            const { year, month } = this.parseSelectedDate();
            const monthStr = `${year}-${String(month + 1).padStart(2, '0')}-01`;

            // Build API URL
            let apiUrl = `/api/attendance/month/${monthStr}`;
            if (this.selectedEmployeeId) {
                apiUrl += `?employee_id=${this.selectedEmployeeId}`;
            }

            const response = await fetch(apiUrl, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }

            const data = await response.json();
            console.log('[AttendanceCalendar] Attendance data loaded:', data);

            // Group attendance by date
            this.attendanceData = data.attendance_by_date || {};
            this.statisticsData = data.statistics || {};

        } catch (error) {
            console.error('[AttendanceCalendar] Failed to load attendance:', error);
            this.showNotification('Failed to load attendance data', 'error');
            this.attendanceData = {};
            this.statisticsData = {};
        }
    }

    /**
     * Render the calendar grid
     */
    renderCalendar() {
        console.log('[AttendanceCalendar] Rendering calendar...');

        const calendarGrid = document.getElementById('calendar-grid');
        if (!calendarGrid) return;

        // Parse selected date without timezone issues
        const { year, month } = this.parseSelectedDate();

        // Get first day of month and total days
        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
        const startDayOfWeek = firstDay.getDay(); // 0 = Sunday
        const totalDays = lastDay.getDate();

        // Build calendar HTML
        let calendarHTML = '';

        // Add empty cells for days before month starts
        for (let i = 0; i < startDayOfWeek; i++) {
            calendarHTML += '<div class="calendar-day calendar-day--empty"></div>';
        }

        // Add day cells
        for (let day = 1; day <= totalDays; day++) {
            const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
            const dayData = this.attendanceData[dateStr] || {};
            const hasData = Object.keys(dayData).length > 0;

            // Determine status for color coding
            const status = this.getDominantStatus(dayData);
            const statusClass = status ? `calendar-day--${status}` : 'calendar-day--no-data';

            // Check if today
            const today = new Date();
            const isToday = (
                year === today.getFullYear() &&
                month === today.getMonth() &&
                day === today.getDate()
            );

            calendarHTML += `
                <div class="calendar-day ${statusClass} ${isToday ? 'calendar-day--today' : ''}"
                     data-date="${dateStr}"
                     role="button"
                     tabindex="0"
                     aria-label="${this.getDateAriaLabel(day, dateStr, dayData)}">
                    <div class="calendar-day-number">${day}</div>
                    ${hasData ? this.renderDayBadges(dayData) : '<div class="calendar-day-no-data">No records</div>'}
                </div>
            `;
        }

        calendarGrid.innerHTML = calendarHTML;

        // Attach click listeners to day cells
        calendarGrid.querySelectorAll('.calendar-day').forEach(dayCell => {
            dayCell.addEventListener('click', (e) => {
                const dateStr = e.currentTarget.getAttribute('data-date');
                if (dateStr) {
                    this.showDateDetail(dateStr);
                }
            });

            // Keyboard accessibility
            dayCell.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    const dateStr = e.currentTarget.getAttribute('data-date');
                    if (dateStr) {
                        this.showDateDetail(dateStr);
                    }
                }
            });

            // Story 4.5: Hover tooltips
            const dateStr = dayCell.getAttribute('data-date');
            if (dateStr) {
                // Desktop: mouseenter/mouseleave
                dayCell.addEventListener('mouseenter', (e) => {
                    this.showTooltip(e.currentTarget, dateStr);
                });

                dayCell.addEventListener('mouseleave', () => {
                    this.hideTooltip();
                });

                // Mobile: long press (tap and hold)
                let touchTimer = null;
                dayCell.addEventListener('touchstart', (e) => {
                    touchTimer = setTimeout(() => {
                        this.showTooltip(e.currentTarget, dateStr);
                    }, 500); // 500ms long press
                });

                dayCell.addEventListener('touchend', () => {
                    if (touchTimer) {
                        clearTimeout(touchTimer);
                        touchTimer = null;
                    }
                });

                dayCell.addEventListener('touchmove', () => {
                    if (touchTimer) {
                        clearTimeout(touchTimer);
                        touchTimer = null;
                    }
                });
            }
        });
    }

    /**
     * Get dominant attendance status for a date
     */
    getDominantStatus(dayData) {
        if (!dayData || Object.keys(dayData).length === 0) return null;

        // Count statuses
        const statusCounts = {
            on_time: 0,
            late: 0,
            called_in: 0,
            no_call_no_show: 0
        };

        Object.values(dayData).forEach(records => {
            records.forEach(record => {
                if (statusCounts.hasOwnProperty(record.status)) {
                    statusCounts[record.status]++;
                }
            });
        });

        // Priority order: no_call_no_show > late > called_in > on_time
        if (statusCounts.no_call_no_show > 0) return 'no_call_no_show';
        if (statusCounts.late > 0) return 'late';
        if (statusCounts.called_in > 0) return 'called_in';
        if (statusCounts.on_time > 0) return 'on_time';

        return null;
    }

    /**
     * Render day badges (status counts)
     */
    renderDayBadges(dayData) {
        if (!dayData || Object.keys(dayData).length === 0) {
            return '<div class="calendar-day-no-data">No records</div>';
        }

        // Count total records
        let totalRecords = 0;
        Object.values(dayData).forEach(records => {
            totalRecords += records.length;
        });

        return `<div class="calendar-day-count">${totalRecords} record${totalRecords !== 1 ? 's' : ''}</div>`;
    }

    /**
     * Get ARIA label for date
     */
    getDateAriaLabel(day, dateStr, dayData) {
        const parts = dateStr.split('-');
        const date = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
        const dayName = date.toLocaleDateString('en-US', { weekday: 'long' });
        const monthName = date.toLocaleDateString('en-US', { month: 'long' });

        let label = `${dayName}, ${monthName} ${day}`;

        if (dayData && Object.keys(dayData).length > 0) {
            let totalRecords = 0;
            Object.values(dayData).forEach(records => {
                totalRecords += records.length;
            });
            label += `, ${totalRecords} attendance record${totalRecords !== 1 ? 's' : ''}`;
        } else {
            label += ', No attendance records';
        }

        return label;
    }

    /**
     * Show date detail panel
     */
    showDateDetail(dateStr) {
        console.log(`[AttendanceCalendar] Showing detail for: ${dateStr}`);

        const detailContainer = document.getElementById('date-detail-container');
        if (!detailContainer) return;

        const dayData = this.attendanceData[dateStr] || {};
        const date = new Date(dateStr);
        const formattedDate = date.toLocaleDateString('en-US', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });

        // Build detail HTML
        let detailHTML = `
            <div class="date-detail-header">
                <h3 class="date-detail-title">${formattedDate}</h3>
                <button class="btn-close-detail" aria-label="Close detail panel">✕</button>
            </div>
        `;

        if (Object.keys(dayData).length === 0) {
            detailHTML += '<div class="date-detail-empty">No attendance records for this date.</div>';
        } else {
            detailHTML += '<div class="date-detail-records">';

            // Group by employee
            Object.entries(dayData).forEach(([employeeName, records]) => {
                detailHTML += `
                    <div class="employee-attendance-group">
                        <h4 class="employee-name">${this.escapeHtml(employeeName)}</h4>
                        <div class="attendance-records">
                `;

                records.forEach(record => {
                    const statusLabels = {
                        'on_time': '🟢 On-Time',
                        'late': '🟡 Late',
                        'called_in': '📞 Called-In',
                        'no_call_no_show': '🔴 No-Call-No-Show'
                    };
                    const statusLabel = statusLabels[record.status] || record.status;

                    detailHTML += `
                        <div class="attendance-record" data-record-id="${record.id}">
                            <div class="record-header">
                                <span class="record-status attendance-badge--${record.status}">${statusLabel}</span>
                                ${record.recorded_at ? `<span class="record-time">Recorded: ${this.formatDateTime(record.recorded_at)}</span>` : ''}
                            </div>
                            ${record.notes ? `<div class="record-notes">📝 ${this.escapeHtml(record.notes)}</div>` : ''}
                            ${record.recorded_by ? `<div class="record-by">Recorded by: ${this.escapeHtml(record.recorded_by)}</div>` : ''}
                            <div class="record-actions">
                                <button class="btn-edit-record" data-record-id="${record.id}" data-record='${JSON.stringify(record)}' aria-label="Edit record">
                                    ✏️ Edit
                                </button>
                                <button class="btn-delete-record" data-record-id="${record.id}" aria-label="Delete record">
                                    🗑️ Delete
                                </button>
                            </div>
                        </div>
                    `;
                });

                detailHTML += `
                        </div>
                    </div>
                `;
            });

            detailHTML += '</div>';
        }

        detailContainer.innerHTML = detailHTML;
        detailContainer.style.display = 'block';

        // Attach close button listener
        const closeBtn = detailContainer.querySelector('.btn-close-detail');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.closeDateDetail());
        }

        // Attach edit button listeners
        detailContainer.querySelectorAll('.btn-edit-record').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const recordData = JSON.parse(e.currentTarget.getAttribute('data-record'));
                this.showEditModal(recordData);
            });
        });

        // Attach delete button listeners
        detailContainer.querySelectorAll('.btn-delete-record').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const recordId = e.currentTarget.getAttribute('data-record-id');
                this.showDeleteConfirmation(recordId);
            });
        });

        // Scroll to detail panel
        detailContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    /**
     * Close date detail panel
     */
    closeDateDetail() {
        const detailContainer = document.getElementById('date-detail-container');
        if (detailContainer) {
            detailContainer.style.display = 'none';
            detailContainer.innerHTML = '';
        }
    }

    /**
     * Render statistics
     */
    renderStatistics() {
        console.log('[AttendanceCalendar] Rendering statistics...');

        const statsContainer = document.getElementById('attendance-stats');
        if (!statsContainer) return;

        if (!this.statisticsData || Object.keys(this.statisticsData).length === 0) {
            statsContainer.innerHTML = '<div class="stats-empty">No attendance data for this period.</div>';
            return;
        }

        const stats = this.statisticsData;

        const statsHTML = `
            <h3 class="stats-title">Monthly Summary</h3>
            <div class="stats-grid">
                <div class="stat-card stat-card--total">
                    <div class="stat-value">${stats.total_records || 0}</div>
                    <div class="stat-label">Total Records</div>
                </div>
                <div class="stat-card stat-card--on-time">
                    <div class="stat-value">${stats.on_time || 0}</div>
                    <div class="stat-label">🟢 On-Time</div>
                </div>
                <div class="stat-card stat-card--late">
                    <div class="stat-value">${stats.late || 0}</div>
                    <div class="stat-label">🟡 Late</div>
                </div>
                <div class="stat-card stat-card--called-in">
                    <div class="stat-value">${stats.called_in || 0}</div>
                    <div class="stat-label">📞 Called-In</div>
                </div>
                <div class="stat-card stat-card--no-call">
                    <div class="stat-value">${stats.no_call_no_show || 0}</div>
                    <div class="stat-label">🔴 No-Call-No-Show</div>
                </div>
                <div class="stat-card stat-card--rate">
                    <div class="stat-value">${stats.on_time_rate || '0%'}</div>
                    <div class="stat-label">On-Time Rate</div>
                </div>
            </div>
        `;

        statsContainer.innerHTML = statsHTML;
    }

    /**
     * Show notification
     */
    showNotification(message, type = 'info') {
        if (window.toaster) {
            window.toaster.show(message, type);
        } else {
            console.log(`[Notification] ${type}: ${message}`);
        }
    }

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Format datetime string
     */
    formatDateTime(isoString) {
        if (!isoString) return '';
        const date = new Date(isoString);
        return date.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        });
    }

    /**
     * Show edit modal (Story 4.4)
     */
    showEditModal(record) {
        console.log('[AttendanceCalendar] Showing edit modal for record:', record);

        const statusLabels = {
            'on_time': 'On-Time',
            'late': 'Late',
            'called_in': 'Called-In',
            'no_call_no_show': 'No-Call-No-Show'
        };

        const modalHTML = `
            <div class="modal modal-open" id="edit-attendance-modal" role="dialog" aria-modal="true" aria-labelledby="edit-modal-title">
                <div class="modal-overlay" aria-hidden="true"></div>
                <div class="modal-container modal-container--medium">
                    <div class="modal-header">
                        <h2 class="modal-title" id="edit-modal-title">Edit Attendance Record</h2>
                        <button class="modal-close" aria-label="Close" data-action="cancel">✕</button>
                    </div>
                    <div class="modal-body">
                        <div class="form-group">
                            <label for="edit-status" class="form-label">
                                Status: <span class="required">*</span>
                            </label>
                            <select id="edit-status" class="form-control" required>
                                <option value="on_time" ${record.status === 'on_time' ? 'selected' : ''}>🟢 On-Time</option>
                                <option value="late" ${record.status === 'late' ? 'selected' : ''}>🟡 Late</option>
                                <option value="called_in" ${record.status === 'called_in' ? 'selected' : ''}>📞 Called-In</option>
                                <option value="no_call_no_show" ${record.status === 'no_call_no_show' ? 'selected' : ''}>🔴 No-Call-No-Show</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label for="edit-notes" class="form-label">
                                Notes (optional):
                            </label>
                            <textarea id="edit-notes" class="form-control" rows="4" placeholder="Add context about the attendance status...">${record.notes || ''}</textarea>
                            <small class="form-help">Provide additional details about the attendance status</small>
                        </div>
                        <div class="form-group">
                            <div class="record-metadata">
                                <small>Record ID: ${record.id}</small>
                                ${record.recorded_by ? `<small>Recorded by: ${this.escapeHtml(record.recorded_by)}</small>` : ''}
                                ${record.recorded_at ? `<small>Recorded at: ${this.formatDateTime(record.recorded_at)}</small>` : ''}
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" data-action="cancel">Cancel</button>
                        <button class="btn btn-primary" data-action="save">Save Changes</button>
                    </div>
                </div>
            </div>
        `;

        // Insert modal
        document.body.insertAdjacentHTML('beforeend', modalHTML);

        const modal = document.getElementById('edit-attendance-modal');
        const statusSelect = document.getElementById('edit-status');
        const notesTextarea = document.getElementById('edit-notes');
        const saveBtn = modal.querySelector('[data-action="save"]');
        const cancelBtns = modal.querySelectorAll('[data-action="cancel"]');
        const overlay = modal.querySelector('.modal-overlay');

        // Focus status select
        statusSelect.focus();

        // Prevent body scroll
        document.body.style.overflow = 'hidden';

        // Handle save
        const handleSave = async () => {
            const newStatus = statusSelect.value;
            const newNotes = notesTextarea.value.trim();

            // Validate
            if (!newStatus) {
                this.showNotification('Please select a status', 'error');
                return;
            }

            // Send to API
            try {
                const response = await fetch(`/api/attendance/${record.id}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': this.getCsrfToken()
                    },
                    body: JSON.stringify({
                        status: newStatus,
                        notes: newNotes
                    })
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    this.showNotification('Attendance record updated successfully', 'success');
                    cleanup();

                    // Reload data and re-render
                    await this.loadAttendanceData();
                    this.renderCalendar();
                    this.renderStatistics();
                    this.closeDateDetail();
                } else {
                    throw new Error(data.error || 'Failed to update attendance record');
                }

            } catch (error) {
                console.error('Failed to update attendance:', error);
                this.showNotification(error.message || 'Failed to update attendance record', 'error');
            }
        };

        // Handle cancel
        const handleCancel = () => {
            cleanup();
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
    }

    /**
     * Show delete confirmation (Story 4.4)
     */
    showDeleteConfirmation(recordId) {
        console.log('[AttendanceCalendar] Showing delete confirmation for record:', recordId);

        const modalHTML = `
            <div class="modal modal-open" id="delete-attendance-modal" role="dialog" aria-modal="true" aria-labelledby="delete-modal-title">
                <div class="modal-overlay" aria-hidden="true"></div>
                <div class="modal-container modal-container--small">
                    <div class="modal-header">
                        <h2 class="modal-title" id="delete-modal-title">Delete Attendance Record</h2>
                        <button class="modal-close" aria-label="Close" data-action="cancel">✕</button>
                    </div>
                    <div class="modal-body">
                        <p class="confirmation-text">
                            Are you sure you want to delete this attendance record?
                        </p>
                        <p class="confirmation-warning">
                            ⚠️ This action cannot be undone.
                        </p>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" data-action="cancel">Cancel</button>
                        <button class="btn btn-danger" data-action="confirm">Delete</button>
                    </div>
                </div>
            </div>
        `;

        // Insert modal
        document.body.insertAdjacentHTML('beforeend', modalHTML);

        const modal = document.getElementById('delete-attendance-modal');
        const confirmBtn = modal.querySelector('[data-action="confirm"]');
        const cancelBtns = modal.querySelectorAll('[data-action="cancel"]');
        const overlay = modal.querySelector('.modal-overlay');

        // Focus confirm button
        confirmBtn.focus();

        // Prevent body scroll
        document.body.style.overflow = 'hidden';

        // Handle confirm
        const handleConfirm = async () => {
            // Send delete request to API
            try {
                const response = await fetch(`/api/attendance/${recordId}`, {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': this.getCsrfToken()
                    }
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    this.showNotification('Attendance record deleted successfully', 'success');
                    cleanup();

                    // Reload data and re-render
                    await this.loadAttendanceData();
                    this.renderCalendar();
                    this.renderStatistics();
                    this.closeDateDetail();
                } else {
                    throw new Error(data.error || 'Failed to delete attendance record');
                }

            } catch (error) {
                console.error('Failed to delete attendance:', error);
                this.showNotification(error.message || 'Failed to delete attendance record', 'error');
            }
        };

        // Handle cancel
        const handleCancel = () => {
            cleanup();
        };

        // Cleanup
        const cleanup = () => {
            modal.remove();
            document.body.style.overflow = '';
        };

        // Attach listeners
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
    }

    /**
     * Get CSRF token
     */
    getCsrfToken() {
        // Try window.getCsrfToken first (from csrf_helper.js)
        if (typeof window.getCsrfToken === 'function') {
            return window.getCsrfToken();
        }

        // Fallback: Try to get from meta tag
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) {
            return metaTag.getAttribute('content');
        }

        // Fallback: Try to get from cookie
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrf_token') {
                return value;
            }
        }

        console.warn('[AttendanceCalendar] CSRF token not found');
        return '';
    }

    /**
     * Show attendance tooltip (Story 4.5)
     */
    showTooltip(element, dateStr) {
        // Remove existing tooltip
        this.hideTooltip();

        const dayData = this.attendanceData[dateStr] || {};

        // Don't show tooltip for empty dates
        if (Object.keys(dayData).length === 0) {
            return;
        }

        // Calculate status counts
        const statusCounts = {
            on_time: 0,
            late: 0,
            called_in: 0,
            no_call_no_show: 0
        };

        let totalRecords = 0;
        Object.values(dayData).forEach(records => {
            records.forEach(record => {
                if (statusCounts.hasOwnProperty(record.status)) {
                    statusCounts[record.status]++;
                }
                totalRecords++;
            });
        });

        // Build tooltip HTML
        const tooltipHTML = `
            <div class="attendance-tooltip" role="tooltip">
                <div class="tooltip-header">
                    <strong>${totalRecords} Record${totalRecords !== 1 ? 's' : ''}</strong>
                </div>
                <div class="tooltip-body">
                    ${statusCounts.on_time > 0 ? `<div class="tooltip-item tooltip-item--on-time">🟢 On-Time: ${statusCounts.on_time}</div>` : ''}
                    ${statusCounts.late > 0 ? `<div class="tooltip-item tooltip-item--late">🟡 Late: ${statusCounts.late}</div>` : ''}
                    ${statusCounts.called_in > 0 ? `<div class="tooltip-item tooltip-item--called-in">📞 Called-In: ${statusCounts.called_in}</div>` : ''}
                    ${statusCounts.no_call_no_show > 0 ? `<div class="tooltip-item tooltip-item--no-call">🔴 No-Call-No-Show: ${statusCounts.no_call_no_show}</div>` : ''}
                </div>
                <div class="tooltip-footer">
                    Click for details
                </div>
            </div>
        `;

        // Create tooltip element
        const tooltip = document.createElement('div');
        tooltip.innerHTML = tooltipHTML;
        const tooltipElement = tooltip.firstElementChild;
        document.body.appendChild(tooltipElement);

        // Position tooltip
        const rect = element.getBoundingClientRect();
        const tooltipRect = tooltipElement.getBoundingClientRect();

        // Default position: below element, centered
        let top = rect.bottom + window.scrollY + 8;
        let left = rect.left + window.scrollX + (rect.width / 2) - (tooltipRect.width / 2);

        // Adjust if tooltip goes off-screen (right)
        if (left + tooltipRect.width > window.innerWidth) {
            left = window.innerWidth - tooltipRect.width - 16;
        }

        // Adjust if tooltip goes off-screen (left)
        if (left < 16) {
            left = 16;
        }

        // Adjust if tooltip goes off-screen (bottom) - position above element instead
        if (top + tooltipRect.height > window.innerHeight + window.scrollY) {
            top = rect.top + window.scrollY - tooltipRect.height - 8;
        }

        // Apply position
        tooltipElement.style.top = `${top}px`;
        tooltipElement.style.left = `${left}px`;

        // Fade in
        setTimeout(() => {
            tooltipElement.classList.add('tooltip-visible');
        }, 10);
    }

    /**
     * Hide attendance tooltip (Story 4.5)
     */
    hideTooltip() {
        const tooltip = document.querySelector('.attendance-tooltip');
        if (tooltip) {
            tooltip.classList.remove('tooltip-visible');
            setTimeout(() => {
                tooltip.remove();
            }, 200); // Wait for fade out animation
        }
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('[AttendanceCalendar] DOM ready, initializing...');
    new AttendanceCalendar();
});
