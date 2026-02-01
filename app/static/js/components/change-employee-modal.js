/**
 * Change Employee Modal Component (Story 3.7)
 *
 * Modal for changing employee assignment with conflict validation
 */

class ChangeEmployeeModal {
    constructor(scheduleData) {
        this.scheduleId = scheduleData.schedule_id;
        this.currentEmployeeName = scheduleData.employee_name;
        this.currentEmployeeId = scheduleData.employee_id;
        this.eventName = scheduleData.event_name;
        this.eventDateTime = scheduleData.datetime;
        this.eventDate = scheduleData.date;
        this.eventType = scheduleData.event_type;
        this.modalElement = null;
        this.selectedEmployeeId = null;
    }

    /**
     * Open the change employee modal
     */
    open() {
        this.render();
        this.attachEventListeners();
        this.loadAvailableEmployees();
        this.modalElement.classList.add('modal-open');
        document.body.style.overflow = 'hidden';
    }

    /**
     * Render modal HTML
     */
    render() {
        const modalHTML = `
            <div class="modal change-employee-modal" id="change-employee-modal">
                <div class="modal-overlay"></div>
                <div class="modal-container">
                    <div class="modal-header">
                        <h2 class="modal-title">Change Employee Assignment</h2>
                        <button class="modal-close" aria-label="Close modal">×</button>
                    </div>

                    <div class="modal-body">
                        <!-- Current Assignment Display -->
                        <div class="current-assignment-display">
                            <h3 class="section-label">Current Assignment:</h3>
                            <div class="assignment-summary">
                                <div class="assignment-employee">👤 ${this.currentEmployeeName}</div>
                                <div class="assignment-details">
                                    <div class="assignment-time">⏰ ${this.formatDateTime(this.eventDateTime)}</div>
                                    <div class="assignment-event">${this.eventName}</div>
                                </div>
                            </div>
                        </div>

                        <div class="section-divider"></div>

                        <!-- Available Employees List -->
                        <div class="available-employees-section">
                            <h3 class="section-label">Select New Employee:</h3>
                            <div id="available-employees-list" class="available-employees-list">
                                <div class="loading-spinner" role="status">
                                    <span class="sr-only">Loading employees...</span>
                                    Loading available employees...
                                </div>
                            </div>
                        </div>

                        <!-- Conflict Display Area -->
                        <div id="change-employee-conflicts" class="conflicts-container" style="display:none;" role="alert"></div>

                        <!-- Error Display -->
                        <div id="change-employee-error" class="error-message" style="display:none;" role="alert"></div>
                    </div>

                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" id="btn-cancel-change">Cancel</button>
                        <button type="button" class="btn btn-primary" id="btn-confirm-change" disabled>
                            Change Employee
                        </button>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if present
        const existingModal = document.getElementById('change-employee-modal');
        if (existingModal) existingModal.remove();

        // Insert new modal
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        this.modalElement = document.getElementById('change-employee-modal');
    }

    /**
     * Attach event listeners
     */
    attachEventListeners() {
        // Close handlers
        const closeBtn = this.modalElement.querySelector('.modal-close');
        const cancelBtn = this.modalElement.querySelector('#btn-cancel-change');
        const overlay = this.modalElement.querySelector('.modal-overlay');
        const confirmBtn = this.modalElement.querySelector('#btn-confirm-change');

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

        // Confirm change button
        confirmBtn.addEventListener('click', () => this.executeChange());
    }

    /**
     * Load available employees from API
     */
    async loadAvailableEmployees() {
        const employeesList = this.modalElement.querySelector('#available-employees-list');
        const confirmBtn = this.modalElement.querySelector('#btn-confirm-change');
        const apiUrl = `/api/available_employees_for_change/${this.eventDate}/${this.eventType}`;

        // Debug logging
        console.log('[ChangeEmployeeModal] Loading employees from:', apiUrl);

        try {
            const response = await fetch(apiUrl);

            console.log('[ChangeEmployeeModal] Response status:', response.status);

            // Parse JSON response first to get error details
            const data = await response.json();

            console.log('[ChangeEmployeeModal] Response data:', data);

            // Check if response is an error object (not an array)
            if (!response.ok) {
                // Extract error message from response body
                const errorMessage = data.error || data.message || `HTTP ${response.status}: ${response.statusText}`;
                throw new Error(errorMessage);
            }

            // Validate that we received an array
            if (!Array.isArray(data)) {
                console.error('[ChangeEmployeeModal] Expected array but got:', typeof data, data);
                throw new Error(data.error || 'Invalid response format from server');
            }

            const employees = data;

            // Filter out current employee
            const availableEmployees = employees.filter(emp => emp.id !== this.currentEmployeeId);

            if (availableEmployees.length === 0) {
                employeesList.innerHTML = `
                    <div class="empty-state" role="status">
                        <p class="empty-state__icon">📭</p>
                        <p class="empty-state__message">No other available employees for this event type and date</p>
                    </div>
                `;
            } else {
                this.renderEmployeeList(availableEmployees);
            }

        } catch (error) {
            console.error('[ChangeEmployeeModal] Failed to load available employees:', error);
            // Display the actual error message to help with debugging
            const errorText = error.message || 'Failed to load employees. Please try again.';
            employeesList.innerHTML = `
                <div class="error-message" role="alert">
                    <span class="icon">×</span>
                    ${this._escapeHtml(errorText)}
                </div>
            `;
        }
    }

    /**
     * Render employee list
     *
     * @param {Array} employees - Array of employee objects
     */
    renderEmployeeList(employees) {
        const employeesList = this.modalElement.querySelector('#available-employees-list');

        const employeesHTML = employees.map(employee => `
            <div class="employee-card"
                 data-employee-id="${employee.id}"
                 role="radio"
                 aria-checked="false"
                 tabindex="0">
                <div class="employee-card-header">
                    <div class="employee-name">👤 ${employee.name}</div>
                    <div class="employee-role">${employee.job_title || ''}</div>
                </div>
                <div class="employee-selection-indicator" aria-hidden="true">
                    <span class="checkmark">✓</span>
                </div>
            </div>
        `).join('');

        employeesList.innerHTML = employeesHTML;

        // Attach selection handlers
        this.attachEmployeeSelectionHandlers();
    }

    /**
     * Attach employee selection handlers
     */
    attachEmployeeSelectionHandlers() {
        const employeeCards = this.modalElement.querySelectorAll('.employee-card');
        const confirmBtn = this.modalElement.querySelector('#btn-confirm-change');

        employeeCards.forEach(card => {
            // Click handler
            card.addEventListener('click', () => {
                this.selectEmployee(card);
            });

            // Keyboard handler
            card.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    this.selectEmployee(card);
                }
            });
        });
    }

    /**
     * Select an employee
     *
     * @param {HTMLElement} card - Selected employee card element
     */
    selectEmployee(card) {
        const confirmBtn = this.modalElement.querySelector('#btn-confirm-change');

        // Deselect all other cards
        this.modalElement.querySelectorAll('.employee-card').forEach(c => {
            c.classList.remove('selected');
            c.setAttribute('aria-checked', 'false');
        });

        // Select this card
        card.classList.add('selected');
        card.setAttribute('aria-checked', 'true');

        // Store selected employee ID
        this.selectedEmployeeId = card.getAttribute('data-employee-id');

        // Enable confirm button
        confirmBtn.disabled = false;

        // Clear any previous conflicts
        this.clearConflicts();
    }

    /**
     * Clear conflict display
     */
    clearConflicts() {
        const conflictsDiv = this.modalElement.querySelector('#change-employee-conflicts');
        const errorDiv = this.modalElement.querySelector('#change-employee-error');
        conflictsDiv.style.display = 'none';
        errorDiv.style.display = 'none';
    }

    /**
     * Execute employee change operation
     */
    async executeChange() {
        if (!this.selectedEmployeeId) {
            console.error('No employee selected');
            return;
        }

        const confirmBtn = this.modalElement.querySelector('#btn-confirm-change');
        const originalText = confirmBtn.textContent;

        try {
            // Show loading state
            confirmBtn.disabled = true;
            confirmBtn.textContent = 'Changing...';

            // Call change employee API
            const response = await fetch(`/api/event/${this.scheduleId}/change-employee`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify({
                    new_employee_id: this.selectedEmployeeId
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
                throw new Error(result.error || 'Failed to change employee');
            }

            // Success
            this.showNotification('Employee changed successfully', 'success');

            // Close modal
            this.close();

            // Reload page to show updated assignment
            setTimeout(() => {
                location.reload();
            }, 1000);

        } catch (error) {
            console.error('Failed to change employee:', error);
            this.displayError(error.message || 'Failed to change employee. Please try again.');
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
        const conflictsDiv = this.modalElement.querySelector('#change-employee-conflicts');
        const errorDiv = this.modalElement.querySelector('#change-employee-error');

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
            <h4 class="conflicts-title">Employee Change Conflicts Detected:</h4>
            ${conflictHTML}
            <p class="conflicts-help">Please select a different employee or resolve the conflicts first.</p>
        `;
        conflictsDiv.style.display = 'block';
    }

    /**
     * Display general error
     *
     * @param {string} message - Error message
     */
    displayError(message) {
        const errorDiv = this.modalElement.querySelector('#change-employee-error');
        const conflictsDiv = this.modalElement.querySelector('#change-employee-conflicts');

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

    /**
     * Escape HTML to prevent XSS
     *
     * @param {string} text - Text to escape
     * @returns {string} Escaped text
     * @private
     */
    _escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Export for use in other modules
window.ChangeEmployeeModal = ChangeEmployeeModal;
