/**
 * LEAD ATTENDANCE CALENDAR VIEW (Spec 5)
 *
 * JavaScript for the lead attendance calendar.
 * Leads can view attendance and submit new records, but cannot edit or delete existing ones.
 * Locking is enforced server-side by Spec 4 API rules.
 */

class LeadAttendanceCalendar {
    constructor() {
        this.container = document.querySelector('.lead-attendance-container');
        if (!this.container) {
            console.error('[LeadAttendance] Container not found');
            return;
        }

        this.selectedDate = this.container.getAttribute('data-selected-date');
        this.username = this.container.getAttribute('data-username') || 'Unknown';
        this.selectedEmployeeId = this.getSelectedEmployeeId();
        this.attendanceData = {};
        this.statisticsData = {};

        this.STATUS_LABELS = {
            'on_time': 'On-Time',
            'late': 'Late',
            'called_in': 'Called-In',
            'no_call_no_show': 'No-Call-No-Show',
            'excused_absence': 'Excused Absence'
        };

        this.STATUS_ICONS = {
            'on_time': 'check_circle',
            'late': 'schedule',
            'called_in': 'phone',
            'no_call_no_show': 'cancel',
            'excused_absence': 'event_busy'
        };

        this.init();
    }

    /**
     * Initialize the calendar
     */
    async init() {
        console.log('[LeadAttendance] Initializing...');

        this.attachEventListeners();

        await this.loadAttendanceData();
        this.renderCalendar();
        this.renderStatistics();

        console.log('[LeadAttendance] Initialized successfully');
    }

    /**
     * Attach event listeners
     */
    attachEventListeners() {
        // Employee selector change
        var employeeSelector = document.getElementById('employee-selector');
        if (employeeSelector) {
            employeeSelector.addEventListener('change', function(e) {
                this.handleEmployeeChange(e.target.value);
            }.bind(this));
        }

        // Close detail panel when clicking outside
        document.addEventListener('click', function(e) {
            var detailContainer = document.getElementById('date-detail-container');
            var calendarGrid = document.getElementById('calendar-grid');

            if (detailContainer &&
                detailContainer.style.display !== 'none' &&
                !detailContainer.contains(e.target) &&
                calendarGrid && !calendarGrid.contains(e.target)) {
                this.closeDateDetail();
            }
        }.bind(this));
    }

    /**
     * Get selected employee ID from URL
     */
    getSelectedEmployeeId() {
        var urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('employee_id') || null;
    }

    /**
     * Handle employee selector change
     */
    handleEmployeeChange(employeeId) {
        var url = window.location.pathname;
        var params = new URLSearchParams(window.location.search);

        if (employeeId) {
            params.set('employee_id', employeeId);
        } else {
            params.delete('employee_id');
        }

        if (params.toString()) {
            window.location.href = url + '?' + params.toString();
        } else {
            window.location.href = url;
        }
    }

    /**
     * Parse the selected date string into {year, month}
     */
    parseSelectedDate() {
        var parts = this.selectedDate.split('-');
        return {
            year: parseInt(parts[0], 10),
            month: parseInt(parts[1], 10) - 1 // 0-indexed
        };
    }

    /**
     * Load attendance data from API
     */
    async loadAttendanceData() {
        console.log('[LeadAttendance] Loading attendance data...');

        try {
            var parsed = this.parseSelectedDate();
            var monthStr = parsed.year + '-' + String(parsed.month + 1).padStart(2, '0') + '-01';

            var apiUrl = '/api/attendance/month/' + monthStr;
            if (this.selectedEmployeeId) {
                apiUrl += '?employee_id=' + this.selectedEmployeeId;
            }

            var response = await fetch(apiUrl, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                throw new Error('API error: ' + response.status);
            }

            var data = await response.json();
            this.attendanceData = data.attendance_by_date || {};
            this.statisticsData = data.statistics || {};

        } catch (error) {
            console.error('[LeadAttendance] Failed to load attendance:', error);
            this.showNotification('Failed to load attendance data', 'error');
            this.attendanceData = {};
            this.statisticsData = {};
        }
    }

    /**
     * Render the calendar grid
     */
    renderCalendar() {
        var calendarGrid = document.getElementById('calendar-grid');
        if (!calendarGrid) return;

        var parsed = this.parseSelectedDate();
        var year = parsed.year;
        var month = parsed.month;

        var firstDay = new Date(year, month, 1);
        var lastDay = new Date(year, month + 1, 0);
        var startDayOfWeek = firstDay.getDay();
        var totalDays = lastDay.getDate();

        var calendarHTML = '';

        // Empty cells before month starts
        for (var i = 0; i < startDayOfWeek; i++) {
            calendarHTML += '<div class="calendar-day calendar-day--empty"></div>';
        }

        // Day cells
        for (var day = 1; day <= totalDays; day++) {
            var dateStr = year + '-' + String(month + 1).padStart(2, '0') + '-' + String(day).padStart(2, '0');
            var dayData = this.attendanceData[dateStr] || {};
            var hasData = Object.keys(dayData).length > 0;

            var status = this.getDominantStatus(dayData);
            var statusClass = status ? 'calendar-day--' + status : 'calendar-day--no-data';

            var today = new Date();
            var isToday = (year === today.getFullYear() && month === today.getMonth() && day === today.getDate());

            calendarHTML +=
                '<div class="calendar-day ' + statusClass + (isToday ? ' calendar-day--today' : '') + '"' +
                ' data-date="' + dateStr + '"' +
                ' role="button"' +
                ' tabindex="0"' +
                ' aria-label="' + this.getDateAriaLabel(day, dateStr, dayData) + '">' +
                '<div class="calendar-day-number">' + day + '</div>' +
                (hasData ? this.renderDayBadges(dayData) : '<div class="calendar-day-no-data">No records</div>') +
                '</div>';
        }

        calendarGrid.innerHTML = calendarHTML;

        // Attach click + keyboard listeners
        var self = this;
        calendarGrid.querySelectorAll('.calendar-day[data-date]').forEach(function(dayCell) {
            dayCell.addEventListener('click', function(e) {
                var ds = e.currentTarget.getAttribute('data-date');
                if (ds) self.showDateDetail(ds);
            });

            dayCell.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    var ds = e.currentTarget.getAttribute('data-date');
                    if (ds) self.showDateDetail(ds);
                }
            });

            // Tooltip on hover
            var ds = dayCell.getAttribute('data-date');
            if (ds) {
                dayCell.addEventListener('mouseenter', function(e) {
                    self.showTooltip(e.currentTarget, ds);
                });
                dayCell.addEventListener('mouseleave', function() {
                    self.hideTooltip();
                });
            }
        });
    }

    /**
     * Get dominant attendance status for a date
     */
    getDominantStatus(dayData) {
        if (!dayData || Object.keys(dayData).length === 0) return null;

        var statusCounts = {
            no_call_no_show: 0,
            late: 0,
            called_in: 0,
            excused_absence: 0,
            on_time: 0
        };

        Object.values(dayData).forEach(function(records) {
            if (!Array.isArray(records)) records = [records];
            records.forEach(function(record) {
                if (statusCounts.hasOwnProperty(record.status)) {
                    statusCounts[record.status]++;
                }
            });
        });

        // Priority: no_call_no_show > late > called_in > excused_absence > on_time
        if (statusCounts.no_call_no_show > 0) return 'no_call_no_show';
        if (statusCounts.late > 0) return 'late';
        if (statusCounts.called_in > 0) return 'called_in';
        if (statusCounts.excused_absence > 0) return 'excused_absence';
        if (statusCounts.on_time > 0) return 'on_time';

        return null;
    }

    /**
     * Render day badges (record count)
     */
    renderDayBadges(dayData) {
        if (!dayData || Object.keys(dayData).length === 0) {
            return '<div class="calendar-day-no-data">No records</div>';
        }

        var totalRecords = 0;
        Object.values(dayData).forEach(function(records) {
            if (Array.isArray(records)) {
                totalRecords += records.length;
            } else {
                totalRecords += 1;
            }
        });

        return '<div class="calendar-day-count">' + totalRecords + ' record' + (totalRecords !== 1 ? 's' : '') + '</div>';
    }

    /**
     * Get ARIA label for a date cell
     */
    getDateAriaLabel(day, dateStr, dayData) {
        var parts = dateStr.split('-');
        var date = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
        var dayName = date.toLocaleDateString('en-US', { weekday: 'long' });
        var monthName = date.toLocaleDateString('en-US', { month: 'long' });

        var label = dayName + ', ' + monthName + ' ' + day;

        if (dayData && Object.keys(dayData).length > 0) {
            var totalRecords = 0;
            Object.values(dayData).forEach(function(records) {
                if (Array.isArray(records)) {
                    totalRecords += records.length;
                } else {
                    totalRecords += 1;
                }
            });
            label += ', ' + totalRecords + ' attendance record' + (totalRecords !== 1 ? 's' : '');
        } else {
            label += ', No attendance records';
        }

        return label;
    }

    /**
     * Show date detail panel — fetches scheduled employees for the date
     */
    async showDateDetail(dateStr) {
        console.log('[LeadAttendance] Showing detail for:', dateStr);

        var detailContainer = document.getElementById('date-detail-container');
        if (!detailContainer) return;

        // Show loading state
        var parts = dateStr.split('-');
        var date = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
        var formattedDate = date.toLocaleDateString('en-US', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });

        detailContainer.innerHTML =
            '<div class="date-detail-header">' +
            '<h3 class="date-detail-title">' + formattedDate + '</h3>' +
            '<button class="btn-close-detail" aria-label="Close detail panel">&times;</button>' +
            '</div>' +
            '<div class="loading-spinner">Loading scheduled employees...</div>';
        detailContainer.style.display = 'block';

        // Attach close button
        var self = this;
        var closeBtn = detailContainer.querySelector('.btn-close-detail');
        if (closeBtn) {
            closeBtn.addEventListener('click', function() { self.closeDateDetail(); });
        }

        // Fetch scheduled employees with attendance
        try {
            var response = await fetch('/api/attendance/scheduled-employees/' + dateStr, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                throw new Error('API error: ' + response.status);
            }

            var data = await response.json();
            this.renderDateDetail(detailContainer, formattedDate, dateStr, data.scheduled_employees || []);

        } catch (error) {
            console.error('[LeadAttendance] Failed to load scheduled employees:', error);
            detailContainer.innerHTML =
                '<div class="date-detail-header">' +
                '<h3 class="date-detail-title">' + formattedDate + '</h3>' +
                '<button class="btn-close-detail" aria-label="Close detail panel">&times;</button>' +
                '</div>' +
                '<div class="date-detail-empty">Error loading employee data. Please try again.</div>';

            closeBtn = detailContainer.querySelector('.btn-close-detail');
            if (closeBtn) {
                closeBtn.addEventListener('click', function() { self.closeDateDetail(); });
            }
        }

        // Scroll into view
        detailContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    /**
     * Render the date detail panel with scheduled employees
     */
    renderDateDetail(container, formattedDate, dateStr, scheduledEmployees) {
        var self = this;
        var html =
            '<div class="date-detail-header">' +
            '<h3 class="date-detail-title">' + formattedDate + '</h3>' +
            '<button class="btn-close-detail" aria-label="Close detail panel">&times;</button>' +
            '</div>';

        if (scheduledEmployees.length === 0) {
            html += '<div class="date-detail-empty">No employees scheduled for this date.</div>';
        } else {
            // Filter by selected employee if set
            var filtered = scheduledEmployees;
            if (this.selectedEmployeeId) {
                filtered = scheduledEmployees.filter(function(emp) {
                    return emp.employee_id === self.selectedEmployeeId;
                });
            }

            if (filtered.length === 0) {
                html += '<div class="date-detail-empty">No matching employees scheduled for this date.</div>';
            } else {
                html += '<div class="date-detail-records">';

                filtered.forEach(function(emp) {
                    if (emp.attendance_status) {
                        // Employee HAS an existing record — show read-only with lock
                        html += self.renderExistingRecord(emp);
                    } else {
                        // Employee has NO record — show submit form
                        html += self.renderSubmitForm(emp, dateStr);
                    }
                });

                html += '</div>';
            }
        }

        container.innerHTML = html;

        // Re-attach close button
        var closeBtn = container.querySelector('.btn-close-detail');
        if (closeBtn) {
            closeBtn.addEventListener('click', function() { self.closeDateDetail(); });
        }

        // Attach submit button listeners
        container.querySelectorAll('[data-action="submit-attendance"]').forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                var employeeId = e.currentTarget.getAttribute('data-employee-id');
                self.submitAttendance(employeeId, dateStr, e.currentTarget);
            });
        });
    }

    /**
     * Render an existing attendance record (read-only with lock icon)
     */
    renderExistingRecord(emp) {
        var statusLabel = this.STATUS_LABELS[emp.attendance_status] || emp.attendance_status;
        var statusIcon = this.STATUS_ICONS[emp.attendance_status] || 'help';
        var employeeName = typeof toTitleCase === 'function' ? toTitleCase(emp.employee_name) : emp.employee_name;
        var escapedName = typeof escapeHtml === 'function' ? escapeHtml(employeeName) : employeeName;

        var html =
            '<div class="employee-attendance-card">' +
            '<div class="employee-card-header">' +
            '<span class="employee-card-name">' + escapedName + '</span>' +
            '<span class="employee-card-time">Start: ' + (typeof escapeHtml === 'function' ? escapeHtml(emp.earliest_start_time) : emp.earliest_start_time) + '</span>' +
            '</div>' +
            '<div>' +
            '<span class="attendance-badge attendance-badge--' + emp.attendance_status + '">' +
            '<span class="material-symbols-outlined" style="font-size: 16px;">' + statusIcon + '</span> ' +
            statusLabel +
            '</span>' +
            '<span class="lock-indicator">' +
            '<span class="material-symbols-outlined">lock</span> Locked' +
            '</span>' +
            '</div>';

        // Notes
        if (emp.attendance_notes) {
            html += '<div class="record-notes">' + (typeof escapeHtml === 'function' ? escapeHtml(emp.attendance_notes) : emp.attendance_notes) + '</div>';
        }

        // Audit trail
        html += '<div class="audit-info">';

        if (emp.recorded_by) {
            html += '<div class="audit-recorded-by">Recorded by ' + (typeof escapeHtml === 'function' ? escapeHtml(emp.recorded_by) : emp.recorded_by) + '</div>';
        }

        if (emp.is_modified && emp.modified_by) {
            var modifiedAt = emp.modified_at ? new Date(emp.modified_at).toLocaleString('en-US', {
                month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true
            }) : '';
            html += '<div class="audit-modified-by">Modified by ' +
                (typeof escapeHtml === 'function' ? escapeHtml(emp.modified_by) : emp.modified_by) +
                (modifiedAt ? ' on ' + modifiedAt : '') +
                '</div>';
        }

        html += '</div>'; // .audit-info
        html += '</div>'; // .employee-attendance-card

        return html;
    }

    /**
     * Render submit attendance form for an employee without a record
     */
    renderSubmitForm(emp, dateStr) {
        var employeeName = typeof toTitleCase === 'function' ? toTitleCase(emp.employee_name) : emp.employee_name;
        var escapedName = typeof escapeHtml === 'function' ? escapeHtml(employeeName) : employeeName;
        var escapedId = typeof escapeHtml === 'function' ? escapeHtml(emp.employee_id) : emp.employee_id;

        return (
            '<div class="submit-attendance-form" id="form-' + emp.employee_id + '">' +
            '<div class="submit-form-header">' +
            '<span class="submit-form-name">' + escapedName + '</span>' +
            '<span class="submit-form-time">Start: ' + (typeof escapeHtml === 'function' ? escapeHtml(emp.earliest_start_time) : emp.earliest_start_time) + '</span>' +
            '</div>' +
            '<label class="submit-form-label">No attendance recorded &mdash; select status to submit:</label>' +
            '<div class="submit-form-controls">' +
            '<select class="submit-form-select" id="status-' + emp.employee_id + '" aria-label="Attendance status for ' + escapedName + '">' +
            '<option value="">-- Select Status --</option>' +
            '<option value="on_time">On-Time</option>' +
            '<option value="late">Late</option>' +
            '<option value="called_in">Called-In</option>' +
            '<option value="no_call_no_show">No-Call-No-Show</option>' +
            '<option value="excused_absence">Excused Absence</option>' +
            '</select>' +
            '<input type="text" class="submit-form-notes" id="notes-' + emp.employee_id + '"' +
            ' placeholder="Notes (optional)" aria-label="Attendance notes for ' + escapedName + '">' +
            '<button class="btn-submit-attendance" data-action="submit-attendance"' +
            ' data-employee-id="' + escapedId + '"' +
            ' aria-label="Submit attendance for ' + escapedName + '">Submit</button>' +
            '</div>' +
            '<div id="result-' + emp.employee_id + '"></div>' +
            '</div>'
        );
    }

    /**
     * Submit attendance record for an employee
     */
    async submitAttendance(employeeId, dateStr, buttonEl) {
        var statusSelect = document.getElementById('status-' + employeeId);
        var notesInput = document.getElementById('notes-' + employeeId);
        var resultDiv = document.getElementById('result-' + employeeId);

        if (!statusSelect || !statusSelect.value) {
            this.showInlineResult(resultDiv, 'Please select an attendance status.', 'error');
            return;
        }

        var status = statusSelect.value;
        var notes = notesInput ? notesInput.value.trim() : '';

        // Disable button during submission
        buttonEl.disabled = true;
        buttonEl.textContent = 'Submitting...';

        try {
            var response = await fetch('/api/attendance', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': this.getCsrfToken()
                },
                body: JSON.stringify({
                    employee_id: employeeId,
                    attendance_date: dateStr,
                    status: status,
                    notes: notes
                })
            });

            var data = await response.json();

            if (response.ok && data.success) {
                this.showInlineResult(resultDiv, 'Attendance recorded successfully!', 'success');
                this.showNotification('Attendance submitted', 'success');

                // Reload data and refresh calendar
                await this.loadAttendanceData();
                this.renderCalendar();
                this.renderStatistics();

                // Refresh detail panel after a brief delay
                var self = this;
                setTimeout(function() {
                    self.showDateDetail(dateStr);
                }, 500);

            } else if (response.status === 403) {
                // Locking enforcement from Spec 4
                this.showInlineResult(resultDiv, data.error || 'This record is locked. Only the supervisor can modify it.', 'error');
                buttonEl.disabled = false;
                buttonEl.textContent = 'Submit';
            } else {
                throw new Error(data.error || 'Failed to submit attendance');
            }

        } catch (error) {
            console.error('[LeadAttendance] Submit failed:', error);
            this.showInlineResult(resultDiv, error.message || 'Failed to submit attendance. Please try again.', 'error');
            buttonEl.disabled = false;
            buttonEl.textContent = 'Submit';
        }
    }

    /**
     * Show inline result message in a form
     */
    showInlineResult(resultDiv, message, type) {
        if (!resultDiv) return;
        var escaped = typeof escapeHtml === 'function' ? escapeHtml(message) : message;
        resultDiv.innerHTML = '<div class="submit-result submit-result--' + type + '">' + escaped + '</div>';

        // Auto-clear after 5 seconds for errors
        if (type === 'error') {
            setTimeout(function() {
                resultDiv.innerHTML = '';
            }, 5000);
        }
    }

    /**
     * Close date detail panel
     */
    closeDateDetail() {
        var detailContainer = document.getElementById('date-detail-container');
        if (detailContainer) {
            detailContainer.style.display = 'none';
            detailContainer.innerHTML = '';
        }
    }

    /**
     * Render statistics
     */
    renderStatistics() {
        var statsContainer = document.getElementById('attendance-stats');
        if (!statsContainer) return;

        if (!this.statisticsData || Object.keys(this.statisticsData).length === 0) {
            statsContainer.innerHTML = '<div class="stats-empty">No attendance data for this period.</div>';
            return;
        }

        var stats = this.statisticsData;

        statsContainer.innerHTML =
            '<h3 class="stats-title">Monthly Summary</h3>' +
            '<div class="stats-grid">' +
            '<div class="stat-card stat-card--total">' +
            '<div class="stat-value">' + (stats.total_records || 0) + '</div>' +
            '<div class="stat-label">Total Records</div>' +
            '</div>' +
            '<div class="stat-card stat-card--on-time">' +
            '<div class="stat-value">' + (stats.on_time || 0) + '</div>' +
            '<div class="stat-label">On-Time</div>' +
            '</div>' +
            '<div class="stat-card stat-card--late">' +
            '<div class="stat-value">' + (stats.late || 0) + '</div>' +
            '<div class="stat-label">Late</div>' +
            '</div>' +
            '<div class="stat-card stat-card--called-in">' +
            '<div class="stat-value">' + (stats.called_in || 0) + '</div>' +
            '<div class="stat-label">Called-In</div>' +
            '</div>' +
            '<div class="stat-card stat-card--no-call">' +
            '<div class="stat-value">' + (stats.no_call_no_show || 0) + '</div>' +
            '<div class="stat-label">No-Call-No-Show</div>' +
            '</div>' +
            '<div class="stat-card stat-card--rate">' +
            '<div class="stat-value">' + (stats.on_time_rate || '0%') + '</div>' +
            '<div class="stat-label">On-Time Rate</div>' +
            '</div>' +
            '</div>';
    }

    /**
     * Show tooltip on hover
     */
    showTooltip(element, dateStr) {
        this.hideTooltip();

        var dayData = this.attendanceData[dateStr] || {};
        if (Object.keys(dayData).length === 0) return;

        var statusCounts = {
            on_time: 0,
            late: 0,
            called_in: 0,
            no_call_no_show: 0,
            excused_absence: 0
        };

        var totalRecords = 0;
        Object.values(dayData).forEach(function(records) {
            if (!Array.isArray(records)) records = [records];
            records.forEach(function(record) {
                if (statusCounts.hasOwnProperty(record.status)) {
                    statusCounts[record.status]++;
                }
                totalRecords++;
            });
        });

        var tooltipHTML =
            '<div class="attendance-tooltip" role="tooltip">' +
            '<div class="tooltip-header">' +
            '<strong>' + totalRecords + ' Record' + (totalRecords !== 1 ? 's' : '') + '</strong>' +
            '</div>' +
            '<div class="tooltip-body">' +
            (statusCounts.on_time > 0 ? '<div class="tooltip-item">On-Time: ' + statusCounts.on_time + '</div>' : '') +
            (statusCounts.late > 0 ? '<div class="tooltip-item">Late: ' + statusCounts.late + '</div>' : '') +
            (statusCounts.called_in > 0 ? '<div class="tooltip-item">Called-In: ' + statusCounts.called_in + '</div>' : '') +
            (statusCounts.no_call_no_show > 0 ? '<div class="tooltip-item">No-Call-No-Show: ' + statusCounts.no_call_no_show + '</div>' : '') +
            (statusCounts.excused_absence > 0 ? '<div class="tooltip-item">Excused: ' + statusCounts.excused_absence + '</div>' : '') +
            '</div>' +
            '<div class="tooltip-footer">Click for details</div>' +
            '</div>';

        var tooltip = document.createElement('div');
        tooltip.innerHTML = tooltipHTML;
        var tooltipElement = tooltip.firstElementChild;
        document.body.appendChild(tooltipElement);

        // Position below element
        var rect = element.getBoundingClientRect();
        var tooltipRect = tooltipElement.getBoundingClientRect();

        var top = rect.bottom + window.scrollY + 8;
        var left = rect.left + window.scrollX + (rect.width / 2) - (tooltipRect.width / 2);

        if (left + tooltipRect.width > window.innerWidth) {
            left = window.innerWidth - tooltipRect.width - 16;
        }
        if (left < 16) {
            left = 16;
        }
        if (top + tooltipRect.height > window.innerHeight + window.scrollY) {
            top = rect.top + window.scrollY - tooltipRect.height - 8;
        }

        tooltipElement.style.top = top + 'px';
        tooltipElement.style.left = left + 'px';

        setTimeout(function() {
            tooltipElement.classList.add('tooltip-visible');
        }, 10);
    }

    /**
     * Hide tooltip
     */
    hideTooltip() {
        var tooltip = document.querySelector('.attendance-tooltip');
        if (tooltip) {
            tooltip.classList.remove('tooltip-visible');
            setTimeout(function() {
                tooltip.remove();
            }, 200);
        }
    }

    /**
     * Show notification via toaster
     */
    showNotification(message, type) {
        if (window.toaster) {
            window.toaster.show(message, type);
        } else {
            console.log('[LeadAttendance] ' + type + ': ' + message);
        }
    }

    /**
     * Get CSRF token
     */
    getCsrfToken() {
        if (typeof window.getCsrfToken === 'function') {
            return window.getCsrfToken();
        }
        var metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) {
            return metaTag.getAttribute('content');
        }
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var parts = cookies[i].trim().split('=');
            if (parts[0] === 'csrf_token') {
                return parts[1];
            }
        }
        return '';
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('[LeadAttendance] DOM ready, initializing...');
    new LeadAttendanceCalendar();
});
