/**
 * Toast Notifications Module
 *
 * Provides non-intrusive notification system for user feedback (success, error,
 * warning, info messages). Includes accessibility support and customizable styling.
 *
 * Epic 1 & 2: UX Enhancement Infrastructure
 * Priority 2: Core Infrastructure - Required for FR17 (User Feedback)
 *
 * Architecture Reference: Section 2.4 (lines 316-467)
 *
 * @module modules/toast-notifications
 */

import { ariaAnnouncer } from './aria-announcer.js';

/**
 * Toast Manager for displaying notifications
 *
 * Manages a queue of toast notifications with automatic dismissal,
 * progress indicators, and accessibility features.
 *
 * @example
 * const toaster = new ToastManager({ position: 'top-right' });
 * toaster.success('Schedule saved successfully');
 * toaster.error('Failed to save schedule');
 * toaster.warning('Employee has conflicting availability');
 * toaster.info('5 new schedules pending approval');
 */
export class ToastManager {
  /**
   * Create a Toast Manager
   *
   * @param {Object} options - Configuration options
   * @param {string} options.position - Toast position: 'top-right', 'top-left', 'bottom-right', 'bottom-left', 'top-center', 'bottom-center' (default: 'top-right')
   * @param {number} options.duration - Default auto-dismiss duration in ms (default: 5000, 0 = no auto-dismiss)
   * @param {number} options.maxToasts - Maximum concurrent toasts (default: 5)
   * @param {boolean} options.pauseOnHover - Pause auto-dismiss on hover (default: true)
   * @param {boolean} options.newestOnTop - Show newest toasts first (default: true)
   * @param {boolean} options.announceToScreenReader - Announce toasts to screen readers (default: true)
   */
  constructor(options = {}) {
    this.options = {
      position: 'top-right',
      duration: 5000,
      maxToasts: 5,
      pauseOnHover: true,
      newestOnTop: true,
      announceToScreenReader: true,
      ...options
    };

    this.toasts = [];
    this.container = null;

    this._initializeContainer();
    console.log('[ToastManager] Initialized at position:', this.options.position);
  }

  // =============================================================================
  // Public Methods - Show Toasts
  // =============================================================================

  /**
   * Show a success toast
   *
   * @param {string} message - Toast message
   * @param {Object} options - Toast-specific options
   * @returns {string} Toast ID
   *
   * @example
   * toaster.success('Schedule saved successfully');
   */
  success(message, options = {}) {
    return this.show(message, { ...options, type: 'success' });
  }

  /**
   * Show an error toast
   *
   * @param {string} message - Toast message
   * @param {Object} options - Toast-specific options
   * @returns {string} Toast ID
   *
   * @example
   * toaster.error('Failed to save schedule');
   */
  error(message, options = {}) {
    return this.show(message, { ...options, type: 'error' });
  }

  /**
   * Show a warning toast
   *
   * @param {string} message - Toast message
   * @param {Object} options - Toast-specific options
   * @returns {string} Toast ID
   *
   * @example
   * toaster.warning('Employee has conflicting availability');
   */
  warning(message, options = {}) {
    return this.show(message, { ...options, type: 'warning' });
  }

  /**
   * Show an info toast
   *
   * @param {string} message - Toast message
   * @param {Object} options - Toast-specific options
   * @returns {string} Toast ID
   *
   * @example
   * toaster.info('5 new schedules pending approval');
   */
  info(message, options = {}) {
    return this.show(message, { ...options, type: 'info' });
  }

  /**
   * Show a toast notification
   *
   * @param {string} message - Toast message
   * @param {Object} options - Toast options
   * @param {string} options.type - Toast type: 'success', 'error', 'warning', 'info' (default: 'info')
   * @param {number} options.duration - Auto-dismiss duration in ms (0 = no auto-dismiss)
   * @param {boolean} options.dismissible - Show close button (default: true)
   * @param {Function} options.onClick - Callback when toast is clicked
   * @param {Function} options.onClose - Callback when toast is closed
   * @param {string} options.icon - Custom icon HTML or class
   * @returns {string} Toast ID
   *
   * @example
   * toaster.show('Custom notification', {
   *   type: 'success',
   *   duration: 3000,
   *   onClick: () => console.log('Toast clicked'),
   *   onClose: () => console.log('Toast closed')
   * });
   */
  show(message, options = {}) {
    const toastOptions = {
      type: 'info',
      duration: this.options.duration,
      dismissible: true,
      ...options
    };

    // Generate unique ID
    const id = `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

    // Create toast object
    const toast = {
      id,
      message,
      ...toastOptions,
      element: null,
      timer: null,
      progressBar: null
    };

    // Remove oldest toast if at max capacity
    if (this.toasts.length >= this.options.maxToasts) {
      const oldestToast = this.options.newestOnTop
        ? this.toasts[this.toasts.length - 1]
        : this.toasts[0];
      this.dismiss(oldestToast.id);
    }

    // Create toast element
    toast.element = this._createToastElement(toast);

    // Add to container
    if (this.options.newestOnTop) {
      this.container.insertBefore(toast.element, this.container.firstChild);
      this.toasts.unshift(toast);
    } else {
      this.container.appendChild(toast.element);
      this.toasts.push(toast);
    }

    // Trigger animation
    requestAnimationFrame(() => {
      toast.element.classList.add('toast--show');
    });

    // Auto-dismiss if duration > 0
    if (toast.duration > 0) {
      this._startAutoDismiss(toast);
    }

    // Announce to screen readers
    if (this.options.announceToScreenReader) {
      const priority = toast.type === 'error' ? 'assertive' : 'polite';
      ariaAnnouncer.announce(message, priority);
    }

    console.log(`[ToastManager] Showed ${toast.type} toast:`, message);
    return id;
  }

  /**
   * Dismiss a toast by ID
   *
   * @param {string} id - Toast ID
   *
   * @example
   * const toastId = toaster.success('Saved');
   * setTimeout(() => toaster.dismiss(toastId), 1000);
   */
  dismiss(id) {
    const toastIndex = this.toasts.findIndex(t => t.id === id);
    if (toastIndex === -1) {
      return;
    }

    const toast = this.toasts[toastIndex];

    // Clear timer if exists
    if (toast.timer) {
      clearTimeout(toast.timer);
    }

    // Trigger exit animation
    toast.element.classList.add('toast--hide');

    // Remove from DOM after animation
    setTimeout(() => {
      if (toast.element && toast.element.parentNode) {
        toast.element.remove();
      }

      // Remove from array
      this.toasts.splice(toastIndex, 1);

      // Call onClose callback
      if (toast.onClose) {
        toast.onClose();
      }

      console.log(`[ToastManager] Dismissed toast: ${id}`);
    }, 300); // Match CSS animation duration
  }

  /**
   * Dismiss all toasts
   *
   * @example
   * toaster.dismissAll();
   */
  dismissAll() {
    const toastIds = this.toasts.map(t => t.id);
    toastIds.forEach(id => this.dismiss(id));
  }

  /**
   * Update an existing toast
   *
   * @param {string} id - Toast ID
   * @param {Object} updates - Properties to update
   *
   * @example
   * const toastId = toaster.info('Saving...');
   * // Later:
   * toaster.update(toastId, {
   *   type: 'success',
   *   message: 'Saved successfully'
   * });
   */
  update(id, updates) {
    const toast = this.toasts.find(t => t.id === id);
    if (!toast) {
      return;
    }

    // Update message if provided
    if (updates.message) {
      toast.message = updates.message;
      const messageElement = toast.element.querySelector('.toast__message');
      if (messageElement) {
        messageElement.textContent = updates.message;
      }
    }

    // Update type if provided
    if (updates.type && updates.type !== toast.type) {
      toast.element.classList.remove(`toast--${toast.type}`);
      toast.element.classList.add(`toast--${updates.type}`);
      toast.type = updates.type;

      // Update icon
      const iconElement = toast.element.querySelector('.toast__icon');
      if (iconElement) {
        iconElement.innerHTML = this._getIconHtml(updates.type);
      }
    }

    // Reset timer if duration changed
    if (updates.duration !== undefined && updates.duration !== toast.duration) {
      if (toast.timer) {
        clearTimeout(toast.timer);
      }
      toast.duration = updates.duration;
      if (toast.duration > 0) {
        this._startAutoDismiss(toast);
      }
    }

    console.log(`[ToastManager] Updated toast: ${id}`);
  }

  // =============================================================================
  // Private Methods - Toast Creation
  // =============================================================================

  /**
   * Create toast HTML element
   *
   * @param {Object} toast - Toast object
   * @returns {HTMLElement} Toast element
   * @private
   */
  _createToastElement(toast) {
    const element = document.createElement('div');
    element.className = `toast toast--${toast.type}`;
    element.id = toast.id;
    element.setAttribute('role', 'status');
    element.setAttribute('aria-live', toast.type === 'error' ? 'assertive' : 'polite');

    // Icon
    const icon = document.createElement('div');
    icon.className = 'toast__icon';
    icon.innerHTML = toast.icon || this._getIconHtml(toast.type);
    element.appendChild(icon);

    // Content
    const content = document.createElement('div');
    content.className = 'toast__content';

    const message = document.createElement('div');
    message.className = 'toast__message';
    message.textContent = toast.message;
    content.appendChild(message);

    element.appendChild(content);

    // Close button
    if (toast.dismissible) {
      const closeButton = document.createElement('button');
      closeButton.className = 'toast__close';
      closeButton.setAttribute('type', 'button');
      closeButton.setAttribute('aria-label', 'Close notification');
      closeButton.innerHTML = '&times;';
      closeButton.addEventListener('click', (e) => {
        e.stopPropagation();
        this.dismiss(toast.id);
      });
      element.appendChild(closeButton);
    }

    // Progress bar
    if (toast.duration > 0) {
      const progressBar = document.createElement('div');
      progressBar.className = 'toast__progress';
      element.appendChild(progressBar);
      toast.progressBar = progressBar;
    }

    // Click handler
    if (toast.onClick) {
      element.style.cursor = 'pointer';
      element.addEventListener('click', () => {
        toast.onClick();
        this.dismiss(toast.id);
      });
    }

    // Pause on hover
    if (this.options.pauseOnHover && toast.duration > 0) {
      element.addEventListener('mouseenter', () => {
        this._pauseAutoDismiss(toast);
      });
      element.addEventListener('mouseleave', () => {
        this._resumeAutoDismiss(toast);
      });
    }

    return element;
  }

  /**
   * Get icon HTML for toast type
   *
   * @param {string} type - Toast type
   * @returns {string} Icon HTML
   * @private
   */
  _getIconHtml(type) {
    const icons = {
      success: `
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <circle cx="10" cy="10" r="9" stroke="currentColor" stroke-width="2"/>
          <path d="M6 10l3 3 5-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      `,
      error: `
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <circle cx="10" cy="10" r="9" stroke="currentColor" stroke-width="2"/>
          <path d="M7 7l6 6M13 7l-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
      `,
      warning: `
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <path d="M10 2L2 17h16L10 2z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
          <path d="M10 8v4M10 14v1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
      `,
      info: `
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <circle cx="10" cy="10" r="9" stroke="currentColor" stroke-width="2"/>
          <path d="M10 10v4M10 6v1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
      `
    };

    return icons[type] || icons.info;
  }

  // =============================================================================
  // Private Methods - Auto-Dismiss
  // =============================================================================

  /**
   * Start auto-dismiss timer with progress bar animation
   *
   * @param {Object} toast - Toast object
   * @private
   */
  _startAutoDismiss(toast) {
    if (toast.timer) {
      clearTimeout(toast.timer);
    }

    // Set timer
    toast.timer = setTimeout(() => {
      this.dismiss(toast.id);
    }, toast.duration);

    // Animate progress bar
    if (toast.progressBar) {
      toast.progressBar.style.transition = 'none';
      toast.progressBar.style.width = '100%';

      requestAnimationFrame(() => {
        toast.progressBar.style.transition = `width ${toast.duration}ms linear`;
        toast.progressBar.style.width = '0%';
      });
    }
  }

  /**
   * Pause auto-dismiss timer
   *
   * @param {Object} toast - Toast object
   * @private
   */
  _pauseAutoDismiss(toast) {
    if (!toast.timer) {
      return;
    }

    clearTimeout(toast.timer);
    toast.timer = null;

    // Pause progress bar animation
    if (toast.progressBar) {
      const computedStyle = window.getComputedStyle(toast.progressBar);
      const currentWidth = computedStyle.width;
      toast.progressBar.style.transition = 'none';
      toast.progressBar.style.width = currentWidth;
      toast.pausedWidth = currentWidth;
    }
  }

  /**
   * Resume auto-dismiss timer
   *
   * @param {Object} toast - Toast object
   * @private
   */
  _resumeAutoDismiss(toast) {
    if (toast.timer || toast.duration <= 0) {
      return;
    }

    // Calculate remaining time based on progress bar width
    let remainingTime = toast.duration;
    if (toast.progressBar && toast.pausedWidth) {
      const pausedPercent = parseFloat(toast.pausedWidth) / toast.element.offsetWidth;
      remainingTime = toast.duration * pausedPercent;
    }

    // Restart timer with remaining time
    toast.timer = setTimeout(() => {
      this.dismiss(toast.id);
    }, remainingTime);

    // Resume progress bar animation
    if (toast.progressBar) {
      requestAnimationFrame(() => {
        toast.progressBar.style.transition = `width ${remainingTime}ms linear`;
        toast.progressBar.style.width = '0%';
      });
    }
  }

  // =============================================================================
  // Private Methods - Container
  // =============================================================================

  /**
   * Initialize toast container in DOM
   * @private
   */
  _initializeContainer() {
    // Create container
    this.container = document.createElement('div');
    this.container.id = 'toast-container';
    this.container.className = `toast-container toast-container--${this.options.position}`;
    this.container.setAttribute('aria-live', 'polite');
    this.container.setAttribute('aria-atomic', 'false');

    // Inject styles
    this._injectStyles();

    // Add to DOM
    document.body.appendChild(this.container);
  }

  /**
   * Inject CSS styles for toasts
   * @private
   */
  _injectStyles() {
    // Check if styles already injected
    if (document.getElementById('toast-styles')) {
      return;
    }

    const styles = document.createElement('style');
    styles.id = 'toast-styles';
    styles.textContent = `
      .toast-container {
        position: fixed;
        z-index: 9999;
        pointer-events: none;
        display: flex;
        flex-direction: column;
        gap: 12px;
        max-width: 400px;
        padding: 16px;
      }

      .toast-container--top-right {
        top: 0;
        right: 0;
      }

      .toast-container--top-left {
        top: 0;
        left: 0;
      }

      .toast-container--bottom-right {
        bottom: 0;
        right: 0;
      }

      .toast-container--bottom-left {
        bottom: 0;
        left: 0;
      }

      .toast-container--top-center {
        top: 0;
        left: 50%;
        transform: translateX(-50%);
      }

      .toast-container--bottom-center {
        bottom: 0;
        left: 50%;
        transform: translateX(-50%);
      }

      .toast {
        pointer-events: auto;
        display: flex;
        align-items: flex-start;
        gap: 12px;
        padding: 16px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        background: white;
        color: #333;
        opacity: 0;
        transform: translateY(-20px);
        transition: opacity 0.3s ease, transform 0.3s ease;
        position: relative;
        overflow: hidden;
        min-width: 300px;
        max-width: 100%;
      }

      .toast--show {
        opacity: 1;
        transform: translateY(0);
      }

      .toast--hide {
        opacity: 0;
        transform: translateX(100%);
      }

      .toast__icon {
        flex-shrink: 0;
        width: 20px;
        height: 20px;
        margin-top: 2px;
      }

      .toast--success {
        border-left: 4px solid #10b981;
      }

      .toast--success .toast__icon {
        color: #10b981;
      }

      .toast--error {
        border-left: 4px solid #ef4444;
      }

      .toast--error .toast__icon {
        color: #ef4444;
      }

      .toast--warning {
        border-left: 4px solid #f59e0b;
      }

      .toast--warning .toast__icon {
        color: #f59e0b;
      }

      .toast--info {
        border-left: 4px solid #3b82f6;
      }

      .toast--info .toast__icon {
        color: #3b82f6;
      }

      .toast__content {
        flex: 1;
        min-width: 0;
      }

      .toast__message {
        font-size: 14px;
        line-height: 1.5;
        word-wrap: break-word;
      }

      .toast__close {
        flex-shrink: 0;
        background: none;
        border: none;
        font-size: 24px;
        line-height: 1;
        color: #666;
        cursor: pointer;
        padding: 0;
        margin: -4px -4px 0 0;
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 4px;
        transition: background 0.2s ease, color 0.2s ease;
      }

      .toast__close:hover {
        background: rgba(0, 0, 0, 0.05);
        color: #333;
      }

      .toast__close:focus {
        outline: 2px solid #3b82f6;
        outline-offset: 2px;
      }

      .toast__progress {
        position: absolute;
        bottom: 0;
        left: 0;
        height: 4px;
        background: currentColor;
        opacity: 0.3;
        width: 100%;
      }

      @media (max-width: 480px) {
        .toast-container {
          max-width: 100%;
          padding: 12px;
        }

        .toast {
          min-width: auto;
          width: 100%;
        }
      }
    `;

    document.head.appendChild(styles);
  }

  /**
   * Destroy the toast manager and remove all toasts
   */
  destroy() {
    this.dismissAll();
    if (this.container) {
      this.container.remove();
      this.container = null;
    }
    console.log('[ToastManager] Destroyed');
  }
}

// Export singleton instance for global use
export const toaster = new ToastManager();

// Make globally available for non-module contexts
if (typeof window !== 'undefined') {
  window.toaster = toaster;
}
