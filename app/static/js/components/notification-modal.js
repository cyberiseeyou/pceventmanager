/**
 * Notification Modal Component
 *
 * Modal for notifying employees about same-week schedule changes.
 * Shows employee contact info and requires acknowledgment before proceeding.
 *
 * Task 4: Add Same-Week Schedule Notification System
 */

class NotificationModal {
    /**
     * Create a notification modal
     *
     * @param {Object} options - Modal options
     * @param {Object} options.employee - Employee data with id, name, phone
     * @param {string} options.eventName - Name of the event
     * @param {string} options.eventDate - ISO date string of the event
     * @param {number} options.daysUntil - Days until the event
     * @param {Function} options.onConfirm - Callback when user confirms (passes selected option)
     * @param {Function} options.onCancel - Callback when user cancels
     */
    constructor(options) {
        this.employee = options.employee || {};
        this.eventName = options.eventName || 'Unknown Event';
        this.eventDate = options.eventDate || '';
        this.daysUntil = options.daysUntil ?? 0;
        this.onConfirm = options.onConfirm || (() => {});
        this.onCancel = options.onCancel || (() => {});
        this.modalElement = null;
        this.selectedOption = null;
    }

    /**
     * Open the notification modal
     */
    open() {
        this.render();
        this.attachEventListeners();
        // Small delay to trigger animation
        requestAnimationFrame(() => {
            this.modalElement.classList.add('notification-modal--open');
        });
        document.body.style.overflow = 'hidden';
    }

    /**
     * Render modal HTML
     */
    render() {
        const formattedDate = this.formatDate(this.eventDate);
        const daysText = this.getDaysText(this.daysUntil);
        const phoneDisplay = this.employee.phone || 'No phone number on file';
        const hasPhone = !!this.employee.phone;

        // Pre-written text message template
        const messageTemplate = `Hi ${this.employee.name}, this is a reminder that you've been scheduled for ${this.eventName} on ${formattedDate}. Please confirm you received this message.`;

        const modalHTML = `
            <div class="notification-modal" id="notification-modal" role="dialog" aria-modal="true" aria-labelledby="notification-modal-title">
                <div class="notification-modal__overlay"></div>
                <div class="notification-modal__container">
                    <div class="notification-modal__header notification-modal__header--warning">
                        <span class="notification-modal__header-icon">&#9888;</span>
                        <h2 class="notification-modal__title" id="notification-modal-title">Same-Week Schedule Change</h2>
                    </div>

                    <div class="notification-modal__body">
                        <div class="notification-modal__alert">
                            <p class="notification-modal__alert-text">
                                This event is <strong>${daysText}</strong>. The employee should be notified of this schedule change.
                            </p>
                        </div>

                        <div class="notification-modal__employee-info">
                            <h3 class="notification-modal__section-title">Employee Contact Information</h3>
                            <div class="notification-modal__contact-card">
                                <div class="notification-modal__contact-row">
                                    <span class="notification-modal__contact-label">Name:</span>
                                    <span class="notification-modal__contact-value">${this._escapeHtml(this.employee.name)}</span>
                                </div>
                                <div class="notification-modal__contact-row">
                                    <span class="notification-modal__contact-label">Phone:</span>
                                    <span class="notification-modal__contact-value ${!hasPhone ? 'notification-modal__contact-value--missing' : ''}">
                                        ${this._escapeHtml(phoneDisplay)}
                                    </span>
                                    ${hasPhone ? `
                                        <button type="button" class="notification-modal__copy-btn" data-copy="${this._escapeHtml(this.employee.phone)}" title="Copy phone number">
                                            <span class="notification-modal__copy-icon">&#128203;</span>
                                            <span class="notification-modal__copy-text">Copy</span>
                                        </button>
                                    ` : ''}
                                </div>
                                <div class="notification-modal__contact-row">
                                    <span class="notification-modal__contact-label">Event:</span>
                                    <span class="notification-modal__contact-value">${this._escapeHtml(this.eventName)}</span>
                                </div>
                                <div class="notification-modal__contact-row">
                                    <span class="notification-modal__contact-label">Date:</span>
                                    <span class="notification-modal__contact-value">${formattedDate}</span>
                                </div>
                            </div>
                        </div>

                        <div class="notification-modal__message-section">
                            <h3 class="notification-modal__section-title">Suggested Message</h3>
                            <div class="notification-modal__message-box">
                                <p class="notification-modal__message-text">${this._escapeHtml(messageTemplate)}</p>
                                <button type="button" class="notification-modal__copy-btn notification-modal__copy-btn--full" data-copy="${this._escapeHtml(messageTemplate)}" title="Copy message">
                                    <span class="notification-modal__copy-icon">&#128203;</span>
                                    <span class="notification-modal__copy-text">Copy Message</span>
                                </button>
                            </div>
                        </div>

                        <div class="notification-modal__options-section">
                            <h3 class="notification-modal__section-title">How will you notify them?</h3>
                            <div class="notification-modal__options" role="radiogroup" aria-label="Notification method">
                                <label class="notification-modal__option">
                                    <input type="radio" name="notification-method" value="text" class="notification-modal__option-input">
                                    <span class="notification-modal__option-radio"></span>
                                    <span class="notification-modal__option-text">I'll text them</span>
                                </label>
                                <label class="notification-modal__option">
                                    <input type="radio" name="notification-method" value="call" class="notification-modal__option-input">
                                    <span class="notification-modal__option-radio"></span>
                                    <span class="notification-modal__option-text">I'll call them</span>
                                </label>
                                <label class="notification-modal__option">
                                    <input type="radio" name="notification-method" value="already" class="notification-modal__option-input">
                                    <span class="notification-modal__option-radio"></span>
                                    <span class="notification-modal__option-text">Already notified</span>
                                </label>
                                <label class="notification-modal__option">
                                    <input type="radio" name="notification-method" value="not_needed" class="notification-modal__option-input">
                                    <span class="notification-modal__option-radio"></span>
                                    <span class="notification-modal__option-text">Not needed</span>
                                </label>
                            </div>
                        </div>
                    </div>

                    <div class="notification-modal__footer">
                        <button type="button" class="notification-modal__btn notification-modal__btn--secondary" id="notification-modal-cancel">
                            Cancel
                        </button>
                        <button type="button" class="notification-modal__btn notification-modal__btn--primary" id="notification-modal-confirm" disabled>
                            Confirm & Assign
                        </button>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if present
        const existingModal = document.getElementById('notification-modal');
        if (existingModal) existingModal.remove();

        // Insert new modal
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        this.modalElement = document.getElementById('notification-modal');
    }

    /**
     * Attach event listeners
     */
    attachEventListeners() {
        const overlay = this.modalElement.querySelector('.notification-modal__overlay');
        const cancelBtn = this.modalElement.querySelector('#notification-modal-cancel');
        const confirmBtn = this.modalElement.querySelector('#notification-modal-confirm');
        const radioInputs = this.modalElement.querySelectorAll('.notification-modal__option-input');
        const copyBtns = this.modalElement.querySelectorAll('.notification-modal__copy-btn');

        // Close handlers
        const closeModal = () => {
            this.close();
            this.onCancel();
        };

        overlay.addEventListener('click', closeModal);
        cancelBtn.addEventListener('click', closeModal);

        // Escape key handler
        const handleEscape = (e) => {
            if (e.key === 'Escape') closeModal();
        };
        document.addEventListener('keydown', handleEscape);
        this.modalElement._escapeHandler = handleEscape;

        // Radio selection handlers
        radioInputs.forEach(input => {
            input.addEventListener('change', (e) => {
                this.selectedOption = e.target.value;
                confirmBtn.disabled = false;
            });
        });

        // Confirm button handler
        confirmBtn.addEventListener('click', () => {
            if (this.selectedOption) {
                this.close();
                this.onConfirm(this.selectedOption);
            }
        });

        // Copy button handlers
        copyBtns.forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                const textToCopy = btn.getAttribute('data-copy');
                await this.copyToClipboard(textToCopy, btn);
            });
        });
    }

    /**
     * Copy text to clipboard
     *
     * @param {string} text - Text to copy
     * @param {HTMLElement} btn - Button element for feedback
     */
    async copyToClipboard(text, btn) {
        try {
            await navigator.clipboard.writeText(text);
            // Show success feedback
            const originalText = btn.querySelector('.notification-modal__copy-text').textContent;
            btn.querySelector('.notification-modal__copy-text').textContent = 'Copied!';
            btn.classList.add('notification-modal__copy-btn--success');

            setTimeout(() => {
                btn.querySelector('.notification-modal__copy-text').textContent = originalText;
                btn.classList.remove('notification-modal__copy-btn--success');
            }, 2000);
        } catch (err) {
            console.error('Failed to copy to clipboard:', err);
            // Fallback for older browsers
            this.fallbackCopy(text);
        }
    }

    /**
     * Fallback copy method for older browsers
     *
     * @param {string} text - Text to copy
     */
    fallbackCopy(text) {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.left = '-9999px';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        try {
            document.execCommand('copy');
        } catch (err) {
            console.error('Fallback copy failed:', err);
        }
        document.body.removeChild(textArea);
    }

    /**
     * Close modal
     */
    close() {
        if (!this.modalElement) return;

        // Remove event listeners
        if (this.modalElement._escapeHandler) {
            document.removeEventListener('keydown', this.modalElement._escapeHandler);
        }

        // Hide modal with animation
        this.modalElement.classList.remove('notification-modal--open');
        document.body.style.overflow = '';

        // Remove from DOM after animation
        setTimeout(() => {
            if (this.modalElement) {
                this.modalElement.remove();
                this.modalElement = null;
            }
        }, 200);
    }

    /**
     * Format date for display
     *
     * @param {string} dateStr - ISO date string
     * @returns {string} Formatted date
     */
    formatDate(dateStr) {
        if (!dateStr) return 'Unknown date';
        try {
            const date = new Date(dateStr + 'T00:00:00');
            const options = {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            };
            return date.toLocaleDateString('en-US', options);
        } catch (e) {
            return dateStr;
        }
    }

    /**
     * Get human-readable days text
     *
     * @param {number} daysUntil - Number of days until event
     * @returns {string} Human-readable text
     */
    getDaysText(daysUntil) {
        if (daysUntil < 0) {
            const daysAgo = Math.abs(daysUntil);
            return daysAgo === 1 ? 'yesterday' : `${daysAgo} days ago`;
        } else if (daysUntil === 0) {
            return 'today';
        } else if (daysUntil === 1) {
            return 'tomorrow';
        } else {
            return `in ${daysUntil} days`;
        }
    }

    /**
     * Escape HTML to prevent XSS
     *
     * @param {string} text - Text to escape
     * @returns {string} Escaped text
     * @private
     */
    _escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Export for use in other modules
window.NotificationModal = NotificationModal;
