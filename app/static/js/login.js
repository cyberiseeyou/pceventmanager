/**
 * Login Page
 *
 * Manages the authentication flow for the Product Connections Scheduler.
 * Handles form validation, credential submission to the Crossmark MVRetail API,
 * password visibility toggling, remember-me persistence, retry tracking,
 * forgot-password recovery, and informational modals (help, privacy, terms).
 *
 * @module login
 */

/**
 * Manages the login form lifecycle: validation, submission, error/success display,
 * password toggle, remember-me, and retry logic.
 */
class LoginManager {
    /**
     * Initialize the LoginManager by caching DOM references, setting initial state,
     * and calling init() to bind events and load remembered credentials.
     */
    constructor() {
        /** @type {HTMLFormElement} */
        this.form = document.getElementById('loginForm');
        /** @type {HTMLInputElement} */
        this.usernameInput = document.getElementById('username');
        /** @type {HTMLInputElement} */
        this.passwordInput = document.getElementById('password');
        /** @type {HTMLButtonElement} */
        this.loginButton = document.getElementById('loginButton');
        /** @type {HTMLElement} */
        this.passwordToggle = document.querySelector('.password-toggle');
        /** @type {HTMLElement} */
        this.errorContainer = document.getElementById('errorContainer');
        /** @type {HTMLElement} */
        this.successContainer = document.getElementById('successContainer');

        /** @type {boolean} Guards against double-submission */
        this.isSubmitting = false;
        /** @type {number} Maximum login attempts before showing support message */
        this.maxRetries = 3;
        /** @type {number} Current failed attempt count */
        this.retryCount = 0;

        this.init();
    }

    /** Set up all event bindings, accessibility attributes, remembered credentials, and focus. */
    init() {
        this.bindEvents();
        this.setupAccessibility();
        this.loadRememberedCredentials();
        this.focusFirstInput();
    }

    /** Bind all DOM event listeners: form submit, password toggle, input validation, focus effects. */
    bindEvents() {
        // Form submission
        this.form.addEventListener('submit', this.handleSubmit.bind(this));

        // Password toggle
        this.passwordToggle.addEventListener('click', this.togglePassword.bind(this));

        // Real-time validation
        this.usernameInput.addEventListener('input', this.validateUsername.bind(this));
        this.passwordInput.addEventListener('input', this.validatePassword.bind(this));

        // Enter key handling
        this.usernameInput.addEventListener('keypress', this.handleEnterKey.bind(this));
        this.passwordInput.addEventListener('keypress', this.handleEnterKey.bind(this));

        // Input focus effects
        [this.usernameInput, this.passwordInput].forEach(input => {
            input.addEventListener('focus', this.handleInputFocus.bind(this));
            input.addEventListener('blur', this.handleInputBlur.bind(this));
        });
    }

    /** Configure ARIA attributes on the form and password toggle for screen reader support. */
    setupAccessibility() {
        // Add ARIA labels for better screen reader support
        this.form.setAttribute('aria-label', 'Login form');
        this.passwordToggle.setAttribute('aria-label', 'Toggle password visibility');

        // Set initial ARIA states
        this.updatePasswordToggleAria();
    }

    /**
     * Restore remembered username from localStorage and check the "remember me" checkbox.
     * If a username is found, focuses the password field instead.
     */
    loadRememberedCredentials() {
        // Check for remembered username (never store password)
        const rememberedUsername = localStorage.getItem('rememberedUsername');
        const rememberCheckbox = document.getElementById('remember');

        if (rememberedUsername) {
            this.usernameInput.value = rememberedUsername;
            rememberCheckbox.checked = true;
            this.passwordInput.focus();
        }
    }

    /** Focus the password field if username is pre-filled, otherwise focus username. */
    focusFirstInput() {
        // Focus appropriate field on page load
        if (this.usernameInput.value) {
            this.passwordInput.focus();
        } else {
            this.usernameInput.focus();
        }
    }

    /**
     * Submit the form when Enter is pressed in either input field.
     *
     * @param {KeyboardEvent} event
     */
    handleEnterKey(event) {
        if (event.key === 'Enter' && !this.isSubmitting) {
            this.form.dispatchEvent(new Event('submit', { bubbles: true }));
        }
    }

    /**
     * Add focus styling to the input container and clear any displayed messages.
     *
     * @param {FocusEvent} event
     */
    handleInputFocus(event) {
        event.target.parentElement.classList.add('focused');
    }

    /**
     * Remove focus styling from the input container.
     *
     * @param {FocusEvent} event
     */
    handleInputBlur(event) {
        event.target.parentElement.classList.remove('focused');
    }

    /**
     * Validate the username input (minimum 3 characters) and update field styling.
     *
     * @returns {boolean} True if the username is valid
     */
    validateUsername() {
        const username = this.usernameInput.value.trim();
        const isValid = username.length >= 3;

        this.updateFieldValidation(this.usernameInput, isValid);
        return isValid;
    }

    /**
     * Validate the password input (minimum 8 characters) and update field styling.
     *
     * @returns {boolean} True if the password is valid
     */
    validatePassword() {
        const password = this.passwordInput.value;
        const isValid = password.length >= 8;

        this.updateFieldValidation(this.passwordInput, isValid);
        return isValid;
    }

    /**
     * Toggle valid/invalid CSS classes on a form field based on validation state.
     * Does nothing if the field is empty (no styling on untouched fields).
     *
     * @param {HTMLInputElement} field - The input element to style
     * @param {boolean} isValid - Whether the field value passes validation
     */
    updateFieldValidation(field, isValid) {
        if (field.value.length === 0) {
            field.classList.remove('valid', 'invalid');
            return;
        }

        field.classList.toggle('valid', isValid);
        field.classList.toggle('invalid', !isValid);
    }

    /** Toggle password field between visible text and masked input, updating the eye icon. */
    togglePassword() {
        const isPassword = this.passwordInput.type === 'password';
        const eyeOpen = this.passwordToggle.querySelector('.eye-open');
        const eyeClosed = this.passwordToggle.querySelector('.eye-closed');

        this.passwordInput.type = isPassword ? 'text' : 'password';
        eyeOpen.style.display = isPassword ? 'none' : 'block';
        eyeClosed.style.display = isPassword ? 'block' : 'none';

        this.updatePasswordToggleAria();

        // Maintain focus on password field
        this.passwordInput.focus();
    }

    /** Update the password toggle button's ARIA label to reflect current visibility state. */
    updatePasswordToggleAria() {
        const isPassword = this.passwordInput.type === 'password';
        this.passwordToggle.setAttribute('aria-label', isPassword ? 'Show password' : 'Hide password');
    }

    /**
     * Handle form submission: validate fields, submit credentials, and route to
     * success or error handling. Guards against double-submission.
     *
     * @param {SubmitEvent} event
     * @returns {Promise<void>}
     */
    async handleSubmit(event) {
        event.preventDefault();

        if (this.isSubmitting) return;

        // Clear previous messages
        this.clearMessages();

        // Validate inputs
        const isUsernameValid = this.validateUsername();
        const isPasswordValid = this.validatePassword();

        if (!isUsernameValid || !isPasswordValid) {
            this.showError('Please fill in all required fields correctly.');
            return;
        }

        // Start submission process
        this.setSubmitting(true);

        try {
            const result = await this.submitLogin();

            if (result.success) {
                this.handleLoginSuccess(result);
            } else {
                this.handleLoginError(result);
            }
        } catch (error) {
            this.handleLoginError({ error: 'Network error. Please check your connection and try again.' });
        } finally {
            this.setSubmitting(false);
        }
    }

    /**
     * Submit login credentials to the server. Handles the "remember me" checkbox
     * by persisting/removing the username in localStorage. Sends form-encoded data
     * and parses JSON or redirect responses.
     *
     * @returns {Promise<Object>} Result object with `success` boolean and optional `redirect` URL or `error` message
     * @throws {Error} On network failure or unexpected HTTP errors
     */
    async submitLogin() {
        const formData = new FormData(this.form);

        // Handle remember me
        if (formData.get('remember')) {
            localStorage.setItem('rememberedUsername', formData.get('username'));
        } else {
            localStorage.removeItem('rememberedUsername');
        }

        // Convert FormData to URLSearchParams for proper form encoding
        const params = new URLSearchParams(formData);

        const response = await fetch(this.form.action, {
            method: 'POST',
            body: params,
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json'
            },
            credentials: 'same-origin'
        });

        const contentType = response.headers.get('content-type');
        let result;

        if (contentType && contentType.includes('application/json')) {
            result = await response.json();
        } else {
            // Handle non-JSON responses (e.g., redirects)
            if (response.ok) {
                result = { success: true, redirect: response.url };
            } else {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
        }

        return result;
    }

    /**
     * Handle a successful login: clear the password field, show a success message,
     * and redirect to the target page after a short delay.
     *
     * @param {Object} result - Success response with optional redirect URL
     * @param {string} [result.redirect] - URL to redirect to (defaults to '/')
     */
    handleLoginSuccess(result) {
        // Clear form for security
        this.passwordInput.value = '';

        // Show success and redirect to loading page
        this.showSuccess('Login successful! Redirecting...');

        // Redirect after short delay
        setTimeout(() => {
            if (result.redirect) {
                window.location.href = result.redirect;
            } else {
                window.location.href = '/';
            }
        }, 500);
    }

    /**
     * Handle a failed login: increment the retry counter, classify the error
     * (auth, timeout, network), display a user-friendly message with attempt count,
     * and focus the password field for retry.
     *
     * @param {Object} result - Error response from submitLogin
     * @param {string} [result.error] - Error message string from the server
     */
    handleLoginError(result) {
        this.retryCount++;

        let errorMessage = 'Login failed. Please check your credentials.';

        if (result.error) {
            if (result.error.includes('401')) {
                errorMessage = 'Invalid username or password. Please try again.';
            } else if (result.error.includes('timeout')) {
                errorMessage = 'Connection timeout. Please check your network and try again.';
            } else if (result.error.includes('network')) {
                errorMessage = 'Network error. Please check your connection.';
            } else {
                errorMessage = result.error;
            }
        }

        // Add retry information
        if (this.retryCount >= this.maxRetries) {
            errorMessage += ' Please contact support if the problem persists.';
        } else {
            errorMessage += ` (Attempt ${this.retryCount}/${this.maxRetries})`;
        }

        this.showError(errorMessage);

        // Focus password field for retry
        this.passwordInput.select();
        this.passwordInput.focus();
    }

    /**
     * Toggle the form's submitting state: disable/enable the button,
     * swap between text and loading spinner, and lock form inputs.
     *
     * @param {boolean} isSubmitting - True to enter loading state, false to restore
     */
    setSubmitting(isSubmitting) {
        this.isSubmitting = isSubmitting;

        const buttonText = this.loginButton.querySelector('.button-text');
        const buttonLoading = this.loginButton.querySelector('.button-loading');

        if (isSubmitting) {
            buttonText.style.display = 'none';
            buttonLoading.style.display = 'flex';
            this.loginButton.disabled = true;
            this.form.classList.add('submitting');
        } else {
            buttonText.style.display = 'block';
            buttonLoading.style.display = 'none';
            this.loginButton.disabled = false;
            this.form.classList.remove('submitting');
        }
    }

    /**
     * Display an error message, hiding any success message. Sets ARIA role='alert'
     * for screen reader announcement and scrolls the error into view.
     *
     * @param {string} message - Error text to display
     */
    showError(message) {
        document.getElementById('errorMessage').textContent = message;
        this.errorContainer.style.display = 'block';
        this.successContainer.style.display = 'none';

        // Announce to screen readers
        this.errorContainer.setAttribute('role', 'alert');

        // Scroll error into view if needed
        this.errorContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    /**
     * Display a success message, hiding any error message. Sets ARIA role='alert'
     * for screen reader announcement.
     *
     * @param {string} message - Success text to display
     */
    showSuccess(message) {
        document.getElementById('successMessage').textContent = message;
        this.successContainer.style.display = 'block';
        this.errorContainer.style.display = 'none';

        // Announce to screen readers
        this.successContainer.setAttribute('role', 'alert');
    }

    /** Hide both error and success message containers. */
    clearMessages() {
        this.errorContainer.style.display = 'none';
        this.successContainer.style.display = 'none';
    }
}

// Enhanced form validation styles and refresh progress styles
const style = document.createElement('style');
style.textContent = `
    .form-input.valid {
        border-color: var(--success-color);
    }

    .form-input.invalid {
        border-color: var(--error-color);
    }

    .input-container.focused {
        transform: translateY(-1px);
    }

    .login-form.submitting .form-input {
        pointer-events: none;
    }

    .login-form.submitting .password-toggle {
        pointer-events: none;
        opacity: 0.5;
    }
`;
document.head.appendChild(style);

// Initialize login manager when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => new LoginManager());
} else {
    new LoginManager();
}

/**
 * Check for a ?reason=timeout query parameter on page load and display the
 * timeout notification banner. Cleans up the URL without reloading the page.
 */
(function checkTimeoutReason() {
    const urlParams = new URLSearchParams(window.location.search);
    const reason = urlParams.get('reason');

    if (reason === 'timeout') {
        const timeoutContainer = document.getElementById('timeoutContainer');
        if (timeoutContainer) {
            timeoutContainer.style.display = 'block';
        }
        // Clean up the URL without reloading the page
        const newUrl = window.location.pathname;
        window.history.replaceState({}, document.title, newUrl);
    }
})();

// Global error handler for uncaught errors
window.addEventListener('error', (event) => {
    console.error('Login page error:', event.error);

    // Show user-friendly error if login manager exists
    if (window.loginManager) {
        window.loginManager.showError('An unexpected error occurred. Please refresh the page and try again.');
    }
});

// Handle network status changes
window.addEventListener('online', () => {
    if (document.querySelector('.error-message')) {
        location.reload();
    }
});

window.addEventListener('offline', () => {
    if (window.loginManager) {
        window.loginManager.showError('You appear to be offline. Please check your connection.');
    }
});

/**
 * Forgot Password Modal Manager
 * Handles the account recovery popup functionality
 */
class ForgotPasswordModal {
    /** Initialize DOM references and bind all modal event listeners. */
    constructor() {
        /** @type {HTMLElement} */
        this.modal = document.getElementById('forgotPasswordModal');
        /** @type {HTMLFormElement} */
        this.form = document.getElementById('forgotPasswordForm');
        /** @type {HTMLInputElement} */
        this.emailInput = document.getElementById('recoveryEmail');
        /** @type {HTMLElement} */
        this.messageContainer = document.getElementById('recoveryMessage');
        /** @type {HTMLButtonElement} */
        this.submitBtn = document.getElementById('recoverySubmit');
        /** @type {boolean} */
        this.isSubmitting = false;

        this.init();
    }

    /** Bind open/close/submit events for the forgot password modal. */
    init() {
        // Open modal when forgot password link is clicked
        document.getElementById('forgotPasswordLink').addEventListener('click', (e) => {
            e.preventDefault();
            this.openModal();
        });

        // Close modal events
        document.getElementById('modalClose').addEventListener('click', () => this.closeModal());
        document.getElementById('modalCancel').addEventListener('click', () => this.closeModal());

        // Close on overlay click
        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) {
                this.closeModal();
            }
        });

        // Close on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.modal.style.display !== 'none') {
                this.closeModal();
            }
        });

        // Form submission
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));
    }

    /** Show the forgot password modal, clear previous state, and focus the email input. */
    openModal() {
        this.modal.style.display = 'flex';
        this.emailInput.value = '';
        this.hideMessage();
        this.emailInput.focus();
        document.body.style.overflow = 'hidden';
    }

    /** Hide the forgot password modal and restore page scrolling. */
    closeModal() {
        this.modal.style.display = 'none';
        document.body.style.overflow = '';
        this.hideMessage();
    }

    /**
     * Submit the password recovery request to the MVRetail API.
     * Shows a success message regardless of whether the email exists (security best practice).
     * Auto-closes the modal on success after 4 seconds.
     *
     * @param {SubmitEvent} e - Form submit event
     * @returns {Promise<void>}
     */
    async handleSubmit(e) {
        e.preventDefault();

        if (this.isSubmitting) return;

        const email = this.emailInput.value.trim();
        if (!email) {
            this.showMessage('Please enter your email address.', 'error');
            return;
        }

        this.setSubmitting(true);
        this.hideMessage();

        try {
            const response = await fetch(`https://crossmark.mvretail.com/login/recover?Email=${encodeURIComponent(email)}`, {
                method: 'POST',
                headers: {
                    'Accept': 'application/json, text/plain, */*',
                    'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"'
                }
            });

            if (response.ok) {
                this.showMessage('If an account exists with that email, recovery instructions have been sent. Please check your inbox.', 'success');
                this.emailInput.value = '';
                // Close modal after delay on success
                setTimeout(() => this.closeModal(), 4000);
            } else {
                this.showMessage('Unable to process your request. Please try again later.', 'error');
            }
        } catch (error) {
            console.error('Recovery request failed:', error);
            this.showMessage('Network error. Please check your connection and try again.', 'error');
        } finally {
            this.setSubmitting(false);
        }
    }

    /**
     * Toggle the submitting state: swap button text/spinner and disable form inputs.
     *
     * @param {boolean} isSubmitting - True to enter loading state
     */
    setSubmitting(isSubmitting) {
        this.isSubmitting = isSubmitting;
        const btnText = this.submitBtn.querySelector('.btn-text');
        const btnLoading = this.submitBtn.querySelector('.btn-loading');

        if (isSubmitting) {
            btnText.style.display = 'none';
            btnLoading.style.display = 'flex';
            this.submitBtn.disabled = true;
            this.emailInput.disabled = true;
        } else {
            btnText.style.display = 'inline';
            btnLoading.style.display = 'none';
            this.submitBtn.disabled = false;
            this.emailInput.disabled = false;
        }
    }

    /**
     * Display a message in the recovery modal.
     *
     * @param {string} message - Message text
     * @param {('success'|'error')} type - Message type, applied as a CSS class
     */
    showMessage(message, type) {
        this.messageContainer.textContent = message;
        this.messageContainer.className = `recovery-message recovery-message-${type}`;
        this.messageContainer.style.display = 'block';
    }

    /** Hide the recovery message container. */
    hideMessage() {
        this.messageContainer.style.display = 'none';
    }
}

// Initialize forgot password modal when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => new ForgotPasswordModal());
} else {
    new ForgotPasswordModal();
}

/**
 * Simple Modal Manager for Help, Privacy, and Terms.
 * Handles opening/closing of informational modals via trigger links,
 * with overlay click and Escape key to dismiss.
 */
class InfoModal {
    /**
     * Create an InfoModal bound to a trigger link and a modal element.
     * If either element is missing from the DOM, initialization is skipped.
     *
     * @param {string} linkId - DOM ID of the anchor element that opens the modal
     * @param {string} modalId - DOM ID of the modal overlay element
     */
    constructor(linkId, modalId) {
        this.link = document.getElementById(linkId);
        this.modal = document.getElementById(modalId);

        if (this.link && this.modal) {
            this.init();
        }
    }

    /** Bind all open/close event listeners: link click, close buttons, overlay click, Escape key. */
    init() {
        // Open modal on link click
        this.link.addEventListener('click', (e) => {
            e.preventDefault();
            this.openModal();
        });

        // Close on X button
        const closeBtn = this.modal.querySelector('.modal-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.closeModal());
        }

        // Close on "Got It" / "Close" button
        const closeActionBtn = this.modal.querySelector('.modal-btn-close');
        if (closeActionBtn) {
            closeActionBtn.addEventListener('click', () => this.closeModal());
        }

        // Close on overlay click
        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) {
                this.closeModal();
            }
        });

        // Close on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.modal.style.display !== 'none') {
                this.closeModal();
            }
        });
    }

    /** Show the modal and prevent background scrolling. Focuses the close button for accessibility. */
    openModal() {
        this.modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
        // Focus the close button for accessibility
        const closeBtn = this.modal.querySelector('.modal-btn-close');
        if (closeBtn) {
            closeBtn.focus();
        }
    }

    /** Hide the modal and restore background scrolling. */
    closeModal() {
        this.modal.style.display = 'none';
        document.body.style.overflow = '';
    }
}

/**
 * Create InfoModal instances for the Help, Privacy, and Terms footer links.
 * Called once on DOMContentLoaded.
 */
function initInfoModals() {
    new InfoModal('helpLink', 'helpModal');
    new InfoModal('privacyLink', 'privacyModal');
    new InfoModal('termsLink', 'termsModal');
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initInfoModals);
} else {
    initInfoModals();
}