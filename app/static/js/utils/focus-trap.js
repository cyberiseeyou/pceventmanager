/**
 * Focus Trap Utility
 *
 * Manages keyboard focus within modals and other overlays to ensure
 * accessibility and prevent focus from escaping the modal.
 *
 * @module utils/focus-trap
 */

/**
 * Focus Trap Class
 *
 * Traps keyboard focus within a container element (typically a modal).
 * Handles Tab/Shift+Tab cycling, Escape key dismissal, and focus restoration.
 *
 * @example
 * const trap = new FocusTrap(modalElement, {
 *   onEscape: () => closeModal(),
 *   returnFocusOnDeactivate: true
 * });
 * trap.activate();
 * // Later: trap.deactivate();
 */
export class FocusTrap {
  /**
   * Create a focus trap
   *
   * @param {HTMLElement} element - Container element to trap focus within
   * @param {Object} options - Configuration options
   * @param {Function} options.onEscape - Callback when Escape key is pressed
   * @param {boolean} options.returnFocusOnDeactivate - Return focus to trigger element (default: true)
   * @param {boolean} options.allowOutsideClick - Allow clicking outside to dismiss (default: false)
   * @param {HTMLElement} options.initialFocus - Element to focus initially (default: first focusable)
   */
  constructor(element, options = {}) {
    this.element = element;
    this.options = {
      onEscape: null,
      returnFocusOnDeactivate: true,
      allowOutsideClick: false,
      initialFocus: null,
      ...options
    };

    this.previouslyFocused = null;
    this.isActive = false;
    this.focusableElements = [];
    this.firstFocusable = null;
    this.lastFocusable = null;

    // Bind event handlers
    this.handleKeyDown = this.handleKeyDown.bind(this);
    this.handleFocusIn = this.handleFocusIn.bind(this);
  }

  /**
   * Get all focusable elements within the container
   * @returns {HTMLElement[]} Array of focusable elements
   */
  getFocusableElements() {
    const focusableSelectors = [
      'a[href]',
      'button:not([disabled])',
      'input:not([disabled])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
      '[contenteditable="true"]'
    ].join(', ');

    const elements = Array.from(
      this.element.querySelectorAll(focusableSelectors)
    ).filter(el => {
      // Filter out hidden elements
      return el.offsetParent !== null &&
             !el.hasAttribute('hidden') &&
             window.getComputedStyle(el).display !== 'none' &&
             window.getComputedStyle(el).visibility !== 'hidden';
    });

    return elements;
  }

  /**
   * Activate the focus trap
   * Stores current focus, moves focus into trap, and sets up event listeners
   */
  activate() {
    if (this.isActive) return;

    // Store currently focused element to return to later
    this.previouslyFocused = document.activeElement;

    // Get focusable elements
    this.updateFocusableElements();

    if (this.focusableElements.length === 0) {
      console.warn('[FocusTrap] No focusable elements found in container');
      return;
    }

    // Set up event listeners
    document.addEventListener('keydown', this.handleKeyDown, true);
    this.element.addEventListener('focusin', this.handleFocusIn, true);

    // Focus initial element
    const initialFocus = this.options.initialFocus || this.firstFocusable;
    if (initialFocus) {
      // Use setTimeout to ensure modal is visible before focusing
      setTimeout(() => {
        initialFocus.focus();
      }, 10);
    }

    this.isActive = true;
    console.log('[FocusTrap] Activated');
  }

  /**
   * Deactivate the focus trap
   * Removes event listeners and optionally returns focus to trigger element
   */
  deactivate() {
    if (!this.isActive) return;

    // Remove event listeners
    document.removeEventListener('keydown', this.handleKeyDown, true);
    this.element.removeEventListener('focusin', this.handleFocusIn, true);

    // Return focus to previously focused element
    if (this.options.returnFocusOnDeactivate && this.previouslyFocused) {
      setTimeout(() => {
        this.previouslyFocused.focus();
      }, 10);
    }

    this.isActive = false;
    this.previouslyFocused = null;
    console.log('[FocusTrap] Deactivated');
  }

  /**
   * Update the list of focusable elements
   * Call this if the modal content changes dynamically
   */
  updateFocusableElements() {
    this.focusableElements = this.getFocusableElements();
    this.firstFocusable = this.focusableElements[0] || null;
    this.lastFocusable = this.focusableElements[this.focusableElements.length - 1] || null;
  }

  /**
   * Handle keydown events for focus trapping
   * @param {KeyboardEvent} event - Keyboard event
   */
  handleKeyDown(event) {
    if (!this.isActive) return;

    // Handle Escape key
    if (event.key === 'Escape') {
      if (this.options.onEscape) {
        event.preventDefault();
        event.stopPropagation();
        this.options.onEscape();
      }
      return;
    }

    // Handle Tab key
    if (event.key === 'Tab') {
      // Update focusable elements in case modal content changed
      this.updateFocusableElements();

      if (this.focusableElements.length === 0) return;

      // Shift+Tab (backwards)
      if (event.shiftKey) {
        if (document.activeElement === this.firstFocusable) {
          event.preventDefault();
          this.lastFocusable.focus();
        }
      }
      // Tab (forwards)
      else {
        if (document.activeElement === this.lastFocusable) {
          event.preventDefault();
          this.firstFocusable.focus();
        }
      }
    }
  }

  /**
   * Handle focusin events to prevent focus from escaping
   * @param {FocusEvent} event - Focus event
   */
  handleFocusIn(event) {
    if (!this.isActive) return;

    // If focus moved outside the trap, move it back
    if (!this.element.contains(event.target)) {
      event.stopPropagation();
      if (this.firstFocusable) {
        this.firstFocusable.focus();
      }
    }
  }

  /**
   * Pause the focus trap temporarily
   * Useful when opening a nested modal
   */
  pause() {
    if (!this.isActive) return;
    document.removeEventListener('keydown', this.handleKeyDown, true);
    this.element.removeEventListener('focusin', this.handleFocusIn, true);
  }

  /**
   * Resume the focus trap after pausing
   */
  resume() {
    if (!this.isActive) return;
    document.addEventListener('keydown', this.handleKeyDown, true);
    this.element.addEventListener('focusin', this.handleFocusIn, true);
  }
}

/**
 * Simple helper to create and manage a focus trap
 *
 * @param {HTMLElement} element - Element to trap focus within
 * @param {Object} options - Focus trap options
 * @returns {FocusTrap} Focus trap instance
 *
 * @example
 * const trap = createFocusTrap(modalElement, {
 *   onEscape: () => modal.close()
 * });
 * trap.activate();
 */
export function createFocusTrap(element, options = {}) {
  return new FocusTrap(element, options);
}

// Make available globally for non-module scripts
if (typeof window !== 'undefined') {
  window.FocusTrap = FocusTrap;
  window.createFocusTrap = createFocusTrap;
}
