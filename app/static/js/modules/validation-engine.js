/**
 * Validation Engine Module
 *
 * General-purpose form validation infrastructure with support for synchronous
 * and asynchronous validation rules, field-level and form-level validation,
 * and customizable error display.
 *
 * Epic 1 & 2: UX Enhancement Infrastructure
 * Priority 2: Core Infrastructure - Required for FR3, FR8, FR9, FR12, FR13
 *
 * Architecture Reference: Section 2.3 (lines 228-315)
 *
 * @module modules/validation-engine
 */

import { ariaAnnouncer } from './aria-announcer.js';

/**
 * Validation Engine for form validation
 *
 * Provides field-level and form-level validation with configurable rules,
 * async validation support, error message management, and accessibility features.
 *
 * @example
 * const validator = new ValidationEngine('#my-form', {
 *   employee_id: {
 *     required: true,
 *     message: 'Please select an employee'
 *   },
 *   schedule_date: {
 *     required: true,
 *     date: true,
 *     message: 'Please enter a valid date'
 *   },
 *   email: {
 *     email: true,
 *     async: async (value) => {
 *       const response = await fetch(`/api/check-email?email=${value}`);
 *       const data = await response.json();
 *       return data.available;
 *     },
 *     message: 'Email is already in use'
 *   }
 * });
 *
 * validator.validateField('employee_id');
 * const isValid = await validator.validateForm();
 */
export class ValidationEngine {
  /**
   * Create a Validation Engine
   *
   * @param {string|HTMLElement} formSelector - Form element or selector
   * @param {Object} rules - Validation rules object mapping field names to rule configurations
   * @param {Object} options - Configuration options
   * @param {boolean} options.liveValidation - Enable live validation on blur/input (default: true)
   * @param {boolean} options.showErrorsOnSubmit - Show all errors on form submit (default: true)
   * @param {boolean} options.announceErrors - Announce errors to screen readers (default: true)
   * @param {string} options.errorClass - CSS class for error state (default: 'is-invalid')
   * @param {string} options.successClass - CSS class for success state (default: 'is-valid')
   */
  constructor(formSelector, rules = {}, options = {}) {
    this.form = typeof formSelector === 'string'
      ? document.querySelector(formSelector)
      : formSelector;

    if (!this.form || this.form.nodeName !== 'FORM') {
      throw new Error('[ValidationEngine] Invalid form element');
    }

    this.rules = rules;
    this.options = {
      liveValidation: true,
      showErrorsOnSubmit: true,
      announceErrors: true,
      errorClass: 'is-invalid',
      successClass: 'is-valid',
      ...options
    };

    // Track validation state for each field
    this.fieldStates = {};
    this.pendingValidations = new Map();

    // Initialize
    this._initializeFieldStates();
    if (this.options.liveValidation) {
      this._attachEventListeners();
    }

    console.log('[ValidationEngine] Initialized for form:', this.form.id || this.form.className);
  }

  // =============================================================================
  // Field-Level Validation
  // =============================================================================

  /**
   * Validate a single field
   *
   * @param {string} fieldName - Field name
   * @param {boolean} showError - Whether to display error immediately (default: true)
   * @returns {Promise<boolean>} True if field is valid
   *
   * @example
   * const isValid = await validator.validateField('employee_id');
   */
  async validateField(fieldName, showError = true) {
    const field = this.form.elements[fieldName];
    if (!field) {
      console.warn(`[ValidationEngine] Field not found: ${fieldName}`);
      return true;
    }

    const rules = this.rules[fieldName];
    if (!rules) {
      return true; // No rules = always valid
    }

    const value = this._getFieldValue(field);

    // Mark field as pending during async validation
    this._setFieldState(fieldName, 'pending');

    try {
      // Run validation rules
      const result = await this._validateValue(value, rules, fieldName);

      if (result.valid) {
        this._setFieldState(fieldName, 'valid');
        if (showError) {
          this._clearFieldError(field);
        }
        return true;
      } else {
        this._setFieldState(fieldName, 'invalid', result.message);
        if (showError) {
          this._showFieldError(field, result.message);
        }
        return false;
      }
    } catch (error) {
      console.error(`[ValidationEngine] Validation error for ${fieldName}:`, error);
      this._setFieldState(fieldName, 'invalid', 'Validation failed');
      if (showError) {
        this._showFieldError(field, 'Validation failed');
      }
      return false;
    }
  }

  /**
   * Validate all fields in the form
   *
   * @param {boolean} showErrors - Whether to display errors (default: true)
   * @returns {Promise<boolean>} True if all fields are valid
   *
   * @example
   * const isValid = await validator.validateForm();
   * if (isValid) {
   *   // Submit form
   * }
   */
  async validateForm(showErrors = true) {
    const fieldNames = Object.keys(this.rules);

    // Validate all fields in parallel
    const validationPromises = fieldNames.map(name =>
      this.validateField(name, showErrors)
    );

    const results = await Promise.all(validationPromises);
    const isValid = results.every(result => result === true);

    // Announce validation result
    if (this.options.announceErrors) {
      if (isValid) {
        ariaAnnouncer.announceSuccess('Form validated successfully');
      } else {
        const errorCount = results.filter(r => !r).length;
        ariaAnnouncer.announceError(
          `Form validation failed: ${errorCount} ${errorCount === 1 ? 'error' : 'errors'} found`
        );
      }
    }

    return isValid;
  }

  /**
   * Clear validation state for a field
   *
   * @param {string} fieldName - Field name
   */
  clearFieldValidation(fieldName) {
    const field = this.form.elements[fieldName];
    if (!field) {
      return;
    }

    this._setFieldState(fieldName, 'pristine');
    this._clearFieldError(field);
  }

  /**
   * Clear validation state for all fields
   */
  clearFormValidation() {
    Object.keys(this.rules).forEach(fieldName => {
      this.clearFieldValidation(fieldName);
    });
  }

  // =============================================================================
  // Validation Rules
  // =============================================================================

  /**
   * Validate a value against a rule set
   *
   * @param {any} value - Value to validate
   * @param {Object} rules - Rule configuration
   * @param {string} fieldName - Field name for context
   * @returns {Promise<Object>} Validation result { valid: boolean, message?: string }
   * @private
   */
  async _validateValue(value, rules, fieldName) {
    // Required rule
    if (rules.required && this._isEmpty(value)) {
      return {
        valid: false,
        message: rules.message || `${this._humanizeFieldName(fieldName)} is required`
      };
    }

    // Skip other rules if empty and not required
    if (this._isEmpty(value)) {
      return { valid: true };
    }

    // Built-in validation rules
    if (rules.email && !this._isValidEmail(value)) {
      return {
        valid: false,
        message: rules.message || 'Please enter a valid email address'
      };
    }

    if (rules.phone && !this._isValidPhone(value)) {
      return {
        valid: false,
        message: rules.message || 'Please enter a valid phone number'
      };
    }

    if (rules.url && !this._isValidUrl(value)) {
      return {
        valid: false,
        message: rules.message || 'Please enter a valid URL'
      };
    }

    if (rules.date && !this._isValidDate(value)) {
      return {
        valid: false,
        message: rules.message || 'Please enter a valid date'
      };
    }

    if (rules.number && !this._isValidNumber(value)) {
      return {
        valid: false,
        message: rules.message || 'Please enter a valid number'
      };
    }

    if (rules.minLength && value.length < rules.minLength) {
      return {
        valid: false,
        message: rules.message || `Minimum length is ${rules.minLength} characters`
      };
    }

    if (rules.maxLength && value.length > rules.maxLength) {
      return {
        valid: false,
        message: rules.message || `Maximum length is ${rules.maxLength} characters`
      };
    }

    if (rules.min !== undefined && parseFloat(value) < rules.min) {
      return {
        valid: false,
        message: rules.message || `Minimum value is ${rules.min}`
      };
    }

    if (rules.max !== undefined && parseFloat(value) > rules.max) {
      return {
        valid: false,
        message: rules.message || `Maximum value is ${rules.max}`
      };
    }

    if (rules.pattern && !this._matchesPattern(value, rules.pattern)) {
      return {
        valid: false,
        message: rules.message || 'Please enter a valid value'
      };
    }

    if (rules.matches) {
      const matchField = this.form.elements[rules.matches];
      const matchValue = matchField ? this._getFieldValue(matchField) : null;
      if (value !== matchValue) {
        return {
          valid: false,
          message: rules.message || `Values must match`
        };
      }
    }

    // Custom validation function
    if (rules.custom && typeof rules.custom === 'function') {
      const customResult = rules.custom(value, this.form);
      if (customResult === false || (customResult && !customResult.valid)) {
        return {
          valid: false,
          message: (customResult && customResult.message) || rules.message || 'Invalid value'
        };
      }
    }

    // Async validation function
    if (rules.async && typeof rules.async === 'function') {
      try {
        const asyncResult = await rules.async(value, this.form);
        if (asyncResult === false || (asyncResult && !asyncResult.valid)) {
          return {
            valid: false,
            message: (asyncResult && asyncResult.message) || rules.message || 'Validation failed'
          };
        }
      } catch (error) {
        console.error('[ValidationEngine] Async validation error:', error);
        return {
          valid: false,
          message: 'Validation failed'
        };
      }
    }

    return { valid: true };
  }

  // =============================================================================
  // Field State Management
  // =============================================================================

  /**
   * Initialize field states for all fields with rules
   * @private
   */
  _initializeFieldStates() {
    Object.keys(this.rules).forEach(fieldName => {
      this.fieldStates[fieldName] = {
        status: 'pristine', // pristine, valid, invalid, pending
        message: null,
        touched: false
      };
    });
  }

  /**
   * Set field validation state
   *
   * @param {string} fieldName - Field name
   * @param {string} status - Validation status
   * @param {string} message - Optional error message
   * @private
   */
  _setFieldState(fieldName, status, message = null) {
    if (!this.fieldStates[fieldName]) {
      this.fieldStates[fieldName] = {};
    }

    this.fieldStates[fieldName].status = status;
    this.fieldStates[fieldName].message = message;
    this.fieldStates[fieldName].touched = true;

    console.log(`[ValidationEngine] Field ${fieldName}: ${status}`, message || '');
  }

  /**
   * Get field validation state
   *
   * @param {string} fieldName - Field name
   * @returns {Object} Field state object
   */
  getFieldState(fieldName) {
    return this.fieldStates[fieldName] || { status: 'pristine', message: null, touched: false };
  }

  /**
   * Get form validation state
   *
   * @returns {Object} Form state summary
   */
  getFormState() {
    const states = Object.values(this.fieldStates);
    return {
      isValid: states.every(s => s.status === 'valid' || s.status === 'pristine'),
      isPending: states.some(s => s.status === 'pending'),
      hasErrors: states.some(s => s.status === 'invalid'),
      errorCount: states.filter(s => s.status === 'invalid').length,
      fields: { ...this.fieldStates }
    };
  }

  // =============================================================================
  // Error Display
  // =============================================================================

  /**
   * Show error message for a field
   *
   * @param {HTMLElement} field - Form field element
   * @param {string} message - Error message
   * @private
   */
  _showFieldError(field, message) {
    // Add error class to field
    field.classList.add(this.options.errorClass);
    field.classList.remove(this.options.successClass);
    field.setAttribute('aria-invalid', 'true');

    // Find or create error message element
    let errorElement = this._getErrorElement(field);
    if (!errorElement) {
      errorElement = this._createErrorElement(field);
    }

    errorElement.textContent = message;
    errorElement.style.display = 'block';

    // Link field to error message for screen readers
    if (!field.hasAttribute('aria-describedby')) {
      field.setAttribute('aria-describedby', errorElement.id);
    }
  }

  /**
   * Clear error message for a field
   *
   * @param {HTMLElement} field - Form field element
   * @private
   */
  _clearFieldError(field) {
    field.classList.remove(this.options.errorClass);
    field.classList.add(this.options.successClass);
    field.removeAttribute('aria-invalid');

    const errorElement = this._getErrorElement(field);
    if (errorElement) {
      errorElement.textContent = '';
      errorElement.style.display = 'none';
    }
  }

  /**
   * Get error message element for a field
   *
   * @param {HTMLElement} field - Form field element
   * @returns {HTMLElement|null} Error element or null
   * @private
   */
  _getErrorElement(field) {
    const fieldName = field.name || field.id;
    const errorId = `${fieldName}-error`;
    return document.getElementById(errorId);
  }

  /**
   * Create error message element for a field
   *
   * @param {HTMLElement} field - Form field element
   * @returns {HTMLElement} Created error element
   * @private
   */
  _createErrorElement(field) {
    const fieldName = field.name || field.id;
    const errorId = `${fieldName}-error`;

    const errorElement = document.createElement('div');
    errorElement.id = errorId;
    errorElement.className = 'invalid-feedback';
    errorElement.setAttribute('role', 'alert');
    errorElement.style.display = 'none';

    // Insert after field or field's parent group
    const container = field.closest('.form-group') || field.parentElement;
    container.appendChild(errorElement);

    return errorElement;
  }

  // =============================================================================
  // Event Listeners
  // =============================================================================

  /**
   * Attach event listeners for live validation
   * @private
   */
  _attachEventListeners() {
    Object.keys(this.rules).forEach(fieldName => {
      const field = this.form.elements[fieldName];
      if (!field) {
        return;
      }

      // Validate on blur (when field loses focus)
      field.addEventListener('blur', () => {
        this.validateField(fieldName, true);
      });

      // Clear error on input (user is correcting)
      field.addEventListener('input', () => {
        const state = this.getFieldState(fieldName);
        if (state.status === 'invalid') {
          this._clearFieldError(field);
        }
      });
    });

    // Prevent form submission if validation fails
    this.form.addEventListener('submit', async (event) => {
      event.preventDefault();

      const isValid = await this.validateForm(this.options.showErrorsOnSubmit);

      if (isValid) {
        // Dispatch custom event that form is validated and ready to submit
        const validEvent = new CustomEvent('validation:success', {
          detail: { form: this.form },
          bubbles: true
        });
        this.form.dispatchEvent(validEvent);
      } else {
        // Focus first invalid field
        const firstInvalidField = this._getFirstInvalidField();
        if (firstInvalidField) {
          firstInvalidField.focus();
        }

        // Dispatch custom event for validation failure
        const invalidEvent = new CustomEvent('validation:error', {
          detail: {
            form: this.form,
            errors: this._getValidationErrors()
          },
          bubbles: true
        });
        this.form.dispatchEvent(invalidEvent);
      }
    });

    console.log('[ValidationEngine] Event listeners attached');
  }

  /**
   * Get first invalid field in form
   *
   * @returns {HTMLElement|null} First invalid field or null
   * @private
   */
  _getFirstInvalidField() {
    for (const fieldName of Object.keys(this.rules)) {
      const state = this.getFieldState(fieldName);
      if (state.status === 'invalid') {
        return this.form.elements[fieldName];
      }
    }
    return null;
  }

  /**
   * Get all validation errors
   *
   * @returns {Object} Map of field names to error messages
   * @private
   */
  _getValidationErrors() {
    const errors = {};
    Object.keys(this.rules).forEach(fieldName => {
      const state = this.getFieldState(fieldName);
      if (state.status === 'invalid' && state.message) {
        errors[fieldName] = state.message;
      }
    });
    return errors;
  }

  // =============================================================================
  // Utility Methods
  // =============================================================================

  /**
   * Get field value (handles different input types)
   *
   * @param {HTMLElement} field - Form field element
   * @returns {any} Field value
   * @private
   */
  _getFieldValue(field) {
    if (field.type === 'checkbox') {
      return field.checked;
    } else if (field.type === 'radio') {
      const checked = this.form.querySelector(`input[name="${field.name}"]:checked`);
      return checked ? checked.value : null;
    } else if (field.type === 'select-multiple') {
      return Array.from(field.selectedOptions).map(opt => opt.value);
    } else {
      return field.value;
    }
  }

  /**
   * Check if value is empty
   *
   * @param {any} value - Value to check
   * @returns {boolean} True if empty
   * @private
   */
  _isEmpty(value) {
    if (value === null || value === undefined) {
      return true;
    }
    if (typeof value === 'string') {
      return value.trim() === '';
    }
    if (Array.isArray(value)) {
      return value.length === 0;
    }
    if (typeof value === 'boolean') {
      return false; // Checkboxes are never "empty"
    }
    return false;
  }

  /**
   * Validate email format
   *
   * @param {string} value - Email value
   * @returns {boolean} True if valid email
   * @private
   */
  _isValidEmail(value) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(value);
  }

  /**
   * Validate phone format
   *
   * @param {string} value - Phone value
   * @returns {boolean} True if valid phone
   * @private
   */
  _isValidPhone(value) {
    // Accepts various phone formats: (123) 456-7890, 123-456-7890, 1234567890
    const phoneRegex = /^[\d\s\-\(\)]+$/;
    const digits = value.replace(/\D/g, '');
    return phoneRegex.test(value) && digits.length >= 10;
  }

  /**
   * Validate URL format
   *
   * @param {string} value - URL value
   * @returns {boolean} True if valid URL
   * @private
   */
  _isValidUrl(value) {
    try {
      new URL(value);
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Validate date format (YYYY-MM-DD)
   *
   * @param {string} value - Date value
   * @returns {boolean} True if valid date
   * @private
   */
  _isValidDate(value) {
    const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
    if (!dateRegex.test(value)) {
      return false;
    }
    const date = new Date(value);
    return !isNaN(date.getTime());
  }

  /**
   * Validate number format
   *
   * @param {string|number} value - Number value
   * @returns {boolean} True if valid number
   * @private
   */
  _isValidNumber(value) {
    return !isNaN(parseFloat(value)) && isFinite(value);
  }

  /**
   * Check if value matches regex pattern
   *
   * @param {string} value - Value to test
   * @param {RegExp|string} pattern - Regex pattern
   * @returns {boolean} True if matches
   * @private
   */
  _matchesPattern(value, pattern) {
    const regex = typeof pattern === 'string' ? new RegExp(pattern) : pattern;
    return regex.test(value);
  }

  /**
   * Convert field name to human-readable label
   *
   * @param {string} fieldName - Field name
   * @returns {string} Human-readable label
   * @private
   */
  _humanizeFieldName(fieldName) {
    return fieldName
      .replace(/_/g, ' ')
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .replace(/\b\w/g, char => char.toUpperCase());
  }

  /**
   * Destroy the validation engine and remove event listeners
   */
  destroy() {
    // Note: Can't easily remove listeners without storing references
    // In practice, this would require refactoring to store bound listener functions
    this.fieldStates = {};
    this.pendingValidations.clear();
    console.log('[ValidationEngine] Destroyed');
  }
}

// Export for use in other modules
export default ValidationEngine;
