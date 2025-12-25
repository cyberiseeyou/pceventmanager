/**
 * Reschedule Modal Component (Story 3.6)
 *
 * Modal for rescheduling events with date/time picker and conflict validation
 */

class RescheduleModal {
    constructor(scheduleData) {
        this.scheduleId = scheduleData.schedule_id;
        this.employeeName = scheduleData.employee_name;
        this.eventName = scheduleData.event_name;
        this.currentDateTime = scheduleData.datetime;
        this.currentDate = scheduleData.date;
        this.eventType = scheduleData.event_type;
        this.validDateRange = scheduleData.valid_date_range; // {start: 'YYYY-MM-DD', end: 'YYYY-MM-DD'}
        this.modalElement = null;
    }

    /**
     * Open the reschedule modal
     */
    open() {
        this.render();
        this.attachEventListeners();
        this.modalElement.classList.add('modal-open');
        document.body.style.overflow = 'hidden';
    }

    /**
     * Render modal HTML
     */
    render() {
        const modalHTML = `
            <div class="modal reschedule-modal" id="reschedule-modal">
                <div class="modal-overlay"></div>
                <div class="modal-container">
                    <div class="modal-header">
                        <h2 class="modal-title">Reschedule Event</h2>
                        <button class="modal-close" aria-label="Close modal">×</button>
                    </div>

                    <div class="modal-body">
                        <!-- Current Event Display -->
                        <div class="current-event-display">
                            <h3 class="section-label">Current Schedule:</h3>
                            <div class="event-summary">
                                <div class="event-employee">👤 ${this.employeeName}</div>
                                <div class="event-details">
                                    <div class="event-time">⏰ ${this.formatDateTime(this.currentDateTime)}</div>
                                    <div class="event-name">${this.eventName}</div>
                                </div>
                            </div>
                        </div>

                        <div class="section-divider"></div>

                        <!-- New Date/Time Picker -->
                        <div class="datetime-picker-section">
                            <h3 class="section-label">New Date & Time:</h3>

                            <div class="form-row">
                                <div class="form-group">
                                    <label for="new-date" class="form-label">Date</label>
                                    <input type="date"
                                           id="new-date"
                                           class="form-date-input"
                                           min="${this.validDateRange?.start || ''}"
                                           max="${this.validDateRange?.end || ''}"
                                           value="${this.currentDate}"
                                           aria-label="Select new date"
                                           required>
                                    <p class="form-help">Event must be scheduled within valid date range</p>
                                </div>

                                <div class="form-group">
                                    <label for="new-time" class="form-label">Time</label>
                                    <input type="time"
                                           id="new-time"
                                           class="form-time-input"
                                           value="${this.extractTime(this.currentDateTime)}"
                                           aria-label="Select new time"
                                           required>
                                    <p class="form-help">Select the start time for the event</p>
                                </div>
                            </div>
                        </div>

                        <!-- Conflict Display Area -->
                        <div id="reschedule-conflicts" class="conflicts-container" style="display:none;" role="alert"></div>

                        <!-- Error Display -->
                        <div id="reschedule-error" class="error-message" style="display:none;" role="alert"></div>
                    </div>

                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" id="btn-cancel-reschedule">Cancel</button>
                        <button type="button" class="btn btn-primary" id="btn-confirm-reschedule">
                            Reschedule Event
                        </button>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if present
        const existingModal = document.getElementById('reschedule-modal');
        if (existingModal) existingModal.remove();

        // Insert new modal
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        this.modalElement = document.getElementById('reschedule-modal');
    }

    /**
     * Attach event listeners
     */
    attachEventListeners() {
        // Close handlers
        const closeBtn = this.modalElement.querySelector('.modal-close');
        const cancelBtn = this.modalElement.querySelector('#btn-cancel-reschedule');
        const overlay = this.modalElement.querySelector('.modal-overlay');
        const confirmBtn = this.modalElement.querySelector('#btn-confirm-reschedule');

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

        // Confirm reschedule button
        confirmBtn.addEventListener('click', () => this.executeReschedule());

        // Real-time validation on date/time change
        const dateInput = this.modalElement.querySelector('#new-date');
        const timeInput = this.modalElement.querySelector('#new-time');

        dateInput.addEventListener('change', () => this.clearConflicts());
        timeInput.addEventListener('change', () => this.clearConflicts());
    }

    /**
     * Clear conflict display
     */
    clearConflicts() {
        const conflictsDiv = this.modalElement.querySelector('#reschedule-conflicts');
        const errorDiv = this.modalElement.querySelector('#reschedule-error');
        conflictsDiv.style.display = 'none';
        errorDiv.style.display = 'none';
    }

    /**
     * Execute reschedule operation
     */
    async executeReschedule() {
        const confirmBtn = this.modalElement.querySelector('#btn-confirm-reschedule');
        const originalText = confirmBtn.textContent;

        try {
            // Get new date and time values
            const newDate = this.modalElement.querySelector('#new-date').value;
            const newTime = this.modalElement.querySelector('#new-time').value;

            // Validate inputs
            if (!newDate || !newTime) {
                this.displayError('Please select both date and time');
                return;
            }

            // Show loading state
            confirmBtn.disabled = true;
            confirmBtn.textContent = 'Rescheduling...';

            // Call reschedule API
            const response = await fetch(`/api/event/${this.scheduleId}/reschedule`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify({
                    new_date: newDate,
                    new_time: newTime
                })
            });

            const result = await response.json();

            if (response.status === 409) {
                // Conflict detected
                this.displayConflicts(result.conflicts);
                confirmBtn.disabled = false;
                confirmBtn.textContent = originalText;
                return;
            }

            if (!response.ok) {
                throw new Error(result.error || 'Failed to reschedule event');
            }

            // Success
            this.showNotification('Event rescheduled successfully', 'success');

            // Close modal
            this.close();

            // Reload page to show updated schedule
            setTimeout(() => {
                location.reload();
            }, 1000);

        } catch (error) {
            console.error('Failed to reschedule event:', error);
            this.displayError(error.message || 'Failed to reschedule event. Please try again.');
            confirmBtn.disabled = false;
            confirmBtn.textContent = originalText;
        }
    }

    /**
     * Display conflict errors
     *
     * @param {Array} conflicts - Array of conflict objects
     */
    displayConflicts(conflicts) {
        const conflictsDiv = this.modalElement.querySelector('#reschedule-conflicts');
        const errorDiv = this.modalElement.querySelector('#reschedule-error');

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
            <h4 class="conflicts-title">Reschedule Conflicts Detected:</h4>
            ${conflictHTML}
            <p class="conflicts-help">Please select a different date/time or resolve the conflicts first.</p>
        `;
        conflictsDiv.style.display = 'block';
    }

    /**
     * Display general error
     *
     * @param {string} message - Error message
     */
    displayError(message) {
        const errorDiv = this.modalElement.querySelector('#reschedule-error');
        const conflictsDiv = this.modalElement.querySelector('#reschedule-conflicts');

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
     * Extract time from datetime string
     *
     * @param {string} datetimeStr - ISO datetime string
     * @returns {string} Time in HH:MM format
     */
    extractTime(datetimeStr) {
        const date = new Date(datetimeStr);
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${hours}:${minutes}`;
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
window.RescheduleModal = RescheduleModal;
