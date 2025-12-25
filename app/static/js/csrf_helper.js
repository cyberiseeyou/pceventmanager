/**
 * CSRF Protection Helper
 *
 * Automatically includes CSRF tokens in AJAX requests to protect against
 * Cross-Site Request Forgery (CSRF) attacks.
 *
 * This script:
 * 1. Reads CSRF token from cookie set by Flask backend
 * 2. Automatically adds token to all AJAX requests (jQuery, fetch, XMLHttpRequest)
 * 3. Only applies to state-changing methods (POST, PUT, DELETE, PATCH)
 *
 * @author Dev Agent (James)
 * @date 2025-01-09
 * @ticket CRITICAL-02
 */

(function() {
    'use strict';

    /**
     * Get CSRF token from cookie
     * @returns {string|null} CSRF token or null if not found
     */
    function getCsrfToken() {
        const name = 'csrf_token=';
        const decodedCookie = decodeURIComponent(document.cookie);
        const cookieArray = decodedCookie.split(';');

        for (let i = 0; i < cookieArray.length; i++) {
            let cookie = cookieArray[i].trim();
            if (cookie.indexOf(name) === 0) {
                return cookie.substring(name.length);
            }
        }
        return null;
    }

    /**
     * Check if HTTP method requires CSRF protection
     * @param {string} method - HTTP method
     * @returns {boolean} True if CSRF protection needed
     */
    function requiresCsrfToken(method) {
        return !/^(GET|HEAD|OPTIONS|TRACE)$/i.test(method);
    }

    /**
     * Setup CSRF protection for jQuery AJAX requests
     */
    function setupJQueryCsrf() {
        if (typeof $ !== 'undefined' && $.ajaxSetup) {
            $.ajaxSetup({
                beforeSend: function(xhr, settings) {
                    if (requiresCsrfToken(settings.type)) {
                        const token = getCsrfToken();
                        if (token) {
                            xhr.setRequestHeader('X-CSRF-Token', token);
                        } else {
                            console.warn('CSRF token not found in cookies');
                        }
                    }
                }
            });
            console.log('[CSRF] jQuery AJAX protection enabled');
        }
    }

    /**
     * Setup CSRF protection for Fetch API
     */
    function setupFetchCsrf() {
        if (typeof window.fetch !== 'undefined') {
            const originalFetch = window.fetch;

            window.fetch = function(url, options = {}) {
                // Add CSRF token for state-changing requests
                if (options.method && requiresCsrfToken(options.method)) {
                    const token = getCsrfToken();
                    if (token) {
                        options.headers = options.headers || {};

                        // Handle different header formats
                        if (options.headers instanceof Headers) {
                            options.headers.append('X-CSRF-Token', token);
                        } else {
                            options.headers['X-CSRF-Token'] = token;
                        }
                    } else {
                        console.warn('CSRF token not found in cookies for fetch request');
                    }
                }

                return originalFetch(url, options);
            };

            console.log('[CSRF] Fetch API protection enabled');
        }
    }

    /**
     * Setup CSRF protection for XMLHttpRequest
     */
    function setupXHRCsrf() {
        const originalOpen = XMLHttpRequest.prototype.open;
        const originalSend = XMLHttpRequest.prototype.send;

        XMLHttpRequest.prototype.open = function(method, url, async, user, password) {
            this._method = method;
            return originalOpen.apply(this, arguments);
        };

        XMLHttpRequest.prototype.send = function(data) {
            if (this._method && requiresCsrfToken(this._method)) {
                const token = getCsrfToken();
                if (token) {
                    this.setRequestHeader('X-CSRF-Token', token);
                } else {
                    console.warn('CSRF token not found in cookies for XHR request');
                }
            }
            return originalSend.apply(this, arguments);
        };

        console.log('[CSRF] XMLHttpRequest protection enabled');
    }

    /**
     * Add CSRF token to all forms (traditional form submissions)
     */
    function setupFormCsrf() {
        // Find all forms without CSRF token
        const forms = document.querySelectorAll('form');

        forms.forEach(function(form) {
            // Skip forms that already have CSRF token
            const existingToken = form.querySelector('input[name="csrf_token"]');
            if (existingToken) {
                return;
            }

            // Only add to POST/PUT/DELETE/PATCH forms
            const method = (form.method || 'GET').toUpperCase();
            if (requiresCsrfToken(method)) {
                const token = getCsrfToken();
                if (token) {
                    const input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = 'csrf_token';
                    input.value = token;
                    form.appendChild(input);
                }
            }
        });
    }

    /**
     * Initialize CSRF protection when DOM is ready
     */
    function initializeCsrfProtection() {
        // Setup AJAX protections
        setupJQueryCsrf();
        setupFetchCsrf();
        setupXHRCsrf();

        // Setup form protection
        setupFormCsrf();

        // Re-apply form protection when new forms are added dynamically
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.addedNodes.length) {
                    setupFormCsrf();
                }
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        console.log('[CSRF] Protection initialized successfully');
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeCsrfProtection);
    } else {
        // DOM already loaded
        initializeCsrfProtection();
    }

    // Expose helper function globally for manual use
    window.getCsrfToken = getCsrfToken;

})();
