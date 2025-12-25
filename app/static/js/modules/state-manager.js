/**
 * State Manager Module
 *
 * Centralized state management for user preferences, session data, saved searches,
 * and URL state. Provides a consistent API for persisting and retrieving application state.
 *
 * Epic 1 & 2: UX Enhancement Infrastructure
 * Priority 2: Required for FR6 (Saved Searches), FR11 (Calendar Filters), FR14 (URL State), FR28 (Preferences)
 *
 * Architecture Reference: Section 2.2 (lines 174-227)
 *
 * @module modules/state-manager
 */

/**
 * State Manager for application-wide state persistence
 *
 * Handles four types of state:
 * 1. User Preferences - Long-term settings (localStorage)
 * 2. Session Filters - Temporary filters (sessionStorage)
 * 3. Saved Searches - Named search configurations (localStorage)
 * 4. URL State - Browser history and shareable URLs (History API)
 *
 * @example
 * const manager = new StateManager();
 * manager.saveUserPreference('theme', 'dark');
 * manager.saveSessionFilter('event_type', 'Core');
 * manager.saveSavedSearch('my-search', { date: '2025-10-15', employee: 'EMP001' });
 */
export class StateManager {
  /**
   * Create a State Manager
   *
   * @param {string} namespace - Namespace prefix for storage keys (default: 'scheduler')
   */
  constructor(namespace = 'scheduler') {
    this.namespace = namespace;
    this.storageAvailable = this._checkStorageAvailability();

    if (!this.storageAvailable) {
      console.warn('[StateManager] localStorage/sessionStorage not available. State persistence disabled.');
    }
  }

  // =============================================================================
  // User Preferences (localStorage - persistent across sessions)
  // =============================================================================

  /**
   * Save a user preference to localStorage
   *
   * @param {string} key - Preference key
   * @param {any} value - Preference value (will be JSON serialized)
   * @returns {boolean} Success status
   *
   * @example
   * manager.saveUserPreference('default_view', 'calendar');
   * manager.saveUserPreference('rows_per_page', 25);
   */
  saveUserPreference(key, value) {
    if (!this.storageAvailable) {
      return false;
    }

    try {
      const storageKey = `${this.namespace}:pref:${key}`;
      localStorage.setItem(storageKey, JSON.stringify(value));
      console.log(`[StateManager] Saved preference: ${key}`, value);
      return true;
    } catch (error) {
      console.error(`[StateManager] Failed to save preference: ${key}`, error);
      return false;
    }
  }

  /**
   * Get a user preference from localStorage
   *
   * @param {string} key - Preference key
   * @param {any} defaultValue - Default value if preference not found
   * @returns {any} Preference value or default
   *
   * @example
   * const view = manager.getUserPreference('default_view', 'dashboard');
   */
  getUserPreference(key, defaultValue = null) {
    if (!this.storageAvailable) {
      return defaultValue;
    }

    try {
      const storageKey = `${this.namespace}:pref:${key}`;
      const item = localStorage.getItem(storageKey);
      return item !== null ? JSON.parse(item) : defaultValue;
    } catch (error) {
      console.error(`[StateManager] Failed to get preference: ${key}`, error);
      return defaultValue;
    }
  }

  /**
   * Delete a user preference
   *
   * @param {string} key - Preference key
   * @returns {boolean} Success status
   */
  deleteUserPreference(key) {
    if (!this.storageAvailable) {
      return false;
    }

    try {
      const storageKey = `${this.namespace}:pref:${key}`;
      localStorage.removeItem(storageKey);
      console.log(`[StateManager] Deleted preference: ${key}`);
      return true;
    } catch (error) {
      console.error(`[StateManager] Failed to delete preference: ${key}`, error);
      return false;
    }
  }

  // =============================================================================
  // Session Filters (sessionStorage - temporary for current session)
  // =============================================================================

  /**
   * Save a session filter to sessionStorage
   *
   * @param {string} key - Filter key
   * @param {any} value - Filter value (will be JSON serialized)
   * @returns {boolean} Success status
   *
   * @example
   * manager.saveSessionFilter('calendar_view', 'week');
   * manager.saveSessionFilter('selected_employee', 'EMP001');
   */
  saveSessionFilter(key, value) {
    if (!this.storageAvailable) {
      return false;
    }

    try {
      const storageKey = `${this.namespace}:session:${key}`;
      sessionStorage.setItem(storageKey, JSON.stringify(value));
      console.log(`[StateManager] Saved session filter: ${key}`, value);
      return true;
    } catch (error) {
      console.error(`[StateManager] Failed to save session filter: ${key}`, error);
      return false;
    }
  }

  /**
   * Get a session filter from sessionStorage
   *
   * @param {string} key - Filter key
   * @param {any} defaultValue - Default value if filter not found
   * @returns {any} Filter value or default
   *
   * @example
   * const view = manager.getSessionFilter('calendar_view', 'month');
   */
  getSessionFilter(key, defaultValue = null) {
    if (!this.storageAvailable) {
      return defaultValue;
    }

    try {
      const storageKey = `${this.namespace}:session:${key}`;
      const item = sessionStorage.getItem(storageKey);
      return item !== null ? JSON.parse(item) : defaultValue;
    } catch (error) {
      console.error(`[StateManager] Failed to get session filter: ${key}`, error);
      return defaultValue;
    }
  }

  /**
   * Delete a session filter
   *
   * @param {string} key - Filter key
   * @returns {boolean} Success status
   */
  deleteSessionFilter(key) {
    if (!this.storageAvailable) {
      return false;
    }

    try {
      const storageKey = `${this.namespace}:session:${key}`;
      sessionStorage.removeItem(storageKey);
      console.log(`[StateManager] Deleted session filter: ${key}`);
      return true;
    } catch (error) {
      console.error(`[StateManager] Failed to delete session filter: ${key}`, error);
      return false;
    }
  }

  /**
   * Clear all session filters
   *
   * @returns {boolean} Success status
   */
  clearSessionFilters() {
    if (!this.storageAvailable) {
      return false;
    }

    try {
      const prefix = `${this.namespace}:session:`;
      const keys = Object.keys(sessionStorage).filter(key => key.startsWith(prefix));

      keys.forEach(key => sessionStorage.removeItem(key));
      console.log(`[StateManager] Cleared ${keys.length} session filters`);
      return true;
    } catch (error) {
      console.error('[StateManager] Failed to clear session filters', error);
      return false;
    }
  }

  // =============================================================================
  // Saved Searches (localStorage - named search configurations)
  // =============================================================================

  /**
   * Save a named search configuration
   *
   * @param {string} name - Search name
   * @param {Object} filters - Search filter object
   * @returns {boolean} Success status
   *
   * @example
   * manager.saveSavedSearch('core-events-this-week', {
   *   event_type: 'Core',
   *   date_start: '2025-10-15',
   *   date_end: '2025-10-22'
   * });
   */
  saveSavedSearch(name, filters) {
    if (!this.storageAvailable) {
      return false;
    }

    try {
      const searches = this.getSavedSearches();
      searches[name] = {
        filters,
        created: new Date().toISOString(),
        modified: new Date().toISOString()
      };

      const storageKey = `${this.namespace}:searches`;
      localStorage.setItem(storageKey, JSON.stringify(searches));
      console.log(`[StateManager] Saved search: ${name}`, filters);
      return true;
    } catch (error) {
      console.error(`[StateManager] Failed to save search: ${name}`, error);
      return false;
    }
  }

  /**
   * Get a saved search by name
   *
   * @param {string} name - Search name
   * @returns {Object|null} Search configuration or null if not found
   *
   * @example
   * const search = manager.getSavedSearch('core-events-this-week');
   * if (search) {
   *   applyFilters(search.filters);
   * }
   */
  getSavedSearch(name) {
    const searches = this.getSavedSearches();
    return searches[name] || null;
  }

  /**
   * Get all saved searches
   *
   * @returns {Object} Object mapping search names to configurations
   *
   * @example
   * const searches = manager.getSavedSearches();
   * Object.keys(searches).forEach(name => console.log(name, searches[name].filters));
   */
  getSavedSearches() {
    if (!this.storageAvailable) {
      return {};
    }

    try {
      const storageKey = `${this.namespace}:searches`;
      const item = localStorage.getItem(storageKey);
      return item !== null ? JSON.parse(item) : {};
    } catch (error) {
      console.error('[StateManager] Failed to get saved searches', error);
      return {};
    }
  }

  /**
   * Delete a saved search
   *
   * @param {string} name - Search name
   * @returns {boolean} Success status
   */
  deleteSavedSearch(name) {
    if (!this.storageAvailable) {
      return false;
    }

    try {
      const searches = this.getSavedSearches();
      delete searches[name];

      const storageKey = `${this.namespace}:searches`;
      localStorage.setItem(storageKey, JSON.stringify(searches));
      console.log(`[StateManager] Deleted search: ${name}`);
      return true;
    } catch (error) {
      console.error(`[StateManager] Failed to delete search: ${name}`, error);
      return false;
    }
  }

  /**
   * Rename a saved search
   *
   * @param {string} oldName - Current search name
   * @param {string} newName - New search name
   * @returns {boolean} Success status
   */
  renameSavedSearch(oldName, newName) {
    const search = this.getSavedSearch(oldName);
    if (!search) {
      return false;
    }

    search.modified = new Date().toISOString();
    this.saveSavedSearch(newName, search.filters);
    this.deleteSavedSearch(oldName);
    return true;
  }

  // =============================================================================
  // URL State (History API - shareable and bookmarkable URLs)
  // =============================================================================

  /**
   * Save current state to URL query parameters
   *
   * @param {Object} params - Parameters to encode in URL
   * @param {boolean} replace - Whether to replace current history entry (default: true)
   *
   * @example
   * manager.saveUrlState({ view: 'calendar', date: '2025-10-15', employee: 'EMP001' });
   * // URL becomes: /calendar?view=calendar&date=2025-10-15&employee=EMP001
   */
  saveUrlState(params, replace = true) {
    try {
      const url = new URL(window.location.href);

      // Clear existing query parameters
      url.search = '';

      // Add new parameters
      Object.keys(params).forEach(key => {
        const value = params[key];
        if (value !== null && value !== undefined && value !== '') {
          url.searchParams.set(key, value);
        }
      });

      // Update browser history
      if (replace) {
        window.history.replaceState(params, '', url.toString());
      } else {
        window.history.pushState(params, '', url.toString());
      }

      console.log('[StateManager] Saved URL state:', params);
      return true;
    } catch (error) {
      console.error('[StateManager] Failed to save URL state', error);
      return false;
    }
  }

  /**
   * Get current state from URL query parameters
   *
   * @returns {Object} Parameters from URL query string
   *
   * @example
   * const urlParams = manager.getUrlState();
   * // Returns: { view: 'calendar', date: '2025-10-15', employee: 'EMP001' }
   */
  getUrlState() {
    try {
      const url = new URL(window.location.href);
      const params = {};

      url.searchParams.forEach((value, key) => {
        params[key] = value;
      });

      return params;
    } catch (error) {
      console.error('[StateManager] Failed to get URL state', error);
      return {};
    }
  }

  /**
   * Update a single URL parameter without replacing all parameters
   *
   * @param {string} key - Parameter key
   * @param {any} value - Parameter value
   * @param {boolean} replace - Whether to replace current history entry (default: true)
   *
   * @example
   * manager.updateUrlParam('date', '2025-10-16');
   */
  updateUrlParam(key, value, replace = true) {
    try {
      const url = new URL(window.location.href);

      if (value !== null && value !== undefined && value !== '') {
        url.searchParams.set(key, value);
      } else {
        url.searchParams.delete(key);
      }

      if (replace) {
        window.history.replaceState({}, '', url.toString());
      } else {
        window.history.pushState({}, '', url.toString());
      }

      console.log(`[StateManager] Updated URL param: ${key} = ${value}`);
      return true;
    } catch (error) {
      console.error(`[StateManager] Failed to update URL param: ${key}`, error);
      return false;
    }
  }

  /**
   * Clear all URL query parameters
   *
   * @param {boolean} replace - Whether to replace current history entry (default: true)
   */
  clearUrlState(replace = true) {
    try {
      const url = new URL(window.location.href);
      url.search = '';

      if (replace) {
        window.history.replaceState({}, '', url.toString());
      } else {
        window.history.pushState({}, '', url.toString());
      }

      console.log('[StateManager] Cleared URL state');
      return true;
    } catch (error) {
      console.error('[StateManager] Failed to clear URL state', error);
      return false;
    }
  }

  // =============================================================================
  // Utility Methods
  // =============================================================================

  /**
   * Check if Web Storage API is available
   *
   * @returns {boolean} True if localStorage and sessionStorage are available
   * @private
   */
  _checkStorageAvailability() {
    try {
      const test = '__storage_test__';
      localStorage.setItem(test, test);
      localStorage.removeItem(test);
      sessionStorage.setItem(test, test);
      sessionStorage.removeItem(test);
      return true;
    } catch (error) {
      return false;
    }
  }

  /**
   * Clear all state (preferences, session filters, saved searches)
   *
   * WARNING: This will delete all stored data for this application.
   *
   * @returns {boolean} Success status
   */
  clearAllState() {
    if (!this.storageAvailable) {
      return false;
    }

    try {
      const prefix = `${this.namespace}:`;

      // Clear from localStorage
      const localKeys = Object.keys(localStorage).filter(key => key.startsWith(prefix));
      localKeys.forEach(key => localStorage.removeItem(key));

      // Clear from sessionStorage
      const sessionKeys = Object.keys(sessionStorage).filter(key => key.startsWith(prefix));
      sessionKeys.forEach(key => sessionStorage.removeItem(key));

      console.warn(`[StateManager] Cleared all state (${localKeys.length + sessionKeys.length} items)`);
      return true;
    } catch (error) {
      console.error('[StateManager] Failed to clear all state', error);
      return false;
    }
  }
}

// Export singleton instance for global use
export const stateManager = new StateManager();

// Make globally available for non-module contexts
if (typeof window !== 'undefined') {
  window.stateManager = stateManager;
}
