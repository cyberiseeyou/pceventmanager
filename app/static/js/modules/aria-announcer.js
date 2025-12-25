/**
 * ARIA Announcer Module
 *
 * Provides screen reader announcements via ARIA live regions for accessibility.
 * Ensures WCAG 2.1 AA compliance for dynamic content updates.
 *
 * Epic 1: Real-Time Validation Infrastructure
 * Priority 1 Blocker: Required for accessibility compliance
 *
 * Architecture Reference: Section 2.5 (lines 468-500)
 *
 * @module modules/aria-announcer
 */

/**
 * ARIA Announcer for screen reader notifications
 *
 * Creates and manages ARIA live regions to announce dynamic content changes
 * to users relying on assistive technologies.
 *
 * @example
 * const announcer = new AriaAnnouncer();
 * announcer.announce('Schedule validated successfully');
 * announcer.announce('Error: Employee unavailable', 'assertive');
 */
export class AriaAnnouncer {
  /**
   * Create an ARIA Announcer
   *
   * Automatically creates two ARIA live regions:
   * - Polite: For non-urgent notifications
   * - Assertive: For urgent notifications that should interrupt
   */
  constructor() {
    this.politeRegion = null;
    this.assertiveRegion = null;
    this.announceTimeout = null;
    this.debounceDelay = 100; // ms - prevent announcement spam

    this._initializeLiveRegions();
  }

  /**
   * Announce a message to screen readers
   *
   * @param {string} message - Message to announce
   * @param {string} priority - Announcement priority: 'polite' (default) or 'assertive'
   *
   * @example
   * announcer.announce('Form submitted successfully');
   * announcer.announce('Critical error occurred', 'assertive');
   */
  announce(message, priority = 'polite') {
    if (!message || typeof message !== 'string') {
      console.warn('[AriaAnnouncer] Invalid message:', message);
      return;
    }

    // Validate priority
    if (priority !== 'polite' && priority !== 'assertive') {
      console.warn(`[AriaAnnouncer] Invalid priority "${priority}". Using "polite".`);
      priority = 'polite';
    }

    // Select appropriate region
    const region = priority === 'assertive' ? this.assertiveRegion : this.politeRegion;

    if (!region) {
      console.error('[AriaAnnouncer] Live region not initialized');
      return;
    }

    // Clear any pending announcements to prevent spam
    if (this.announceTimeout) {
      clearTimeout(this.announceTimeout);
    }

    // Debounce announcements to prevent overwhelming screen readers
    this.announceTimeout = setTimeout(() => {
      // Clear region first to ensure announcement is detected as new content
      region.textContent = '';

      // Use setTimeout to ensure screen reader detects the change
      setTimeout(() => {
        region.textContent = message;
        console.log(`[AriaAnnouncer] Announced (${priority}): ${message}`);
      }, 50);
    }, this.debounceDelay);
  }

  /**
   * Announce a validation result
   *
   * Convenience method for announcing validation feedback with appropriate priority.
   *
   * @param {boolean} isValid - Whether validation passed
   * @param {string} message - Validation message
   */
  announceValidation(isValid, message) {
    const priority = isValid ? 'polite' : 'assertive';
    this.announce(message, priority);
  }

  /**
   * Announce a success message (polite priority)
   *
   * @param {string} message - Success message
   */
  announceSuccess(message) {
    this.announce(message, 'polite');
  }

  /**
   * Announce an error message (assertive priority)
   *
   * @param {string} message - Error message
   */
  announceError(message) {
    this.announce(message, 'assertive');
  }

  /**
   * Announce a warning message (assertive priority)
   *
   * @param {string} message - Warning message
   */
  announceWarning(message) {
    this.announce(message, 'assertive');
  }

  /**
   * Clear all pending announcements
   */
  clear() {
    if (this.announceTimeout) {
      clearTimeout(this.announceTimeout);
      this.announceTimeout = null;
    }

    if (this.politeRegion) {
      this.politeRegion.textContent = '';
    }

    if (this.assertiveRegion) {
      this.assertiveRegion.textContent = '';
    }
  }

  /**
   * Destroy the announcer and remove live regions from DOM
   */
  destroy() {
    this.clear();

    if (this.politeRegion) {
      this.politeRegion.remove();
      this.politeRegion = null;
    }

    if (this.assertiveRegion) {
      this.assertiveRegion.remove();
      this.assertiveRegion = null;
    }
  }

  /**
   * Initialize ARIA live regions in the DOM
   *
   * Creates two hidden live regions for polite and assertive announcements.
   * These regions are visually hidden but accessible to screen readers.
   *
   * @private
   */
  _initializeLiveRegions() {
    // Create polite live region
    this.politeRegion = this._createLiveRegion('aria-live-polite', 'polite');
    document.body.appendChild(this.politeRegion);

    // Create assertive live region
    this.assertiveRegion = this._createLiveRegion('aria-live-assertive', 'assertive');
    document.body.appendChild(this.assertiveRegion);

    console.log('[AriaAnnouncer] Live regions initialized');
  }

  /**
   * Create a single ARIA live region element
   *
   * @param {string} id - Element ID
   * @param {string} ariaLive - ARIA live priority ('polite' or 'assertive')
   * @returns {HTMLElement} The created live region
   * @private
   */
  _createLiveRegion(id, ariaLive) {
    const region = document.createElement('div');

    // Set attributes for accessibility
    region.id = id;
    region.setAttribute('aria-live', ariaLive);
    region.setAttribute('aria-atomic', 'true');
    region.setAttribute('role', 'status');

    // Visually hide but keep accessible to screen readers
    // Using sr-only pattern
    region.style.position = 'absolute';
    region.style.left = '-10000px';
    region.style.width = '1px';
    region.style.height = '1px';
    region.style.overflow = 'hidden';
    region.style.clip = 'rect(0, 0, 0, 0)';
    region.style.whiteSpace = 'nowrap';

    return region;
  }
}

// Export singleton instance for global use
export const ariaAnnouncer = new AriaAnnouncer();

// Make globally available for non-module contexts
if (typeof window !== 'undefined') {
  window.ariaAnnouncer = ariaAnnouncer;
}
