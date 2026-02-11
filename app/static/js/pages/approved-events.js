/**
 * Approved Events Dashboard JavaScript
 *
 * Handles Walmart authentication, fetching approved events,
 * rendering action-based panels, rolling events, and scan-out tracking.
 *
 * Extracted from dashboard/approved_events.html inline script.
 */

function escapeHtml(text) {
    if (text == null) return '';
    return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

// State
var isAuthenticated = false;
var sessionTimer = null;
var deadlineTimer = null;
var currentEvents = [];
var currentFilter = 'all';
var viewMode = 'panels'; // 'panels' or 'table'

// Initialize on page load
document.addEventListener('DOMContentLoaded', function () {
    checkScanoutStatus();
    checkSessionStatus();

    // MFA input auto-submit
    document.getElementById('mfaCode').addEventListener('input', function (e) {
        if (e.target.value.length === 6) {
            submitMFA();
        }
    });
});

// Check scan-out warning status and start countdown
async function checkScanoutStatus() {
    try {
        var response = await fetch('/api/walmart/events/scanout-status');
        var data = await response.json();

        if (data.show_warning) {
            // Show warning banner
            var banner = document.getElementById('scanoutWarning');
            banner.style.display = 'flex';
            banner.className = 'scanout-warning ' + data.urgency;

            document.getElementById('warningReason').textContent =
                'Today is ' + data.reason + ' - Scan-out deadline day!';
            document.getElementById('warningDeadline').textContent = data.deadline;

            if (data.urgency === 'urgent') {
                document.getElementById('warningDetail').textContent =
                    'URGENT: Less than 1 hour remaining!';
            }

            // Start deadline countdown
            startDeadlineCountdown(data.urgency);
        }
    } catch (error) {
        console.error('Failed to check scan-out status:', error);
    }
}

// Start 6 PM deadline countdown
function startDeadlineCountdown(urgency) {
    var countdownEl = document.getElementById('deadlineCountdown');
    countdownEl.style.display = 'block';
    countdownEl.className = 'deadline-countdown ' + urgency;

    function updateCountdown() {
        var now = new Date();
        var deadline = new Date();
        deadline.setHours(18, 0, 0, 0); // 6 PM today

        var diff = deadline - now;
        if (diff < 0) {
            document.getElementById('countdownTimer').textContent = 'PAST DEADLINE';
            document.getElementById('countdownRemaining').textContent = 'All events should be complete!';
            countdownEl.className = 'deadline-countdown urgent';
            return;
        }

        var hours = Math.floor(diff / (1000 * 60 * 60));
        var minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
        var seconds = Math.floor((diff % (1000 * 60)) / 1000);

        document.getElementById('countdownTimer').textContent =
            hours.toString().padStart(2, '0') + ':' + minutes.toString().padStart(2, '0') + ':' + seconds.toString().padStart(2, '0');

        // Update urgency class based on time remaining
        if (hours < 1) {
            countdownEl.className = 'deadline-countdown urgent';
        } else if (hours < 3) {
            countdownEl.className = 'deadline-countdown warning';
        }
    }

    updateCountdown();
    deadlineTimer = setInterval(updateCountdown, 1000);
}

// Check if user has active Walmart session
async function checkSessionStatus() {
    try {
        var response = await fetch('/api/walmart/auth/session-status');
        var data = await response.json();

        if (data.has_session && data.session_info && data.session_info.is_authenticated) {
            showAuthenticatedUI(data.session_info);
            fetchApprovedEvents();
        } else {
            showAuthSection();
        }
    } catch (error) {
        console.error('Failed to check session status:', error);
        showAuthSection();
    }
}

// Request MFA code
async function requestMFA() {
    document.getElementById('authError').style.display = 'none';
    document.getElementById('authStep1').innerHTML =
        '<div class="loading-spinner" style="width: 24px; height: 24px; margin: 0 auto;"></div>';

    try {
        var response = await fetch('/api/walmart/auth/request-mfa', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        var data = await response.json();

        if (data.success) {
            document.getElementById('authStep1').style.display = 'none';
            document.getElementById('authStep2').style.display = 'block';
            document.getElementById('mfaCode').focus();
        } else {
            showAuthError(data.message || 'Failed to request MFA code');
            document.getElementById('authStep1').innerHTML =
                '<button class="btn btn-primary" data-action="request-mfa"><i class="fas fa-key"></i> Request MFA Code</button>';
        }
    } catch (error) {
        showAuthError('Network error. Please try again.');
        document.getElementById('authStep1').innerHTML =
            '<button class="btn btn-primary" data-action="request-mfa"><i class="fas fa-key"></i> Request MFA Code</button>';
    }
}

// Submit MFA code
async function submitMFA() {
    var code = document.getElementById('mfaCode').value.trim();
    if (code.length !== 6) {
        showAuthError('Please enter a 6-digit code');
        return;
    }

    document.getElementById('authError').style.display = 'none';

    try {
        var response = await fetch('/api/walmart/auth/authenticate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mfa_code: code })
        });
        var data = await response.json();

        if (data.success) {
            showAuthenticatedUI(data.session_info);
            fetchApprovedEvents();
        } else {
            showAuthError(data.message || 'Invalid MFA code');
            document.getElementById('mfaCode').value = '';
            document.getElementById('mfaCode').focus();
        }
    } catch (error) {
        showAuthError('Network error. Please try again.');
    }
}

// Show authentication section
function showAuthSection() {
    document.getElementById('authSection').style.display = 'block';
    document.getElementById('sessionInfo').style.display = 'none';
    document.getElementById('filterSection').style.display = 'none';
    document.getElementById('statsSection').style.display = 'none';
    document.getElementById('eventsSection').style.display = 'none';
    document.getElementById('authStep1').style.display = 'block';
    document.getElementById('authStep1').innerHTML =
        '<button class="btn btn-primary" data-action="request-mfa"><i class="fas fa-key"></i> Request MFA Code</button>';
    document.getElementById('authStep2').style.display = 'none';
}

// Show authenticated UI
function showAuthenticatedUI(sessionInfo) {
    isAuthenticated = true;
    document.getElementById('authSection').style.display = 'none';
    document.getElementById('sessionInfo').style.display = 'flex';
    document.getElementById('filterSection').style.display = 'flex';
    document.getElementById('statsSection').style.display = 'flex';
    document.getElementById('actionPanels').style.display = 'block';

    // Start session timer
    if (sessionInfo && sessionInfo.time_remaining_seconds) {
        startSessionTimer(sessionInfo.time_remaining_seconds);
    }
}

// Start session countdown timer
function startSessionTimer(seconds) {
    if (sessionTimer) clearInterval(sessionTimer);

    var remaining = seconds;
    updateTimerDisplay(remaining);

    sessionTimer = setInterval(function () {
        remaining--;
        updateTimerDisplay(remaining);

        if (remaining <= 0) {
            clearInterval(sessionTimer);
            showAuthSection();
        }
    }, 1000);
}

function updateTimerDisplay(seconds) {
    var mins = Math.floor(seconds / 60);
    var secs = seconds % 60;
    document.getElementById('sessionTimeRemaining').textContent =
        mins + ':' + secs.toString().padStart(2, '0');
}

// Show auth error
function showAuthError(message) {
    document.getElementById('authError').style.display = 'block';
    document.getElementById('authErrorMsg').textContent = message;
}

// Logout
async function logout() {
    try {
        await fetch('/api/walmart/auth/logout', { method: 'POST' });
    } catch (error) {
        console.error('Logout error:', error);
    }

    if (sessionTimer) clearInterval(sessionTimer);
    showAuthSection();
}

// Fetch approved events
async function fetchApprovedEvents() {
    var club = document.getElementById('clubInput').value.trim();
    if (!club) {
        alert('Please enter a club number');
        return;
    }

    document.getElementById('loadingState').style.display = 'flex';
    document.getElementById('eventsSection').style.display = 'none';
    document.getElementById('emptyState').style.display = 'none';

    try {
        var response = await fetch('/api/walmart/events/approved?club=' + club);
        var data = await response.json();

        document.getElementById('loadingState').style.display = 'none';

        if (!data.success) {
            if (data.message && data.message.includes('authenticate')) {
                // User needs to authenticate first
                showAuthSection();
                // Also show helpful empty state
                showEmptyState(false);
            } else {
                // Other error - show alert with details
                var errorMsg = data.message || 'Failed to fetch events';
                alert('Error: ' + errorMsg + '\n\nTip: Check the club number and date range, or try authenticating again.');
                // Show empty state for clarity
                document.getElementById('emptyStateTitle').textContent = 'Unable to Load Events';
                document.getElementById('emptyStateMessage').textContent = errorMsg;
                document.getElementById('emptyState').querySelector('.icon i').className = 'fas fa-exclamation-triangle';
                document.getElementById('emptyState').style.display = 'block';
            }
            return;
        }

        // Update session timer
        if (data.session_info && data.session_info.time_remaining_seconds) {
            startSessionTimer(data.session_info.time_remaining_seconds);
        }

        // Store events for filtering
        currentEvents = data.events || [];

        // Log summary for debugging
        console.log('Fetched ' + currentEvents.length + ' approved events from Walmart');
        console.log('Date range:', data.date_range);
        console.log('Summary:', data.summary);

        // Log rolling status breakdown
        var needsRolling = currentEvents.filter(function (e) { return e.needs_rolling; }).length;
        var scheduled = currentEvents.filter(function (e) { return e.is_scheduled; }).length;
        console.log('Rolling status: ' + needsRolling + ' need rolling, ' + scheduled + ' scheduled locally');

        if (currentEvents.length === 0) {
            console.info('No events found. This could mean:');
            console.info('1. All approved events have been processed');
            console.info('2. No APPROVED status events exist for this club/date range');
            console.info('3. Events are in a different date range than the default (2 weeks)');
        }

        // Update stats (returns total LIA count)
        var totalLIAs = updateStats(data.summary, currentEvents);

        // Update countdown remaining count to match category totals
        document.getElementById('countdownRemaining').textContent =
            totalLIAs + ' events remaining';

        // Render view
        if (currentEvents.length > 0) {
            if (viewMode === 'panels') {
                renderPanelView(currentEvents);
            } else {
                renderEventsTable(currentEvents);
            }
        } else {
            // Show empty state with appropriate messaging
            showEmptyState(isAuthenticated);
        }

        // Show/hide print all button
        updatePrintAllVisibility();

    } catch (error) {
        document.getElementById('loadingState').style.display = 'none';
        console.error('Failed to fetch approved events:', error);
        alert('Network error. Please try again.');
    }
}

// Helper function to check if a date is on or before today
function isOnOrBeforeToday(dateStr) {
    if (!dateStr) return false;

    var today = new Date();
    today.setHours(0, 0, 0, 0);

    var eventDate;
    if (typeof dateStr === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
        var parts = dateStr.split('-').map(Number);
        eventDate = new Date(parts[0], parts[1] - 1, parts[2]);
    } else {
        eventDate = new Date(dateStr);
    }
    eventDate.setHours(0, 0, 0, 0);

    return eventDate <= today;
}

// Update stats display with action-based counts
function updateStats(summary, events) {
    // Count by action type using same logic as renderPanelView
    var scanOutCount = events.filter(function (e) {
        // Event must be assigned/scheduled
        if (!e.is_scheduled || !e.assigned_employee_name) return false;

        var dateToCheck = e.schedule_datetime || e.scheduled_date;
        return isOnOrBeforeToday(dateToCheck);
    }).length;

    var rollScheduledCount = events.filter(function (e) {
        if (!e.is_scheduled || !e.needs_rolling) return false;
        var dateToCheck = e.schedule_datetime || e.scheduled_date;
        return !isOnOrBeforeToday(dateToCheck);
    }).length;

    var rollUnscheduledCount = events.filter(function (e) {
        // Must be unscheduled/unassigned
        if (e.is_scheduled || e.assigned_employee_name) return false;

        // Must be in unscheduled or not_in_db status
        if (e.local_status !== 'unscheduled' && e.local_status !== 'not_in_db') return false;

        return true;
    }).length;

    var totalLIAs = scanOutCount + rollScheduledCount + rollUnscheduledCount;

    document.getElementById('statScanOut').textContent = scanOutCount;
    document.getElementById('statRollScheduled').textContent = rollScheduledCount;
    document.getElementById('statRollUnscheduled').textContent = rollUnscheduledCount;
    document.getElementById('statTotal').textContent = totalLIAs;

    return totalLIAs;
}

// Render panel view (action-based grouping)
function renderPanelView(events) {
    // Group events by action type based on date and rolling status
    // Scan-Out: Events scheduled on or before today (ready to scan out)
    // MUST be assigned to an employee to be ready for scan-out
    var scanOutEvents = events.filter(function (e) {
        // Event must be assigned/scheduled
        if (!e.is_scheduled || !e.assigned_employee_name) return false;

        // Use schedule_datetime if available, otherwise use scheduled_date (Walmart date)
        var dateToCheck = e.schedule_datetime || e.scheduled_date;
        return isOnOrBeforeToday(dateToCheck);
    });

    // Roll Scheduled: Events that are scheduled locally for future dates and need rolling
    // (Walmart date doesn't match local scheduled date)
    var rollScheduledEvents = events.filter(function (e) {
        if (!e.is_scheduled || !e.needs_rolling) return false;
        var dateToCheck = e.schedule_datetime || e.scheduled_date;
        return !isOnOrBeforeToday(dateToCheck);
    });

    // Roll Unscheduled: Events not scheduled locally
    // This includes both future events and past events that weren't scheduled
    var rollUnscheduledEvents = events.filter(function (e) {
        // Must be unscheduled/unassigned
        if (e.is_scheduled || e.assigned_employee_name) return false;

        // Must be in unscheduled or not_in_db status
        if (e.local_status !== 'unscheduled' && e.local_status !== 'not_in_db') return false;

        return true;
    });

    // Apply filter if set
    var showScanOut = currentFilter === 'all' || currentFilter === 'scan_out';
    var showRollScheduled = currentFilter === 'all' || currentFilter === 'roll_scheduled';
    var showRollUnscheduled = currentFilter === 'all' || currentFilter === 'roll_unscheduled';

    // Render Scan-Out Panel
    var scanOutPanel = document.getElementById('scanOutPanel');
    if (scanOutEvents.length > 0 && showScanOut) {
        scanOutPanel.style.display = 'block';
        document.getElementById('scanOutPanelCount').textContent = scanOutEvents.length;
        document.getElementById('scanOutEvents').innerHTML = scanOutEvents.map(function (e) {
            return renderEventCard(e, 'scan_out');
        }).join('');
    } else {
        scanOutPanel.style.display = 'none';
    }

    // Render Roll Scheduled Panel
    var rollScheduledPanel = document.getElementById('rollScheduledPanel');
    if (rollScheduledEvents.length > 0 && showRollScheduled) {
        rollScheduledPanel.style.display = 'block';
        document.getElementById('rollScheduledPanelCount').textContent = rollScheduledEvents.length;
        document.getElementById('rollScheduledEvents').innerHTML = rollScheduledEvents.map(function (e) {
            return renderEventCard(e, 'roll_scheduled');
        }).join('');
    } else {
        rollScheduledPanel.style.display = 'none';
    }

    // Render Roll Unscheduled Panel
    var rollUnscheduledPanel = document.getElementById('rollUnscheduledPanel');
    if (rollUnscheduledEvents.length > 0 && showRollUnscheduled) {
        rollUnscheduledPanel.style.display = 'block';
        document.getElementById('rollUnscheduledPanelCount').textContent = rollUnscheduledEvents.length;
        document.getElementById('rollUnscheduledEvents').innerHTML = rollUnscheduledEvents.map(function (e) {
            return renderEventCard(e, 'roll_unscheduled');
        }).join('');
    } else {
        rollUnscheduledPanel.style.display = 'none';
    }

    // Show panels container
    document.getElementById('actionPanels').style.display = 'block';
    document.getElementById('eventsSection').style.display = 'none';
}

// Render a single event card
function renderEventCard(event, actionType) {
    var actionContent = '';
    var rollDateContent = '';

    if (actionType === 'scan_out') {
        actionContent = '<button class="action-btn primary" data-action="open-walmart" data-event-id="' + event.event_id + '">' +
            '<i class="fas fa-external-link-alt"></i> View in Walmart</button>';
    } else if (actionType === 'roll_scheduled') {
        var scheduledDate = event.schedule_datetime ?
            formatDate(event.schedule_datetime) : 'Unknown';
        var walmartDate = formatDate(event.scheduled_date);
        rollDateContent = '<span class="roll-to-date" style="background: #fef3c7; color: #92400e;">' +
            '<i class="fas fa-exclamation-triangle"></i> Walmart: ' + walmartDate + ' &rarr; Roll to: ' + scheduledDate +
            '</span>';
        actionContent = '<button class="action-btn secondary" data-action="roll-event" data-event-id="' + event.event_id + '" data-date="' + event.schedule_datetime + '" data-roll-type="scheduled">' +
            '<i class="fas fa-calendar-alt"></i> Roll to Scheduled Date</button>';
    } else if (actionType === 'roll_unscheduled') {
        // Calculate one day before due date (use due_datetime if available, fallback to scheduled_date)
        var dueDateToUse = event.due_datetime || event.scheduled_date;
        var rollToDate = getOneDayBeforeDueDate(dueDateToUse);

        if (rollToDate) {
            rollDateContent = '<span class="roll-to-date" style="background: #fef3c7; color: #92400e;">' +
                '<i class="fas fa-exclamation-triangle"></i> Roll to: ' + rollToDate + ' (one day before due)' +
                '</span>';
            actionContent = '<button class="action-btn secondary" data-action="navigate-events" data-event-id="' + event.event_id + '">' +
                '<i class="fas fa-calendar-plus"></i> Schedule</button>' +
                '<button class="action-btn secondary" data-action="roll-event" data-event-id="' + event.event_id + '" data-date="' + rollToDate + '" data-roll-type="unscheduled" style="margin-left: 8px;">' +
                '<i class="fas fa-forward"></i> Roll to ' + rollToDate + '</button>';
        } else {
            // No due date available
            actionContent = '<button class="action-btn secondary" data-action="navigate-events" data-event-id="' + event.event_id + '">' +
                '<i class="fas fa-calendar-plus"></i> Schedule</button>';
        }
    }

    // Determine what dates to show
    var dateDisplay = '';
    var cardWalmartDate = formatDate(event.scheduled_date);
    var localScheduledDate = event.schedule_datetime ? formatDate(event.schedule_datetime) : null;

    // For scan-out events (already due), don't show rolling indicator even if dates differ
    // For roll events, show both dates to indicate mismatch
    var showRollingIndicator = actionType !== 'scan_out' && event.needs_rolling;

    if (localScheduledDate && showRollingIndicator) {
        // Show both dates if they differ (only for events that need rolling)
        dateDisplay = '<span class="event-date" style="font-size: 12px;">' +
            '<div style="color: #dc2626;"><i class="fas fa-exclamation-circle"></i> Walmart: ' + cardWalmartDate + '</div>' +
            '<div style="color: #059669;"><i class="fas fa-calendar-check"></i> Scheduled: ' + localScheduledDate + '</div>' +
            '</span>';
    } else if (localScheduledDate) {
        // Show local scheduled date only
        dateDisplay = '<span class="event-date" style="color: #059669;"><i class="fas fa-calendar-check"></i> ' + localScheduledDate + '</span>';
    } else {
        // Show Walmart date only (not scheduled locally)
        dateDisplay = '<span class="event-date"><i class="fas fa-calendar"></i> ' + cardWalmartDate + '</span>';
    }

    var assignedContent = event.assigned_employee_name ?
        '<span class="assigned-to"><i class="fas fa-user"></i> ' + escapeHtml(event.assigned_employee_name) + '</span>' :
        '<span class="assigned-to" style="color: #dc2626;"><i class="fas fa-user-slash"></i> Unassigned</span>';

    return '<div class="event-card">' +
        '<span class="event-id">' + escapeHtml(event.event_id) + '</span>' +
        '<span class="event-name" title="' + escapeHtml(event.event_name) + '">' + escapeHtml(event.event_name) + '</span>' +
        dateDisplay +
        assignedContent +
        rollDateContent +
        actionContent +
        '</div>';
}

// Get latest possible roll date
function getLatestRollDate() {
    var today = new Date();
    var dayOfWeek = today.getDay();

    // If Friday (5) or Saturday (6), return today
    if (dayOfWeek === 5 || dayOfWeek === 6) {
        return formatDate(today.toISOString());
    }

    // Otherwise return next Friday
    var daysUntilFriday = (5 - dayOfWeek + 7) % 7 || 7;
    var nextFriday = new Date(today);
    nextFriday.setDate(today.getDate() + daysUntilFriday);
    return formatDate(nextFriday.toISOString());
}

// Get one day before the due date for unscheduled events
function getOneDayBeforeDueDate(dueDateString) {
    if (!dueDateString) return null;

    // Handle ISO date strings (YYYY-MM-DD) without timezone conversion
    var dueDate;
    if (typeof dueDateString === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(dueDateString)) {
        var parts = dueDateString.split('-').map(Number);
        dueDate = new Date(parts[0], parts[1] - 1, parts[2]);
    } else {
        dueDate = new Date(dueDateString);
    }

    var oneDayBefore = new Date(dueDate);
    oneDayBefore.setDate(dueDate.getDate() - 1);

    // Format as YYYY-MM-DD
    var year = oneDayBefore.getFullYear();
    var month = String(oneDayBefore.getMonth() + 1).padStart(2, '0');
    var day = String(oneDayBefore.getDate()).padStart(2, '0');
    return year + '-' + month + '-' + day;
}

// Open event in Walmart Retail Link
function openInWalmart(eventId) {
    window.open('https://retaillink2.wal-mart.com/EventManagement/browse-event?eventId=' + eventId, '_blank');
}

// Roll event to specified date
async function rollEventToDate(eventId, dateString, rollType) {
    try {
        // Parse the date string and format it as YYYY-MM-DD
        var scheduledDate;
        if (dateString.includes('T')) {
            // ISO datetime format
            scheduledDate = dateString.split('T')[0];
        } else {
            // Already in YYYY-MM-DD format
            scheduledDate = dateString;
        }

        // Show confirmation
        var confirmMsg = rollType === 'scheduled'
            ? 'Roll event ' + eventId + ' to its scheduled date (' + scheduledDate + ')?'
            : 'Roll event ' + eventId + ' to ' + scheduledDate + ' (one day before due)?';

        if (!confirm(confirmMsg)) {
            return;
        }

        // Show loading indicator on button
        var button = event.target;
        var originalHTML = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Rolling...';

        // Make API call
        var response = await fetch('/api/walmart/events/roll', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
            },
            body: JSON.stringify({
                event_id: eventId,
                scheduled_date: scheduledDate,
                club_id: '8135'
            })
        });

        var result = await response.json();

        if (response.ok && result.success) {
            // Success - show message and refresh events
            alert('Event ' + eventId + ' successfully rolled to ' + scheduledDate);
            fetchApprovedEvents();  // Refresh the events list
        } else {
            // Error - show error message
            alert('Failed to roll event: ' + (result.message || 'Unknown error'));
            button.disabled = false;
            button.innerHTML = originalHTML;
        }

    } catch (error) {
        console.error('Roll event error:', error);
        alert('Failed to roll event: ' + error.message);
        // Restore button
        if (event.target) {
            event.target.disabled = false;
            event.target.innerHTML = originalHTML;
        }
    }
}

// Roll ALL scheduled events to their scheduled dates
async function rollAllScheduledEvents() {
    // Get all events that need rolling (scheduled locally but Walmart date differs)
    var eventsToRoll = currentEvents.filter(function (e) {
        return e.is_scheduled && e.needs_rolling && e.schedule_datetime;
    });

    if (eventsToRoll.length === 0) {
        alert('No events to roll.');
        return;
    }

    // Confirm action
    if (!confirm('Roll ' + eventsToRoll.length + ' event(s) to their scheduled dates?\n\nThis will update each event in Walmart Retail Link.')) {
        return;
    }

    // Disable the button and show progress
    var rollAllBtn = document.getElementById('rollAllScheduledBtn');
    var originalBtnHTML = rollAllBtn.innerHTML;
    rollAllBtn.disabled = true;

    var successCount = 0;
    var failCount = 0;
    var errors = [];

    // Process events one by one
    for (var i = 0; i < eventsToRoll.length; i++) {
        var evt = eventsToRoll[i];
        rollAllBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Rolling ' + (i + 1) + '/' + eventsToRoll.length + '...';

        try {
            // Parse the scheduled date
            var scheduledDate = evt.schedule_datetime;
            if (scheduledDate.includes('T')) {
                scheduledDate = scheduledDate.split('T')[0];
            }

            // Make API call
            var response = await fetch('/api/walmart/events/roll', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
                },
                body: JSON.stringify({
                    event_id: evt.event_id,
                    scheduled_date: scheduledDate,
                    club_id: '8135'
                })
            });

            var result = await response.json();

            if (response.ok && result.success) {
                successCount++;
                console.log('Rolled event ' + evt.event_id + ' to ' + scheduledDate);
            } else {
                failCount++;
                errors.push(evt.event_id + ': ' + (result.message || 'Unknown error'));
                console.error('Failed to roll event ' + evt.event_id + ':', result.message);
            }

            // Small delay between requests to avoid overwhelming the API
            await new Promise(function (resolve) { setTimeout(resolve, 500); });

        } catch (error) {
            failCount++;
            errors.push(evt.event_id + ': ' + error.message);
            console.error('Exception rolling event ' + evt.event_id + ':', error);
        }
    }

    // Restore button
    rollAllBtn.disabled = false;
    rollAllBtn.innerHTML = originalBtnHTML;

    // Show results
    var message = 'Roll All Complete!\n\nSuccess: ' + successCount + '\nFailed: ' + failCount;
    if (errors.length > 0 && errors.length <= 5) {
        message += '\n\nErrors:\n' + errors.join('\n');
    } else if (errors.length > 5) {
        message += '\n\nFirst 5 errors:\n' + errors.slice(0, 5).join('\n') + '\n... and ' + (errors.length - 5) + ' more';
    }
    alert(message);

    // Refresh the events list
    fetchApprovedEvents();
}

// Filter by action type
function filterByAction(actionType) {
    currentFilter = actionType;

    // Update active card
    document.querySelectorAll('.stat-card.action-card').forEach(function (card) {
        card.classList.remove('active');
    });

    if (actionType !== 'all') {
        event.target.closest('.stat-card').classList.add('active');
    }

    // Re-render panels
    if (currentEvents.length > 0) {
        renderPanelView(currentEvents);
    }
}

// Toggle view modes
function showPanelView() {
    viewMode = 'panels';
    document.querySelectorAll('.view-toggle').forEach(function (btn) { btn.classList.remove('active'); });
    event.target.classList.add('active');

    document.getElementById('actionPanels').style.display = 'block';
    document.getElementById('eventsSection').style.display = 'none';

    if (currentEvents.length > 0) {
        renderPanelView(currentEvents);
    }
}

function showTableView() {
    viewMode = 'table';
    document.querySelectorAll('.view-toggle').forEach(function (btn) { btn.classList.remove('active'); });
    event.target.classList.add('active');

    document.getElementById('actionPanels').style.display = 'none';
    document.getElementById('eventsSection').style.display = 'block';

    if (currentEvents.length > 0) {
        renderEventsTable(currentEvents);
    }
}

// Render events table
function renderEventsTable(events) {
    var tbody = document.getElementById('eventsTableBody');
    var statusFilter = document.getElementById('statusFilter').value;

    // Filter events
    var filteredEvents = events;
    if (statusFilter !== 'all') {
        filteredEvents = events.filter(function (e) { return e.local_status === statusFilter; });
    }

    // Sort: unscheduled first, then scheduled, then submitted
    var statusOrder = { 'not_in_db': 0, 'unscheduled': 1, 'scheduled': 2, 'api_failed': 3, 'api_submitted': 4 };
    filteredEvents.sort(function (a, b) { return (statusOrder[a.local_status] || 5) - (statusOrder[b.local_status] || 5); });

    tbody.innerHTML = filteredEvents.map(function (evt) {
        // Determine action required
        var actionRequired = '';
        var actionButton = '';

        if (evt.local_status === 'api_submitted') {
            actionRequired = '<span style="color: #059669;">Scan out in Walmart</span>';
            actionButton = '<button class="action-btn primary" data-action="open-walmart" data-event-id="' + evt.event_id + '">' +
                '<i class="fas fa-barcode"></i> Scan Out</button>';
        } else if (evt.local_status === 'scheduled') {
            actionRequired = '<span style="color: #f59e0b;">Roll to ' + formatDate(evt.schedule_datetime) + '</span>';
            actionButton = '<button class="action-btn secondary" data-action="open-walmart" data-event-id="' + evt.event_id + '">' +
                '<i class="fas fa-calendar-alt"></i> Roll</button>';
        } else {
            actionRequired = '<span style="color: #dc2626;">Schedule or Roll to latest date</span>';
            actionButton = '<button class="action-btn secondary" data-action="navigate-events" data-event-id="' + evt.event_id + '">' +
                '<i class="fas fa-calendar-plus"></i> Schedule</button>';
        }

        return '<tr>' +
            '<td class="event-id">' + escapeHtml(evt.event_id) + '</td>' +
            '<td class="event-name" title="' + escapeHtml(evt.event_name) + '">' + escapeHtml(evt.event_name) + '</td>' +
            '<td>' + formatDate(evt.scheduled_date) + '</td>' +
            '<td><span class="status-badge ' + escapeHtml(evt.local_status).replace('_', '-') + '">' +
            escapeHtml(evt.local_status_icon) + ' ' + escapeHtml(evt.local_status_label) + '</span></td>' +
            '<td>' + (evt.assigned_employee_name ? escapeHtml(evt.assigned_employee_name) : '<span style="color: #dc2626;">-</span>') + '</td>' +
            '<td>' + (evt.schedule_datetime ? formatDate(evt.schedule_datetime) : '-') + '</td>' +
            '<td>' + actionRequired + '</td>' +
            '</tr>';
    }).join('');

    document.getElementById('eventsSection').style.display = 'block';
}

// Format date - FIXED: Timezone-aware parsing
// When dateStr is "2026-01-18" (date only), we need to parse it as local date, not UTC
function formatDate(dateStr) {
    if (!dateStr) return '-';

    // Handle ISO date strings (YYYY-MM-DD) without timezone conversion
    // This prevents the off-by-one-day bug when UTC midnight converts to previous day in local TZ
    if (typeof dateStr === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
        var parts = dateStr.split('-').map(Number);
        var date = new Date(parts[0], parts[1] - 1, parts[2]); // month is 0-indexed
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }

    // For datetime strings or other formats, use standard parsing
    var date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// Format datetime - FIXED: Timezone-aware parsing for date-only strings
function formatDateTime(dateStr) {
    if (!dateStr) return '-';

    // Handle ISO date strings (YYYY-MM-DD) without timezone conversion
    if (typeof dateStr === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
        var parts = dateStr.split('-').map(Number);
        var date = new Date(parts[0], parts[1] - 1, parts[2]);
        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric'
        });
    }

    var date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit'
    });
}

// Show empty state with appropriate messaging
function showEmptyState(authenticated) {
    var emptyState = document.getElementById('emptyState');
    var title = document.getElementById('emptyStateTitle');
    var message = document.getElementById('emptyStateMessage');

    if (!authenticated) {
        // User needs to authenticate first
        title.textContent = 'Authentication Required';
        message.textContent = 'Please authenticate with Walmart Retail Link using the "Request MFA Code" button above to view approved events.';
        emptyState.querySelector('.icon i').className = 'fas fa-lock';
    } else {
        // Authenticated but no events found
        title.textContent = 'No Approved Events Remaining';
        message.textContent = 'Great work! All approved events have been processed (scheduled, rolled, and scanned out), or there are no APPROVED events in the selected date range.';
        emptyState.querySelector('.icon i').className = 'fas fa-check-circle';
    }

    emptyState.style.display = 'block';
}

// Filter change handler
document.getElementById('statusFilter').addEventListener('change', function () {
    // Re-render current view with new filter
    if (currentEvents.length > 0) {
        if (viewMode === 'panels') {
            renderPanelView(currentEvents);
        } else {
            renderEventsTable(currentEvents);
        }
    }
});

// Print a specific category
function printCategory(category) {
    // Set print date
    document.getElementById('printDate').textContent = new Date().toLocaleString();

    // Add class to body to control which panels are visible during print
    document.body.classList.add('printing-' + category);

    // Trigger print
    window.print();

    // Remove the class after printing
    setTimeout(function () {
        document.body.classList.remove('printing-' + category);
    }, 500);
}

// Print all categories
function printAllCategories() {
    // Set print date
    document.getElementById('printDate').textContent = new Date().toLocaleString();

    // Print without any category filter (shows all visible panels)
    window.print();
}

// Show/hide print all button based on events
function updatePrintAllVisibility() {
    var printAllContainer = document.getElementById('printAllContainer');
    var hasEvents = currentEvents.length > 0;
    printAllContainer.style.display = hasEvents && isAuthenticated ? 'flex' : 'none';
}

// Delegated click handler - replaces inline onclick attributes
document.addEventListener('click', function(e) {
    var target = e.target.closest('[data-action]');
    if (!target) return;
    var action = target.dataset.action;

    switch (action) {
        case 'request-mfa': requestMFA(); break;
        case 'submit-mfa': submitMFA(); break;
        case 'logout': logout(); break;
        case 'fetch-events': fetchApprovedEvents(); break;
        case 'filter-action': filterByAction(target.dataset.filter); break;
        case 'print-all': printAllCategories(); break;
        case 'print-category': printCategory(target.dataset.category); break;
        case 'roll-all-scheduled': rollAllScheduledEvents(); break;
        case 'show-panel-view': showPanelView(); break;
        case 'show-table-view': showTableView(); break;
        case 'open-walmart': openInWalmart(target.dataset.eventId); break;
        case 'roll-event': rollEventToDate(target.dataset.eventId, target.dataset.date, target.dataset.rollType); break;
        case 'navigate-events': window.location.href = '/events?search=' + target.dataset.eventId; break;
    }
});
