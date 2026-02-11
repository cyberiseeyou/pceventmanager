/**
 * Index (Dashboard) Page JavaScript
 *
 * Handles event details modal, schedule printing, verification widget,
 * MFA authentication, EDR reports, and paperwork generation.
 *
 * Refactored from inline <script> in index.html.
 * Server-side data is passed via a <script type="application/json" id="page-data"> block.
 */

// Read server-side data from JSON data block
var PAGE_DATA = (function() {
    var el = document.getElementById('page-data');
    if (el) {
        try {
            return JSON.parse(el.textContent);
        } catch (e) {
            console.error('Failed to parse page-data JSON:', e);
            return {};
        }
    }
    return {};
})();

// Global variables for event details modal
var currentEventScheduleId = null;
var currentEventRefNum = null;
var currentEventType = null;

// XSS protection: escape dynamic values before inserting into innerHTML
function escapeHtml(text) {
    if (text == null) return '';
    return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

// Show Event Details Modal
function showEventDetails(scheduleId, eventRefNum, eventName, employeeName, scheduledDate, scheduledTime, startDate, dueDate, eventType) {
    currentEventScheduleId = scheduleId;
    currentEventRefNum = eventRefNum;
    currentEventType = eventType;

    // Populate modal fields
    document.getElementById('detail-event-number').textContent = eventRefNum;
    document.getElementById('detail-event-name').textContent = eventName;
    document.getElementById('detail-event-type').textContent = eventType;
    document.getElementById('detail-employee').textContent = employeeName;
    document.getElementById('detail-scheduled-date').textContent = scheduledDate;
    document.getElementById('detail-scheduled-time').textContent = scheduledTime;
    document.getElementById('detail-start-date').textContent = startDate;
    document.getElementById('detail-due-date').textContent = dueDate;

    // Show modal
    var modal = document.getElementById('event-details-modal');
    modal.style.display = 'flex';
}

// Close Event Details Modal
function closeEventDetails() {
    var modal = document.getElementById('event-details-modal');
    modal.style.display = 'none';
    currentEventScheduleId = null;
    currentEventRefNum = null;
    currentEventType = null;
}

// Reschedule Event
function rescheduleEvent() {
    if (!currentEventScheduleId) return;

    var eventName = document.getElementById('detail-event-name').textContent;
    var eventType = document.getElementById('detail-event-type').textContent;
    var currentTime = document.getElementById('detail-scheduled-time').textContent;
    var employeeName = document.getElementById('detail-employee').textContent;
    var currentDate = document.getElementById('detail-scheduled-date').textContent;

    openRescheduleModal(currentEventScheduleId, eventName, eventType, currentTime, employeeName, convertDateToISO(currentDate));
}

// Unschedule Event
function unscheduleEvent() {
    if (!currentEventScheduleId) return;

    if (confirm('Are you sure you want to unschedule this event? This will remove the schedule assignment.')) {
        // Get CSRF token
        var csrfToken = window.getCsrfToken ? window.getCsrfToken() : null;

        fetch('/api/unschedule/' + currentEventScheduleId, {
            method: 'DELETE',
            headers: csrfToken ? {
                'X-CSRF-Token': csrfToken
            } : {}
        })
        .then(function(response) {
            if (!response.ok) {
                return response.text().then(function(text) {
                    throw new Error('Server returned ' + response.status + ': ' + text);
                });
            }
            return response.json();
        })
        .then(function(data) {
            if (data.success) {
                alert('Event unscheduled successfully');
                closeEventDetails();
                location.reload();
            } else {
                alert('Error unscheduling event: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(function(error) {
            console.error('Unschedule error:', error);
            alert('Error unscheduling event: ' + error.message);
        });
    }
}

// Change Employee
function changeEmployee() {
    if (!currentEventScheduleId) return;

    var eventName = document.getElementById('detail-event-name').textContent;
    var eventType = document.getElementById('detail-event-type').textContent;
    var time = document.getElementById('detail-scheduled-time').textContent;
    var employeeName = document.getElementById('detail-employee').textContent;
    var date = document.getElementById('detail-scheduled-date').textContent;

    openChangeEmployeeModal(currentEventScheduleId, eventName, eventType, time, employeeName, convertDateToISO(date));
}

// Helper function to convert MM-DD-YYYY to YYYY-MM-DD
function convertDateToISO(dateStr) {
    var parts = dateStr.split('-');
    if (parts.length === 3) {
        return parts[2] + '-' + parts[0] + '-' + parts[1]; // Convert MM-DD-YYYY to YYYY-MM-DD
    }
    return dateStr;
}

// Modal management
function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

// Reschedule Modal Functions
function openRescheduleModal(scheduleId, eventName, eventType, currentTime, employeeName, currentDate) {
    try {
        document.getElementById('reschedule-schedule-id').value = scheduleId;
        document.getElementById('reschedule-event-info').innerHTML =
            '<strong>' + escapeHtml(eventName) + '</strong> (' + escapeHtml(eventType) + ')<br>' +
            'Current: ' + escapeHtml(currentDate) + ' at ' + escapeHtml(currentTime) + ' with ' + escapeHtml(employeeName);

        // Convert displayed time to 24-hour format for comparison
        var time24 = convertTo24Hour(currentTime);

        // Set up time restrictions for event type
        setupTimeRestrictions('reschedule', eventType, time24);

        // Load available employees with role-based filtering
        loadAvailableEmployeesForReschedule('reschedule-employee', currentDate, eventType);

        document.getElementById('reschedule-modal').style.display = 'flex';
    } catch (error) {
        console.error('Error opening reschedule modal:', error);
        alert('Error opening reschedule modal. Please try again.');
    }
}

// Change Employee Modal Functions
function openChangeEmployeeModal(scheduleId, eventName, eventType, time, employeeName, date) {
    try {
        document.getElementById('change-schedule-id').value = scheduleId;
        document.getElementById('change-event-info').innerHTML =
            '<strong>' + escapeHtml(eventName) + '</strong> (' + escapeHtml(eventType) + ')<br>' +
            'Date: ' + escapeHtml(date) + ' at ' + escapeHtml(time) + '<br>' +
            'Current Employee: ' + escapeHtml(employeeName);

        // Load available employees for this date
        loadAvailableEmployeesForChange(date, eventType);

        document.getElementById('change-employee-modal').style.display = 'flex';
    } catch (error) {
        console.error('Error opening change employee modal:', error);
        alert('Error opening change employee modal. Please try again.');
    }
}

// Helper function to setup time restrictions
function setupTimeRestrictions(prefix, eventType, currentTime) {
    var timeInput = document.getElementById(prefix + '-time');
    var timeDropdown = document.getElementById(prefix + '-time-dropdown');

    var timeRestrictions = {
        'Core': ['09:45', '10:30', '11:00', '11:30'],
        'Supervisor': ['12:00'],
        'Freeosk': ['09:00', '12:00'],
        'Digitals': ['09:15', '09:30', '09:45', '10:00']
    };

    if (timeRestrictions[eventType]) {
        timeInput.style.display = 'none';
        timeInput.required = false;
        timeDropdown.style.display = 'block';
        timeDropdown.required = true;

        timeDropdown.innerHTML = '<option value="">Select a time</option>';
        timeRestrictions[eventType].forEach(function(time) {
            var option = document.createElement('option');
            option.value = time;
            option.textContent = formatTime(time);
            if (currentTime && time === currentTime) {
                option.selected = true;
            }
            timeDropdown.appendChild(option);
        });
    } else {
        timeInput.style.display = 'block';
        timeInput.required = true;
        timeDropdown.style.display = 'none';
        timeDropdown.required = false;
    }
}

// Helper function to format time
function formatTime(time24) {
    var parts = time24.split(':');
    var hours = parts[0];
    var minutes = parts[1];
    var hour = parseInt(hours);
    var ampm = hour >= 12 ? 'PM' : 'AM';
    var displayHour = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
    return displayHour + ':' + minutes + ' ' + ampm;
}

// Helper function to convert 12-hour time to 24-hour time
function convertTo24Hour(time12) {
    if (!time12 || !time12.includes(':')) {
        return time12;
    }

    var timeParts = time12.split(' ');
    var time = timeParts[0];
    var modifier = timeParts[1];
    if (!modifier) {
        return time12;
    }

    var colonParts = time.split(':');
    var hours = colonParts[0];
    var minutes = colonParts[1];
    var hour = parseInt(hours);

    if (modifier.toUpperCase() === 'PM' && hour !== 12) {
        hour += 12;
    } else if (modifier.toUpperCase() === 'AM' && hour === 12) {
        hour = 0;
    }

    return (hour < 10 ? '0' : '') + hour + ':' + minutes;
}

// Load available employees functions
function loadAvailableEmployeesForReschedule(selectId, date, eventType) {
    var select = document.getElementById(selectId);
    select.innerHTML = '<option value="">Loading...</option>';

    fetch('/api/available_employees_for_change/' + date + '/' + eventType)
        .then(function(response) { return response.json(); })
        .then(function(employees) {
            select.innerHTML = '<option value="">Select an employee</option>';
            employees.forEach(function(employee) {
                var option = document.createElement('option');
                option.value = employee.id;
                option.textContent = employee.name + ' (' + employee.job_title + ')';
                select.appendChild(option);
            });
        })
        .catch(function(error) {
            console.error('Error loading employees:', error);
            select.innerHTML = '<option value="">Error loading employees</option>';
        });
}

function loadAvailableEmployeesForChange(date, eventType) {
    var select = document.getElementById('change-new-employee');
    select.innerHTML = '<option value="">Loading...</option>';

    fetch('/api/available_employees_for_change/' + date + '/' + eventType)
        .then(function(response) { return response.json(); })
        .then(function(employees) {
            select.innerHTML = '<option value="">Select new employee...</option>';
            employees.forEach(function(employee) {
                var option = document.createElement('option');
                option.value = employee.id;
                option.textContent = employee.name + ' (' + employee.job_title + ')';
                select.appendChild(option);
            });
        })
        .catch(function(error) {
            console.error('Error loading employees:', error);
            select.innerHTML = '<option value="">Error loading employees</option>';
        });
}

// Form submission handlers
document.addEventListener('DOMContentLoaded', function() {
    // Reschedule form submission
    document.getElementById('reschedule-form').addEventListener('submit', function(e) {
        e.preventDefault();

        var scheduleId = document.getElementById('reschedule-schedule-id').value;
        var date = document.getElementById('reschedule-date').value;
        var timeInput = document.getElementById('reschedule-time');
        var timeDropdown = document.getElementById('reschedule-time-dropdown');
        var time = timeDropdown.style.display !== 'none' ? timeDropdown.value : timeInput.value;
        var employeeId = document.getElementById('reschedule-employee').value;

        if (!date || !time || !employeeId) {
            alert('Please fill in all fields');
            return;
        }

        fetch('/api/reschedule', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                schedule_id: parseInt(scheduleId),
                new_date: date,
                new_time: time,
                employee_id: employeeId
            })
        })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (data.success) {
                alert(data.message);
                closeModal('reschedule-modal');
                closeEventDetails();
                location.reload();
            } else {
                alert('Error: ' + data.error);
            }
        })
        .catch(function(error) {
            console.error('Error:', error);
            alert('Error rescheduling event');
        });
    });

    // Change employee form submission
    document.getElementById('change-employee-form').addEventListener('submit', function(e) {
        e.preventDefault();

        var scheduleId = document.getElementById('change-schedule-id').value;
        var newEmployeeId = document.getElementById('change-new-employee').value;

        if (!newEmployeeId) {
            alert('Please select a new employee');
            return;
        }

        fetch('/api/change_employee', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                schedule_id: parseInt(scheduleId),
                employee_id: newEmployeeId
            })
        })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (data.success) {
                alert(data.message);
                closeModal('change-employee-modal');
                closeEventDetails();
                location.reload();
            } else {
                alert('Error: ' + data.error);
            }
        })
        .catch(function(error) {
            console.error('Error:', error);
            alert('Error changing employee');
        });
    });

    // Close modals when clicking outside
    document.querySelectorAll('.modal-backdrop').forEach(function(modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === this) {
                closeModal(this.id);
            }
        });
    });
});

// Print EDR
function printEDR() {
    if (!currentEventRefNum) return;

    // Show loading message
    var statusDiv = document.createElement('div');
    statusDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: var(--pc-navy); color: white; padding: 1rem 1.5rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 9999;';
    statusDiv.textContent = 'Generating EDR report...';
    document.body.appendChild(statusDiv);

    // Request EDR for this specific event
    fetch('/api/edr_reports/generate_single/' + currentEventRefNum, {
        method: 'POST'
    })
    .then(function(response) {
        if (response.ok) {
            return response.blob();
        } else {
            return response.json().then(function(err) {
                throw new Error(err.error || 'Failed to generate EDR');
            });
        }
    })
    .then(function(blob) {
        // Download the PDF
        var url = window.URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'EDR_' + currentEventRefNum + '.pdf';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        statusDiv.style.background = '#27ae60';
        statusDiv.textContent = 'EDR generated successfully!';
        setTimeout(function() { document.body.removeChild(statusDiv); }, 3000);
    })
    .catch(function(error) {
        statusDiv.style.background = '#e74c3c';
        statusDiv.textContent = 'Error: ' + error.message;
        setTimeout(function() { document.body.removeChild(statusDiv); }, 5000);
    });
}

// Print Instructions
function printInstructions() {
    if (!currentEventRefNum) return;

    // Show loading message
    var statusDiv = document.createElement('div');
    statusDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: var(--pc-navy); color: white; padding: 1rem 1.5rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 9999;';
    statusDiv.textContent = 'Generating instructions...';
    document.body.appendChild(statusDiv);

    // Request instructions for this specific event
    fetch('/api/instructions/generate/' + currentEventRefNum, {
        method: 'POST'
    })
    .then(function(response) {
        if (response.ok) {
            return response.blob();
        } else {
            return response.json().then(function(err) {
                throw new Error(err.error || 'Failed to generate instructions');
            });
        }
    })
    .then(function(blob) {
        // Download the PDF
        var url = window.URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'Instructions_' + currentEventRefNum + '.pdf';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        statusDiv.style.background = '#27ae60';
        statusDiv.textContent = 'Instructions generated successfully!';
        setTimeout(function() { document.body.removeChild(statusDiv); }, 3000);
    })
    .catch(function(error) {
        statusDiv.style.background = '#e74c3c';
        statusDiv.textContent = 'Error: ' + error.message;
        setTimeout(function() { document.body.removeChild(statusDiv); }, 5000);
    });
}

// Print Both (EDR and Instructions)
function printBoth() {
    if (!currentEventRefNum) return;

    // Show loading message
    var statusDiv = document.createElement('div');
    statusDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: var(--pc-navy); color: white; padding: 1rem 1.5rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 9999;';
    statusDiv.textContent = 'Generating EDR and Instructions...';
    document.body.appendChild(statusDiv);

    // Request both EDR and instructions
    fetch('/api/paperwork/generate_both/' + currentEventRefNum, {
        method: 'POST'
    })
    .then(function(response) {
        if (response.ok) {
            return response.blob();
        } else {
            return response.json().then(function(err) {
                throw new Error(err.error || 'Failed to generate paperwork');
            });
        }
    })
    .then(function(blob) {
        // Download the PDF
        var url = window.URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'Paperwork_' + currentEventRefNum + '.pdf';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        statusDiv.style.background = '#27ae60';
        statusDiv.textContent = 'Paperwork generated successfully!';
        setTimeout(function() { document.body.removeChild(statusDiv); }, 3000);
    })
    .catch(function(error) {
        statusDiv.style.background = '#e74c3c';
        statusDiv.textContent = 'Error: ' + error.message;
        setTimeout(function() { document.body.removeChild(statusDiv); }, 5000);
    });
}

// Print today's schedule functionality - matching calendar format exactly
function printTodaySchedule() {
    // Use data from the page-data JSON block
    var todayStr = PAGE_DATA.todayFormatted || '';

    // Prepare events data for printing (Core and Juicer Production only)
    var printableEvents = (PAGE_DATA.todayCoreEvents || []).map(function(evt) {
        return {
            employee_name: evt.employee_name,
            time: evt.time,
            event_name: evt.event_name,
            event_type: evt.event_type,
            minutes: convertTimeToMinutes(evt.time)
        };
    });

    // Filter and sort events (same logic as calendar)
    var filteredEvents = printableEvents.filter(function(event) {
        return event.event_type === 'Core' ||
               (event.event_type === 'Juicer' &&
                event.event_name.includes('Production') &&
                !event.event_name.toLowerCase().includes('survey'));
    });

    // Sort by time
    filteredEvents.sort(function(a, b) { return a.minutes - b.minutes; });

    if (filteredEvents.length === 0) {
        alert('No Core or Juicer Production events found for this day.');
        return;
    }

    // Generate printable HTML with exact same format as calendar
    var printContent = generatePrintableSchedule(todayStr, filteredEvents);

    // Create and open print window
    var printWindow = window.open('', '_blank');
    printWindow.document.write(printContent);
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
}

function printTomorrowSchedule() {
    // Use data from the page-data JSON block
    var tomorrowStr = PAGE_DATA.tomorrowFormatted || '';

    // Prepare tomorrow's events data
    var printableEvents = (PAGE_DATA.tomorrowCoreEvents || []).map(function(evt) {
        return {
            employee_name: evt.employee_name,
            time: evt.time,
            event_name: evt.event_name,
            event_type: evt.event_type
        };
    });

    // Filter for Core and Juicer Production events only
    var filteredEvents = printableEvents.filter(function(event) {
        return event.event_type === 'Core' || event.event_type === 'Juicer';
    });

    var printContent = generatePrintableSchedule(tomorrowStr, filteredEvents);

    // Create and open print window
    var printWindow = window.open('', '_blank');
    printWindow.document.write(printContent);
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
}

// New function for date-based schedule printing
function printScheduleByDate() {
    var dateInput = document.getElementById('schedule-date');
    var selectedDate = dateInput.value;

    if (!selectedDate) {
        alert('Please select a date');
        return;
    }

    // Show loading indicator
    var statusDiv = document.createElement('div');
    statusDiv.id = 'schedule-loading-status';
    statusDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: var(--pc-navy); color: white; padding: 1rem 1.5rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 999;';
    statusDiv.textContent = 'Loading schedule...';
    document.body.appendChild(statusDiv);

    // Fetch schedule data for the selected date
    fetch('/api/schedule/print/' + selectedDate)
        .then(function(response) {
            if (!response.ok) {
                throw new Error('Failed to fetch schedule data');
            }
            return response.json();
        })
        .then(function(data) {
            // Remove loading indicator
            document.body.removeChild(statusDiv);

            if (!data.events || data.events.length === 0) {
                alert('No Core or Juicer Production events found for this date.');
                return;
            }

            // Sort events by time
            data.events.sort(function(a, b) { return a.minutes - b.minutes; });

            // Generate printable HTML
            var printContent = generatePrintableSchedule(data.formatted_date, data.events);

            // Create and open print window
            var printWindow = window.open('', '_blank');
            printWindow.document.write(printContent);
            printWindow.document.close();
            printWindow.focus();
            printWindow.print();
        })
        .catch(function(error) {
            // Remove loading indicator if it exists
            var loadingDiv = document.getElementById('schedule-loading-status');
            if (loadingDiv) {
                document.body.removeChild(loadingDiv);
            }
            alert('Error loading schedule: ' + error.message);
            console.error('Error:', error);
        });
}

function convertTimeToMinutes(timeStr) {
    // Convert time like "9:15 AM" to minutes for sorting
    var parts = timeStr.split(' ');
    var time = parts[0];
    var modifier = parts[1];
    var timeParts = time.split(':');
    var hours = timeParts[0];
    var minutes = timeParts[1];
    var hour = parseInt(hours);

    if (modifier === 'PM' && hour !== 12) {
        hour += 12;
    } else if (modifier === 'AM' && hour === 12) {
        hour = 0;
    }

    return hour * 60 + parseInt(minutes);
}

function generatePrintableSchedule(dateStr, printableEvents) {
    var rows = printableEvents.map(function(event) {
        return '<tr>' +
            '<td class="employee-name">' + escapeHtml(event.employee_name) + '</td>' +
            '<td class="event-time">' + escapeHtml(event.time) + '</td>' +
            '<td class="event-name">' + escapeHtml(event.event_name) + '</td>' +
            '</tr>';
    }).join('');

    return '<!DOCTYPE html>' +
    '<html>' +
    '<head>' +
        '<title>Core Events Schedule - ' + escapeHtml(dateStr) + '</title>' +
        '<style>' +
            'body {' +
                'font-family: Arial, sans-serif;' +
                'margin: 40px;' +
                'background: white;' +
            '}' +
            '.header {' +
                'text-align: center;' +
                'margin-bottom: 30px;' +
                'border-bottom: 3px solid #2E4C73;' +
                'padding-bottom: 20px;' +
            '}' +
            '.date-title {' +
                'font-size: 24px;' +
                'font-weight: bold;' +
                'color: #2E4C73;' +
                'margin: 0;' +
            '}' +
            '.subtitle {' +
                'font-size: 16px;' +
                'color: #666;' +
                'margin: 5px 0 0 0;' +
            '}' +
            '.schedule-table {' +
                'width: 100%;' +
                'border-collapse: collapse;' +
                'margin-top: 20px;' +
            '}' +
            '.schedule-table th {' +
                'background: #2E4C73;' +
                'color: white;' +
                'padding: 12px;' +
                'text-align: left;' +
                'font-weight: bold;' +
                'font-size: 14px;' +
                'border: 1px solid #ddd;' +
            '}' +
            '.schedule-table td {' +
                'padding: 10px 12px;' +
                'border: 1px solid #ddd;' +
                'font-size: 13px;' +
            '}' +
            '.schedule-table tr:nth-child(even) {' +
                'background-color: #f9f9f9;' +
            '}' +
            '.schedule-table tr:hover {' +
                'background-color: #f0f0f0;' +
            '}' +
            '.employee-name {' +
                'font-weight: bold;' +
                'color: #2E4C73;' +
            '}' +
            '.event-time {' +
                'font-weight: bold;' +
                'color: #1B9BD8;' +
            '}' +
            '.event-name {' +
                'color: #333;' +
            '}' +
            '.footer {' +
                'margin-top: 40px;' +
                'text-align: center;' +
                'font-size: 12px;' +
                'color: #888;' +
                'border-top: 1px solid #ddd;' +
                'padding-top: 20px;' +
            '}' +
            '@media print {' +
                'body { margin: 20px; }' +
                '.header { page-break-after: avoid; }' +
            '}' +
        '</style>' +
    '</head>' +
    '<body>' +
        '<div class="header">' +
            '<h1 class="date-title">' + escapeHtml(dateStr) + '</h1>' +
            '<p class="subtitle">Daily Schedule</p>' +
        '</div>' +
        '<table class="schedule-table">' +
            '<thead>' +
                '<tr>' +
                    '<th style="width: 30%;">Employee Name</th>' +
                    '<th style="width: 20%;">Scheduled Time</th>' +
                    '<th style="width: 50%;">Event Name</th>' +
                '</tr>' +
            '</thead>' +
            '<tbody>' +
                rows +
            '</tbody>' +
        '</table>' +
        '<div class="footer">' +
            '<p>Generated on ' + new Date().toLocaleString() + ' | Product Connections Scheduler</p>' +
        '</div>' +
    '</body>' +
    '</html>';
}

// Sync status functions removed - moved to dedicated Sync Settings page

// Global variable to track pending paperwork type
var pendingPaperworkType = null;
var pendingEDRDate = null;

// MFA Modal functions
function showMFAModal(paperworkType) {
    pendingPaperworkType = paperworkType;
    var modal = document.getElementById('mfa-modal');
    var input = document.getElementById('mfa-code-input');
    var error = document.getElementById('mfa-error');

    modal.style.display = 'flex';
    input.value = '';
    error.style.display = 'none';
    input.focus();
}

function cancelMFAAuth() {
    var modal = document.getElementById('mfa-modal');
    modal.style.display = 'none';
    pendingPaperworkType = null;
    pendingEDRDate = null;
}

function submitMFACode() {
    var input = document.getElementById('mfa-code-input');
    var error = document.getElementById('mfa-error');
    var submitBtn = document.getElementById('mfa-submit-btn');
    var mfaCode = input.value.trim();

    if (!mfaCode || mfaCode.length !== 6) {
        error.textContent = 'Please enter a 6-digit MFA code';
        error.style.display = 'block';
        return;
    }

    // Determine which workflow to use (paperwork or EDR)
    if (pendingEDRDate) {
        submitMFACodeForEDR(mfaCode, submitBtn, error);
    } else if (selectedPaperworkDate) {
        submitMFACodeForPaperwork(mfaCode, submitBtn, error);
    } else {
        error.textContent = 'No operation pending';
        error.style.display = 'block';
    }
}

function submitMFACodeForPaperwork(mfaCode, submitBtn, error) {
    // Disable button and show loading
    submitBtn.disabled = true;
    submitBtn.textContent = 'Generating Paperwork...';
    error.style.display = 'none';

    // Generate daily paperwork with MFA code
    fetch('/api/daily_paperwork/generate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            mfa_code: mfaCode,
            date: selectedPaperworkDate
        })
    })
    .then(function(response) {
        if (response.ok) {
            // Close modal
            cancelMFAAuth();

            // Download the PDF
            return response.blob().then(function(blob) {
                var url = window.URL.createObjectURL(blob);
                var a = document.createElement('a');
                a.href = url;
                a.download = 'Paperwork_' + selectedPaperworkDate + '.pdf';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);

                // Show success message
                var successDiv = document.createElement('div');
                successDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: #27ae60; color: white; padding: 1rem 1.5rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 999;';
                successDiv.textContent = 'Daily paperwork generated successfully!';
                document.body.appendChild(successDiv);
                setTimeout(function() { document.body.removeChild(successDiv); }, 3000);

                selectedPaperworkDate = null;  // Reset after use
            });
        } else {
            return response.json().then(function(data) {
                throw new Error(data.error || 'Failed to generate paperwork');
            });
        }
    })
    .catch(function(err) {
        error.textContent = err.message || 'Unknown error occurred';
        error.style.display = 'block';
    })
    .finally(function() {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Authenticate';
    });
}

function submitMFACodeForEDR(mfaCode, submitBtn, error) {
    // Disable button and show loading
    submitBtn.disabled = true;
    submitBtn.textContent = 'Generating EDR Reports...';
    error.style.display = 'none';

    // Generate EDR reports with MFA code
    fetch('/api/edr_reports/generate_by_date', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            mfa_code: mfaCode,
            date: pendingEDRDate
        })
    })
    .then(function(response) {
        if (response.ok) {
            // Close modal
            cancelMFAAuth();

            // Download the PDF
            return response.blob().then(function(blob) {
                var url = window.URL.createObjectURL(blob);
                var a = document.createElement('a');
                a.href = url;
                a.download = 'EDR_Reports_' + pendingEDRDate + '.pdf';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);

                // Show success message
                var successDiv = document.createElement('div');
                successDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: #27ae60; color: white; padding: 1rem 1.5rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 999;';
                successDiv.textContent = 'EDR reports generated successfully!';
                document.body.appendChild(successDiv);
                setTimeout(function() { document.body.removeChild(successDiv); }, 3000);

                pendingEDRDate = null;  // Reset after use
            });
        } else {
            return response.json().then(function(data) {
                throw new Error(data.error || 'Failed to generate EDR reports');
            });
        }
    })
    .catch(function(err) {
        error.textContent = err.message || 'Unknown error occurred';
        error.style.display = 'block';
    })
    .finally(function() {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Authenticate';
    });
}

function generatePaperworkByDate(dateStr) {
    console.log('Generating paperwork for date:', dateStr);
    var statusDiv = document.createElement('div');
    statusDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: var(--pc-navy); color: white; padding: 1rem 1.5rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 999;';
    statusDiv.textContent = 'Generating comprehensive paperwork PDF...';
    document.body.appendChild(statusDiv);

    fetch('/api/print_paperwork_by_date/' + dateStr)
        .then(function(response) {
            console.log('Response received:', response.status, response.statusText);
            if (response.ok) {
                return response.blob();
            } else {
                return response.json().then(function(err) { return Promise.reject(err); });
            }
        })
        .then(function(blob) {
            console.log('Blob received, size:', blob.size);
            // Create download link
            var url = window.URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = 'Sales_Tools_' + dateStr + '.pdf';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

            statusDiv.style.background = '#27ae60';
            statusDiv.textContent = 'PDF downloaded successfully!';
            setTimeout(function() { document.body.removeChild(statusDiv); }, 3000);
        })
        .catch(function(error) {
            console.error('Error generating paperwork:', error);
            statusDiv.style.background = '#e74c3c';
            statusDiv.textContent = 'Error: ' + (error.error || error.message || 'Unknown error');
            setTimeout(function() { document.body.removeChild(statusDiv); }, 5000);
        });
}

// Allow Enter key to submit MFA code
document.addEventListener('DOMContentLoaded', function() {
    var mfaInput = document.getElementById('mfa-code-input');
    if (mfaInput) {
        mfaInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                submitMFACode();
            }
        });
    }
});

// Global variable to store the selected date for paperwork
var selectedPaperworkDate = null;

// Paperwork printing functions
function printPaperworkByDate() {
    var dateInput = document.getElementById('paperwork-date');
    selectedPaperworkDate = dateInput.value;

    if (!selectedPaperworkDate) {
        alert('Please select a date');
        return;
    }

    // Request MFA code and show modal
    requestMFACodeAndShowModalForPaperwork();
}

// Print SalesTools for selected date
function printSalesToolsByDate() {
    var dateInput = document.getElementById('paperwork-date');
    var selectedDate = dateInput.value;

    if (!selectedDate) {
        alert('Please select a date');
        return;
    }

    // Show loading indicator
    var statusDiv = document.createElement('div');
    statusDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: var(--pc-navy); color: white; padding: 1rem 1.5rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 999;';
    statusDiv.textContent = 'Downloading and merging SalesTools PDFs...';
    document.body.appendChild(statusDiv);

    fetch('/api/print_salestools_by_date/' + selectedDate)
        .then(function(response) {
            if (response.ok) {
                return response.blob();
            } else {
                return response.json().then(function(err) {
                    throw new Error(err.error || 'Failed to generate SalesTools PDF');
                });
            }
        })
        .then(function(blob) {
            // Create download link
            var url = window.URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = 'SalesTools_' + selectedDate + '.pdf';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

            // Update status
            statusDiv.style.background = '#27ae60';
            statusDiv.textContent = 'SalesTools PDF downloaded successfully!';
            setTimeout(function() { document.body.removeChild(statusDiv); }, 3000);

            // Open print dialog
            var printWindow = window.open(url, '_blank');
            if (printWindow) {
                printWindow.onload = function() {
                    printWindow.print();
                };
            }
        })
        .catch(function(error) {
            console.error('Error generating SalesTools PDF:', error);
            statusDiv.style.background = '#e74c3c';
            statusDiv.textContent = 'Error: ' + error.message;
            setTimeout(function() { document.body.removeChild(statusDiv); }, 5000);
        });
}

function requestMFACodeAndShowModalForPaperwork() {
    // Show loading indicator
    var statusDiv = document.createElement('div');
    statusDiv.id = 'mfa-request-status';
    statusDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: var(--pc-navy); color: white; padding: 1rem 1.5rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 999;';
    statusDiv.textContent = 'Requesting MFA code...';
    document.body.appendChild(statusDiv);

    // Request MFA code to be sent
    fetch('/api/daily_paperwork/request_mfa', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        // Remove loading indicator
        document.body.removeChild(statusDiv);

        if (data.success) {
            // Show success message briefly
            var successDiv = document.createElement('div');
            successDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: #27ae60; color: white; padding: 1rem 1.5rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 999;';
            successDiv.textContent = 'MFA code sent to your phone!';
            document.body.appendChild(successDiv);

            setTimeout(function() {
                document.body.removeChild(successDiv);
                // Now show the MFA modal
                showMFAModalForPaperwork();
            }, 1500);
        } else {
            alert('Failed to request MFA code: ' + (data.error || data.message || 'Unknown error'));
        }
    })
    .catch(function(err) {
        // Remove loading indicator
        var loadingDiv = document.getElementById('mfa-request-status');
        if (loadingDiv) {
            document.body.removeChild(loadingDiv);
        }
        alert('Error requesting MFA code: ' + (err.message || 'Unknown error'));
    });
}

function showMFAModalForPaperwork() {
    var modal = document.getElementById('mfa-modal');
    var input = document.getElementById('mfa-code-input');
    var error = document.getElementById('mfa-error');

    modal.style.display = 'flex';
    input.value = '';
    error.style.display = 'none';
    input.focus();
}

// Legacy functions (kept for backward compatibility)
function printTodayPaperwork() {
    var today = new Date().toISOString().split('T')[0];
    document.getElementById('paperwork-date').value = today;
    printPaperworkByDate();
}

function printTomorrowPaperwork() {
    var tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    document.getElementById('paperwork-date').value = tomorrow.toISOString().split('T')[0];
    printPaperworkByDate();
}

function requestMFACodeAndShowModal(paperworkType) {
    // Show loading indicator
    var statusDiv = document.createElement('div');
    statusDiv.id = 'mfa-request-status';
    statusDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: var(--pc-navy); color: white; padding: 1rem 1.5rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 999;';
    statusDiv.textContent = 'Requesting MFA code...';
    document.body.appendChild(statusDiv);

    // Request MFA code to be sent
    fetch('/api/edr/request_code', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        // Remove loading indicator
        document.body.removeChild(statusDiv);

        if (data.success) {
            // Show success message briefly
            var successDiv = document.createElement('div');
            successDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: #27ae60; color: white; padding: 1rem 1.5rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 999;';
            successDiv.textContent = 'MFA code sent to your phone!';
            document.body.appendChild(successDiv);

            setTimeout(function() {
                document.body.removeChild(successDiv);
                // Now show the MFA modal
                showMFAModal(paperworkType);
            }, 1500);
        } else {
            alert('Failed to request MFA code: ' + (data.message || 'Unknown error'));
        }
    })
    .catch(function(err) {
        // Remove loading indicator
        var loadingDiv = document.getElementById('mfa-request-status');
        if (loadingDiv) {
            document.body.removeChild(loadingDiv);
        }
        alert('Error requesting MFA code: ' + (err.message || 'Unknown error'));
    });
}

function generatePaperwork(type) {
    console.log('generatePaperwork called with type:', type);
    var statusDiv = document.createElement('div');
    statusDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: var(--pc-navy); color: white; padding: 1rem 1.5rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 999;';
    statusDiv.textContent = 'Generating PDF...';
    document.body.appendChild(statusDiv);
    console.log('Status div added to body');

    console.log('Fetching:', '/api/print_paperwork/' + type);
    fetch('/api/print_paperwork/' + type)
        .then(function(response) {
            console.log('Response received:', response.status, response.statusText);
            if (response.ok) {
                return response.blob();
            } else {
                return response.json().then(function(err) { return Promise.reject(err); });
            }
        })
        .then(function(blob) {
            console.log('Blob received, size:', blob.size);
            // Create download link
            var url = window.URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            var dateStr = type === 'today'
                ? new Date().toISOString().split('T')[0]
                : (function() { var d = new Date(); d.setDate(d.getDate() + 1); return d.toISOString().split('T')[0]; })();
            a.download = 'Sales_Tools_' + type + '_' + dateStr + '.pdf';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

            statusDiv.style.background = '#27ae60';
            statusDiv.textContent = 'PDF downloaded successfully!';
            setTimeout(function() { document.body.removeChild(statusDiv); }, 3000);
        })
        .catch(function(error) {
            console.error('Error generating paperwork:', error);
            statusDiv.style.background = '#e74c3c';
            statusDiv.textContent = 'Error: ' + (error.error || error.message || 'Unknown error');
            setTimeout(function() { document.body.removeChild(statusDiv); }, 5000);
        });
}

// Removed auto-scheduler functions - moved to dedicated Auto-Scheduler page

// EDR Reports generation function
function generateEDRReports() {
    var dateInput = document.getElementById('paperwork-date');
    var selectedDate = dateInput.value;

    if (!selectedDate) {
        alert('Please select a date');
        return;
    }

    // Store the date globally
    pendingEDRDate = selectedDate;

    // Request MFA code and show modal
    requestMFACodeForEDR();
}

function requestMFACodeForEDR() {
    // Show loading indicator
    var statusDiv = document.createElement('div');
    statusDiv.id = 'mfa-request-status-edr';
    statusDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: var(--pc-navy); color: white; padding: 1rem 1.5rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 999;';
    statusDiv.textContent = 'Requesting MFA code for EDR reports...';
    document.body.appendChild(statusDiv);

    // Request MFA code to be sent
    fetch('/api/edr_reports/request_mfa', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        // Remove loading indicator
        document.body.removeChild(statusDiv);

        if (data.success) {
            // Show success message briefly
            var successDiv = document.createElement('div');
            successDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: #27ae60; color: white; padding: 1rem 1.5rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 999;';
            successDiv.textContent = 'MFA code sent to your phone!';
            document.body.appendChild(successDiv);

            setTimeout(function() {
                document.body.removeChild(successDiv);
                // Now show the MFA modal
                showMFAModalForEDR();
            }, 1500);
        } else {
            alert('Failed to request MFA code: ' + (data.error || data.message || 'Unknown error'));
            pendingEDRDate = null;
        }
    })
    .catch(function(err) {
        // Remove loading indicator
        var loadingDiv = document.getElementById('mfa-request-status-edr');
        if (loadingDiv) {
            document.body.removeChild(loadingDiv);
        }
        alert('Error requesting MFA code: ' + (err.message || 'Unknown error'));
        pendingEDRDate = null;
    });
}

function showMFAModalForEDR() {
    var modal = document.getElementById('mfa-modal');
    var input = document.getElementById('mfa-code-input');
    var error = document.getElementById('mfa-error');

    modal.style.display = 'flex';
    input.value = '';
    error.style.display = 'none';
    input.focus();
}

// Schedule Verification Widget Functions
function runVerification() {
    var dateInput = document.getElementById('verification-date');
    var selectedDate = dateInput.value;

    if (!selectedDate) {
        alert('Please select a date');
        return;
    }

    // Show loading state
    document.getElementById('verification-widget-initial').style.display = 'none';
    document.getElementById('verification-widget-results').style.display = 'none';
    document.getElementById('verification-widget-loading').style.display = 'block';

    fetch('/auto-schedule/api/verify-date?date=' + selectedDate)
        .then(function(response) {
            if (!response.ok) {
                throw new Error('Verification failed: ' + response.status + ' ' + response.statusText);
            }
            return response.json();
        })
        .then(function(data) {
            // Hide loading, show results
            document.getElementById('verification-widget-loading').style.display = 'none';
            document.getElementById('verification-widget-results').style.display = 'block';

            // Display results
            displayWidgetVerificationResults(data, selectedDate);
        })
        .catch(function(error) {
            console.error('Verification error:', error);
            document.getElementById('verification-widget-loading').style.display = 'none';
            document.getElementById('verification-widget-initial').style.display = 'block';
            alert('Error running verification: ' + error.message);
        });
}

function displayWidgetVerificationResults(data, selectedDate) {
    var criticalCount = data.critical_issues ? data.critical_issues.length : 0;
    var warningCount = data.warnings ? data.warnings.length : 0;
    var infoCount = data.info ? data.info.length : 0;

    // Format the date for display
    var dateObj = new Date(selectedDate + 'T00:00:00');
    var formattedDate = dateObj.toLocaleDateString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });

    // Update status badge
    var statusBadge = document.getElementById('verification-status-badge');
    var icon = document.getElementById('verification-widget-icon');

    if (criticalCount > 0) {
        statusBadge.style.background = 'rgba(192, 57, 43, 0.1)';
        statusBadge.style.border = '2px solid #c0392b';
        statusBadge.style.color = '#c0392b';
        statusBadge.innerHTML = '\uD83D\uDEA8 ' + criticalCount + ' Critical Issue' + (criticalCount !== 1 ? 's' : '') + ' Found';
        icon.textContent = '\uD83D\uDEA8';
    } else if (warningCount > 0) {
        statusBadge.style.background = 'rgba(230, 126, 34, 0.1)';
        statusBadge.style.border = '2px solid #e67e22';
        statusBadge.style.color = '#e67e22';
        statusBadge.innerHTML = '\u26A0\uFE0F ' + warningCount + ' Warning' + (warningCount !== 1 ? 's' : '') + ' - Review Recommended';
        icon.textContent = '\u26A0\uFE0F';
    } else {
        statusBadge.style.background = 'rgba(39, 174, 96, 0.1)';
        statusBadge.style.border = '2px solid #27ae60';
        statusBadge.style.color = '#27ae60';
        statusBadge.innerHTML = '\u2705 All schedules verified for ' + escapeHtml(formattedDate);
        icon.textContent = '\u2705';
    }

    // Display critical issues
    var criticalSection = document.getElementById('verification-critical-section');
    var criticalList = document.getElementById('verification-critical-list');
    if (criticalCount > 0) {
        criticalSection.style.display = 'block';
        criticalList.innerHTML = data.critical_issues.map(function(issue) {
            return formatVerificationIssue(issue, 'critical');
        }).join('');
    } else {
        criticalSection.style.display = 'none';
    }

    // Display warnings
    var warningsSection = document.getElementById('verification-warnings-section');
    var warningsList = document.getElementById('verification-warnings-list');
    if (warningCount > 0) {
        warningsSection.style.display = 'block';
        warningsList.innerHTML = data.warnings.map(function(issue) {
            return formatVerificationIssue(issue, 'warning');
        }).join('');
    } else {
        warningsSection.style.display = 'none';
    }

    // Display info messages
    var infoSection = document.getElementById('verification-info-section');
    var infoList = document.getElementById('verification-info-list');
    if (infoCount > 0) {
        infoSection.style.display = 'block';
        infoList.innerHTML = data.info.map(function(issue) {
            return formatVerificationIssue(issue, 'info');
        }).join('');
    } else {
        infoSection.style.display = 'none';
    }
}

function formatVerificationIssue(issue, severity) {
    return '<div class="verification-issue-item ' + severity + '">' +
        '<div class="verification-issue-message">' + escapeHtml(issue.message) + '</div>' +
        (issue.details ? '<div class="verification-issue-details">' + escapeHtml(issue.details) + '</div>' : '') +
        (issue.action ? '<div class="verification-issue-action">\uD83D\uDCA1 ' + escapeHtml(issue.action) + '</div>' : '') +
    '</div>';
}

// Delegated click handler - replaces inline onclick attributes
document.addEventListener('click', function(e) {
    var target = e.target.closest('[data-action]');
    if (!target) return;
    var action = target.dataset.action;

    switch (action) {
        case 'run-verification': runVerification(); break;
        case 'show-event-details':
            showEventDetails(
                parseInt(target.dataset.scheduleId),
                target.dataset.refNum,
                target.dataset.eventName,
                target.dataset.employeeName,
                target.dataset.scheduledDate,
                target.dataset.scheduledTime,
                target.dataset.startDate,
                target.dataset.dueDate,
                target.dataset.eventType
            );
            break;
        case 'print-schedule': printScheduleByDate(); break;
        case 'print-paperwork': printPaperworkByDate(); break;
        case 'print-sales-tools': printSalesToolsByDate(); break;
        case 'generate-edr': generateEDRReports(); break;
        case 'cancel-mfa': cancelMFAAuth(); break;
        case 'submit-mfa': submitMFACode(); break;
        case 'close-event-details': closeEventDetails(); break;
        case 'reschedule-event': rescheduleEvent(); break;
        case 'unschedule-event': unscheduleEvent(); break;
        case 'change-employee': changeEmployee(); break;
        case 'print-edr': printEDR(); break;
        case 'print-instructions': printInstructions(); break;
        case 'print-both': printBoth(); break;
        case 'close-modal': closeModal(target.dataset.modal); break;
    }
});
