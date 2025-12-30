/**
 * Conflict Validator Component
 *
 * Frontend module for real-time schedule validation with conflict detection.
 * Provides debounced, cached validation with loading states and error handling.
 *
 * Epic 1, Story 1.3: Build Conflict Validation Frontend JavaScript Module
 *
 * @module components/conflict-validator
 *
 * @example
 * import { ConflictValidator } from './components/conflict-validator.js';
 *
 * const validator = new ConflictValidator();
 *
 * validator.validateSchedule({
 *   employee_id: 'EMP001',
 *   event_id: 606034,
 *   schedule_datetime: '2025-10-15T09:00:00',
 *   duration_minutes: 120
 * }, (result) => {
 *   if (result.loading) {
 *     showSpinner();
 *   } else if (result.error) {
 *     showError(result.error, result.retry);
 *   } else {
 *     displayConflicts(result.severity, result.conflicts, result.warnings);
 *   }
 * });
 */

import { ApiClient } from '../utils/api-client.js';
import { CacheManager } from '../utils/cache-manager.js';
import { debounce } from '../utils/debounce.js';

/**
 * Real-time schedule conflict validator
 */
export class ConflictValidator {
  /**
   * Create a conflict validator
   *
   * @param {string} apiEndpoint - API endpoint URL (default: '/api/validate-schedule')
   * @param {number} debounceMs - Debounce delay in milliseconds (default: 300)
   * @param {number} cacheTtlMs - Cache TTL in milliseconds (default: 60000)
   */
  constructor(apiEndpoint = '/api/validate-schedule', debounceMs = 300, cacheTtlMs = 60000) {
    this.apiClient = new ApiClient();
    this.endpoint = apiEndpoint;
    this.cache = new CacheManager(cacheTtlMs);
    this.debounceMs = debounceMs;
    this.isValidating = false;
    this.currentCallback = null;

    // Create debounced validation method
    this._debouncedValidate = debounce(
      this._performValidation.bind(this),
      this.debounceMs
    );
  }

  /**
   * Validate a schedule assignment
   *
   * @param {Object} formData - Form data to validate
   * @param {string} formData.employee_id - Employee ID
   * @param {number} formData.event_id - Event ID
   * @param {string} formData.schedule_datetime - Schedule datetime (ISO format)
   * @param {number} [formData.duration_minutes=120] - Duration in minutes
   * @param {Function} callback - Callback function called with result
   *
   * Result format:
   * - {loading: true} - Validation in progress
   * - {error: string, retry: Function} - Validation error
   * - {severity: string, conflicts: [], warnings: []} - Validation result
   */
  validateSchedule(formData, callback) {
    if (!this._validateFormData(formData)) {
      callback({
        error: 'Invalid form data: missing required fields',
        retry: null
      });
      return;
    }

    // Store callback for debounced execution
    this.currentCallback = callback;

    // Immediately signal loading state
    callback({ loading: true });

    // Check cache first
    const cacheKey = this._getCacheKey(formData);
    const cached = this.cache.get(cacheKey);

    if (cached) {
      console.log('[ConflictValidator] Cache hit:', cacheKey);
      callback(cached);
      return;
    }

    // Debounce the actual validation
    this._debouncedValidate(formData, callback, cacheKey);
  }

  /**
   * Perform the actual validation (called after debounce delay)
   *
   * @param {Object} formData - Form data
   * @param {Function} callback - Callback function
   * @param {string} cacheKey - Cache key for storing result
   * @private
   */
  async _performValidation(formData, callback, cacheKey) {
    // Prevent concurrent validations
    if (this.isValidating) {
      console.log('[ConflictValidator] Validation already in progress, skipping');
      return;
    }

    this.isValidating = true;

    try {
      console.log('[ConflictValidator] Validating:', formData);

      const response = await this.apiClient.post(this.endpoint, formData);

      this.isValidating = false;

      if (!response.success) {
        // API returned error
        const result = {
          error: response.error || 'Validation failed',
          retry: () => this.validateSchedule(formData, callback)
        };
        callback(result);
        return;
      }

      // Format successful response
      const result = {
        severity: response.severity,
        conflicts: response.conflicts || [],
        warnings: response.warnings || [],
        valid: response.valid
      };

      // Cache the result
      this.cache.set(cacheKey, result);

      callback(result);

    } catch (error) {
      this.isValidating = false;

      console.error('[ConflictValidator] Validation error:', error);

      const result = {
        error: error.message || 'Network error during validation',
        retry: () => this.validateSchedule(formData, callback)
      };

      callback(result);
    }
  }

  /**
   * Validate form data has required fields
   *
   * @param {Object} formData - Form data to validate
   * @returns {boolean} True if valid
   * @private
   */
  _validateFormData(formData) {
    if (!formData) return false;
    if (!formData.employee_id) return false;
    if (!formData.event_id) return false;
    if (!formData.schedule_datetime) return false;
    return true;
  }

  /**
   * Generate cache key from form data
   *
   * @param {Object} formData - Form data
   * @returns {string} Cache key
   * @private
   */
  _getCacheKey(formData) {
    return JSON.stringify({
      employee_id: formData.employee_id,
      event_id: formData.event_id,
      schedule_datetime: formData.schedule_datetime,
      duration_minutes: formData.duration_minutes || 120
    });
  }

  /**
   * Clear the validation cache
   */
  clearCache() {
    this.cache.clear();
  }

  /**
   * Get cache statistics
   *
   * @returns {Object} Cache stats
   */
  getCacheStats() {
    return this.cache.getStats();
  }

  /**
   * Check if validation is currently in progress
   *
   * @returns {boolean} True if validating
   */
  isLoading() {
    return this.isValidating;
  }
}

/**
 * Create a singleton validator instance for global use
 * @type {ConflictValidator}
 */
export const defaultValidator = new ConflictValidator();
