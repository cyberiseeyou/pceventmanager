/**
 * Database Refresh Modal Handler
 * Handles the global "Refresh Database" button functionality
 */

class DatabaseRefreshManager {
    constructor() {
        this.refreshBtn = document.getElementById('refreshDatabaseBtn');
        this.modal = document.getElementById('refreshDatabaseModal');
        this.modalOverlay = this.modal?.querySelector('.modal-overlay');
        this.closeBtn = document.getElementById('closeRefreshModal');
        this.cancelBtn = document.getElementById('cancelRefresh');
        this.confirmBtn = document.getElementById('confirmRefresh');
        this.progressContainer = document.getElementById('refreshProgress');
        this.resultContainer = document.getElementById('refreshResult');
        this.progressText = document.getElementById('refreshProgressText');
        this.resultMessage = document.getElementById('refreshResultMessage');
        this.modalFooter = document.getElementById('refreshModalFooter');

        this.isRefreshing = false;

        this.init();
    }

    init() {
        if (!this.refreshBtn || !this.modal) {
            console.warn('Database refresh elements not found');
            return;
        }

        this.bindEvents();
    }

    bindEvents() {
        // Open modal
        this.refreshBtn.addEventListener('click', () => this.openModal());

        // Close modal
        this.closeBtn.addEventListener('click', () => this.closeModal());
        this.cancelBtn.addEventListener('click', () => this.closeModal());
        this.modalOverlay.addEventListener('click', () => this.closeModal());

        // Confirm refresh
        this.confirmBtn.addEventListener('click', () => this.startRefresh());

        // ESC key to close
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.modal.classList.contains('modal-open')) {
                this.closeModal();
            }
        });
    }

    openModal() {
        // Reset modal state
        this.progressContainer.style.display = 'none';
        this.resultContainer.style.display = 'none';
        this.modalFooter.style.display = 'flex';
        this.confirmBtn.disabled = false;
        this.isRefreshing = false;

        // Show modal (CSS handles display via .modal-open class)
        this.modal.classList.add('modal-open');
        document.body.style.overflow = 'hidden';

        // Focus confirm button
        setTimeout(() => this.confirmBtn.focus(), 100);

        // Announce to screen readers
        this.modal.setAttribute('aria-hidden', 'false');
    }

    closeModal() {
        if (this.isRefreshing) {
            // Don't allow closing while refreshing
            return;
        }

        // Hide modal (CSS handles visibility via .modal-open class)
        this.modal.classList.remove('modal-open');
        document.body.style.overflow = '';
        this.modal.setAttribute('aria-hidden', 'true');

        // Return focus to refresh button
        this.refreshBtn.focus();
    }

    async startRefresh() {
        if (this.isRefreshing) return;

        this.isRefreshing = true;

        // Hide footer buttons and show progress
        this.modalFooter.style.display = 'none';
        this.progressContainer.style.display = 'block';
        this.progressText.textContent = 'Clearing existing data and fetching latest events from Crossmark API...';

        try {
            const response = await fetch('/api/refresh/database', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': this.getCsrfToken()
                },
                credentials: 'same-origin'
            });

            const result = await response.json();

            if (result.success) {
                this.showSuccess(result);
            } else {
                this.showError(result.message || 'Database refresh failed');
            }
        } catch (error) {
            console.error('Database refresh error:', error);
            this.showError('Failed to refresh database. Please try again.');
        }
    }

    showSuccess(result) {
        const stats = result.stats;
        let message = `Database completely refreshed!\n\n`;
        message += `✓ Cleared ${stats.cleared} old events\n`;
        message += `✓ Fetched ${stats.total_fetched} events from Crossmark API\n`;
        message += `✓ Added ${stats.created} fresh events to database`;

        // Show warning if there are Staffed events without schedules
        if (result.warning) {
            message += `\n\n⚠️ ${result.warning}`;
        }

        this.progressContainer.style.display = 'none';
        this.resultContainer.style.display = 'block';
        this.resultMessage.className = 'refresh-result-message refresh-result-success';
        this.resultMessage.textContent = message;

        // Show close button
        const closeOnlyFooter = document.createElement('div');
        closeOnlyFooter.className = 'modal-footer';
        closeOnlyFooter.innerHTML = '<button class="btn btn-primary" id="closeAfterRefresh">Close</button>';
        this.modalFooter.replaceWith(closeOnlyFooter);

        document.getElementById('closeAfterRefresh').addEventListener('click', () => {
            this.isRefreshing = false;
            this.closeModal();
            // Reload page to show updated data
            setTimeout(() => window.location.reload(), 300);
        });

        this.isRefreshing = false;
    }

    showError(message) {
        this.progressContainer.style.display = 'none';
        this.resultContainer.style.display = 'block';
        this.resultMessage.className = 'refresh-result-message refresh-result-error';
        this.resultMessage.textContent = `❌ ${message}`;

        // Show close button
        const closeOnlyFooter = document.createElement('div');
        closeOnlyFooter.className = 'modal-footer';
        closeOnlyFooter.innerHTML = '<button class="btn btn-secondary" id="closeAfterError">Close</button>';
        this.modalFooter.replaceWith(closeOnlyFooter);

        document.getElementById('closeAfterError').addEventListener('click', () => {
            this.isRefreshing = false;
            this.closeModal();
        });

        this.isRefreshing = false;
    }

    getCsrfToken() {
        // Try to get from meta tag first (if set)
        const metaToken = document.querySelector('meta[name="csrf-token"]')?.content;
        if (metaToken) return metaToken;

        // Fallback to cookie
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrf_token='))
            ?.split('=')[1];
        return cookieValue || '';
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => new DatabaseRefreshManager());
} else {
    new DatabaseRefreshManager();
}
