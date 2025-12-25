/**
 * Schedule Form with Inline Conflict Validation
 *
 * Page-specific module for the manual scheduling form that provides
 * real-time conflict validation as users fill out form fields.
 *
 * Epic 1, Story 1.4: Add Inline Conflict Warnings to Manual Scheduling Form
 *
 * @module pages/schedule-form
 */

import { ConflictValidator } from '../components/conflict-validator.js';

/**
 * Schedule Form Controller
 * Manages inline validation for the manual scheduling form
 */
class ScheduleFormController {
  /**
   * Initialize the schedule form controller
   */
  constructor() {
    this.validator = new ConflictValidator();
    this.form = document.getElementById('scheduling-form');
    this.fields = {
      eventId: document.querySelector('input[name="event_id"]'),
      scheduledDate: document.getElementById('scheduled_date'),
      employeeId: document.getElementById('employee_id'),
      startTime: document.getElementById('start_time'),
      overrideConstraints: document.getElementById('override_constraints')
    };
    this.submitBtn = this.form.querySelector('button[type="submit"]');

    // Validation state
    this.validationState = {
      hasErrors: false,
      hasWarnings: false,
      isValidating: false,
      lastResult: null
    };

    // Session storage key for state persistence
    this.storageKey = `schedule-form-validation-${this.fields.eventId.value}`;

    this._init();
  }

  /**
   * Initialize the form controller
   * @private
   */
  _init() {
    console.log('[ScheduleForm] Initializing inline validation');

    // Add validation containers to form
    this._injectValidationContainers();

    // Restore validation state from session storage
    this._restoreValidationState();

    // Attach event listeners
    this._attachEventListeners();

    // Load default time from settings based on event type
    this._loadDefaultTime();

    // Initial validation if all required fields are filled
    this._checkInitialValidation();
  }

  /**
   * Load default start time from settings based on event type
   * @private
   */
  async _loadDefaultTime() {
    // Get event type from window.eventData (set in template)
    const eventType = window.eventData?.eventType;

    if (!eventType) {
      console.warn('[ScheduleForm] No event type found, using fallback time');
      this.fields.startTime.value = '09:00';
      return;
    }

    try {
      console.log('[ScheduleForm] Loading default time for event type:', eventType);

      const response = await fetch(`/api/event-default-time/${encodeURIComponent(eventType)}`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();

      if (data.success && data.default_time) {
        this.fields.startTime.value = data.default_time;
        console.log('[ScheduleForm] Default time set to:', data.default_time);
      } else {
        // Fallback to 09:00
        this.fields.startTime.value = '09:00';
        console.log('[ScheduleForm] Using fallback time: 09:00');
      }
    } catch (error) {
      console.error('[ScheduleForm] Error loading default time:', error);
      // Fallback to 09:00
      this.fields.startTime.value = '09:00';
    }
  }

  /**
   * Inject validation message containers into the form
   * @private
   */
  _injectValidationContainers() {
    // Add validation container after employee field
    const employeeGroup = this.fields.employeeId.closest('.form-group');
    if (employeeGroup && !employeeGroup.querySelector('.validation-message')) {
      const container = document.createElement('div');
      container.className = 'validation-message';
      container.id = 'employee-validation';
      container.setAttribute('role', 'alert');
      container.setAttribute('aria-live', 'polite');
      employeeGroup.appendChild(container);
    }

    // Add validation container after date field
    const dateGroup = this.fields.scheduledDate.closest('.form-group');
    if (dateGroup && !dateGroup.querySelector('.validation-message')) {
      const container = document.createElement('div');
      container.className = 'validation-message';
      container.id = 'date-validation';
      container.setAttribute('role', 'alert');
      container.setAttribute('aria-live', 'polite');
      dateGroup.appendChild(container);
    }

    // Add validation container after time field
    const timeGroup = this.fields.startTime.closest('.form-group');
    if (timeGroup && !timeGroup.querySelector('.validation-message')) {
      const container = document.createElement('div');
      container.className = 'validation-message';
      container.id = 'time-validation';
      container.setAttribute('role', 'alert');
      container.setAttribute('aria-live', 'polite');
      timeGroup.appendChild(container);
    }

    // Add global validation summary at top of form
    if (!this.form.querySelector('.validation-summary')) {
      const summary = document.createElement('div');
      summary.className = 'validation-summary';
      summary.id = 'validation-summary';
      summary.setAttribute('role', 'alert');
      summary.setAttribute('aria-live', 'assertive');
      summary.style.display = 'none';
      this.form.insertBefore(summary, this.form.firstChild);
    }
  }

  /**
   * Attach event listeners to form fields
   * @private
   */
  _attachEventListeners() {
    // Validate on field change
    this.fields.scheduledDate.addEventListener('change', () => this._handleFieldChange());
    this.fields.employeeId.addEventListener('change', () => this._handleFieldChange());
    this.fields.startTime.addEventListener('change', () => this._handleFieldChange());

    // Clear validation on override checkbox
    this.fields.overrideConstraints.addEventListener('change', (e) => {
      if (e.target.checked) {
        this._clearValidation();
        this._updateSubmitButton(false); // Enable submit when overriding
      } else {
        this._handleFieldChange();
      }
    });

    // Save validation state before form submit
    this.form.addEventListener('submit', () => {
      this._saveValidationState();
    });

    // Clear validation state when user navigates away
    window.addEventListener('beforeunload', () => {
      // Only clear if form wasn't submitted
      if (!this.form.dataset.submitted) {
        sessionStorage.removeItem(this.storageKey);
      }
    });

    this.form.addEventListener('submit', () => {
      this.form.dataset.submitted = 'true';
    });
  }

  /**
   * Handle form field change event
   * @private
   */
  _handleFieldChange() {
    // Skip validation if override is checked
    if (this.fields.overrideConstraints.checked) {
      return;
    }

    // Check if all required fields are filled
    if (!this._areRequiredFieldsFilled()) {
      this._clearValidation();
      this._updateSubmitButton(true); // Disable submit
      return;
    }

    // Trigger validation
    this._performValidation();
  }

  /**
   * Check if all required fields are filled
   * @returns {boolean}
   * @private
   */
  _areRequiredFieldsFilled() {
    return (
      this.fields.eventId.value &&
      this.fields.scheduledDate.value &&
      this.fields.employeeId.value &&
      this.fields.startTime.value
    );
  }

  /**
   * Perform validation using ConflictValidator
   * @private
   */
  _performValidation() {
    console.log('[ScheduleForm] Triggering validation');

    // Build form data
    const formData = {
      employee_id: this.fields.employeeId.value,
      event_id: parseInt(this.fields.eventId.value, 10),
      schedule_datetime: this._buildDatetimeString(),
      duration_minutes: 120 // Default duration
    };

    // Call validator with callback
    this.validator.validateSchedule(formData, (result) => {
      this._handleValidationResult(result);
    });
  }

  /**
   * Build ISO datetime string from form fields
   * @returns {string}
   * @private
   */
  _buildDatetimeString() {
    const date = this.fields.scheduledDate.value; // YYYY-MM-DD
    const time = this.fields.startTime.value; // HH:MM
    return `${date}T${time}:00`;
  }

  /**
   * Handle validation result from ConflictValidator
   * @param {Object} result - Validation result
   * @private
   */
  _handleValidationResult(result) {
    console.log('[ScheduleForm] Validation result:', result);

    if (result.loading) {
      // Show loading state
      this._showLoadingState();
      return;
    }

    if (result.error) {
      // Show error state
      this._showErrorState(result.error, result.retry);
      return;
    }

    // Show validation result
    this._showValidationResult(result);

    // Save to session storage
    this.validationState.lastResult = result;
    this._saveValidationState();
  }

  /**
   * Show loading state
   * @private
   */
  _showLoadingState() {
    this.validationState.isValidating = true;

    const summary = document.getElementById('validation-summary');
    summary.innerHTML = `
      <div class="validation-loading">
        <span class="spinner"></span>
        <span>Checking for conflicts...</span>
      </div>
    `;
    summary.style.display = 'block';
    summary.className = 'validation-summary validation-loading';

    // Disable submit button while validating
    this._updateSubmitButton(true);
  }

  /**
   * Show error state
   * @param {string} errorMessage - Error message
   * @param {Function|null} retryFn - Retry function
   * @private
   */
  _showErrorState(errorMessage, retryFn) {
    this.validationState.isValidating = false;
    this.validationState.hasErrors = true;

    const summary = document.getElementById('validation-summary');
    summary.innerHTML = `
      <div class="validation-error">
        <span class="icon icon-error">⚠</span>
        <span class="message">${this._escapeHtml(errorMessage)}</span>
        ${retryFn ? '<button type="button" class="btn-retry btn-link">Retry</button>' : ''}
      </div>
    `;
    summary.style.display = 'block';
    summary.className = 'validation-summary validation-error';

    // Attach retry handler
    if (retryFn) {
      const retryBtn = summary.querySelector('.btn-retry');
      retryBtn.addEventListener('click', () => {
        retryFn();
      });
    }

    // Disable submit button on validation error
    this._updateSubmitButton(true);
  }

  /**
   * Show validation result (success, warnings, or conflicts)
   * @param {Object} result - Validation result
   * @private
   */
  _showValidationResult(result) {
    this.validationState.isValidating = false;
    this.validationState.hasErrors = result.severity === 'error';
    this.validationState.hasWarnings = result.severity === 'warning';

    const summary = document.getElementById('validation-summary');

    if (result.severity === 'success') {
      // No conflicts
      summary.innerHTML = `
        <div class="validation-success">
          <span class="icon icon-success">✓</span>
          <span class="message">No scheduling conflicts found</span>
        </div>
      `;
      summary.style.display = 'block';
      summary.className = 'validation-summary validation-success';
      this._updateSubmitButton(false); // Enable submit
    } else if (result.severity === 'warning') {
      // Warnings only - enhanced with detailed context (Story 1.5)
      const warningHtml = result.warnings.map(w => this._formatConflictItem(w)).join('');

      summary.innerHTML = `
        <div class="validation-warning">
          <span class="icon icon-warning">⚠</span>
          <div class="message">
            <strong>Scheduling Warnings:</strong>
            <ul class="conflict-list">${warningHtml}</ul>
            <div class="conflict-actions">
              <button type="button" class="btn-schedule-anyway btn-warning">Schedule Anyway</button>
              <small>Or adjust the schedule to resolve these warnings.</small>
            </div>
          </div>
        </div>
      `;
      summary.style.display = 'block';
      summary.className = 'validation-summary validation-warning';

      // Attach "Schedule Anyway" handler (Story 1.5 Task 6)
      const scheduleAnywayBtn = summary.querySelector('.btn-schedule-anyway');
      if (scheduleAnywayBtn) {
        scheduleAnywayBtn.addEventListener('click', () => this._handleScheduleAnyway(result));
      }

      this._updateSubmitButton(false); // Allow submit with warnings
    } else if (result.severity === 'error') {
      // Hard conflicts - enhanced with detailed context and suggestions (Story 1.5)
      const conflictHtml = result.conflicts.map(c => this._formatConflictItem(c)).join('');

      const warningHtml = result.warnings.length > 0 ? result.warnings.map(w => this._formatConflictItem(w)).join('') : '';

      summary.innerHTML = `
        <div class="validation-conflict">
          <span class="icon icon-error">✕</span>
          <div class="message">
            <strong>Scheduling Conflicts:</strong>
            <ul class="conflict-list">${conflictHtml}</ul>
            ${warningHtml ? `<strong>Additional Warnings:</strong><ul class="conflict-list">${warningHtml}</ul>` : ''}
            <div id="employee-suggestions" class="employee-suggestions" style="margin-top: 1rem;"></div>
            <small>Resolve these conflicts or check "Override Scheduling Constraints" to proceed.</small>
          </div>
        </div>
      `;
      summary.style.display = 'block';
      summary.className = 'validation-summary validation-conflict';
      this._updateSubmitButton(true); // Disable submit on conflicts

      // Fetch and display employee suggestions (Story 1.5 Task 5)
      this._fetchAndDisplaySuggestions();
    }
  }

  /**
   * Format a conflict/warning item with detailed context (Story 1.5 Task 3)
   * @param {Object} item - Conflict or warning object
   * @returns {string} HTML string
   * @private
   */
  _formatConflictItem(item) {
    const type = this._escapeHtml(item.type || 'unknown');
    const message = this._escapeHtml(item.message);
    const detail = item.detail ? this._escapeHtml(item.detail) : '';

    // Enhanced details from Story 1.5 backend
    const conflictingEventName = item.conflicting_event_name ? this._escapeHtml(item.conflicting_event_name) : null;
    const conflictingTimeRange = item.conflicting_time_range ? this._escapeHtml(item.conflicting_time_range) : null;
    const conflictingEventId = item.conflicting_event_id || null;

    let html = `
      <li class="conflict-item">
        <div class="conflict-header">
          <strong>${type}:</strong> ${message}
        </div>
    `;

    // Show detailed context if available
    if (conflictingEventName || conflictingTimeRange) {
      html += `<div class="conflict-details">`;

      if (conflictingEventName) {
        if (conflictingEventId) {
          html += `<span class="conflict-event"><strong>Event:</strong> <a href="#" class="view-conflict-link" data-event-id="${conflictingEventId}">${conflictingEventName}</a></span>`;
        } else {
          html += `<span class="conflict-event"><strong>Event:</strong> ${conflictingEventName}</span>`;
        }
      }

      if (conflictingTimeRange) {
        html += `<span class="conflict-time"><strong>Time:</strong> ${conflictingTimeRange}</span>`;
      }

      html += `</div>`;
    }

    if (detail) {
      html += `<small class="conflict-detail">${detail}</small>`;
    }

    html += `</li>`;

    return html;
  }

  /**
   * Handle "Schedule Anyway" button click (Story 1.5 Task 6)
   * @param {Object} result - Validation result with warnings
   * @private
   */
  _handleScheduleAnyway(result) {
    // Build warning summary for confirmation
    const warningList = result.warnings.map(w => `  • ${w.message}`).join('\n');

    const confirmed = confirm(
      `You are about to schedule despite the following warnings:\n\n${warningList}\n\nAre you sure you want to proceed?`
    );

    if (confirmed) {
      console.log('[ScheduleForm] User confirmed schedule with warnings');
      // Enable submission by checking override checkbox
      this.fields.overrideConstraints.checked = true;
      this._clearValidation();
      this._updateSubmitButton(false);

      // Show confirmation message
      const summary = document.getElementById('validation-summary');
      summary.innerHTML = `
        <div class="validation-warning">
          <span class="icon icon-warning">⚠</span>
          <span class="message">Scheduling with warnings - constraints overridden. Click "${this.submitBtn.textContent}" to save.</span>
        </div>
      `;
      summary.style.display = 'block';
      summary.className = 'validation-summary validation-warning';
    }
  }

  /**
   * Fetch and display employee suggestions (Story 1.5 Task 5)
   * @private
   */
  async _fetchAndDisplaySuggestions() {
    const container = document.getElementById('employee-suggestions');
    if (!container) return;

    // Show loading state
    container.innerHTML = `
      <div class="suggestions-loading">
        <span class="spinner"></span>
        <span>Finding alternative employees...</span>
      </div>
    `;

    try {
      const params = new URLSearchParams({
        event_id: this.fields.eventId.value,
        date: this.fields.scheduledDate.value,
        time: this.fields.startTime.value,
        limit: '3'
      });

      const response = await fetch(`/api/suggest-employees?${params}`);
      const data = await response.json();

      if (!data.success) {
        container.innerHTML = `<small class="suggestions-error">Could not load suggestions: ${this._escapeHtml(data.error)}</small>`;
        return;
      }

      if (data.suggestions && data.suggestions.length > 0) {
        this._displaySuggestions(data.suggestions, container);
      } else {
        container.innerHTML = `<small class="suggestions-empty">No alternative employees available at this time.</small>`;
      }
    } catch (error) {
      console.error('[ScheduleForm] Error fetching suggestions:', error);
      container.innerHTML = `<small class="suggestions-error">Failed to load employee suggestions</small>`;
    }
  }

  /**
   * Display employee suggestions in the UI (Story 1.5 Task 5)
   * @param {Array} suggestions - Array of suggestion objects
   * @param {HTMLElement} container - Container element
   * @private
   */
  _displaySuggestions(suggestions, container) {
    const suggestionsHtml = suggestions.map(s => `
      <div class="suggestion-card" data-employee-id="${this._escapeHtml(s.employee_id)}">
        <div class="suggestion-info">
          <strong>${this._escapeHtml(s.employee_name)}</strong>
          <small>${this._escapeHtml(s.employee_role)}</small>
          <small class="suggestion-reason">${this._escapeHtml(s.reason)}</small>
        </div>
        <button type="button" class="btn-use-employee" data-employee-id="${this._escapeHtml(s.employee_id)}">
          Use This Employee
        </button>
      </div>
    `).join('');

    container.innerHTML = `
      <div class="suggestions-header">
        <strong>Suggested Alternatives:</strong>
      </div>
      <div class="suggestions-list">
        ${suggestionsHtml}
      </div>
    `;

    // Attach click handlers to suggestion buttons
    container.querySelectorAll('.btn-use-employee').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const employeeId = e.target.dataset.employeeId;
        this._applySuggestion(employeeId);
      });
    });
  }

  /**
   * Apply an employee suggestion (Story 1.5 Task 5)
   * @param {string} employeeId - Employee ID to apply
   * @private
   */
  _applySuggestion(employeeId) {
    console.log('[ScheduleForm] Applying suggestion:', employeeId);

    // Update employee dropdown
    this.fields.employeeId.value = employeeId;

    // Trigger validation with new employee
    this._performValidation();
  }

  /**
   * Clear all validation messages
   * @private
   */
  _clearValidation() {
    console.log('[ScheduleForm] Clearing validation');

    const summary = document.getElementById('validation-summary');
    summary.style.display = 'none';
    summary.innerHTML = '';

    this.validationState = {
      hasErrors: false,
      hasWarnings: false,
      isValidating: false,
      lastResult: null
    };

    // Clear session storage
    sessionStorage.removeItem(this.storageKey);
  }

  /**
   * Update submit button state
   * @param {boolean} disabled - Whether to disable the button
   * @private
   */
  _updateSubmitButton(disabled) {
    this.submitBtn.disabled = disabled;

    if (disabled) {
      this.submitBtn.setAttribute('aria-disabled', 'true');
      this.submitBtn.title = 'Resolve conflicts or fill all required fields to submit';
    } else {
      this.submitBtn.removeAttribute('aria-disabled');
      this.submitBtn.title = '';
    }
  }

  /**
   * Check if initial validation should be performed (on page load)
   * @private
   */
  _checkInitialValidation() {
    if (this._areRequiredFieldsFilled() && !this.fields.overrideConstraints.checked) {
      console.log('[ScheduleForm] Performing initial validation');
      this._performValidation();
    }
  }

  /**
   * Save validation state to session storage
   * @private
   */
  _saveValidationState() {
    try {
      const state = {
        validationState: this.validationState,
        timestamp: Date.now()
      };
      sessionStorage.setItem(this.storageKey, JSON.stringify(state));
      console.log('[ScheduleForm] Validation state saved');
    } catch (e) {
      console.warn('[ScheduleForm] Failed to save validation state:', e);
    }
  }

  /**
   * Restore validation state from session storage
   * @private
   */
  _restoreValidationState() {
    try {
      const stored = sessionStorage.getItem(this.storageKey);
      if (!stored) return;

      const state = JSON.parse(stored);
      const age = Date.now() - state.timestamp;

      // Only restore if less than 5 minutes old
      if (age < 5 * 60 * 1000) {
        this.validationState = state.validationState;
        if (this.validationState.lastResult) {
          console.log('[ScheduleForm] Restored validation state');
          this._showValidationResult(this.validationState.lastResult);
        }
      } else {
        // Clear expired state
        sessionStorage.removeItem(this.storageKey);
      }
    } catch (e) {
      console.warn('[ScheduleForm] Failed to restore validation state:', e);
    }
  }

  /**
   * Escape HTML to prevent XSS
   * @param {string} text - Text to escape
   * @returns {string}
   * @private
   */
  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}

// Initialize on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    // Only initialize if scheduling form exists
    if (document.getElementById('scheduling-form')) {
      new ScheduleFormController();
    }
  });
} else {
  // DOM already loaded
  if (document.getElementById('scheduling-form')) {
    new ScheduleFormController();
  }
}
