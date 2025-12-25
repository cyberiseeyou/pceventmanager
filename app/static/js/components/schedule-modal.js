/**
 * Schedule Modal Component
 *
 * Modal dialog for quickly scheduling events from the dashboard.
 * Extends base Modal class with scheduling form and validation.
 *
 * Epic 2, Story 2.1: Create Schedule Now Modal Component
 *
 * @module components/schedule-modal
 *
 * @example
 * import { ScheduleModal } from './schedule-modal.js';
 *
 * const eventData = {
 *   event_id: 606034,
 *   event_name: 'Walmart Core Demo',
 *   event_type: 'Core',
 *   location: 'Walmart #1234',
 *   duration: 120,
 *   date_needed: '2025-10-15'
 * };
 *
 * const modal = new ScheduleModal(eventData);
 * modal.render();
 */

import { Modal } from './modal.js';
import { ConflictValidator } from './conflict-validator.js';

/**
 * Schedule Modal Class
 * Specialized modal for scheduling events with validation
 */
export class ScheduleModal {
  /**
   * Create a schedule modal
   * @param {Object} eventData - Event information
   * @param {number} eventData.event_id - Event ID
   * @param {string} eventData.event_name - Event name
   * @param {string} eventData.event_type - Event type (Core, Juicer, etc.)
   * @param {string} [eventData.location] - Event location
   * @param {number} [eventData.duration=120] - Event duration in minutes
   * @param {string} [eventData.date_needed] - Suggested date (YYYY-MM-DD)
   */
  constructor(eventData) {
    this.eventData = eventData;
    this.modal = null;
    this.validator = null;
    this.formElement = null;
    this.validationState = {
      hasErrors: false,
      hasWarnings: false,
      isValidating: false
    };

    // Bind methods
    this._handleDateChange = this._handleDateChange.bind(this);
    this._handleFieldChange = this._handleFieldChange.bind(this);
    this._handleSubmit = this._handleSubmit.bind(this);
    this._handleCancel = this._handleCancel.bind(this);
  }

  /**
   * Render the modal
   * Creates modal content and opens it
   */
  render() {
    console.log('[ScheduleModal] Rendering for event:', this.eventData.event_id);

    // Create modal instance
    this.modal = new Modal({
      id: `schedule-modal-${this.eventData.event_id}`
    });

    // Generate form content
    const formContent = this._createFormContent();

    // Open modal
    this.modal.open(formContent, {
      title: `Schedule Event: ${this.eventData.event_name}`,
      size: 'medium',
      closeButton: true,
      onClose: () => this._cleanup()
    });

    // Wait for modal to be in DOM, then initialize
    requestAnimationFrame(() => {
      this._initializeForm();
    });
  }

  /**
   * Create form HTML content
   * @returns {string} HTML string
   * @private
   */
  _createFormContent() {
    const today = new Date().toISOString().split('T')[0];
    const defaultDate = this.eventData.date_needed || today;
    const defaultDuration = this.eventData.duration || 120;

    return `
      <form id="schedule-form-${this.eventData.event_id}" class="schedule-modal__form">
        <!-- Event Info (Read-only) -->
        <div class="form-group form-group--full">
          <label for="event-name">Event</label>
          <input type="text"
                 id="event-name"
                 value="${this._escapeHtml(this.eventData.event_name)}"
                 readonly
                 class="form-control form-control--readonly">
          ${this.eventData.location ? `<small class="form-text">${this._escapeHtml(this.eventData.location)}</small>` : ''}
        </div>

        <!-- Employee Dropdown -->
        <div class="form-group form-group--full">
          <label for="employee-id">
            Employee <span class="required" aria-label="required">*</span>
          </label>
          <select id="employee-id"
                  name="employee_id"
                  class="form-control"
                  aria-required="true"
                  disabled>
            <option value="">Loading employees...</option>
          </select>
          <div id="employee-loading" class="field-loading" style="display:none;">
            <span class="spinner-small"></span> Loading...
          </div>
          <div role="alert" aria-live="polite" class="validation-message" id="employee-validation"></div>
        </div>

        <!-- Date Picker -->
        <div class="form-group">
          <label for="scheduled-date">
            Date <span class="required" aria-label="required">*</span>
          </label>
          <input type="date"
                 id="scheduled-date"
                 name="scheduled_date"
                 value="${defaultDate}"
                 class="form-control"
                 aria-required="true"
                 required>
          <div role="alert" aria-live="polite" class="validation-message" id="date-validation"></div>
        </div>

        <!-- Time Picker -->
        <div class="form-group">
          <label for="start-time">
            Time <span class="required" aria-label="required">*</span>
          </label>
          <input type="time"
                 id="start-time"
                 name="start_time"
                 value=""
                 class="form-control"
                 aria-required="true"
                 required
                 placeholder="Loading...">
          <div role="alert" aria-live="polite" class="validation-message" id="time-validation"></div>
        </div>

        <!-- Duration -->
        <div class="form-group">
          <label for="duration">Duration (minutes)</label>
          <input type="number"
                 id="duration"
                 name="duration"
                 value="${defaultDuration}"
                 min="30"
                 max="480"
                 step="15"
                 class="form-control">
        </div>

        <!-- Validation Summary -->
        <div class="form-group form-group--full">
          <div id="validation-summary" class="validation-summary" style="display:none;" role="alert" aria-live="assertive"></div>
        </div>

        <!-- Form Actions -->
        <div class="modal__footer">
          <button type="button" id="btn-cancel" class="btn btn-secondary">
            Cancel
          </button>
          <button type="submit" id="btn-submit" class="btn btn-primary" disabled>
            <span class="btn-text">Schedule Event</span>
            <span class="btn-spinner" style="display:none;">⏳</span>
          </button>
        </div>
      </form>
    `;
  }

  /**
   * Initialize form after it's in the DOM
   * @private
   */
  _initializeForm() {
    // Get form element
    this.formElement = document.getElementById(`schedule-form-${this.eventData.event_id}`);

    if (!this.formElement) {
      console.error('[ScheduleModal] Form element not found');
      return;
    }

    // Initialize validator
    this.validator = new ConflictValidator();

    // Attach event listeners
    this._attachEventListeners();

    // Load default time from settings based on event type
    this._loadDefaultTime();

    // Load available employees for default date
    const dateInput = this.formElement.querySelector('#scheduled-date');
    this._loadAvailableEmployees(dateInput.value);
  }

  /**
   * Load default start time from settings based on event type
   * @private
   */
  async _loadDefaultTime() {
    const timeInput = this.formElement.querySelector('#start-time');

    try {
      console.log('[ScheduleModal] Loading default time for event type:', this.eventData.event_type);

      const response = await fetch(`/api/event-default-time/${encodeURIComponent(this.eventData.event_type)}`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();

      if (data.success && data.default_time) {
        timeInput.value = data.default_time;
        console.log('[ScheduleModal] Default time set to:', data.default_time);
      } else {
        // Fallback to 09:00
        timeInput.value = '09:00';
        console.log('[ScheduleModal] Using fallback time: 09:00');
      }
    } catch (error) {
      console.error('[ScheduleModal] Error loading default time:', error);
      // Fallback to 09:00
      timeInput.value = '09:00';
    }
  }

  /**
   * Attach event listeners to form fields
   * @private
   */
  _attachEventListeners() {
    // Date change triggers employee reload
    const dateInput = this.formElement.querySelector('#scheduled-date');
    dateInput.addEventListener('change', this._handleDateChange);

    // Field changes trigger validation
    const fieldIds = ['employee-id', 'scheduled-date', 'start-time', 'duration'];
    fieldIds.forEach(id => {
      const field = this.formElement.querySelector(`#${id}`);
      if (field) {
        field.addEventListener('change', this._handleFieldChange);
      }
    });

    // Form submission
    this.formElement.addEventListener('submit', this._handleSubmit);

    // Cancel button
    const cancelBtn = this.formElement.querySelector('#btn-cancel');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', this._handleCancel);
    }
  }

  /**
   * Handle date change (reload employees)
   * @param {Event} e - Change event
   * @private
   */
  async _handleDateChange(e) {
    const newDate = e.target.value;
    console.log('[ScheduleModal] Date changed to:', newDate);

    // Clear employee dropdown
    const employeeSelect = this.formElement.querySelector('#employee-id');
    employeeSelect.innerHTML = '<option value="">Loading employees...</option>';
    employeeSelect.disabled = true;

    // Reload employees
    await this._loadAvailableEmployees(newDate);

    // Re-validate if employee was selected
    if (employeeSelect.value) {
      this._validateForm();
    }
  }

  /**
   * Load available employees for a given date
   * @param {string} date - Date in YYYY-MM-DD format
   * @private
   */
  async _loadAvailableEmployees(date) {
    const employeeSelect = this.formElement.querySelector('#employee-id');
    const loadingIndicator = this.formElement.querySelector('#employee-loading');

    try {
      // Show loading
      if (loadingIndicator) {
        loadingIndicator.style.display = 'block';
      }

      console.log('[ScheduleModal] Loading employees for date:', date);

      // Fetch available employees
      const response = await fetch(`/api/available_employees_for_change/${date}/${this.eventData.event_type}`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const employees = await response.json();

      console.log('[ScheduleModal] Loaded', employees.length, 'employees');

      // Populate dropdown
      employeeSelect.innerHTML = '<option value="">Select Employee...</option>';

      if (employees.length === 0) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'No available employees';
        option.disabled = true;
        employeeSelect.appendChild(option);
      } else {
        employees.forEach(emp => {
          const option = document.createElement('option');
          option.value = emp.id;
          option.textContent = `${emp.name} (${emp.job_title || 'Unknown'})`;
          employeeSelect.appendChild(option);
        });
      }

      employeeSelect.disabled = false;

    } catch (error) {
      console.error('[ScheduleModal] Error loading employees:', error);
      employeeSelect.innerHTML = '<option value="">Error loading employees</option>';
      employeeSelect.disabled = true;
    } finally {
      // Hide loading
      if (loadingIndicator) {
        loadingIndicator.style.display = 'none';
      }
    }
  }

  /**
   * Handle field change (trigger validation)
   * @private
   */
  _handleFieldChange() {
    // Check if all required fields are filled
    if (this._areRequiredFieldsFilled()) {
      this._validateForm();
    } else {
      this._clearValidation();
      this._updateSubmitButton(true);
    }
  }

  /**
   * Check if all required fields are filled
   * @returns {boolean}
   * @private
   */
  _areRequiredFieldsFilled() {
    const employeeId = this.formElement.querySelector('#employee-id').value;
    const date = this.formElement.querySelector('#scheduled-date').value;
    const time = this.formElement.querySelector('#start-time').value;

    return employeeId && date && time;
  }

  /**
   * Validate form using ConflictValidator
   * @private
   */
  _validateForm() {
    const formData = {
      employee_id: this.formElement.querySelector('#employee-id').value,
      event_id: this.eventData.event_id,
      schedule_datetime: this._buildDateTimeString(),
      duration_minutes: parseInt(this.formElement.querySelector('#duration').value, 10)
    };

    console.log('[ScheduleModal] Validating:', formData);

    this.validator.validateSchedule(formData, (result) => {
      this._handleValidationResult(result);
    });
  }

  /**
   * Build ISO datetime string
   * @returns {string}
   * @private
   */
  _buildDateTimeString() {
    const date = this.formElement.querySelector('#scheduled-date').value;
    const time = this.formElement.querySelector('#start-time').value;
    return `${date}T${time}:00`;
  }

  /**
   * Handle validation result
   * @param {Object} result - Validation result
   * @private
   */
  _handleValidationResult(result) {
    if (result.loading) {
      this._showLoadingState();
      return;
    }

    if (result.error) {
      this._showErrorState(result.error);
      return;
    }

    this._showValidationResult(result);
  }

  /**
   * Show loading state
   * @private
   */
  _showLoadingState() {
    this.validationState.isValidating = true;

    const summary = this.formElement.querySelector('#validation-summary');
    summary.innerHTML = `
      <div class="validation-loading">
        <span class="spinner"></span>
        <span>Checking for conflicts...</span>
      </div>
    `;
    summary.style.display = 'block';
    summary.className = 'validation-summary validation-loading';

    this._updateSubmitButton(true);
  }

  /**
   * Show error state
   * @param {string} errorMessage - Error message
   * @private
   */
  _showErrorState(errorMessage) {
    this.validationState.isValidating = false;
    this.validationState.hasErrors = true;

    const summary = this.formElement.querySelector('#validation-summary');
    summary.innerHTML = `
      <div class="validation-error">
        <span class="icon icon-error">⚠</span>
        <span class="message">${this._escapeHtml(errorMessage)}</span>
      </div>
    `;
    summary.style.display = 'block';
    summary.className = 'validation-summary validation-error';

    this._updateSubmitButton(true);
  }

  /**
   * Show validation result
   * @param {Object} result - Validation result
   * @private
   */
  _showValidationResult(result) {
    this.validationState.isValidating = false;
    this.validationState.hasErrors = result.severity === 'error';
    this.validationState.hasWarnings = result.severity === 'warning';

    const summary = this.formElement.querySelector('#validation-summary');

    if (result.severity === 'success') {
      summary.innerHTML = `
        <div class="validation-success">
          <span class="icon icon-success">✓</span>
          <span class="message">No scheduling conflicts found</span>
        </div>
      `;
      summary.style.display = 'block';
      summary.className = 'validation-summary validation-success';
      this._updateSubmitButton(false);
    } else if (result.severity === 'warning') {
      const warningHtml = result.warnings.map(w => `
        <li>
          <strong>${this._escapeHtml(w.type)}:</strong> ${this._escapeHtml(w.message)}
          ${w.detail ? `<br><small>${this._escapeHtml(w.detail)}</small>` : ''}
        </li>
      `).join('');

      summary.innerHTML = `
        <div class="validation-warning">
          <span class="icon icon-warning">⚠</span>
          <div class="message">
            <strong>Scheduling Warnings:</strong>
            <ul class="conflict-list">${warningHtml}</ul>
            <small>You can proceed, but review these warnings first.</small>
          </div>
        </div>
      `;
      summary.style.display = 'block';
      summary.className = 'validation-summary validation-warning';
      this._updateSubmitButton(false); // Allow submit with warnings
    } else if (result.severity === 'error') {
      const conflictHtml = result.conflicts.map(c => `
        <li>
          <strong>${this._escapeHtml(c.type)}:</strong> ${this._escapeHtml(c.message)}
          ${c.detail ? `<br><small>${this._escapeHtml(c.detail)}</small>` : ''}
        </li>
      `).join('');

      summary.innerHTML = `
        <div class="validation-conflict">
          <span class="icon icon-error">✕</span>
          <div class="message">
            <strong>Scheduling Conflicts:</strong>
            <ul class="conflict-list">${conflictHtml}</ul>
            <small>Resolve these conflicts before scheduling.</small>
          </div>
        </div>
      `;
      summary.style.display = 'block';
      summary.className = 'validation-summary validation-conflict';
      this._updateSubmitButton(true); // Disable submit
    }
  }

  /**
   * Clear validation messages
   * @private
   */
  _clearValidation() {
    const summary = this.formElement.querySelector('#validation-summary');
    if (summary) {
      summary.style.display = 'none';
      summary.innerHTML = '';
    }

    this.validationState = {
      hasErrors: false,
      hasWarnings: false,
      isValidating: false
    };
  }

  /**
   * Update submit button state
   * @param {boolean} disabled - Whether to disable
   * @private
   */
  _updateSubmitButton(disabled) {
    const submitBtn = this.formElement.querySelector('#btn-submit');
    if (submitBtn) {
      submitBtn.disabled = disabled;

      if (disabled) {
        submitBtn.setAttribute('aria-disabled', 'true');
        submitBtn.title = 'Resolve conflicts or fill all required fields to submit';
      } else {
        submitBtn.removeAttribute('aria-disabled');
        submitBtn.title = '';
      }
    }
  }

  /**
   * Handle form submission
   * @param {Event} e - Submit event
   * @private
   */
  async _handleSubmit(e) {
    e.preventDefault();

    console.log('[ScheduleModal] Form submitted');

    // Show loading state on button
    const submitBtn = this.formElement.querySelector('#btn-submit');
    const btnText = submitBtn.querySelector('.btn-text');
    const btnSpinner = submitBtn.querySelector('.btn-spinner');

    submitBtn.disabled = true;
    btnText.style.display = 'none';
    btnSpinner.style.display = 'inline';

    // Story 2.4: AJAX submission implementation
    try {
      // Gather form data
      const formData = {
        employee_id: this.formElement.querySelector('#employee-id').value,
        event_id: this.eventData.event_id,
        schedule_datetime: this._buildDateTimeString(),
        duration_minutes: parseInt(this.formElement.querySelector('#duration').value, 10)
      };

      console.log('[ScheduleModal] Submitting schedule:', formData);

      // Submit to backend API
      const response = await fetch('/api/schedule-event', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
      });

      const result = await response.json();

      if (response.ok && result.success) {
        // Success - show message and close modal
        console.log('[ScheduleModal] Schedule successful:', result);

        // Show success message
        this._showSuccessMessage(result.message || 'Event scheduled successfully!');

        // Close modal after brief delay
        setTimeout(() => {
          this.modal.close();

          // Refresh the page to show updated schedule
          window.location.reload();
        }, 1500);

      } else {
        // Error from API
        console.error('[ScheduleModal] Schedule failed:', result);
        this._showSubmitError(result.error || 'Failed to schedule event');

        // Re-enable submit button
        submitBtn.disabled = false;
        btnText.style.display = 'inline';
        btnSpinner.style.display = 'none';
      }

    } catch (error) {
      // Network or other error
      console.error('[ScheduleModal] Submit error:', error);
      this._showSubmitError('Network error. Please try again.');

      // Re-enable submit button
      submitBtn.disabled = false;
      btnText.style.display = 'inline';
      btnSpinner.style.display = 'none';
    }
  }

  /**
   * Show success message in modal
   * @param {string} message - Success message
   * @private
   */
  _showSuccessMessage(message) {
    const summary = this.formElement.querySelector('#validation-summary');
    summary.innerHTML = `
      <div class="validation-success">
        <span class="icon icon-success">✓</span>
        <span class="message">${this._escapeHtml(message)}</span>
      </div>
    `;
    summary.style.display = 'block';
    summary.className = 'validation-summary validation-success';
  }

  /**
   * Show error message on submit failure
   * @param {string} errorMessage - Error message
   * @private
   */
  _showSubmitError(errorMessage) {
    const summary = this.formElement.querySelector('#validation-summary');
    summary.innerHTML = `
      <div class="validation-error">
        <span class="icon icon-error">✕</span>
        <span class="message">${this._escapeHtml(errorMessage)}</span>
      </div>
    `;
    summary.style.display = 'block';
    summary.className = 'validation-summary validation-error';
  }

  /**
   * Handle cancel button
   * @private
   */
  _handleCancel() {
    console.log('[ScheduleModal] Cancelled');
    this.modal.close();
  }

  /**
   * Cleanup when modal closes
   * @private
   */
  _cleanup() {
    console.log('[ScheduleModal] Cleanup');
    this.validator = null;
    this.formElement = null;
  }

  /**
   * Escape HTML to prevent XSS
   * @param {string} text - Text to escape
   * @returns {string}
   * @private
   */
  _escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * Close the modal programmatically
   */
  close() {
    if (this.modal) {
      this.modal.close();
    }
  }
}
