/**
 * Daily Validation Dashboard
 * Handles date navigation, employee report times, health score styling,
 * keyboard shortcuts, and auto-refresh for the daily validation page.
 */

// Read server-side data from the page-data JSON block
var pageDataEl = document.getElementById('page-data');
var pageData = pageDataEl ? JSON.parse(pageDataEl.textContent) : {};

/**
 * Navigate to a different date on the validation dashboard
 */
function navigateToDate(dateValue) {
    if (dateValue) {
        window.location.href = '/dashboard/daily-validation?date=' + dateValue;
    }
}

/**
 * Navigate to today's validation dashboard
 */
function navigateToToday() {
    var today = new Date().toISOString().split('T')[0];
    window.location.href = '/dashboard/daily-validation?date=' + today;
}

// Delegated click handler for data-action buttons
document.addEventListener('click', function(e) {
    var target = e.target.closest('[data-action]');
    if (!target) return;
    var action = target.dataset.action;
    switch (action) {
        case 'navigate-to-today':
            navigateToToday();
            break;
        case 'reload-page':
            location.reload();
            break;
    }
});

document.addEventListener('change', function(e) {
    var target = e.target.closest('[data-action="navigate-to-date"]');
    if (target) {
        navigateToDate(target.value);
    }
});

document.addEventListener('DOMContentLoaded', function() {
    // Load employee report times
    loadEmployeeReportTimes();

    // Enhanced health score color coding with animations
    var healthScore = pageData.healthScore || 0;
    var scoreCard = document.querySelector('.health-score-card');

    if (scoreCard) {
        if (healthScore >= 90) {
            scoreCard.style.background = 'linear-gradient(135deg, #10b981 0%, #059669 100%)';
            scoreCard.style.boxShadow = '0 20px 25px rgba(16, 185, 129, 0.4)';
        } else if (healthScore >= 75) {
            scoreCard.style.background = 'linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%)';
            scoreCard.style.boxShadow = '0 20px 25px rgba(139, 92, 246, 0.4)';
        } else if (healthScore >= 60) {
            scoreCard.style.background = 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)';
            scoreCard.style.boxShadow = '0 20px 25px rgba(245, 158, 11, 0.4)';
        } else {
            scoreCard.style.background = 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)';
            scoreCard.style.boxShadow = '0 20px 25px rgba(239, 68, 68, 0.4)';
        }
    }

    // Smooth scroll to validation issues if any critical ones exist
    var criticalIssues = document.querySelectorAll('.issue-critical');
    if (criticalIssues.length > 0 && window.location.hash !== '#issues-viewed') {
        // Add a subtle notification
        setTimeout(function () {
            var issuesSection = document.querySelector('.issue-card');
            if (issuesSection) {
                issuesSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
                // Mark as viewed to prevent repeated scrolling
                window.location.hash = '#issues-viewed';
            }
        }, 1000);
    }

    // Add hover effects to metric cards with number animation
    var metricCards = document.querySelectorAll('.metric-card');
    metricCards.forEach(function (card) {
        card.addEventListener('mouseenter', function() {
            var value = this.querySelector('.metric-value');
            if (value) {
                value.style.transform = 'scale(1.1)';
            }
        });
        card.addEventListener('mouseleave', function() {
            var value = this.querySelector('.metric-value');
            if (value) {
                value.style.transform = 'scale(1)';
            }
        });
    });

    // Enhanced tab switching with fade effects
    var tabLinks = document.querySelectorAll('.nav-tabs .nav-link');
    tabLinks.forEach(function (link) {
        link.addEventListener('click', function(e) {
            // Add subtle haptic feedback (visual)
            this.style.transform = 'scale(0.95)';
            var self = this;
            setTimeout(function () {
                self.style.transform = 'scale(1)';
            }, 100);
        });
    });

    // Auto-refresh dashboard every 5 minutes with notification
    var refreshCountdown = 5 * 60; // 5 minutes in seconds

    var refreshTimer = setInterval(function () {
        refreshCountdown--;

        // Show notification 30 seconds before refresh
        if (refreshCountdown === 30) {
            var refreshBtn = document.querySelector('.btn-outline-primary');
            if (refreshBtn) {
                refreshBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Refreshing in 30s...';
                refreshBtn.style.borderColor = '#f59e0b';
                refreshBtn.style.color = '#f59e0b';
            }
        }

        if (refreshCountdown <= 0) {
            clearInterval(refreshTimer);
            location.reload();
        }
    }, 1000);

    // Manual refresh button enhancement
    var refreshBtn = document.querySelector('.btn-outline-primary');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Refreshing...';
            this.style.pointerEvents = 'none';
        });
    }

    // Add keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Press 'R' to refresh
        if (e.key === 'r' || e.key === 'R') {
            if (!e.ctrlKey && !e.metaKey) {
                location.reload();
            }
        }
        // Press '1' to view selected date's calendar
        if (e.key === '1') {
            window.location.href = pageData.calendarUrl || '/calendar';
        }
        // Press '2' to view selected date's daily schedule
        if (e.key === '2') {
            window.location.href = pageData.scheduleUrl || '/schedule/daily';
        }
        // Press '3' to run auto-scheduler
        if (e.key === '3') {
            window.location.href = pageData.autoScheduleUrl || '/auto-schedule';
        }
    });

    // Add tooltip for keyboard shortcuts
    console.log('%cKeyboard Shortcuts Available:', 'font-weight: bold; color: #8b5cf6; font-size: 14px;');
    console.log('%cPress "R" to refresh dashboard', 'color: #6b7280;');
    console.log('%cPress "1" to view calendar for selected date', 'color: #6b7280;');
    console.log('%cPress "2" to view daily schedule for selected date', 'color: #6b7280;');
    console.log('%cPress "3" to run auto-scheduler', 'color: #6b7280;');
});

/**
 * Load and display employee report times for selected date
 */
async function loadEmployeeReportTimes() {
    var container = document.getElementById('employee-report-times');
    if (!container) return;

    var selectedDate = pageData.selectedDate || '';

    try {
        var response = await fetch('/api/daily-employees/' + selectedDate);
        if (!response.ok) {
            throw new Error('API error: ' + response.status);
        }

        var data = await response.json();
        console.log('Employee report times loaded:', data);

        renderEmployeeReportTimes(data.employees);
    } catch (error) {
        console.error('Failed to load employee report times:', error);
        container.innerHTML =
            '<div class="no-employees-message">' +
                '<div class="no-employees-icon">Warning</div>' +
                '<div>Failed to load employee report times</div>' +
            '</div>';
    }
}

/**
 * Render employee report times cards
 */
function renderEmployeeReportTimes(employees) {
    var container = document.getElementById('employee-report-times');
    if (!container) return;

    // Check if no employees
    if (!employees || employees.length === 0) {
        container.innerHTML =
            '<div class="no-employees-message">' +
                '<div class="no-employees-icon">No Data</div>' +
                '<div>No employees scheduled for this date</div>' +
            '</div>';
        return;
    }

    // Build HTML for employee cards
    var html = '';
    employees.forEach(function (employee) {
        var firstLetter = employee.employee_name ? employee.employee_name[0].toUpperCase() : '?';

        // Determine attendance badge
        var attendanceBadge = '';
        if (employee.attendance_status) {
            var statusLabels = {
                'on_time': 'On-Time',
                'late': 'Late',
                'called_in': 'Called-In',
                'no_call_no_show': 'No-Call-No-Show'
            };
            var statusLabel = statusLabels[employee.attendance_status] || employee.attendance_status;
            attendanceBadge =
                '<div class="employee-attendance-badge attendance-badge--' + employee.attendance_status + '">' +
                    statusLabel +
                '</div>';
        } else {
            attendanceBadge =
                '<div class="employee-attendance-badge attendance-badge--not_recorded">' +
                    'Not Recorded' +
                '</div>';
        }

        html +=
            '<div class="employee-report-card">' +
                '<div class="employee-report-header">' +
                    '<div class="employee-report-avatar">' + firstLetter + '</div>' +
                    '<div class="employee-report-name">' + escapeHtml(employee.employee_name) + '</div>' +
                '</div>' +
                '<div class="employee-report-time">' +
                    '<i class="fas fa-clock"></i>' +
                    employee.earliest_time +
                '</div>' +
                '<div class="employee-report-details">' +
                    '<div class="employee-report-detail">' +
                        '<i class="fas fa-calendar-check"></i>' +
                        '<span>' + employee.event_count + ' event' + (employee.event_count !== 1 ? 's' : '') + ' today</span>' +
                    '</div>' +
                    '<div class="employee-report-detail">' +
                        '<i class="fas fa-user"></i>' +
                        '<span>' + escapeHtml(employee.employee_id) + '</span>' +
                    '</div>' +
                '</div>' +
                attendanceBadge +
                (employee.attendance_notes ?
                    '<div class="employee-report-detail" style="margin-top: 8px; font-style: italic;">' +
                        '<i class="fas fa-sticky-note"></i>' +
                        '<span>' + escapeHtml(employee.attendance_notes) + '</span>' +
                    '</div>'
                : '') +
            '</div>';
    });

    container.innerHTML = html;
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    if (!text) return '';
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
