/**
 * App Lock Screen
 * Shows a PIN entry overlay after inactivity for persistent sessions.
 * Supports WebAuthn biometric unlock with PIN fallback.
 * The server session stays alive — this is purely a UI gate.
 */
(function() {
    'use strict';

    const INACTIVITY_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes
    const ACTIVITY_EVENTS = ['mousedown', 'touchstart', 'keydown', 'scroll'];

    let inactivityTimer = null;
    let lockOverlay = null;
    let isLocked = false;
    let hasPinConfigured = false;
    let hasWebAuthn = false;

    function getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.content ||
               document.cookie.split('; ').find(c => c.startsWith('csrf_token='))?.split('=')[1] || '';
    }

    /** Check if the current user has a lock PIN and/or WebAuthn configured */
    async function checkLockMethods(retryCount) {
        retryCount = retryCount || 0;
        try {
            const resp = await fetch('/api/auth/has-lock-pin', {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            if (resp.ok) {
                const data = await resp.json();
                hasPinConfigured = data.has_pin;
            }
        } catch (e) {
            console.warn('Failed to check lock PIN status:', e.message);
            if (retryCount < 2) {
                setTimeout(function() { checkLockMethods(retryCount + 1); }, 5000);
                return;
            }
        }

        // Check for WebAuthn credentials
        if (window.PublicKeyCredential) {
            try {
                const resp = await fetch('/api/auth/webauthn/credentials', {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });
                if (resp.ok) {
                    const data = await resp.json();
                    hasWebAuthn = data.credentials && data.credentials.length > 0;
                }
            } catch (e) {
                console.warn('Failed to check WebAuthn credentials:', e.message);
            }
        }
    }

    /** Reset the inactivity timer */
    function resetTimer() {
        if (isLocked) return;
        clearTimeout(inactivityTimer);
        inactivityTimer = setTimeout(lockScreen, INACTIVITY_TIMEOUT_MS);
    }

    /** Attempt WebAuthn biometric authentication */
    async function attemptBiometric(errorEl) {
        try {
            // Get authentication options from server
            const optResp = await fetch('/api/auth/webauthn/authenticate/options', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest',
                },
            });
            if (!optResp.ok) return false;

            const options = await optResp.json();

            // Convert base64url fields to ArrayBuffer for the browser API
            options.challenge = base64urlToBuffer(options.challenge);
            if (options.allowCredentials) {
                options.allowCredentials = options.allowCredentials.map(c => ({
                    ...c,
                    id: base64urlToBuffer(c.id),
                }));
            }

            // Prompt user for biometric
            const assertion = await navigator.credentials.get({ publicKey: options });

            // Convert response to JSON for server
            const credentialJSON = {
                id: assertion.id,
                rawId: bufferToBase64url(assertion.rawId),
                type: assertion.type,
                response: {
                    authenticatorData: bufferToBase64url(assertion.response.authenticatorData),
                    clientDataJSON: bufferToBase64url(assertion.response.clientDataJSON),
                    signature: bufferToBase64url(assertion.response.signature),
                },
            };
            if (assertion.response.userHandle) {
                credentialJSON.response.userHandle = bufferToBase64url(assertion.response.userHandle);
            }

            // Verify with server
            const verifyResp = await fetch('/api/auth/webauthn/authenticate/verify', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify(credentialJSON),
            });
            const result = await verifyResp.json();
            return result.success === true;

        } catch (e) {
            // User cancelled or biometric failed — fall back to PIN
            if (errorEl) {
                errorEl.textContent = 'Biometric failed. Use PIN instead.';
                errorEl.classList.add('visible');
            }
            return false;
        }
    }

    /** Show the lock screen overlay */
    function lockScreen() {
        if (isLocked || (!hasPinConfigured && !hasWebAuthn)) return;
        isLocked = true;

        lockOverlay = document.createElement('div');
        lockOverlay.id = 'app-lock-overlay';
        lockOverlay.innerHTML = `
            <div class="app-lock-container">
                <div class="app-lock-icon">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                        <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                    </svg>
                </div>
                <h2 class="app-lock-title">Session Locked</h2>
                <p class="app-lock-subtitle" id="lock-subtitle">Enter your PIN to unlock</p>
                ${hasWebAuthn ? `
                <button class="app-lock-biometric-btn" id="biometric-btn">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04a17.95 17.95 0 0 1-.227-2.531c0-5.523 4.477-10 10-10a9.96 9.96 0 0 1 5.42 1.598m2.007 4.402a10 10 0 0 1-2.007 6"/>
                        <circle cx="12" cy="11" r="3"/>
                    </svg>
                    Use Biometric
                </button>
                <div class="app-lock-divider"><span>or enter PIN</span></div>
                ` : ''}
                <div class="app-lock-pin-display">
                    <span class="pin-dot"></span>
                    <span class="pin-dot"></span>
                    <span class="pin-dot"></span>
                    <span class="pin-dot"></span>
                    <span class="pin-dot"></span>
                    <span class="pin-dot"></span>
                </div>
                <div class="app-lock-error" id="lock-error"></div>
                <div class="app-lock-keypad">
                    <button class="keypad-btn" data-digit="1">1</button>
                    <button class="keypad-btn" data-digit="2">2</button>
                    <button class="keypad-btn" data-digit="3">3</button>
                    <button class="keypad-btn" data-digit="4">4</button>
                    <button class="keypad-btn" data-digit="5">5</button>
                    <button class="keypad-btn" data-digit="6">6</button>
                    <button class="keypad-btn" data-digit="7">7</button>
                    <button class="keypad-btn" data-digit="8">8</button>
                    <button class="keypad-btn" data-digit="9">9</button>
                    <button class="keypad-btn keypad-clear" data-action="clear">C</button>
                    <button class="keypad-btn" data-digit="0">0</button>
                    <button class="keypad-btn keypad-delete" data-action="delete">&larr;</button>
                </div>
            </div>
        `;
        document.body.appendChild(lockOverlay);

        const errorEl = lockOverlay.querySelector('#lock-error');

        // Auto-trigger biometric if available
        if (hasWebAuthn) {
            const bioBtn = lockOverlay.querySelector('#biometric-btn');
            bioBtn.addEventListener('click', async function() {
                clearError();
                bioBtn.disabled = true;
                bioBtn.textContent = 'Verifying...';
                const ok = await attemptBiometric(errorEl);
                if (ok) {
                    unlockScreen();
                    return;
                }
                bioBtn.disabled = false;
                bioBtn.innerHTML = `
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04a17.95 17.95 0 0 1-.227-2.531c0-5.523 4.477-10 10-10a9.96 9.96 0 0 1 5.42 1.598m2.007 4.402a10 10 0 0 1-2.007 6"/>
                        <circle cx="12" cy="11" r="3"/>
                    </svg>
                    Use Biometric`;
            });

            // Auto-trigger on lock
            setTimeout(() => bioBtn.click(), 300);
        }

        // PIN keypad logic
        let pinBuffer = '';
        const dots = lockOverlay.querySelectorAll('.pin-dot');

        function updateDots() {
            dots.forEach((dot, i) => {
                dot.classList.toggle('filled', i < pinBuffer.length);
            });
        }

        function clearError() {
            errorEl.textContent = '';
            errorEl.classList.remove('visible');
        }

        async function submitPin() {
            try {
                const resp = await fetch('/api/auth/verify-lock-pin', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': getCsrfToken(),
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                    body: JSON.stringify({ pin: pinBuffer }),
                });
                const data = await resp.json();

                if (data.success) {
                    unlockScreen();
                } else if (data.session_destroyed) {
                    window.location.href = '/login';
                } else {
                    errorEl.textContent = data.error || 'Incorrect PIN';
                    errorEl.classList.add('visible');
                    pinBuffer = '';
                    updateDots();
                }
            } catch (e) {
                errorEl.textContent = 'Connection error. Try again.';
                errorEl.classList.add('visible');
                pinBuffer = '';
                updateDots();
            }
        }

        lockOverlay.addEventListener('click', function(e) {
            const btn = e.target.closest('.keypad-btn');
            if (!btn) return;

            clearError();

            if (btn.dataset.digit !== undefined) {
                if (pinBuffer.length < 6) {
                    pinBuffer += btn.dataset.digit;
                    updateDots();
                    if (pinBuffer.length >= 4) {
                        submitPin();
                    }
                }
            } else if (btn.dataset.action === 'clear') {
                pinBuffer = '';
                updateDots();
            } else if (btn.dataset.action === 'delete') {
                pinBuffer = pinBuffer.slice(0, -1);
                updateDots();
            }
        });

        // Physical keyboard support
        document.addEventListener('keydown', function onKey(e) {
            if (!isLocked) {
                document.removeEventListener('keydown', onKey);
                return;
            }
            clearError();
            if (e.key >= '0' && e.key <= '9' && pinBuffer.length < 6) {
                pinBuffer += e.key;
                updateDots();
                if (pinBuffer.length >= 4) {
                    submitPin();
                }
            } else if (e.key === 'Backspace') {
                pinBuffer = pinBuffer.slice(0, -1);
                updateDots();
            } else if (e.key === 'Escape') {
                pinBuffer = '';
                updateDots();
            }
        });
    }

    /** Remove the lock screen overlay */
    function unlockScreen() {
        isLocked = false;
        if (lockOverlay) {
            lockOverlay.remove();
            lockOverlay = null;
        }
        resetTimer();
    }

    // ─── Base64URL helpers for WebAuthn ─────────────────────────────
    function base64urlToBuffer(base64url) {
        const padding = '='.repeat((4 - base64url.length % 4) % 4);
        const base64 = base64url.replace(/-/g, '+').replace(/_/g, '/') + padding;
        const binary = atob(base64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        return bytes.buffer;
    }

    function bufferToBase64url(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.length; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    }

    /** Initialize the app lock system */
    function init() {
        // Only activate for persistent sessions
        const roleEl = document.querySelector('[data-user-role]');
        const role = roleEl ? roleEl.dataset.userRole : null;
        if (!role) return;

        checkLockMethods().then(() => {
            if (!hasPinConfigured && !hasWebAuthn) return;

            // Start monitoring activity
            ACTIVITY_EVENTS.forEach(evt => {
                document.addEventListener(evt, resetTimer, { passive: true });
            });
            resetTimer();
        });
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
