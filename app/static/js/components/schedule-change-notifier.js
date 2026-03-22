/**
 * Schedule Change Notifier
 *
 * Polls /api/my-schedule-updates and fires a browser Notification whenever
 * the employee's upcoming-week schedule fingerprint changes.
 *
 * Only runs for employees with an employee_id in the session (specialist role).
 * Uses localStorage to persist the last-known fingerprint so a change is
 * detected even across page loads.
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'pc_schedule_fingerprint';
    var POLL_MS = 120000; // 2 minutes
    var FIRST_POLL_MS = 5000; // first check 5s after page load
    var pollTimer = null;

    /** Request browser notification permission (non-blocking). */
    function requestPermission() {
        if (!('Notification' in window)) return;
        if (Notification.permission === 'default') {
            Notification.requestPermission();
        }
    }

    /** Show a browser notification + optional in-app toast. */
    function notify(title, body) {
        // Browser Notification
        if ('Notification' in window && Notification.permission === 'granted') {
            try {
                var n = new Notification(title, {
                    body: body,
                    icon: '/static/img/pwa-icon-192.png',
                    badge: '/static/img/favicon-48x48.png',
                    tag: 'schedule-change', // replaces previous
                });
                n.onclick = function () {
                    window.focus();
                    n.close();
                };
            } catch (e) {
                // Some browsers block Notification constructor in insecure contexts
            }
        }

        // In-app toast (if toaster is available from base.html modules)
        if (window.toaster && typeof window.toaster.show === 'function') {
            window.toaster.show(body, 'info', 6000);
        }
    }

    /** Poll the API and compare fingerprint. */
    function checkForChanges() {
        fetch('/api/my-schedule-updates', { credentials: 'same-origin' })
            .then(function (resp) {
                if (!resp.ok) return null;
                return resp.json();
            })
            .then(function (data) {
                if (!data) return;

                var prev = localStorage.getItem(STORAGE_KEY);
                var current = data.fingerprint;

                if (prev === null) {
                    // First visit — just save, don't notify
                    localStorage.setItem(STORAGE_KEY, current);
                    return;
                }

                if (current !== prev) {
                    localStorage.setItem(STORAGE_KEY, current);

                    // Build a short description of what changed
                    if (data.count === 0) {
                        notify(
                            'Schedule Updated',
                            'Your events this week have been removed or rescheduled. Check your dashboard.'
                        );
                    } else {
                        notify(
                            'Schedule Updated',
                            'Your schedule for this week has changed — you now have ' +
                            data.count + ' event' + (data.count !== 1 ? 's' : '') + '.'
                        );
                    }
                }
            })
            .catch(function () {
                // Silently ignore network errors
            });
    }

    /** Start polling. */
    function start() {
        requestPermission();

        // First check shortly after page load
        setTimeout(checkForChanges, FIRST_POLL_MS);

        // Then every POLL_MS
        pollTimer = setInterval(checkForChanges, POLL_MS);
    }

    // Only start if we're on a page that has the CSRF meta tag (authenticated)
    if (document.querySelector('meta[name="csrf-token"]')) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', start);
        } else {
            start();
        }
    }
})();
