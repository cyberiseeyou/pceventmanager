/**
 * Focus Trap Module
 *
 * Traps keyboard focus inside a container element for accessibility.
 * Used by modal dialogs to prevent keyboard users from tabbing outside the modal.
 *
 * Epic 1, Story 1.6: Create Shared Modal Component Foundation
 * Task 1: Create Focus Trap Module
 *
 * @module modules/focus-trap
 *
 * @example
 * import { FocusTrap } from './modules/focus-trap.js';
 *
 * const modal = document.querySelector('.modal');
 * const trap = new FocusTrap(modal);
 * trap.activate();
 *
 * // Later...
 * trap.deactivate();
 */

/**
 * Focus Trap Class
 * Manages keyboard focus within a container element
 */
export class FocusTrap {
  /**
   * Create a focus trap
   * @param {HTMLElement} element - Container element to trap focus within
   */
  constructor(element) {
    this.element = element;

    // Focusable elements selector
    this.focusableSelectors = [
      'button:not([disabled])',
      '[href]',
      'input:not([disabled])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])'
    ].join(', ');

    this.previousFocus = null;
    this.firstFocusable = null;
    this.lastFocusable = null;
    this.isActive = false;

    // Bind methods for event listeners
    this._handleKeyDown = this._handleKeyDown.bind(this);
  }

  /**
   * Activate the focus trap
   * Stores current focus and sets focus to first focusable element
   */
  activate() {
    if (this.isActive) return;

    // Store current focus to restore later
    this.previousFocus = document.activeElement;

    // Get all focusable elements
    this._updateFocusableElements();

    // Activate trap
    this.isActive = true;
    this.element.addEventListener('keydown', this._handleKeyDown);

    // Focus first element
    if (this.firstFocusable) {
      this.firstFocusable.focus();
    }

    console.log('[FocusTrap] Activated');
  }

  /**
   * Deactivate the focus trap
   * Restores focus to previously focused element
   */
  deactivate() {
    if (!this.isActive) return;

    this.isActive = false;
    this.element.removeEventListener('keydown', this._handleKeyDown);

    // Restore focus
    if (this.previousFocus && document.contains(this.previousFocus)) {
      this.previousFocus.focus();
    }

    console.log('[FocusTrap] Deactivated');
  }

  /**
   * Update the list of focusable elements
   * Call this if the modal content changes dynamically
   * @private
   */
  _updateFocusableElements() {
    const focusable = this.element.querySelectorAll(this.focusableSelectors);
    this.firstFocusable = focusable[0] || null;
    this.lastFocusable = focusable[focusable.length - 1] || null;
  }

  /**
   * Handle keyboard events
   * @param {KeyboardEvent} e - Keyboard event
   * @private
   */
  _handleKeyDown(e) {
    if (e.key === 'Tab') {
      this._handleTab(e);
    } else if (e.key === 'Escape') {
      this._handleEscape(e);
    }
  }

  /**
   * Handle Tab key to trap focus
   * @param {KeyboardEvent} e - Keyboard event
   * @private
   */
  _handleTab(e) {
    // Update focusable elements in case content changed
    this._updateFocusableElements();

    // If no focusable elements, prevent tab
    if (!this.firstFocusable) {
      e.preventDefault();
      return;
    }

    // Shift+Tab on first element -> go to last
    if (e.shiftKey && document.activeElement === this.firstFocusable) {
      e.preventDefault();
      this.lastFocusable.focus();
    }
    // Tab on last element -> go to first
    else if (!e.shiftKey && document.activeElement === this.lastFocusable) {
      e.preventDefault();
      this.firstFocusable.focus();
    }
  }

  /**
   * Handle Escape key to emit event
   * @param {KeyboardEvent} e - Keyboard event
   * @private
   */
  _handleEscape(e) {
    // Emit custom event for parent component to handle
    this.element.dispatchEvent(new CustomEvent('escape', {
      bubbles: true,
      cancelable: true
    }));

    console.log('[FocusTrap] Escape key pressed');
  }

  /**
   * Check if trap is active
   * @returns {boolean}
   */
  get active() {
    return this.isActive;
  }
}
