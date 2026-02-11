/**
 * Weekly Validation Dashboard
 * Handles filtering, modals, and action buttons for the weekly validation page.
 */

function escapeHtml(text) {
    if (text == null) return '';
    return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

document.addEventListener('DOMContentLoaded', function () {
    // Day filter
    document.querySelectorAll('.day-pill').forEach(function (pill) {
        pill.addEventListener('click', function () {
            document.querySelectorAll('.day-pill').forEach(function (p) { p.classList.remove('active'); });
            this.classList.add('active');
            filterIssues();
        });
    });

    // Severity filter
    document.querySelectorAll('.filter-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.filter-btn').forEach(function (b) { b.classList.remove('active'); });
            this.classList.add('active');
            filterIssues();
        });
    });

    // Initialize counts on page load
    updateIssueCounts();
});

function filterIssues() {
    var dayFilter = document.querySelector('.day-pill.active').dataset.filter;
    var severityFilter = document.querySelector('.filter-btn.active').dataset.severity;

    document.querySelectorAll('.issue-item').forEach(function (item) {
        var matchesDay = dayFilter === 'all' || item.dataset.date === dayFilter || item.dataset.date === 'weekly';
        var matchesSeverity = severityFilter === 'all' || item.dataset.severity === severityFilter;
        item.style.display = (matchesDay && matchesSeverity) ? '' : 'none';
    });
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('show');
}

function showLoading() {
    document.getElementById('loading').classList.add('show');
}

function hideLoading() {
    document.getElementById('loading').classList.remove('show');
}

// ===== CSRF TOKEN HELPER =====
function getCsrfToken() {
    // Try to get from cookie first
    var name = 'csrf_token=';
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i].trim();
        if (cookie.startsWith(name)) {
            return cookie.substring(name.length);
        }
    }
    // Fallback to meta tag
    var metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag) return metaTag.content;
    // Fallback to global function
    if (window.getCsrfToken) return window.getCsrfToken();
    return '';
}

// ===== EVENT DELEGATION FOR ACTION BUTTONS =====

// Reschedule buttons
document.addEventListener('click', function(e) {
    var btn = e.target.closest('.reschedule-btn');
    if (!btn) return;
    openRescheduleModal(
        btn.dataset.scheduleId,
        btn.dataset.employeeName,
        btn.dataset.date,
        btn.dataset.eventType
    );
});

// Change employee buttons
document.addEventListener('click', function(e) {
    var btn = e.target.closest('.change-employee-btn');
    if (!btn) return;
    openChangeEmployeeModal(
        btn.dataset.scheduleId,
        btn.dataset.employeeName,
        btn.dataset.date,
        btn.dataset.eventType
    );
});

// Unschedule buttons
document.addEventListener('click', function(e) {
    var btn = e.target.closest('.unschedule-btn');
    if (!btn) return;
    unscheduleEvent(btn.dataset.scheduleId);
});

// Rotation buttons
document.addEventListener('click', function(e) {
    var btn = e.target.closest('.rotation-btn');
    if (!btn) return;
    reassignToRotation(
        btn.dataset.scheduleId,
        btn.dataset.rotationEmployee,
        btn.dataset.date
    );
});

// ===== RESCHEDULE MODAL =====
var currentRescheduleEventType = null;  // Store event type for date change handler

function openRescheduleModal(scheduleId, employeeName, dateStr, eventType) {
    document.getElementById('reschedule-schedule-id').value = scheduleId;
    document.getElementById('reschedule-employee').value = employeeName || 'Unknown';
    document.getElementById('reschedule-date').value = dateStr;
    currentRescheduleEventType = eventType;

    // Load valid times for the event type with scheduled counts
    if (eventType) {
        loadValidTimes(eventType, 'reschedule-time', dateStr);
    }

    document.getElementById('reschedule-modal').classList.add('show');
}

// Reload times when reschedule date changes
var rescheduleDateEl = document.getElementById('reschedule-date');
if (rescheduleDateEl) {
    rescheduleDateEl.addEventListener('change', function() {
        if (currentRescheduleEventType) {
            loadValidTimes(currentRescheduleEventType, 'reschedule-time', this.value);
        }
    });
}

async function loadValidTimes(eventType, selectId, dateStr) {
    try {
        // Build URL with date parameter to get scheduled counts
        var url = '/api/event-allowed-times/' + encodeURIComponent(eventType);
        if (dateStr) {
            url += '?date=' + dateStr;
        }

        var response = await fetch(url);
        if (response.ok) {
            var data = await response.json();
            var select = document.getElementById(selectId);
            select.innerHTML = '';

            // Use time_details which includes scheduled counts
            var times = data.time_details || data.allowed_times || [];

            if (times.length === 0) {
                // No time restrictions - add common times
                var defaultTimes = ['09:00', '10:00', '11:00', '12:00'];
                defaultTimes.forEach(function (t) {
                    var option = document.createElement('option');
                    option.value = t;
                    option.textContent = t;
                    select.appendChild(option);
                });
            } else {
                times.forEach(function (time) {
                    var option = document.createElement('option');
                    // Handle both object format {value, label} and string format
                    if (typeof time === 'object') {
                        option.value = time.value;
                        option.textContent = time.label;
                    } else {
                        option.value = time;
                        option.textContent = time;
                    }
                    select.appendChild(option);
                });
            }
        }
    } catch (err) {
        console.error('Error loading times:', err);
    }
}

var rescheduleForm = document.getElementById('reschedule-form');
if (rescheduleForm) {
    rescheduleForm.addEventListener('submit', async function (e) {
        e.preventDefault();
        var scheduleId = document.getElementById('reschedule-schedule-id').value;
        var newDate = document.getElementById('reschedule-date').value;
        var newTime = document.getElementById('reschedule-time').value;

        showLoading();

        try {
            var response = await fetch('/api/event/' + scheduleId + '/reschedule', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                body: JSON.stringify({
                    new_date: newDate,
                    new_time: newTime,
                    override_conflicts: true
                })
            });

            if (response.ok) {
                location.reload();
            } else {
                var data = await response.json();
                alert('Error: ' + (data.error || 'Failed to reschedule'));
            }
        } catch (err) {
            alert('Error: ' + err.message);
        } finally {
            hideLoading();
            closeModal('reschedule-modal');
        }
    });
}

// ===== CHANGE EMPLOYEE MODAL =====
async function openChangeEmployeeModal(scheduleId, currentEmployee, dateStr, eventType) {
    document.getElementById('change-schedule-id').value = scheduleId;
    document.getElementById('change-current-employee').value = currentEmployee || 'Unknown';
    document.getElementById('change-selected-employee').value = '';
    document.getElementById('confirm-change-btn').disabled = true;

    // Load available employees
    var employeeList = document.getElementById('employee-list');
    employeeList.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div> Loading...</div>';

    document.getElementById('change-employee-modal').classList.add('show');

    try {
        var url = eventType
            ? '/api/available_employees_for_change/' + dateStr + '/' + eventType
            : '/api/available_employees_for_change/' + dateStr + '/Core';

        var response = await fetch(url);
        if (response.ok) {
            var data = await response.json();
            renderEmployeeList(data.employees || data, 'employee-list', 'change');
        } else {
            employeeList.innerHTML = '<div class="text-danger">Error loading employees</div>';
        }
    } catch (err) {
        employeeList.innerHTML = '<div class="text-danger">Error: ' + err.message + '</div>';
    }
}

function renderEmployeeList(employees, containerId, mode) {
    var container = document.getElementById(containerId);
    if (!employees || employees.length === 0) {
        container.innerHTML = '<div class="text-muted py-3">No available employees found</div>';
        return;
    }

    container.innerHTML = employees.map(function (emp) {
        return '<div class="employee-option" data-action="select-employee" data-employee-id="' + emp.id + '" data-employee-name="' + escapeHtml(emp.name) + '" data-mode="' + mode + '">' +
            '<div>' +
                '<div class="employee-name">' + escapeHtml(emp.name) + '</div>' +
                '<div class="employee-title">' + escapeHtml(emp.job_title || '') + '</div>' +
            '</div>' +
            (emp.scheduled_count !== undefined ? '<span class="badge bg-secondary">' + emp.scheduled_count + ' events</span>' : '') +
        '</div>';
    }).join('');
}

function selectEmployee(employeeId, employeeName, mode) {
    // Remove selected class from all options in this mode
    var container = mode === 'change' ? 'employee-list' : 'quick-schedule-employee-list';
    document.querySelectorAll('#' + container + ' .employee-option').forEach(function (opt) { opt.classList.remove('selected'); });

    // Add selected class to clicked option
    event.currentTarget.classList.add('selected');

    // Update hidden field and enable button
    if (mode === 'change') {
        document.getElementById('change-selected-employee').value = employeeId;
        document.getElementById('confirm-change-btn').disabled = false;
    } else {
        document.getElementById('quick-schedule-selected-employee').value = employeeId;
        document.getElementById('confirm-schedule-btn').disabled = false;
    }
}

async function confirmChangeEmployee() {
    var scheduleId = document.getElementById('change-schedule-id').value;
    var newEmployeeId = document.getElementById('change-selected-employee').value;

    if (!newEmployeeId) {
        alert('Please select an employee');
        return;
    }

    showLoading();

    try {
        var response = await fetch('/api/event/' + scheduleId + '/change-employee', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({
                new_employee_id: newEmployeeId,
                override_conflicts: true
            })
        });

        if (response.ok) {
            location.reload();
        } else {
            var data = await response.json();
            alert('Error: ' + (data.error || 'Failed to change employee'));
        }
    } catch (err) {
        alert('Error: ' + err.message);
    } finally {
        hideLoading();
        closeModal('change-employee-modal');
    }
}

// ===== QUICK SCHEDULE MODAL =====
// Event delegation for quick schedule buttons
document.addEventListener('click', function(e) {
    var btn = e.target.closest('.quick-schedule-btn');
    if (!btn) return;

    var eventId = btn.dataset.eventId;
    var eventName = btn.dataset.eventName;
    var eventType = btn.dataset.eventType;
    openQuickScheduleModal(eventId, eventName, eventType);
});

async function openQuickScheduleModal(eventId, eventName, eventType) {
    document.getElementById('quick-schedule-event-id').value = eventId;
    document.getElementById('quick-schedule-event-name').value = eventName;
    document.getElementById('quick-schedule-event-type').value = eventType;
    document.getElementById('quick-schedule-selected-employee').value = '';
    document.getElementById('confirm-schedule-btn').disabled = true;

    // Set default date to tomorrow
    var tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    var tomorrowStr = tomorrow.toISOString().split('T')[0];
    document.getElementById('quick-schedule-date').value = tomorrowStr;

    // Load valid times with scheduled counts
    loadValidTimes(eventType, 'quick-schedule-time', tomorrowStr);

    // Load available employees
    var employeeList = document.getElementById('quick-schedule-employee-list');
    employeeList.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div> Loading...</div>';

    document.getElementById('quick-schedule-modal').classList.add('show');

    try {
        var dateStr = document.getElementById('quick-schedule-date').value;
        var response = await fetch('/api/available_employees_for_change/' + dateStr + '/' + eventType);
        if (response.ok) {
            var data = await response.json();
            renderEmployeeList(data.employees || data, 'quick-schedule-employee-list', 'schedule');
        } else {
            employeeList.innerHTML = '<div class="text-danger">Error loading employees</div>';
        }
    } catch (err) {
        employeeList.innerHTML = '<div class="text-danger">Error: ' + err.message + '</div>';
    }
}

// Update employee list and times when date changes
var quickScheduleDateEl = document.getElementById('quick-schedule-date');
if (quickScheduleDateEl) {
    quickScheduleDateEl.addEventListener('change', async function() {
        var dateStr = this.value;
        var eventType = document.getElementById('quick-schedule-event-type').value || 'Core';

        // Reload times with new date to show updated scheduled counts
        loadValidTimes(eventType, 'quick-schedule-time', dateStr);

        var employeeList = document.getElementById('quick-schedule-employee-list');
        employeeList.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div> Loading...</div>';

        try {
            var response = await fetch('/api/available_employees_for_change/' + dateStr + '/' + eventType);
            if (response.ok) {
                var data = await response.json();
                renderEmployeeList(data.employees || data, 'quick-schedule-employee-list', 'schedule');
            }
        } catch (err) {
            console.error('Error loading employees:', err);
        }
    });
}

async function confirmQuickSchedule() {
    var eventId = document.getElementById('quick-schedule-event-id').value;
    var dateStr = document.getElementById('quick-schedule-date').value;
    var timeStr = document.getElementById('quick-schedule-time').value;
    var employeeId = document.getElementById('quick-schedule-selected-employee').value;

    if (!employeeId) {
        alert('Please select an employee');
        return;
    }

    showLoading();

    try {
        var response = await fetch('/api/schedule-event', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({
                event_ref_num: eventId,
                employee_id: employeeId,
                schedule_date: dateStr,
                schedule_time: timeStr,
                override_conflicts: true
            })
        });

        if (response.ok) {
            location.reload();
        } else {
            var data = await response.json();
            alert('Error: ' + (data.error || 'Failed to schedule event'));
        }
    } catch (err) {
        alert('Error: ' + err.message);
    } finally {
        hideLoading();
        closeModal('quick-schedule-modal');
    }
}

// ===== EMPLOYEE SCHEDULES MODAL (for conflicts) =====
async function showEmployeeSchedules(employeeId, dateStr, eventType) {
    var container = document.getElementById('employee-schedules-list');
    container.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div> Loading...</div>';

    document.getElementById('employee-schedules-modal').classList.add('show');

    try {
        // Get employee's schedules for this date
        var response = await fetch('/api/events/daily/' + dateStr);
        if (response.ok) {
            var data = await response.json();
            var employeeSchedules = data.events.filter(function (ev) { return ev.employee_id === employeeId; });

            if (employeeSchedules.length === 0) {
                container.innerHTML = '<div class="text-muted py-3">No schedules found for this employee on this date</div>';
                return;
            }

            container.innerHTML = employeeSchedules.map(function (sched) {
                return '<div class="employee-option">' +
                    '<div>' +
                        '<div class="employee-name">' + escapeHtml(sched.event_name) + '</div>' +
                        '<div class="employee-title">' + escapeHtml(sched.event_type) + ' - ' + escapeHtml(sched.start_time) + '</div>' +
                    '</div>' +
                    '<div class="d-flex gap-2">' +
                        '<button class="action-btn primary" data-action="open-change-employee" data-schedule-id="' + sched.schedule_id + '" data-employee-name="' + escapeHtml(sched.employee_name) + '" data-date="' + dateStr + '" data-event-type="' + escapeHtml(sched.event_type) + '">' +
                            '<i class="fas fa-user-edit"></i> Reassign' +
                        '</button>' +
                        '<button class="action-btn danger" data-action="unschedule-and-close" data-schedule-id="' + sched.schedule_id + '">' +
                            '<i class="fas fa-times"></i> Remove' +
                        '</button>' +
                    '</div>' +
                '</div>';
            }).join('');
        }
    } catch (err) {
        container.innerHTML = '<div class="text-danger">Error: ' + err.message + '</div>';
    }
}

// ===== ASSIGN SUPERVISOR EVENT =====
async function assignSupervisorEvent(coreEventRef, dateStr) {
    showLoading();

    try {
        var response = await fetch('/dashboard/api/validation/assign-supervisor', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({
                core_event_ref: coreEventRef,
                date: dateStr
            })
        });

        var data = await response.json();

        if (response.ok && data.success) {
            alert('Supervisor event assigned successfully!');
            location.reload();
        } else {
            alert('Error: ' + (data.error || 'Failed to assign supervisor'));
        }
    } catch (err) {
        alert('Error: ' + err.message);
    } finally {
        hideLoading();
    }
}

// ===== REASSIGN TO ROTATION PERSON =====
async function reassignToRotation(scheduleId, rotationEmployee, dateStr) {
    if (!confirm('Reassign this event to ' + rotationEmployee + ' (the rotation employee for this day)?')) return;

    showLoading();

    try {
        // First get the rotation employee's ID
        var response = await fetch('/api/available_employees_for_change/' + dateStr + '/Juicer');
        if (!response.ok) throw new Error('Failed to load employees');

        var data = await response.json();
        var employees = data.employees || data;
        var rotationEmp = employees.find(function (e) { return e.name === rotationEmployee; });

        if (!rotationEmp) {
            alert('Could not find ' + rotationEmployee + ' in available employees');
            return;
        }

        // Now change the employee
        var changeResponse = await fetch('/api/event/' + scheduleId + '/change-employee', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({
                new_employee_id: rotationEmp.id,
                override_conflicts: true
            })
        });

        if (changeResponse.ok) {
            location.reload();
        } else {
            var errorData = await changeResponse.json();
            alert('Error: ' + (errorData.error || 'Failed to reassign'));
        }
    } catch (err) {
        alert('Error: ' + err.message);
    } finally {
        hideLoading();
    }
}

// ===== SHOW DUPLICATE EVENTS =====
// Event delegation for duplicate events buttons
document.addEventListener('click', function(e) {
    var btn = e.target.closest('.duplicate-events-btn');
    if (!btn) return;

    var events = [];
    try {
        events = JSON.parse(btn.dataset.events || '[]');
    } catch (parseErr) {
        console.error('Failed to parse events:', parseErr);
    }
    var dateStr = btn.dataset.date;
    showDuplicateEvents(events, dateStr);
});

function showDuplicateEvents(events, dateStr) {
    var container = document.getElementById('employee-schedules-list');

    container.innerHTML =
        '<p class="text-muted mb-3">Multiple events for the same product are scheduled. Choose one to reschedule or remove:</p>' +
        events.map(function (evt) {
            return '<div class="employee-option">' +
                '<div>' +
                    '<div class="employee-name">' + escapeHtml(evt.event_name) + '</div>' +
                    '<div class="employee-title">Schedule ID: ' + evt.schedule_id + '</div>' +
                '</div>' +
                '<div class="d-flex gap-2">' +
                    '<button class="action-btn primary" data-action="open-reschedule" data-schedule-id="' + evt.schedule_id + '" data-date="' + dateStr + '" data-event-type="Core">' +
                        '<i class="fas fa-clock"></i> Move' +
                    '</button>' +
                    '<button class="action-btn danger" data-action="unschedule-and-close" data-schedule-id="' + evt.schedule_id + '">' +
                        '<i class="fas fa-times"></i> Remove' +
                    '</button>' +
                '</div>' +
            '</div>';
        }).join('');

    document.getElementById('employee-schedules-modal').classList.add('show');
}

// ===== UNSCHEDULE EVENT =====
async function unscheduleEvent(scheduleId) {
    if (!confirm('Are you sure you want to unschedule this event?')) return;

    showLoading();

    try {
        var response = await fetch('/api/event/' + scheduleId + '/unschedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() }
        });

        if (response.ok) {
            location.reload();
        } else {
            var data = await response.json();
            alert('Error: ' + (data.error || 'Failed to unschedule'));
        }
    } catch (err) {
        alert('Error: ' + err.message);
    } finally {
        hideLoading();
    }
}

// ===== IGNORE ISSUE =====
// Event delegation for ignore buttons
document.addEventListener('click', async function(e) {
    var btn = e.target.closest('.ignore-btn');
    if (!btn) return;

    if (!confirm('Ignore this issue? It won\'t appear in future validations until unignored.')) return;

    var ruleName = btn.dataset.ruleName;
    var message = btn.dataset.message;
    var severity = btn.dataset.severity;
    var details = {};

    try {
        details = JSON.parse(btn.dataset.details || '{}');
    } catch (parseErr) {
        console.error('Failed to parse details:', parseErr);
    }

    showLoading();

    try {
        var response = await fetch('/dashboard/api/validation/ignore', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({
                rule_name: ruleName,
                details: details,
                message: message,
                severity: severity
            })
        });

        var data = await response.json();

        if (response.ok && data.success) {
            // Remove the issue from the DOM
            btn.closest('.issue-item').remove();

            // Update counts
            updateIssueCounts();
        } else {
            alert('Error: ' + (data.error || 'Failed to ignore issue'));
        }
    } catch (err) {
        alert('Error: ' + err.message);
    } finally {
        hideLoading();
    }
});

function updateIssueCounts() {
    // Recount all issues (excluding removed ones)
    var allIssues = document.querySelectorAll('.issue-item');
    var totalCritical = 0;
    var totalWarning = 0;

    // Track issues by date
    var issuesByDate = {};

    allIssues.forEach(function (issue) {
        var severity = issue.dataset.severity;
        var date = issue.dataset.date;

        if (severity === 'critical') totalCritical++;
        if (severity === 'warning') totalWarning++;

        // Track by date (skip 'weekly' issues for day pills)
        if (date && date !== 'weekly') {
            if (!issuesByDate[date]) {
                issuesByDate[date] = { critical: 0, warning: 0 };
            }
            if (severity === 'critical') issuesByDate[date].critical++;
            if (severity === 'warning') issuesByDate[date].warning++;
        }
    });

    // Update header stats
    document.getElementById('critical-count').textContent = totalCritical;
    document.getElementById('warning-count').textContent = totalWarning;

    // Update day pills
    var dayPills = document.querySelectorAll('.day-pill[data-filter]');
    var passingDays = 0;

    dayPills.forEach(function (pill) {
        var date = pill.dataset.filter;
        if (date === 'all') return; // Skip the "All" pill

        var dateIssues = issuesByDate[date] || { critical: 0, warning: 0 };
        var criticalCount = dateIssues.critical;
        var warningCount = dateIssues.warning;

        // Update pill styling
        pill.classList.remove('has-critical', 'has-warning');
        if (criticalCount > 0) {
            pill.classList.add('has-critical');
        } else if (warningCount > 0) {
            pill.classList.add('has-warning');
        }

        // Update issue count display in pill
        var issueCountEl = pill.querySelector('.issue-count');
        if (issueCountEl) {
            if (criticalCount > 0 || warningCount > 0) {
                var countHtml = '';
                if (criticalCount > 0) {
                    countHtml += '<span class="critical">' + criticalCount + '</span>';
                }
                if (warningCount > 0) {
                    countHtml += (criticalCount > 0 ? '/' : '') + '<span class="warning">' + warningCount + '</span>';
                }
                issueCountEl.innerHTML = countHtml;
            } else {
                issueCountEl.innerHTML = '\u2713';
                passingDays++;
            }
        } else if (criticalCount === 0 && warningCount === 0) {
            passingDays++;
        }
    });

    // Update passing days count
    var passingCountEl = document.getElementById('passing-count');
    if (passingCountEl) {
        passingCountEl.textContent = passingDays;
    }

    // Show/hide "no issues" message
    var noIssuesMsg = document.getElementById('no-issues-message');
    if (noIssuesMsg) {
        if (totalCritical === 0 && totalWarning === 0) {
            noIssuesMsg.style.display = '';
        } else {
            noIssuesMsg.style.display = 'none';
        }
    }
}

// Refresh data when navigating to this page via tab
if (performance.navigation.type === performance.navigation.TYPE_BACK_FORWARD) {
    location.reload();
}

// Delegated click handler - replaces inline onclick attributes
document.addEventListener('click', function(e) {
    var target = e.target.closest('[data-action]');
    if (!target) return;
    var action = target.dataset.action;

    switch (action) {
        case 'close-modal': closeModal(target.dataset.modal); break;
        case 'show-employee-schedules':
            showEmployeeSchedules(target.dataset.employeeId, target.dataset.date, target.dataset.eventType || null);
            break;
        case 'assign-supervisor': assignSupervisorEvent(target.dataset.eventRef, target.dataset.date); break;
        case 'confirm-change-employee': confirmChangeEmployee(); break;
        case 'confirm-quick-schedule': confirmQuickSchedule(); break;
        case 'select-employee': selectEmployee(target.dataset.employeeId, target.dataset.employeeName, target.dataset.mode); break;
        case 'open-change-employee':
            openChangeEmployeeModal(target.dataset.scheduleId, target.dataset.employeeName, target.dataset.date, target.dataset.eventType);
            closeModal('employee-schedules-modal');
            break;
        case 'unschedule-and-close':
            unscheduleEvent(target.dataset.scheduleId);
            closeModal('employee-schedules-modal');
            break;
        case 'open-reschedule':
            openRescheduleModal(target.dataset.scheduleId, '', target.dataset.date, target.dataset.eventType);
            closeModal('employee-schedules-modal');
            break;
    }
});
