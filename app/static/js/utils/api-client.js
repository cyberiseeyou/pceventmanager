/**
 * API Client
 *
 * Standardized HTTP client for making AJAX requests to backend APIs.
 * Handles CSRF tokens, timeouts, retries, and error responses.
 *
 * Epic 1: Real-Time Validation Infrastructure
 * Priority 1 Blocker: NFR17 requires 10s timeout with retry logic and user-friendly errors
 *
 * @module utils/api-client
 */

/**
 * HTTP Client for API requests with CSRF token handling, timeouts, and retries
 */
export class ApiClient {
  /**
   * Create an API client
   *
   * @param {string} baseUrl - Base URL for all requests (default: '')
   * @param {number} timeoutMs - Request timeout in milliseconds (default: 10000)
   * @param {number} maxRetries - Maximum retry attempts for failed requests (default: 1)
   * @param {number} retryDelayMs - Delay between retries in milliseconds (default: 1000)
   */
  constructor(baseUrl = '', timeoutMs = 10000, maxRetries = 1, retryDelayMs = 1000) {
    this.baseUrl = baseUrl;
    this.timeoutMs = timeoutMs;
    this.maxRetries = maxRetries;
    this.retryDelayMs = retryDelayMs;
  }

  /**
   * Make an HTTP request with timeout and retry support
   *
   * @param {string} url - Request URL (relative to baseUrl)
   * @param {Object} options - Fetch options
   * @param {number} retryCount - Current retry attempt (internal)
   * @returns {Promise<Object>} Response JSON data
   * @throws {Error} On network errors, timeouts, or HTTP errors after all retries
   */
  async request(url, options = {}, retryCount = 0) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await fetch(this.baseUrl + url, {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': this.getCsrfToken(),
          ...options.headers
        }
      });

      clearTimeout(timeoutId);

      // Parse JSON response
      const data = await response.json();

      // Check if response indicates error status
      if (!response.ok) {
        const errorMessage = data.error || this._getHttpErrorMessage(response.status);
        throw new Error(errorMessage);
      }

      return data;

    } catch (error) {
      clearTimeout(timeoutId);

      // Handle timeout errors with user-friendly messages
      if (error.name === 'AbortError') {
        const timeoutError = new Error(
          `Request timed out after ${this.timeoutMs / 1000} seconds. ` +
          `Please check your network connection and try again.`
        );
        timeoutError.code = 'TIMEOUT';

        // Retry on timeout if retries available
        if (retryCount < this.maxRetries) {
          console.warn(`[ApiClient] Request timeout. Retrying (${retryCount + 1}/${this.maxRetries})...`);
          await this._delay(this.retryDelayMs);
          return this.request(url, options, retryCount + 1);
        }

        console.error(`[ApiClient] Request timeout (no retries left): ${url}`, timeoutError);
        throw timeoutError;
      }

      // Handle network errors with user-friendly messages
      if (!navigator.onLine || error.message === 'Failed to fetch' || error.message.includes('NetworkError')) {
        const networkError = new Error(
          'Unable to connect to the server. Please check your internet connection and try again.'
        );
        networkError.code = 'NETWORK_ERROR';

        // Retry on network error if retries available
        if (retryCount < this.maxRetries) {
          console.warn(`[ApiClient] Network error. Retrying (${retryCount + 1}/${this.maxRetries})...`);
          await this._delay(this.retryDelayMs);
          return this.request(url, options, retryCount + 1);
        }

        console.error(`[ApiClient] Network error (no retries left): ${url}`, networkError);
        throw networkError;
      }

      // Re-throw other errors (including HTTP errors from API)
      console.error(`[ApiClient] Request failed: ${url}`, error);
      throw error;
    }
  }

  /**
   * Make a GET request
   *
   * @param {string} url - Request URL
   * @param {Object} options - Additional fetch options
   * @returns {Promise<Object>} Response data
   */
  async get(url, options = {}) {
    return this.request(url, {
      ...options,
      method: 'GET'
    });
  }

  /**
   * Make a POST request
   *
   * @param {string} url - Request URL
   * @param {Object} data - Request body data
   * @param {Object} options - Additional fetch options
   * @returns {Promise<Object>} Response data
   */
  async post(url, data, options = {}) {
    return this.request(url, {
      ...options,
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  /**
   * Make a PUT request
   *
   * @param {string} url - Request URL
   * @param {Object} data - Request body data
   * @param {Object} options - Additional fetch options
   * @returns {Promise<Object>} Response data
   */
  async put(url, data, options = {}) {
    return this.request(url, {
      ...options,
      method: 'PUT',
      body: JSON.stringify(data)
    });
  }

  /**
   * Make a DELETE request
   *
   * @param {string} url - Request URL
   * @param {Object} options - Additional fetch options
   * @returns {Promise<Object>} Response data
   */
  async delete(url, options = {}) {
    return this.request(url, {
      ...options,
      method: 'DELETE'
    });
  }

  /**
   * Get user-friendly HTTP error message based on status code
   *
   * @param {number} statusCode - HTTP status code
   * @returns {string} User-friendly error message
   * @private
   */
  _getHttpErrorMessage(statusCode) {
    const messages = {
      400: 'Invalid request. Please check your input and try again.',
      401: 'Authentication required. Please log in and try again.',
      403: 'You do not have permission to perform this action.',
      404: 'The requested resource was not found.',
      409: 'Conflict detected. The resource may have been modified by another user.',
      422: 'Validation error. Please check your input and try again.',
      429: 'Too many requests. Please wait a moment and try again.',
      500: 'Internal server error. Please try again later or contact support.',
      502: 'Server temporarily unavailable. Please try again in a few moments.',
      503: 'Service temporarily unavailable. Please try again later.',
      504: 'Server response timed out. Please try again.'
    };

    return messages[statusCode] || `HTTP Error ${statusCode}: Request failed`;
  }

  /**
   * Delay helper for retry mechanism
   *
   * @param {number} ms - Milliseconds to delay
   * @returns {Promise<void>}
   * @private
   */
  _delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * Get CSRF token from page meta tag or global function
   *
   * @returns {string} CSRF token or empty string
   * @private
   */
  getCsrfToken() {
    // Try meta tag first
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag?.content) {
      return metaTag.content;
    }

    // Fallback to global function if available
    if (typeof window.getCsrfToken === 'function') {
      return window.getCsrfToken() || '';
    }

    return '';
  }
}

// Export singleton instance for convenience
export const apiClient = new ApiClient();
