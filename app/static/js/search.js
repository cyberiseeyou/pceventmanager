/**
 * Universal Search Functionality
 * Provides fuzzy search across events, employees, and schedules
 */

let searchTimeout = null;
let currentContext = 'scheduling'; // Default context
let searchResultsVisible = false;

document.addEventListener('DOMContentLoaded', function() {
    initializeUniversalSearch();
});

function initializeUniversalSearch() {
    const searchInput = document.getElementById('universal-search');
    const searchFilters = document.getElementById('search-filters');
    const contextButtons = document.querySelectorAll('.context-btn');
    const statusFilter = document.getElementById('status-filter');
    const eventTypeFilter = document.getElementById('event-type-filter');
    const priorityFilter = document.getElementById('priority-filter');
    const clearSearchBtn = document.getElementById('clear-search');

    if (!searchInput) return; // Not on a page with search

    // Context button handling
    contextButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            // Remove active class from all buttons
            contextButtons.forEach(b => b.classList.remove('active'));
            // Add active class to clicked button
            this.classList.add('active');
            // Update context
            currentContext = this.dataset.context;
            // Re-run search if there's a query
            if (searchInput.value.trim()) {
                performSearch(searchInput.value.trim());
            }
        });
    });

    // Search input handling with debounce
    searchInput.addEventListener('input', function() {
        const query = this.value.trim();

        // Show/hide filters based on query
        if (query) {
            searchFilters.style.display = 'flex';
        } else {
            searchFilters.style.display = 'none';
            hideSearchResults();
        }

        // Clear existing timeout
        if (searchTimeout) {
            clearTimeout(searchTimeout);
        }

        // Set new timeout for search (300ms debounce)
        if (query) {
            searchTimeout = setTimeout(() => {
                performSearch(query);
            }, 300);
        }
    });

    // Filter change handling
    if (statusFilter) {
        statusFilter.addEventListener('change', function() {
            if (searchInput.value.trim()) {
                performSearch(searchInput.value.trim());
            }
        });
    }

    if (eventTypeFilter) {
        eventTypeFilter.addEventListener('change', function() {
            if (searchInput.value.trim()) {
                performSearch(searchInput.value.trim());
            }
        });
    }

    if (priorityFilter) {
        priorityFilter.addEventListener('change', function() {
            if (searchInput.value.trim()) {
                performSearch(searchInput.value.trim());
            }
        });
    }

    // Clear search button
    if (clearSearchBtn) {
        clearSearchBtn.addEventListener('click', function() {
            searchInput.value = '';
            searchFilters.style.display = 'none';
            hideSearchResults();
            if (statusFilter) statusFilter.value = '';
            if (eventTypeFilter) eventTypeFilter.value = '';
            if (priorityFilter) priorityFilter.value = '';
        });
    }

    // Click outside to close search results
    document.addEventListener('click', function(e) {
        const searchContainer = document.querySelector('.universal-search-container');
        if (searchContainer && !searchContainer.contains(e.target)) {
            hideSearchResults();
        }
    });

    // Prevent closing when clicking inside search results
    const searchResultsContainer = document.getElementById('search-results');
    if (searchResultsContainer) {
        searchResultsContainer.addEventListener('click', function(e) {
            e.stopPropagation();
        });
    }
}

function performSearch(query) {
    const statusFilter = document.getElementById('status-filter');
    const eventTypeFilter = document.getElementById('event-type-filter');
    const priorityFilter = document.getElementById('priority-filter');

    // Build query parameters
    const params = new URLSearchParams({
        q: query,
        context: currentContext
    });

    // Add filters
    if (statusFilter && statusFilter.value) {
        params.append('filters', `status:${statusFilter.value}`);
    }
    if (eventTypeFilter && eventTypeFilter.value) {
        params.append('filters', `event_type:${eventTypeFilter.value}`);
    }

    // Fetch search results
    fetch(`/api/universal_search?${params.toString()}`)
        .then(response => response.json())
        .then(data => {
            displaySearchResults(data, priorityFilter ? priorityFilter.value : '');
        })
        .catch(error => {
            console.error('Search error:', error);
            showSearchError('Failed to search. Please try again.');
        });
}

function displaySearchResults(data, priorityFilter) {
    let resultsContainer = document.getElementById('search-results');

    // Create results container if it doesn't exist
    if (!resultsContainer) {
        resultsContainer = document.createElement('div');
        resultsContainer.id = 'search-results';
        resultsContainer.className = 'search-results';
        const searchContainer = document.querySelector('.universal-search-container');
        searchContainer.appendChild(resultsContainer);
    }

    // Clear previous results
    resultsContainer.innerHTML = '';

    // Apply priority filter if needed
    let filteredEvents = data.events || [];
    if (priorityFilter && filteredEvents.length > 0) {
        filteredEvents = filteredEvents.filter(event => event.priority === priorityFilter);
    }

    // Show total count
    const totalResults = filteredEvents.length + (data.employees?.length || 0) + (data.schedules?.length || 0);

    if (totalResults === 0) {
        resultsContainer.innerHTML = `
            <div class="search-result-section">
                <p style="text-align: center; padding: var(--spacing-md); color: var(--text-muted);">
                    No results found for "${data.query}"
                </p>
            </div>
        `;
        resultsContainer.style.display = 'block';
        searchResultsVisible = true;
        return;
    }

    // Display events
    if (filteredEvents.length > 0) {
        const eventsSection = document.createElement('div');
        eventsSection.className = 'search-result-section';
        eventsSection.innerHTML = `
            <div class="search-section-title">Events (${filteredEvents.length})</div>
        `;

        filteredEvents.forEach(event => {
            const eventItem = createEventResultItem(event);
            eventsSection.appendChild(eventItem);
        });

        resultsContainer.appendChild(eventsSection);
    }

    // Display employees
    if (data.employees && data.employees.length > 0) {
        const employeesSection = document.createElement('div');
        employeesSection.className = 'search-result-section';
        employeesSection.innerHTML = `
            <div class="search-section-title">Employees (${data.employees.length})</div>
        `;

        data.employees.forEach(employee => {
            const employeeItem = createEmployeeResultItem(employee);
            employeesSection.appendChild(employeeItem);
        });

        resultsContainer.appendChild(employeesSection);
    }

    // Display schedules
    if (data.schedules && data.schedules.length > 0) {
        const schedulesSection = document.createElement('div');
        schedulesSection.className = 'search-result-section';
        schedulesSection.innerHTML = `
            <div class="search-section-title">Schedules (${data.schedules.length})</div>
        `;

        data.schedules.forEach(schedule => {
            const scheduleItem = createScheduleResultItem(schedule);
            schedulesSection.appendChild(scheduleItem);
        });

        resultsContainer.appendChild(schedulesSection);
    }

    resultsContainer.style.display = 'block';
    searchResultsVisible = true;
}

function createEventResultItem(event) {
    const item = document.createElement('div');
    item.className = 'search-result-item';

    const priorityIcon = getPriorityIcon(event.priority);
    const statusBadge = event.is_scheduled
        ? '<span style="color: green; font-size: 11px;">✓ Scheduled</span>'
        : '<span style="color: orange; font-size: 11px;">⚠ Unscheduled</span>';

    item.innerHTML = `
        <div class="search-result-title">
            <span class="priority-indicator priority-${event.priority}"></span>
            ${event.project_name}
        </div>
        <div class="search-result-details">
            <span>${event.event_type}</span>
            <span>•</span>
            <span>${event.store_name || 'No store'}</span>
            <span>•</span>
            <span>${priorityIcon} ${event.days_remaining} days</span>
            <span>•</span>
            ${statusBadge}
        </div>
    `;

    item.addEventListener('click', function() {
        window.location.href = `/schedule/${event.id}`;
    });

    return item;
}

function createEmployeeResultItem(employee) {
    const item = document.createElement('div');
    item.className = 'search-result-item';

    const supervisorBadge = employee.is_supervisor
        ? '<span style="color: var(--pc-blue); font-size: 11px;">👔 Supervisor</span>'
        : '';

    item.innerHTML = `
        <div class="search-result-title">
            👤 ${employee.name}
        </div>
        <div class="search-result-details">
            <span>${employee.job_title}</span>
            <span>•</span>
            <span>${employee.email || 'No email'}</span>
            ${supervisorBadge ? '<span>•</span>' + supervisorBadge : ''}
        </div>
    `;

    item.addEventListener('click', function() {
        window.location.href = `/employees?highlight=${employee.id}`;
    });

    return item;
}

function createScheduleResultItem(schedule) {
    const item = document.createElement('div');
    item.className = 'search-result-item';

    const scheduleDate = new Date(schedule.schedule_datetime);
    const dateStr = scheduleDate.toLocaleDateString();
    const timeStr = scheduleDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    item.innerHTML = `
        <div class="search-result-title">
            📅 ${schedule.event_name}
        </div>
        <div class="search-result-details">
            <span>👤 ${schedule.employee_name}</span>
            <span>•</span>
            <span>${dateStr} ${timeStr}</span>
            <span>•</span>
            <span>${schedule.event_type}</span>
        </div>
    `;

    item.addEventListener('click', function() {
        window.location.href = `/calendar?date=${scheduleDate.toISOString().split('T')[0]}`;
    });

    return item;
}

function getPriorityIcon(priority) {
    switch (priority) {
        case 'critical':
            return '🔴';
        case 'urgent':
            return '🟡';
        case 'normal':
            return '🟢';
        default:
            return '⚪';
    }
}

function hideSearchResults() {
    const resultsContainer = document.getElementById('search-results');
    if (resultsContainer) {
        resultsContainer.style.display = 'none';
        searchResultsVisible = false;
    }
}

function showSearchError(message) {
    const resultsContainer = document.getElementById('search-results');
    if (resultsContainer) {
        resultsContainer.innerHTML = `
            <div class="search-result-section">
                <p style="text-align: center; padding: var(--spacing-md); color: var(--error-color);">
                    ${message}
                </p>
            </div>
        `;
        resultsContainer.style.display = 'block';
        searchResultsVisible = true;
    }
}
