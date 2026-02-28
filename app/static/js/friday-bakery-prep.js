/**
 * Friday Bakery Prep List – blocking modal flow.
 *
 * On page load (every page via base.html):
 *  1. GET /api/bakery-prep/friday-status
 *  2. If Friday + enabled + not completed + email configured → show modal
 *  3. Walk user through MFA auth → auto-send email → dismiss
 *
 * Steps: INIT → MFA_REQUEST → MFA_INPUT → AUTHENTICATING → SENDING → SUCCESS / ERROR
 */
(function () {
    'use strict';

    // DOM references (resolved after DOMContentLoaded)
    let modal, stepContent, mfaInputGroup, mfaCodeInput, progressEl, progressText, footer;

    // State
    let currentStep = 'INIT';
    let mfaAuthenticated = false;

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    // ---- UI helpers ----

    function showModal() {
        if (modal) {
            modal.style.display = 'flex';
            modal.classList.add('modal-open');
        }
    }

    function hideModal() {
        if (modal) {
            modal.style.display = 'none';
            modal.classList.remove('modal-open');
        }
    }

    function setStep(html) {
        if (stepContent) stepContent.innerHTML = html;
    }

    function showProgress(text) {
        if (progressEl) progressEl.style.display = 'block';
        if (progressText) progressText.textContent = text || 'Working...';
    }

    function hideProgress() {
        if (progressEl) progressEl.style.display = 'none';
    }

    function showMfaInput() {
        if (mfaInputGroup) mfaInputGroup.style.display = 'block';
        if (mfaCodeInput) { mfaCodeInput.value = ''; mfaCodeInput.focus(); }
    }

    function hideMfaInput() {
        if (mfaInputGroup) mfaInputGroup.style.display = 'none';
    }

    function setFooter(buttons) {
        if (!footer) return;
        footer.innerHTML = '';
        buttons.forEach(function (b) {
            var btn = document.createElement('button');
            btn.className = 'btn ' + (b.cls || 'btn-primary');
            btn.textContent = b.label;
            if (b.disabled) btn.disabled = true;
            btn.addEventListener('click', b.onClick);
            footer.appendChild(btn);
        });
    }

    // ---- Step handlers ----

    function goInit() {
        currentStep = 'INIT';
        setStep('<p style="font-size:1.05em;">The bakery needs the weekly prep list. ' +
            'This will authenticate with Walmart and email the list automatically.</p>');
        hideMfaInput();
        hideProgress();

        if (mfaAuthenticated) {
            // Already authed from a previous attempt, skip to sending
            goSending();
            return;
        }

        setFooter([
            { label: 'Start', cls: 'btn-primary', onClick: goMfaRequest }
        ]);
    }

    function goMfaRequest() {
        currentStep = 'MFA_REQUEST';
        setStep('<p>Requesting MFA code from Walmart...</p>');
        hideMfaInput();
        showProgress('Requesting MFA code...');
        setFooter([]);

        fetch('/printing/edr/request-mfa', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() }
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            hideProgress();
            if (data.success || data.mfa_required) {
                goMfaInput();
            } else {
                goError('Failed to request MFA: ' + (data.error || data.message || 'Unknown error'));
            }
        })
        .catch(function (err) {
            hideProgress();
            goError('Network error requesting MFA: ' + err.message);
        });
    }

    function goMfaInput() {
        currentStep = 'MFA_INPUT';
        setStep('<p>An MFA code has been sent to your phone. Enter it below to authenticate.</p>');
        showMfaInput();
        hideProgress();

        setFooter([
            { label: 'Submit Code', cls: 'btn-primary', onClick: goAuthenticating }
        ]);

        // Allow Enter key to submit
        if (mfaCodeInput) {
            mfaCodeInput.onkeydown = function (e) {
                if (e.key === 'Enter') goAuthenticating();
            };
        }
    }

    function goAuthenticating() {
        var code = mfaCodeInput ? mfaCodeInput.value.trim() : '';
        if (!code) return;

        currentStep = 'AUTHENTICATING';
        setStep('<p>Authenticating with Walmart...</p>');
        hideMfaInput();
        showProgress('Verifying MFA code...');
        setFooter([]);

        fetch('/printing/edr/authenticate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ mfa_code: code })
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            hideProgress();
            if (data.success) {
                mfaAuthenticated = true;
                goSending();
            } else {
                goError('Authentication failed: ' + (data.error || data.message || 'Invalid code'));
            }
        })
        .catch(function (err) {
            hideProgress();
            goError('Network error during authentication: ' + err.message);
        });
    }

    function goSending() {
        currentStep = 'SENDING';
        setStep('<p>Fetching bakery prep list and sending email...</p>');
        hideMfaInput();
        showProgress('Sending bakery prep email...');
        setFooter([]);

        fetch('/api/bakery-prep/send-email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() }
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            hideProgress();
            if (data.success) {
                goSuccess(data.message, data.total_items);
            } else {
                goError('Failed to send email: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(function (err) {
            hideProgress();
            goError('Network error sending email: ' + err.message);
        });
    }

    function goSuccess(message, totalItems) {
        currentStep = 'SUCCESS';
        var msg = message || 'Bakery prep list sent successfully!';
        if (totalItems !== undefined) {
            msg += ' (' + totalItems + ' items)';
        }
        setStep(
            '<div style="text-align:center;">' +
            '<span class="material-symbols-outlined" style="font-size:48px;color:#28a745;">check_circle</span>' +
            '<p style="font-size:1.1em;margin-top:10px;color:#28a745;font-weight:bold;">' + msg + '</p>' +
            '</div>'
        );
        hideMfaInput();
        hideProgress();
        setFooter([
            { label: 'Done', cls: 'btn-primary', onClick: hideModal }
        ]);
    }

    function goError(message) {
        currentStep = 'ERROR';
        setStep(
            '<div style="text-align:center;">' +
            '<span class="material-symbols-outlined" style="font-size:48px;color:#dc3545;">error</span>' +
            '<p style="color:#dc3545;margin-top:10px;">' + escapeHtml(message) + '</p>' +
            '</div>'
        );
        hideMfaInput();
        hideProgress();

        var buttons = [];
        // If MFA was already done, retry skips re-auth
        if (mfaAuthenticated) {
            buttons.push({ label: 'Retry Send', cls: 'btn-primary', onClick: goSending });
        } else {
            buttons.push({ label: 'Retry', cls: 'btn-primary', onClick: goMfaRequest });
        }
        buttons.push({ label: 'Skip for Now', cls: 'btn-secondary', onClick: hideModal });
        setFooter(buttons);
    }

    function goMissingConfig(emailConfigured, recipientsConfigured) {
        var issues = [];
        if (!emailConfigured) issues.push('SMTP email settings are not configured');
        if (!recipientsConfigured) issues.push('Bakery prep email recipients are not set');

        setStep(
            '<div style="text-align:center;">' +
            '<span class="material-symbols-outlined" style="font-size:48px;color:#f59e0b;">warning</span>' +
            '<p style="margin-top:10px;">' + issues.join('<br>') + '</p>' +
            '<p style="color:#666;margin-top:10px;">Please configure these in Settings before sending.</p>' +
            '</div>'
        );
        hideMfaInput();
        hideProgress();
        setFooter([
            { label: 'Go to Settings', cls: 'btn-primary', onClick: function () { window.location.href = '/settings'; } },
            { label: 'Dismiss', cls: 'btn-secondary', onClick: hideModal }
        ]);
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }

    // ---- Manual trigger (available globally) ----

    function manualSend() {
        if (!modal) return;
        mfaAuthenticated = false;

        // Check config before opening modal
        fetch('/api/bakery-prep/friday-status')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                showModal();
                if (!data.email_configured || !data.recipients_configured) {
                    goMissingConfig(data.email_configured, data.recipients_configured);
                } else {
                    goInit();
                }
            })
            .catch(function () {
                showModal();
                goInit();
            });
    }

    // Expose for use from settings page or anywhere
    window.triggerBakeryPrepSend = manualSend;

    // ---- Entry point ----

    document.addEventListener('DOMContentLoaded', function () {
        modal = document.getElementById('fridayBakeryPrepModal');
        stepContent = document.getElementById('bakeryPrepStepContent');
        mfaInputGroup = document.getElementById('bakeryPrepMfaInput');
        mfaCodeInput = document.getElementById('bakeryPrepMfaCode');
        progressEl = document.getElementById('bakeryPrepProgress');
        progressText = document.getElementById('bakeryPrepProgressText');
        footer = document.getElementById('bakeryPrepFooter');

        if (!modal) return;

        fetch('/api/bakery-prep/friday-status')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.is_friday || !data.is_enabled || data.is_completed) return;

                // Friday + enabled + not yet completed
                if (!data.email_configured || !data.recipients_configured) {
                    showModal();
                    goMissingConfig(data.email_configured, data.recipients_configured);
                    return;
                }

                showModal();
                goInit();
            })
            .catch(function (err) {
                console.error('[BakeryPrep] Status check failed:', err);
            });
    });
})();
