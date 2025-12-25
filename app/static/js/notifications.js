/**
 * Notifications Manager
 * Handles fetching and displaying system notifications
 */

class NotificationsManager {
    constructor() {
        this.notificationsBtn = document.getElementById('notificationsBtn');
        this.notificationsPanel = document.getElementById('notificationsPanel');
        this.notificationBadge = document.getElementById('notificationBadge');
        this.notificationCount = document.getElementById('notificationCount');
        this.notificationsContent = document.getElementById('notificationsContent');

        this.isOpen = false;
        this.notifications = null;

        this.init();
    }

    init() {
        if (!this.notificationsBtn) {
            console.warn('[Notifications] Notification button not found');
            return;
        }

        // Bind event listeners
        this.notificationsBtn.addEventListener('click', () => this.togglePanel());

        // Close panel when clicking outside
        document.addEventListener('click', (e) => {
            if (this.isOpen &&
                !this.notificationsPanel.contains(e.target) &&
                !this.notificationsBtn.contains(e.target)) {
                this.closePanel();
            }
        });

        // Fetch notifications on load
        this.fetchNotifications();

        // Auto-refresh every 5 minutes
        setInterval(() => this.fetchNotifications(), 5 * 60 * 1000);
    }

    async fetchNotifications() {
        try {
            const response = await fetch('/api/notifications');

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            this.notifications = await response.json();
            this.updateUI();

        } catch (error) {
            console.error('[Notifications] Error fetching notifications:', error);
            this.showError();
        }
    }

    updateUI() {
        if (!this.notifications) return;

        const totalCount = this.notifications.count || 0;

        // Update badge
        if (totalCount > 0) {
            this.notificationBadge.textContent = totalCount;
            this.notificationBadge.style.display = 'inline-flex';
        } else {
            this.notificationBadge.style.display = 'none';
        }

        // Update count in header
        this.notificationCount.textContent = totalCount;

        // Render notifications
        this.renderNotifications();
    }

    renderNotifications() {
        if (!this.notifications) return;

        const { critical, warning, info, count } = this.notifications;

        if (count === 0) {
            this.notificationsContent.innerHTML = `
                <div class="notifications-empty">
                    <div class="notifications-empty__icon">✅</div>
                    <div class="notifications-empty__message">All caught up!</div>
                    <div class="notifications-empty__submessage">No notifications at this time</div>
                </div>
            `;
            return;
        }

        let html = '';

        // Render critical notifications
        if (critical.length > 0) {
            html += '<div class="notifications-section">';
            html += '<div class="notifications-section__header">🔴 Critical</div>';
            critical.forEach(notification => {
                html += this.renderNotificationItem(notification, 'critical');
            });
            html += '</div>';
        }

        // Render warning notifications
        if (warning.length > 0) {
            html += '<div class="notifications-section">';
            html += '<div class="notifications-section__header">⚠️ Warnings</div>';
            warning.forEach(notification => {
                html += this.renderNotificationItem(notification, 'warning');
            });
            html += '</div>';
        }

        // Render info notifications
        if (info.length > 0) {
            html += '<div class="notifications-section">';
            html += '<div class="notifications-section__header">ℹ️ Information</div>';
            info.forEach(notification => {
                html += this.renderNotificationItem(notification, 'info');
            });
            html += '</div>';
        }

        this.notificationsContent.innerHTML = html;

        // Bind click handlers to notification items
        this.bindNotificationClicks();
    }

    renderNotificationItem(notification, priority) {
        return `
            <div class="notification-item notification-item--${priority}" data-notification-id="${notification.id}">
                <div class="notification-item__header">
                    <div class="notification-item__title">${this.escapeHtml(notification.title)}</div>
                </div>
                <div class="notification-item__message">${this.escapeHtml(notification.message)}</div>
                ${notification.action_url ? `
                    <div class="notification-item__action">
                        <a href="${notification.action_url}" class="notification-item__link" data-action-url="${notification.action_url}">
                            ${this.escapeHtml(notification.action_text)} →
                        </a>
                    </div>
                ` : ''}
            </div>
        `;
    }

    bindNotificationClicks() {
        const notificationItems = this.notificationsContent.querySelectorAll('.notification-item');

        notificationItems.forEach(item => {
            item.addEventListener('click', (e) => {
                // If clicking on a link, let it navigate naturally
                if (e.target.tagName === 'A') {
                    this.closePanel();
                    return;
                }

                // Otherwise, navigate to action URL if it exists
                const link = item.querySelector('.notification-item__link');
                if (link) {
                    const url = link.getAttribute('data-action-url');
                    if (url) {
                        this.closePanel();
                        window.location.href = url;
                    }
                }
            });
        });
    }

    togglePanel() {
        if (this.isOpen) {
            this.closePanel();
        } else {
            this.openPanel();
        }
    }

    openPanel() {
        this.notificationsPanel.hidden = false;
        this.notificationsBtn.setAttribute('aria-expanded', 'true');
        this.isOpen = true;

        // Refresh notifications when opening
        this.fetchNotifications();
    }

    closePanel() {
        this.notificationsPanel.hidden = true;
        this.notificationsBtn.setAttribute('aria-expanded', 'false');
        this.isOpen = false;
    }

    showError() {
        this.notificationsContent.innerHTML = `
            <div class="notifications-error">
                <div class="notifications-error__icon">⚠️</div>
                <div class="notifications-error__message">Unable to load notifications</div>
                <button class="notifications-error__retry" onclick="window.notificationsManager.fetchNotifications()">
                    Retry
                </button>
            </div>
        `;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize notifications manager when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.notificationsManager = new NotificationsManager();
    });
} else {
    window.notificationsManager = new NotificationsManager();
}
