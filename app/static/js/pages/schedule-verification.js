/**
 * Schedule Verification Page Controller
 *
 * Handles schedule verification UI and API interaction.
 * Runs 8 validation rules to identify scheduling issues proactively.
 */

class ScheduleVerification {
    constructor() {
        this.resultsContainer = document.getElementById('verification-results');
        this.emptyState = document.getElementById('empty-state');
        this.dateInput = document.getElementById('verify-date');
        this.verifyBtn = document.getElementById('btn-verify');

        // Check if elements were found
        if (!this.verifyBtn) {
            console.error('ScheduleVerification: btn-verify element not found');
            return;
        }
        if (!this.dateInput) {
            console.error('ScheduleVerification: verify-date element not found');
            return;
        }

        this.init();
        console.log('ScheduleVerification initialized successfully');
    }

    init() {
        // Attach event listeners
        this.verifyBtn.addEventListener('click', (e) => {
            e.preventDefault();
            console.log('Verify button clicked');
            this.handleVerify();
        });

        // Allow Enter key to trigger verification
        this.dateInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.handleVerify();
            }
        });
    }

    /**
     * Handle verify button click
     */
    async handleVerify() {
        const date = this.dateInput.value;

        if (!date) {
            this.showNotification('Please select a date', 'error');
            return;
        }

        // Show loading state
        this.showLoading();
        this.emptyState.style.display = 'none';
        this.resultsContainer.classList.remove('results-hidden');

        try {
            // Call verification API
            const response = await fetch('/api/verify-schedule', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'same-origin',
                body: JSON.stringify({ date })
            });

            // Check if redirected to login
            if (response.redirected) {
                window.location.href = response.url;
                return;
            }

            // Check content type before parsing
            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                throw new Error('Session expired. Please refresh the page and try again.');
            }

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to verify schedule');
            }

            const result = await response.json();
            console.log('[Schedule Verification] API Response:', result);

            // Display results
            this.displayResults(result);

        } catch (error) {
            console.error('Verification error:', error);
            this.showError(error.message || 'Failed to verify schedule. Please try again.');
        }
    }

    /**
     * Show loading spinner
     */
    showLoading() {
        this.resultsContainer.innerHTML = `
            <div class="loading-spinner">
                <div class="spinner"></div>
                <p>Running verification checks...</p>
            </div>
        `;
    }

    /**
     * Display verification results
     *
     * @param {Object} result - Verification result from API
     */
    displayResults(result) {
        console.log('[Schedule Verification] displayResults called with:', result);

        if (!result) {
            console.error('[Schedule Verification] Result is null/undefined');
            this.showError('No data received from server');
            return;
        }

        const { status, issues, summary } = result;
        console.log('[Schedule Verification] Status:', status, 'Issues:', issues?.length, 'Summary:', summary);

        // Build HTML
        let html = '';

        // Status Summary
        html += this.buildStatusSummary(status, summary);

        // Summary Stats
        html += this.buildSummaryStats(summary);

        // Issues List
        if (issues && issues.length > 0) {
            html += this.buildIssuesList(issues);
        } else {
            html += this.buildNoIssuesMessage();
        }

        console.log('[Schedule Verification] HTML built, length:', html.length);
        console.log('[Schedule Verification] resultsContainer:', this.resultsContainer);

        if (!this.resultsContainer) {
            console.error('[Schedule Verification] resultsContainer is null!');
            return;
        }

        this.resultsContainer.innerHTML = html;
        console.log('[Schedule Verification] HTML injected into container');

        // Ensure visibility - remove hidden class and show container
        this.resultsContainer.classList.remove('results-hidden');
        this.resultsContainer.style.display = 'block';

        // Hide empty state
        if (this.emptyState) {
            this.emptyState.style.display = 'none';
        }

        console.log('[Schedule Verification] Container visible:',
            !this.resultsContainer.classList.contains('results-hidden'),
            'Display:', getComputedStyle(this.resultsContainer).display);

        // Attach event listeners for toggle buttons
        this.attachToggleListeners();
    }

    /**
     * Build status summary section
     *
     * @param {string} status - Overall status (pass/warning/fail)
     * @param {Object} summary - Summary statistics
     * @returns {string} HTML string
     */
    buildStatusSummary(status, summary) {
        const statusConfig = {
            pass: {
                class: 'status-pass',
                icon: '✅',
                title: 'All Clear!',
                message: `Schedule for ${summary.date} looks good with no issues found.`
            },
            warning: {
                class: 'status-warning',
                icon: '⚠️',
                title: 'Warnings Found',
                message: `Found ${summary.warnings} warning(s) that should be addressed for ${summary.date}.`
            },
            fail: {
                class: 'status-fail',
                icon: '❌',
                title: 'Critical Issues Found',
                message: `Found ${summary.critical_issues} critical issue(s) that must be fixed for ${summary.date}.`
            }
        };

        const config = statusConfig[status] || statusConfig.warning;

        return `
            <div class="status-summary ${config.class}">
                <div class="status-icon">${config.icon}</div>
                <div class="status-content">
                    <h2>${config.title}</h2>
                    <p>${config.message}</p>
                </div>
            </div>
        `;
    }

    /**
     * Build summary statistics cards
     *
     * @param {Object} summary - Summary statistics
     * @returns {string} HTML string
     */
    buildSummaryStats(summary) {
        return `
            <div class="summary-stats">
                <div class="stat-card">
                    <div class="stat-label">Total Issues</div>
                    <div class="stat-value">${summary.total_issues}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Critical Issues</div>
                    <div class="stat-value" style="color: #f44336;">${summary.critical_issues}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Warnings</div>
                    <div class="stat-value" style="color: #ff9800;">${summary.warnings}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Total Events</div>
                    <div class="stat-value">${summary.total_events}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Total Employees</div>
                    <div class="stat-value">${summary.total_employees}</div>
                </div>
            </div>
        `;
    }

    /**
     * Build issues list section
     *
     * @param {Array} issues - Array of issue objects
     * @returns {string} HTML string
     */
    buildIssuesList(issues) {
        // Separate critical and warnings
        const criticalIssues = issues.filter(issue => issue.severity === 'critical');
        const warnings = issues.filter(issue => issue.severity === 'warning');

        let html = '<div class="issues-section">';

        // Critical Issues
        if (criticalIssues.length > 0) {
            html += '<h3>🔴 Critical Issues (Must Fix)</h3>';
            html += '<div class="issues-list">';
            criticalIssues.forEach(issue => {
                html += this.buildIssueCard(issue);
            });
            html += '</div>';
        }

        // Warnings
        if (warnings.length > 0) {
            html += '<h3 style="margin-top: 24px;">⚠️ Warnings (Should Address)</h3>';
            html += '<div class="issues-list">';
            warnings.forEach(issue => {
                html += this.buildIssueCard(issue);
            });
            html += '</div>';
        }

        html += '</div>';
        return html;
    }

    /**
     * Build a single issue card
     *
     * @param {Object} issue - Issue object
     * @returns {string} HTML string
     */
    buildIssueCard(issue) {
        const icon = this.getIssueIcon(issue.severity);
        const hasDetails = issue.details && Object.keys(issue.details).length > 0;

        return `
            <div class="issue-card severity-${issue.severity}">
                <div class="issue-header">
                    <div class="issue-icon">${icon}</div>
                    <div class="issue-content">
                        <div class="issue-rule">${issue.rule_name}</div>
                        <p class="issue-message">${this.escapeHtml(issue.message)}</p>
                        ${hasDetails ? `
                            <button class="issue-details-toggle" data-issue-id="${this.generateId()}">
                                Show Details
                            </button>
                            <div class="details-content" id="details-${this.generateId()}">
                                ${this.buildDetailsSection(issue.details)}
                            </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Build details section for an issue
     *
     * @param {Object} details - Issue details object
     * @returns {string} HTML string
     */
    buildDetailsSection(details) {
        let html = '<div class="issue-details">';

        // Handle swap suggestions specially
        if (details.swap_suggestions && details.swap_suggestions.length > 0) {
            html += '<strong>Suggested Shift Swaps:</strong><ul>';
            details.swap_suggestions.forEach(swap => {
                html += `<li>${this.escapeHtml(swap.suggestion)}</li>`;
            });
            html += '</ul>';
        }

        // Handle shift counts specially
        if (details.shift_counts) {
            html += '<strong>Shift Distribution:</strong><ul>';
            for (const [shift, count] of Object.entries(details.shift_counts)) {
                html += `<li>${shift}: ${count} events</li>`;
            }
            html += '</ul>';
        }

        // Display other details
        for (const [key, value] of Object.entries(details)) {
            // Skip already handled keys
            if (key === 'swap_suggestions' || key === 'shift_counts') continue;

            // Format key nicely
            const formattedKey = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

            // Format value
            let formattedValue;
            if (Array.isArray(value)) {
                formattedValue = value.join(', ');
            } else if (typeof value === 'object' && value !== null) {
                formattedValue = JSON.stringify(value, null, 2);
            } else {
                formattedValue = value;
            }

            html += `<div><strong>${formattedKey}:</strong> ${this.escapeHtml(String(formattedValue))}</div>`;
        }

        html += '</div>';
        return html;
    }

    /**
     * Build no issues message
     *
     * @returns {string} HTML string
     */
    buildNoIssuesMessage() {
        return `
            <div class="empty-state" style="padding: 40px 20px;">
                <div class="empty-state-icon">🎉</div>
                <p class="empty-state-message" style="font-size: 18px; color: #4caf50; font-weight: 600;">
                    Perfect! No issues found with this schedule.
                </p>
            </div>
        `;
    }

    /**
     * Get icon for issue severity
     *
     * @param {string} severity - Issue severity
     * @returns {string} Icon emoji
     */
    getIssueIcon(severity) {
        const icons = {
            critical: '🔴',
            warning: '⚠️',
            info: 'ℹ️'
        };
        return icons[severity] || '❓';
    }

    /**
     * Attach toggle listeners for details sections
     */
    attachToggleListeners() {
        document.querySelectorAll('.issue-details-toggle').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const detailsId = e.target.getAttribute('data-issue-id');
                const detailsDiv = e.target.nextElementSibling;

                if (detailsDiv && detailsDiv.classList.contains('details-content')) {
                    detailsDiv.classList.toggle('show');

                    if (detailsDiv.classList.contains('show')) {
                        e.target.textContent = 'Hide Details';
                    } else {
                        e.target.textContent = 'Show Details';
                    }
                }
            });
        });
    }

    /**
     * Show error message
     *
     * @param {string} message - Error message
     */
    showError(message) {
        this.resultsContainer.innerHTML = `
            <div class="status-summary status-fail">
                <div class="status-icon">❌</div>
                <div class="status-content">
                    <h2>Error</h2>
                    <p>${this.escapeHtml(message)}</p>
                </div>
            </div>
        `;
        this.resultsContainer.classList.remove('results-hidden');
    }

    /**
     * Show notification toast
     *
     * @param {string} message - Notification message
     * @param {string} type - Notification type (success, error, warning, info)
     */
    showNotification(message, type = 'info') {
        // Use global toast if available
        if (window.toast) {
            window.toast.show(message, type);
            return;
        }

        // Fallback: simple alert
        alert(message);
    }

    /**
     * Escape HTML to prevent XSS
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
     * Generate a unique ID
     *
     * @returns {string} Unique ID
     */
    generateId() {
        return `issue-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    }
}
