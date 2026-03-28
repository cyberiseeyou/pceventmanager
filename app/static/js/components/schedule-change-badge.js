/**
 * Schedule Change Badge Polling
 * Polls /api/schedule-changes/unread-count every 60s and updates
 * the bell badge in the bottom nav for specialist/lead roles.
 */
(function () {
    'use strict';

    const POLL_INTERVAL = 60000;
    const badge = document.getElementById('scheduleChangeBadge');
    if (!badge) return;

    async function pollUnreadCount() {
        try {
            const resp = await fetch('/api/schedule-changes/unread-count');
            if (!resp.ok) return;
            const data = await resp.json();
            if (data.unread_count > 0) {
                badge.textContent = data.unread_count > 99 ? '99+' : data.unread_count;
                badge.hidden = false;
            } else {
                badge.hidden = true;
            }
        } catch (e) {
            // Silently fail — badge is non-critical
        }
    }

    // Initial poll
    pollUnreadCount();

    // Poll every 60s
    setInterval(pollUnreadCount, POLL_INTERVAL);
})();
