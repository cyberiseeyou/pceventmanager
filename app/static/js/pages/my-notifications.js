/**
 * My Notifications page — lists schedule change notifications.
 * Polls every 60s, supports mark-as-read and mark-all-read.
 */
(function () {
    'use strict';

    const POLL_INTERVAL = 60000;
    const listEl = document.getElementById('notifList');
    const emptyEl = document.getElementById('notifEmpty');
    const markAllBtn = document.getElementById('markAllRead');
    let pollTimer = null;

    const CHANGE_TYPE_LABELS = {
        event_added: 'New Assignment',
        event_removed: 'Schedule Removed',
        time_changed: 'Time Changed',
        employee_swapped_in: 'New Assignment',
        employee_swapped_out: 'Reassigned',
        event_traded: 'Event Traded',
    };

    const CHANGE_TYPE_ICONS = {
        event_added: { icon: 'add_circle', cls: 'added' },
        event_removed: { icon: 'remove_circle', cls: 'removed' },
        time_changed: { icon: 'schedule', cls: 'changed' },
        employee_swapped_in: { icon: 'swap_horiz', cls: 'swapped' },
        employee_swapped_out: { icon: 'swap_horiz', cls: 'swapped' },
        event_traded: { icon: 'swap_horiz', cls: 'swapped' },
    };

    function relativeTime(isoStr) {
        if (!isoStr) return '';
        const date = new Date(isoStr + 'Z'); // UTC
        const now = new Date();
        const diffMs = now - date;
        const diffMin = Math.floor(diffMs / 60000);
        if (diffMin < 1) return 'Just now';
        if (diffMin < 60) return `${diffMin}m ago`;
        const diffHr = Math.floor(diffMin / 60);
        if (diffHr < 24) return `${diffHr}h ago`;
        const diffDay = Math.floor(diffHr / 24);
        if (diffDay === 1) return 'Yesterday';
        if (diffDay < 7) return `${diffDay}d ago`;
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }

    function renderCard(n) {
        const iconInfo = CHANGE_TYPE_ICONS[n.change_type] || { icon: 'info', cls: 'changed' };
        const label = CHANGE_TYPE_LABELS[n.change_type] || 'Schedule Change';
        const readCls = n.is_read ? ' my-notif__card--read' : '';

        return `
            <div class="my-notif__card${readCls}" data-id="${n.id}" data-read="${n.is_read}">
                <div class="my-notif__card-icon my-notif__card-icon--${iconInfo.cls}">
                    <span class="material-symbols-outlined">${iconInfo.icon}</span>
                </div>
                <div class="my-notif__card-body">
                    <p class="my-notif__card-type">${label}</p>
                    <p class="my-notif__card-desc">${escapeHtml(n.description)}</p>
                    <p class="my-notif__card-time">${relativeTime(n.created_at)}</p>
                </div>
            </div>
        `;
    }

    function escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    async function loadNotifications() {
        try {
            const resp = await fetch('/api/schedule-changes?limit=100');
            if (!resp.ok) return;
            const data = await resp.json();
            renderList(data.notifications, data.unread_count);
            updateBadge(data.unread_count);
        } catch (e) {
            console.warn('[Notifications] Load failed:', e);
        }
    }

    function renderList(notifications, unreadCount) {
        if (!notifications || notifications.length === 0) {
            emptyEl.hidden = false;
            markAllBtn.hidden = true;
            // Remove all cards but keep empty
            listEl.querySelectorAll('.my-notif__card').forEach(el => el.remove());
            return;
        }

        emptyEl.hidden = true;
        markAllBtn.hidden = unreadCount === 0;

        // Remove old cards
        listEl.querySelectorAll('.my-notif__card').forEach(el => el.remove());

        const html = notifications.map(renderCard).join('');
        listEl.insertAdjacentHTML('beforeend', html);

        // Attach click handlers for mark-as-read
        listEl.querySelectorAll('.my-notif__card[data-read="false"]').forEach(card => {
            card.addEventListener('click', () => markAsRead(card));
        });
    }

    function updateBadge(count) {
        const badge = document.getElementById('scheduleChangeBadge');
        if (!badge) return;
        if (count > 0) {
            badge.textContent = count > 99 ? '99+' : count;
            badge.hidden = false;
        } else {
            badge.hidden = true;
        }
    }

    async function markAsRead(card) {
        const id = card.dataset.id;
        try {
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
            await fetch(`/api/schedule-changes/${id}/read`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
                },
            });
            card.classList.add('my-notif__card--read');
            card.dataset.read = 'true';
            // Refresh to update counts
            loadNotifications();
        } catch (e) {
            console.warn('[Notifications] Mark read failed:', e);
        }
    }

    if (markAllBtn) {
        markAllBtn.addEventListener('click', async () => {
            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
                await fetch('/api/schedule-changes/read-all', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
                    },
                });
                loadNotifications();
            } catch (e) {
                console.warn('[Notifications] Mark all read failed:', e);
            }
        });
    }

    // Initial load
    loadNotifications();

    // Poll every 60s
    pollTimer = setInterval(loadNotifications, POLL_INTERVAL);

    // Clean up on page unload
    window.addEventListener('beforeunload', () => {
        if (pollTimer) clearInterval(pollTimer);
    });
})();
