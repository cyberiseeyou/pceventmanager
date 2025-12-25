/**
 * Modal Component
 *
 * Reusable modal dialog component with accessibility features.
 * Provides consistent modal behavior across the application.
 *
 * Epic 1, Story 1.6: Create Shared Modal Component Foundation
 *
 * @module components/modal
 *
 * @example
 * import { Modal } from './components/modal.js';
 *
 * const modal = new Modal();
 * modal.open('<h2>Hello World</h2><p>This is a modal!</p>', {
 *   title: 'Welcome',
 *   size: 'medium',
 *   closeButton: true
 * });
 *
 * // Later...
 * modal.close();
 */

import { FocusTrap } from '../modules/focus-trap.js';

/**
 * Modal Dialog Component
 * Manages modal creation, display, and lifecycle
 */
export class Modal {
  /**
   * Create a modal instance
   * @param {Object} config - Configuration options
   * @param {string} config.id - Unique modal ID (auto-generated if not provided)
   */
  constructor(config = {}) {
    this.id = config.id || `modal-${Date.now()}`;
    this.isOpen = false;
    this.overlay = null;
    this.container = null;
    this.focusTrap = null;

    // Bind methods for event listeners
    this._handleOverlayClick = this._handleOverlayClick.bind(this);
    this._handleEscape = this._handleEscape.bind(this);
    this._handleCloseButton = this._handleCloseButton.bind(this);
  }

  /**
   * Open the modal with content and options
   *
   * @param {string|HTMLElement} content - Modal body content (HTML string or DOM element)
   * @param {Object} options - Display options
   * @param {string} [options.title] - Modal title
   * @param {string} [options.size="medium"] - Modal size: "small", "medium", or "large"
   * @param {boolean} [options.closeButton=true] - Show close button
   * @param {Function} [options.onClose] - Callback when modal closes
   *
   * @example
   * modal.open('<p>Content here</p>', {
   *   title: 'My Modal',
   *   size: 'large',
   *   closeButton: true
   * });
   */
  open(content, options = {}) {
    if (this.isOpen) {
      console.warn('[Modal] Modal already open, closing previous instance');
      this.close();
    }

    // Default options
    const opts = {
      title: options.title || '',
      size: options.size || 'medium',
      closeButton: options.closeButton !== false,
      onClose: options.onClose || null
    };

    this.options = opts;

    // Create modal structure
    this._createModal(content, opts);

    // Show modal
    this._show();

    // Emit open event
    this._emitEvent('modal-opened', { id: this.id, options: opts });

    console.log(`[Modal] Opened: ${this.id}`);
  }

  /**
   * Close the modal
   * @param {boolean} skipCallback - Skip onClose callback (default: false)
   */
  close(skipCallback = false) {
    if (!this.isOpen) return;

    // Deactivate focus trap
    if (this.focusTrap) {
      this.focusTrap.deactivate();
      this.focusTrap = null;
    }

    // Restore body scrolling
    document.body.style.overflow = '';

    // Remove overlay
    if (this.overlay && this.overlay.parentNode) {
      this.overlay.parentNode.removeChild(this.overlay);
    }

    this.isOpen = false;
    this.overlay = null;
    this.container = null;

    // Call onClose callback if provided
    if (!skipCallback && this.options && this.options.onClose) {
      this.options.onClose();
    }

    // Emit close event
    this._emitEvent('modal-closed', { id: this.id });

    console.log(`[Modal] Closed: ${this.id}`);
  }

  /**
   * Destroy the modal instance
   * Closes the modal and removes all references
   */
  destroy() {
    this.close(true);
    console.log(`[Modal] Destroyed: ${this.id}`);
  }

  /**
   * Create modal DOM structure
   * @param {string|HTMLElement} content - Modal content
   * @param {Object} opts - Display options
   * @private
   */
  _createModal(content, opts) {
    // Create overlay
    this.overlay = document.createElement('div');
    this.overlay.className = 'modal__overlay';
    this.overlay.id = `${this.id}-overlay`;
    this.overlay.addEventListener('click', this._handleOverlayClick);

    // Create container
    this.container = document.createElement('div');
    this.container.className = `modal__container modal__container--${opts.size}`;
    this.container.id = `${this.id}-container`;
    this.container.setAttribute('role', 'dialog');
    this.container.setAttribute('aria-modal', 'true');
    if (opts.title) {
      this.container.setAttribute('aria-labelledby', `${this.id}-title`);
    }

    // Stop clicks inside container from closing modal
    this.container.addEventListener('click', (e) => {
      e.stopPropagation();
    });

    // Listen for escape key from focus trap
    this.container.addEventListener('escape', this._handleEscape);

    // Create header (if title or close button)
    if (opts.title || opts.closeButton) {
      const header = document.createElement('div');
      header.className = 'modal__header';

      if (opts.title) {
        const title = document.createElement('h2');
        title.className = 'modal__title';
        title.id = `${this.id}-title`;
        title.textContent = opts.title;
        header.appendChild(title);
      }

      if (opts.closeButton) {
        const closeBtn = document.createElement('button');
        closeBtn.className = 'modal__close';
        closeBtn.type = 'button';
        closeBtn.setAttribute('aria-label', 'Close modal');
        closeBtn.innerHTML = '&times;';
        closeBtn.addEventListener('click', this._handleCloseButton);
        header.appendChild(closeBtn);
      }

      this.container.appendChild(header);
    }

    // Create body
    const body = document.createElement('div');
    body.className = 'modal__body';

    // Insert content (HTML string or DOM element)
    if (typeof content === 'string') {
      body.innerHTML = content;
    } else if (content instanceof HTMLElement) {
      body.appendChild(content);
    }

    this.container.appendChild(body);

    // Append to overlay
    this.overlay.appendChild(this.container);

    // Append to body
    document.body.appendChild(this.overlay);
  }

  /**
   * Show the modal (activate focus trap and prevent body scroll)
   * @private
   */
  _show() {
    // Prevent body scrolling
    document.body.style.overflow = 'hidden';

    // Mark as open
    this.isOpen = true;

    // Activate focus trap
    this.focusTrap = new FocusTrap(this.container);
    this.focusTrap.activate();

    // Add animation class
    requestAnimationFrame(() => {
      this.overlay.classList.add('modal__overlay--open');
    });
  }

  /**
   * Handle overlay click (close modal)
   * @param {MouseEvent} e - Click event
   * @private
   */
  _handleOverlayClick(e) {
    // Only close if clicking directly on overlay (not container)
    if (e.target === this.overlay) {
      this.close();
    }
  }

  /**
   * Handle escape key (close modal)
   * @param {CustomEvent} e - Escape event from focus trap
   * @private
   */
  _handleEscape(e) {
    this.close();
  }

  /**
   * Handle close button click
   * @param {MouseEvent} e - Click event
   * @private
   */
  _handleCloseButton(e) {
    e.preventDefault();
    this.close();
  }

  /**
   * Emit custom event
   * @param {string} eventName - Event name
   * @param {Object} detail - Event detail object
   * @private
   */
  _emitEvent(eventName, detail) {
    const event = new CustomEvent(eventName, {
      detail: detail,
      bubbles: true,
      cancelable: true
    });
    document.dispatchEvent(event);
  }

  /**
   * Get modal open state
   * @returns {boolean} True if modal is open
   */
  get open() {
    return this.isOpen;
  }
}

/**
 * Create and immediately open a modal (convenience function)
 * @param {string|HTMLElement} content - Modal content
 * @param {Object} options - Modal options
 * @returns {Modal} Modal instance
 */
export function createModal(content, options = {}) {
  const modal = new Modal();
  modal.open(content, options);
  return modal;
}
