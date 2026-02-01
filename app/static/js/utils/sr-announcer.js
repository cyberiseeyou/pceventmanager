/**
 * Screen Reader Announcer
 *
 * Provides ARIA live region announcements for screen reader users.
 * Ensures dynamic content changes are communicated accessibly.
 *
 * @module utils/sr-announcer
 */

/**
 * Screen Reader Announcer Class
 *
 * Manages ARIA live regions for announcing dynamic content to screen readers.
 * Supports two priority levels: polite (default) and assertive (urgent).
 *
 * @example
 * const announcer = new ScreenReaderAnnouncer();
 * announcer.announce('Event rescheduled successfully');
 * announcer.announceAssertive('Error: Unable to save changes');
 */
export class ScreenReaderAnnouncer {
  constructor() {
    this.politeRegion = null;
    this.assertiveRegion = null;
    this.init();
  }

  /**
   * Initialize ARIA live regions
   * Creates two regions: one for polite announcements, one for assertive
   */
  init() {
    // Create polite live region (non-interrupting)
    this.politeRegion = document.getElementById('sr-announcer-polite');
    if (!this.politeRegion) {
      this.politeRegion = document.createElement('div');
      this.politeRegion.id = 'sr-announcer-polite';
      this.politeRegion.className = 'sr-only';
      this.politeRegion.setAttribute('role', 'status');
      this.politeRegion.setAttribute('aria-live', 'polite');
      this.politeRegion.setAttribute('aria-atomic', 'true');
      document.body.appendChild(this.politeRegion);
    }

    // Create assertive live region (interrupting)
    this.assertiveRegion = document.getElementById('sr-announcer-assertive');
    if (!this.assertiveRegion) {
      this.assertiveRegion = document.createElement('div');
      this.assertiveRegion.id = 'sr-announcer-assertive';
      this.assertiveRegion.className = 'sr-only';
      this.assertiveRegion.setAttribute('role', 'alert');
      this.assertiveRegion.setAttribute('aria-live', 'assertive');
      this.assertiveRegion.setAttribute('aria-atomic', 'true');
      document.body.appendChild(this.assertiveRegion);
    }
  }

  /**
   * Announce a message with polite priority
   * Use for non-urgent messages that don't need to interrupt the user
   *
   * @param {string} message - The message to announce
   * @param {number} clearDelay - Milliseconds before clearing (default: 1000)
   */
  announce(message, clearDelay = 1000) {
    this.announcePolite(message, clearDelay);
  }

  /**
   * Announce a message with polite priority (alias for announce)
   *
   * @param {string} message - The message to announce
   * @param {number} clearDelay - Milliseconds before clearing (default: 1000)
   */
  announcePolite(message, clearDelay = 1000) {
    if (!this.politeRegion || !message) return;

    // Clear any existing message first
    this.politeRegion.textContent = '';

    // Use setTimeout to ensure screen reader picks up the change
    setTimeout(() => {
      this.politeRegion.textContent = message;

      // Clear after delay to allow re-announcing the same message
      if (clearDelay > 0) {
        setTimeout(() => {
          this.politeRegion.textContent = '';
        }, clearDelay);
      }
    }, 100);
  }

  /**
   * Announce a message with assertive priority
   * Use for urgent messages that need immediate attention (errors, warnings)
   *
   * @param {string} message - The message to announce
   * @param {number} clearDelay - Milliseconds before clearing (default: 1000)
   */
  announceAssertive(message, clearDelay = 1000) {
    if (!this.assertiveRegion || !message) return;

    // Clear any existing message first
    this.assertiveRegion.textContent = '';

    // Use setTimeout to ensure screen reader picks up the change
    setTimeout(() => {
      this.assertiveRegion.textContent = message;

      // Clear after delay to allow re-announcing the same message
      if (clearDelay > 0) {
        setTimeout(() => {
          this.assertiveRegion.textContent = '';
        }, clearDelay);
      }
    }, 100);
  }

  /**
   * Announce a success message
   * Convenience method for success notifications
   *
   * @param {string} message - The success message
   */
  announceSuccess(message) {
    this.announcePolite(`Success: ${message}`);
  }

  /**
   * Announce an error message
   * Uses assertive priority to ensure immediate attention
   *
   * @param {string} message - The error message
   */
  announceError(message) {
    this.announceAssertive(`Error: ${message}`);
  }

  /**
   * Announce a warning message
   * Uses assertive priority for warnings
   *
   * @param {string} message - The warning message
   */
  announceWarning(message) {
    this.announceAssertive(`Warning: ${message}`);
  }

  /**
   * Announce an info message
   * Uses polite priority for informational messages
   *
   * @param {string} message - The info message
   */
  announceInfo(message) {
    this.announcePolite(`Info: ${message}`);
  }

  /**
   * Announce a loading state
   * Informs user that content is being loaded
   *
   * @param {string} description - Description of what's loading
   */
  announceLoading(description = 'Loading') {
    this.announcePolite(`${description}, please wait...`);
  }

  /**
   * Announce that loading is complete
   * Informs user that content has finished loading
   *
   * @param {string} description - Description of what finished loading
   */
  announceLoadingComplete(description = 'Content') {
    this.announcePolite(`${description} loaded successfully`);
  }

  /**
   * Clear all announcements
   * Immediately clears both live regions
   */
  clear() {
    if (this.politeRegion) {
      this.politeRegion.textContent = '';
    }
    if (this.assertiveRegion) {
      this.assertiveRegion.textContent = '';
    }
  }
}

// Create singleton instance
export const srAnnouncer = new ScreenReaderAnnouncer();

// Make available globally for non-module scripts
if (typeof window !== 'undefined') {
  window.srAnnouncer = srAnnouncer;
}
