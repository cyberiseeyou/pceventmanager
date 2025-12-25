/**
 * Trade Modal Component (Stories 3.8 & 3.9)
 *
 * Modal for trading events between employees on same day or different days
 * Includes cross-day trading functionality with date picker
 */

class TradeModal {
    constructor(scheduleData) {
        this.sourceScheduleId = scheduleData.schedule_id;
        this.sourceEmployeeName = scheduleData.employee_name;
        this.sourceEventName = scheduleData.event_name;
        this.sourceDateTime = scheduleData.datetime;
        this.sourceDate = scheduleData.date; // Current date from daily view
        this.modalElement = null;
        this.selectedTargetScheduleId = null;

        // NEW for Story 3.9: Cross-day mode
        this.tradeModeIsCrossDay = false;  // Toggle between same-day and cross-day
        this.targetDate = this.sourceDate; // Initially same as source date
    }

    /**
     * Open the trade modal
     */
    open() {
        this.render();
        this.attachEventListeners();
        this.modalElement.classList.add('modal-open');
        document.body.style.overflow = 'hidden';
    }

    /**
     * Render modal HTML
     * Includes cross-day mode toggle and date picker
     */
    render() {
        // Date picker section (only shown in cross-day mode)
        const datePicker = this.tradeModeIsCrossDay ? `
            <div class="date-picker-section">
                <label for="target-date-picker" class="form-label">Select Target Date:</label>
                <input type="date"
                       id="target-date-picker"
                       class="form-date-input"
                       value="${this.targetDate}"
                       aria-label="Select target date for trade">
                <p class="form-help">Choose the date with the event you want to trade with</p>
            </div>
        ` : '';

        const modalHTML = `
            <div class="modal trade-modal" id="trade-modal">
                <div class="modal-overlay"></div>
                <div class="modal-container">
                    <div class="modal-header">
                        <h2 class="modal-title">Trade Event Assignment</h2>
                        <button class="modal-close" aria-label="Close modal">×</button>
                    </div>

                    <div class="modal-body">
                        <!-- Source Event Display -->
                        <div class="source-event-display">
                            <h3 class="section-label">Current Event:</h3>
                            <div class="event-summary">
                                <div class="event-employee">👤 ${this.sourceEmployeeName}</div>
                                <div class="event-details">
                                    <div class="event-time">⏰ ${this.formatDateTime(this.sourceDateTime)}</div>
                                    <div class="event-name">${this.sourceEventName}</div>
                                </div>
                            </div>
                        </div>

                        <div class="section-divider"></div>

                        <!-- Cross-Day Toggle -->
                        <div class="trade-mode-toggle">
                            <button type="button"
                                    class="btn-toggle ${!this.tradeModeIsCrossDay ? 'active' : ''}"
                                    id="btn-same-day-mode"
                                    aria-pressed="${!this.tradeModeIsCrossDay}">
                                Trade on Same Day
                            </button>
                            <button type="button"
                                    class="btn-toggle ${this.tradeModeIsCrossDay ? 'active' : ''}"
                                    id="btn-cross-day-mode"
                                    aria-pressed="${this.tradeModeIsCrossDay}">
                                Trade on Different Date
                            </button>
                        </div>

                        <!-- Date Picker (conditionally rendered) -->
                        ${datePicker}

                        <!-- Target Events List -->
                        <div class="target-events-section">
                            <h3 class="section-label">
                                ${this.tradeModeIsCrossDay ?
                                    `Events on ${this.formatDate(this.targetDate)}:` :
                                    'Other Events Today:'}
                            </h3>

                            <div id="target-events-list" class="target-events-list">
                                <div class="loading-spinner" role="status">
                                    <span class="sr-only">Loading events...</span>
                                    Loading events...
                                </div>
                            </div>
                        </div>

                        <!-- Conflict Display Area -->
                        <div id="trade-conflicts" class="conflicts-container" style="display:none;" role="alert"></div>

                        <!-- Error Display -->
                        <div id="trade-error" class="error-message" style="display:none;" role="alert"></div>
                    </div>

                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" id="btn-cancel-trade">Cancel</button>
                        <button type="button" class="btn btn-primary" id="btn-execute-trade" disabled>
                            Execute Trade
                        </button>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if present
        const existingModal = document.getElementById('trade-modal');
        if (existingModal) existingModal.remove();

        // Insert new modal
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        this.modalElement = document.getElementById('trade-modal');

        // Load target events for initial date
        this.loadTargetEvents(this.targetDate);
    }

    /**
     * Attach event listeners
     */
    attachEventListeners() {
        // Close handlers
        const closeBtn = this.modalElement.querySelector('.modal-close');
        const cancelBtn = this.modalElement.querySelector('#btn-cancel-trade');
        const overlay = this.modalElement.querySelector('.modal-overlay');
        const executeBtn = this.modalElement.querySelector('#btn-execute-trade');

        const closeModal = () => this.close();
        closeBtn.addEventListener('click', closeModal);
        cancelBtn.addEventListener('click', closeModal);
        overlay.addEventListener('click', closeModal);

        // Escape key handler
        const handleEscape = (e) => {
            if (e.key === 'Escape') closeModal();
        };
        document.addEventListener('keydown', handleEscape);
        this.modalElement._escapeHandler = handleEscape;

        // Execute trade button
        executeBtn.addEventListener('click', () => this.executeTrade());

        // Mode toggle buttons
        const sameDayBtn = this.modalElement.querySelector('#btn-same-day-mode');
        const crossDayBtn = this.modalElement.querySelector('#btn-cross-day-mode');

        sameDayBtn.addEventListener('click', () => this.switchToSameDayMode());
        crossDayBtn.addEventListener('click', () => this.switchToCrossDayMode());

        // Date picker change handler (if in cross-day mode)
        if (this.tradeModeIsCrossDay) {
            const datePicker = this.modalElement.querySelector('#target-date-picker');
            if (datePicker) {
                datePicker.addEventListener('change', (e) => {
                    this.targetDate = e.target.value;
                    this.loadTargetEvents(this.targetDate);
                });
            }
        }
    }

    /**
     * Switch to same-day trade mode
     */
    switchToSameDayMode() {
        if (!this.tradeModeIsCrossDay) return; // Already in same-day mode

        this.tradeModeIsCrossDay = false;
        this.targetDate = this.sourceDate;
        this.selectedTargetScheduleId = null;

        // Re-render modal
        this.render();
        this.attachEventListeners();
    }

    /**
     * Switch to cross-day trade mode
     */
    switchToCrossDayMode() {
        if (this.tradeModeIsCrossDay) return; // Already in cross-day mode

        this.tradeModeIsCrossDay = true;
        this.targetDate = this.sourceDate; // Start with same date
        this.selectedTargetScheduleId = null;

        // Re-render modal
        this.render();
        this.attachEventListeners();
    }

    /**
     * Load target events for specified date
     *
     * @param {string} date - Date in YYYY-MM-DD format
     */
    async loadTargetEvents(date) {
        const eventsList = this.modalElement.querySelector('#target-events-list');
        const executeBtn = this.modalElement.querySelector('#btn-execute-trade');

        // Show loading state
        eventsList.innerHTML = `
            <div class="loading-spinner" role="status">
                <span class="sr-only">Loading events...</span>
                Loading events...
            </div>
        `;
        executeBtn.disabled = true;

        try {
            // Call daily events API endpoint
            const response = await fetch(`/api/daily-events/${date}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();

            // Filter out source event and only show Core events (only Core events can be traded)
            const targetEvents = data.events.filter(
                event => event.schedule_id !== this.sourceScheduleId && event.event_type === 'Core'
            );

            if (targetEvents.length === 0) {
                // Empty state
                eventsList.innerHTML = `
                    <div class="empty-state" role="status">
                        <p class="empty-state__icon">📭</p>
                        <p class="empty-state__message">
                            ${this.tradeModeIsCrossDay ?
                                'No Core events available for trade on this date' :
                                'No other Core events available for trade today'}
                        </p>
                        <p class="empty-state__help">Only Core events can be traded</p>
                    </div>
                `;
            } else {
                // Render event list
                this.renderTargetEvents(targetEvents);
            }

        } catch (error) {
            console.error('Failed to load target events:', error);
            eventsList.innerHTML = `
                <div class="error-message" role="alert">
                    <span class="icon">×</span>
                    Failed to load events. Please try again.
                </div>
            `;
        }
    }

    /**
     * Render target events list
     *
     * @param {Array} events - Array of event objects
     */
    renderTargetEvents(events) {
        const eventsList = this.modalElement.querySelector('#target-events-list');

        const eventsHTML = events.map(event => `
            <div class="target-event-card"
                 data-schedule-id="${event.schedule_id}"
                 role="radio"
                 aria-checked="false"
                 tabindex="0">
                <div class="event-card-header">
                    <div class="event-employee">👤 ${event.employee_name}</div>
                    <div class="event-time">⏰ ${event.start_time}</div>
                </div>
                <div class="event-card-body">
                    <div class="event-name">${event.event_name}</div>
                    ${event.location ? `<div class="event-location">📍 ${event.location}</div>` : ''}
                </div>
                <div class="event-selection-indicator" aria-hidden="true">
                    <span class="checkmark">✓</span>
                </div>
            </div>
        `).join('');

        eventsList.innerHTML = eventsHTML;

        // Attach selection handlers
        this.attachEventSelectionHandlers();
    }

    /**
     * Attach event selection handlers
     */
    attachEventSelectionHandlers() {
        const eventCards = this.modalElement.querySelectorAll('.target-event-card');

        eventCards.forEach(card => {
            // Click handler
            card.addEventListener('click', () => {
                this.selectTargetEvent(card);
            });

            // Keyboard handler
            card.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    this.selectTargetEvent(card);
                }
            });
        });
    }

    /**
     * Select target event for trade
     *
     * @param {HTMLElement} card - Selected event card element
     */
    selectTargetEvent(card) {
        const executeBtn = this.modalElement.querySelector('#btn-execute-trade');

        // Deselect all other cards
        this.modalElement.querySelectorAll('.target-event-card').forEach(c => {
            c.classList.remove('selected');
            c.setAttribute('aria-checked', 'false');
        });

        // Select this card
        card.classList.add('selected');
        card.setAttribute('aria-checked', 'true');

        // Store selected schedule ID
        this.selectedTargetScheduleId = parseInt(card.getAttribute('data-schedule-id'));

        // Enable execute button
        executeBtn.disabled = false;

        // Clear any previous conflicts
        this.clearConflicts();
    }

    /**
     * Clear conflict display
     */
    clearConflicts() {
        const conflictsDiv = this.modalElement.querySelector('#trade-conflicts');
        const errorDiv = this.modalElement.querySelector('#trade-error');
        conflictsDiv.style.display = 'none';
        errorDiv.style.display = 'none';
    }

    /**
     * Execute trade
     * Works for both same-day and cross-day trades
     */
    async executeTrade() {
        if (!this.selectedTargetScheduleId) {
            console.error('No target event selected');
            return;
        }

        const executeBtn = this.modalElement.querySelector('#btn-execute-trade');
        const originalText = executeBtn.textContent;

        try {
            // Show loading state
            executeBtn.disabled = true;
            executeBtn.textContent = 'Trading...';

            // Call trade API (same endpoint for same-day and cross-day)
            const response = await fetch('/api/trade-events', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify({
                    schedule_1_id: this.sourceScheduleId,
                    schedule_2_id: this.selectedTargetScheduleId
                })
            });

            const result = await response.json();

            if (response.status === 409) {
                // Conflict detected
                this.displayConflicts(result.conflicts);
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
            this.close();

            // Reload page to show updated assignments
            setTimeout(() => {
                location.reload();
            }, 1000);

        } catch (error) {
            console.error('Failed to execute trade:', error);
            this.displayError(error.message || 'Failed to execute trade. Please try again.');
            executeBtn.disabled = false;
            executeBtn.textContent = originalText;
        }
    }

    /**
     * Display conflict errors
     *
     * @param {Array} conflicts - Array of conflict objects
     */
    displayConflicts(conflicts) {
        const conflictsDiv = this.modalElement.querySelector('#trade-conflicts');
        const errorDiv = this.modalElement.querySelector('#trade-error');

        // Hide general error
        errorDiv.style.display = 'none';

        const conflictHTML = conflicts.map(conflict => `
            <div class="conflict-item conflict-${conflict.severity}">
                <span class="conflict-icon">⚠️</span>
                <div class="conflict-content">
                    <strong>${conflict.message}</strong>
                    ${conflict.details ? `<p class="conflict-detail">${this.formatConflictDetails(conflict.details)}</p>` : ''}
                </div>
            </div>
        `).join('');

        conflictsDiv.innerHTML = `
            <h4 class="conflicts-title">Trade Conflicts Detected:</h4>
            ${conflictHTML}
            <p class="conflicts-help">Please select a different event or resolve the conflicts first.</p>
        `;
        conflictsDiv.style.display = 'block';
    }

    /**
     * Display general error
     *
     * @param {string} message - Error message
     */
    displayError(message) {
        const errorDiv = this.modalElement.querySelector('#trade-error');
        const conflictsDiv = this.modalElement.querySelector('#trade-conflicts');

        // Hide conflicts
        conflictsDiv.style.display = 'none';

        errorDiv.innerHTML = `<span class="icon">×</span> ${message}`;
        errorDiv.style.display = 'block';
    }

    /**
     * Format conflict details for display
     *
     * @param {object} details - Conflict details object
     * @returns {string} Formatted details
     */
    formatConflictDetails(details) {
        if (!details) return '';

        const parts = [];
        if (details.date) parts.push(`Date: ${details.date}`);
        if (details.time) parts.push(`Time: ${details.time}`);
        if (details.detail) parts.push(details.detail);

        return parts.join(' | ');
    }

    /**
     * Close modal
     */
    close() {
        if (!this.modalElement) return;

        // Remove event listeners
        if (this.modalElement._escapeHandler) {
            document.removeEventListener('keydown', this.modalElement._escapeHandler);
        }

        // Hide modal
        this.modalElement.classList.remove('modal-open');
        document.body.style.overflow = '';

        // Remove from DOM after animation
        setTimeout(() => {
            this.modalElement.remove();
            this.modalElement = null;
        }, 200);
    }

    /**
     * Format datetime for display
     *
     * @param {string} datetimeStr - ISO datetime string
     * @returns {string} Formatted datetime
     */
    formatDateTime(datetimeStr) {
        const date = new Date(datetimeStr);
        const options = {
            weekday: 'short',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        };
        return date.toLocaleString('en-US', options);
    }

    /**
     * Format date for display
     *
     * @param {string} dateStr - Date string (YYYY-MM-DD)
     * @returns {string} Formatted date (e.g., "Oct 16, 2025")
     */
    formatDate(dateStr) {
        const date = new Date(dateStr + 'T00:00:00');
        const options = { year: 'numeric', month: 'short', day: 'numeric' };
        return date.toLocaleDateString('en-US', options);
    }

    /**
     * Show toast notification
     *
     * @param {string} message - Notification message
     * @param {string} type - Notification type (success, error, info)
     */
    showNotification(message, type = 'info') {
        if (window.toast) {
            window.toast.show(message, type);
            return;
        }

        // Fallback notification
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 24px;
            background: ${type === 'success' ? '#10B981' : type === 'error' ? '#DC2626' : '#3B82F6'};
            color: white;
            border-radius: 4px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            z-index: 10000;
        `;
        document.body.appendChild(notification);
        setTimeout(() => notification.remove(), 3000);
    }

    /**
     * Get CSRF token
     *
     * @returns {string} CSRF token
     */
    getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.content || '';
    }
}

// Export for use in other modules
window.TradeModal = TradeModal;
