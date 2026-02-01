/**
 * Loading State Utility
 *
 * Provides consistent loading indicators for async operations across the application.
 * Supports buttons, containers, and full-screen overlays with accessibility features.
 *
 * @module utils/loading-state
 */

/**
 * LoadingState Manager
 *
 * @example
 * const loader = new LoadingState();
 *
 * // Button loading
 * loader.showButtonLoading(button, 'Saving...');
 * await saveData();
 * loader.hideButtonLoading(button, 'Save');
 *
 * // Container loading
 * loader.showContainerLoading(container, 'Loading events...');
 * await fetchEvents();
 * loader.hideContainerLoading(container);
 */
export class LoadingState {
  constructor() {
    this.loadingStates = new WeakMap();
  }

  /**
   * Show loading state on a button
   * @param {HTMLElement} button - Button element
   * @param {string} loadingText - Text to show during loading (optional)
   */
  showButtonLoading(button, loadingText = null) {
    if (!button) return;

    // Store original state
    const originalState = {
      text: button.textContent,
      disabled: button.disabled,
      innerHTML: button.innerHTML
    };
    this.loadingStates.set(button, originalState);

    // Set loading state
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');

    // Create spinner
    const spinner = document.createElement('span');
    spinner.className = 'btn-spinner';
    spinner.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10" stroke-opacity="0.3" />
        <path d="M12 2 A10 10 0 0 1 22 12" stroke-linecap="round">
          <animateTransform
            attributeName="transform"
            attributeType="XML"
            type="rotate"
            from="0 12 12"
            to="360 12 12"
            dur="1s"
            repeatCount="indefinite"/>
        </path>
      </svg>
    `;

    button.innerHTML = '';
    button.appendChild(spinner);

    if (loadingText) {
      const text = document.createElement('span');
      text.textContent = loadingText;
      text.style.marginLeft = '8px';
      button.appendChild(text);
    }
  }

  /**
   * Hide loading state from a button
   * @param {HTMLElement} button - Button element
   * @param {string} text - Text to restore (optional, uses original if not provided)
   */
  hideButtonLoading(button, text = null) {
    if (!button) return;

    const originalState = this.loadingStates.get(button);
    if (!originalState) return;

    // Restore state
    button.disabled = originalState.disabled;
    button.removeAttribute('aria-busy');
    button.innerHTML = text || originalState.innerHTML;

    this.loadingStates.delete(button);
  }

  /**
   * Show loading state in a container
   * @param {HTMLElement} container - Container element
   * @param {string} message - Loading message (optional)
   */
  showContainerLoading(container, message = 'Loading...') {
    if (!container) return;

    // Store original content
    const originalState = {
      content: container.innerHTML,
      ariaBusy: container.getAttribute('aria-busy')
    };
    this.loadingStates.set(container, originalState);

    // Set loading state
    container.setAttribute('aria-busy', 'true');
    container.setAttribute('aria-live', 'polite');

    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'container-loading';
    loadingDiv.innerHTML = `
      <div class="loading-spinner-wrapper">
        <svg class="loading-spinner" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" stroke-opacity="0.3" />
          <path d="M12 2 A10 10 0 0 1 22 12" stroke-linecap="round">
            <animateTransform
              attributeName="transform"
              attributeType="XML"
              type="rotate"
              from="0 12 12"
              to="360 12 12"
              dur="1s"
              repeatCount="indefinite"/>
          </path>
        </svg>
        <p class="loading-message">${message}</p>
      </div>
    `;

    container.innerHTML = '';
    container.appendChild(loadingDiv);
  }

  /**
   * Hide loading state from a container
   * @param {HTMLElement} container - Container element
   */
  hideContainerLoading(container) {
    if (!container) return;

    const originalState = this.loadingStates.get(container);
    if (!originalState) return;

    // Restore state
    container.removeAttribute('aria-busy');
    container.removeAttribute('aria-live');
    if (originalState.ariaBusy !== null) {
      container.setAttribute('aria-busy', originalState.ariaBusy);
    }
    container.innerHTML = originalState.content;

    this.loadingStates.delete(container);
  }

  /**
   * Show full-screen loading overlay
   * @param {string} message - Loading message
   * @returns {HTMLElement} Overlay element (for manual cleanup if needed)
   */
  showOverlay(message = 'Loading...') {
    // Check if overlay already exists
    let overlay = document.getElementById('loading-overlay');
    if (overlay) {
      // Update message if overlay exists
      const messageEl = overlay.querySelector('.loading-overlay-message');
      if (messageEl) {
        messageEl.textContent = message;
      }
      return overlay;
    }

    overlay = document.createElement('div');
    overlay.id = 'loading-overlay';
    overlay.className = 'loading-overlay';
    overlay.setAttribute('role', 'status');
    overlay.setAttribute('aria-live', 'polite');
    overlay.innerHTML = `
      <div class="loading-overlay-content">
        <svg class="loading-overlay-spinner" width="60" height="60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" stroke-opacity="0.3" />
          <path d="M12 2 A10 10 0 0 1 22 12" stroke-linecap="round">
            <animateTransform
              attributeName="transform"
              attributeType="XML"
              type="rotate"
              from="0 12 12"
              to="360 12 12"
              dur="1s"
              repeatCount="indefinite"/>
          </path>
        </svg>
        <p class="loading-overlay-message">${message}</p>
      </div>
    `;

    document.body.appendChild(overlay);

    // Prevent scrolling
    document.body.style.overflow = 'hidden';

    return overlay;
  }

  /**
   * Hide full-screen loading overlay
   */
  hideOverlay() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
      overlay.remove();
      document.body.style.overflow = '';
    }
  }
}

// Create singleton instance
export const loadingState = new LoadingState();

// Make available globally for non-module scripts
if (typeof window !== 'undefined') {
  window.loadingState = loadingState;
}
