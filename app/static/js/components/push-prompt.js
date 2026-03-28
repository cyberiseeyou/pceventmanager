/**
 * Push Notification Permission Prompt
 * Shows a soft banner on the dashboard for specialist/lead roles
 * asking them to enable push notifications for schedule changes.
 */
(function () {
    'use strict';

    // Don't show if already dismissed
    if (localStorage.getItem('push_prompt_dismissed')) return;

    // Don't show if browser doesn't support push
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;

    // Don't show if already granted — just ensure subscription
    if (Notification.permission === 'granted') {
        ensureSubscription();
        return;
    }

    // Don't show if explicitly denied
    if (Notification.permission === 'denied') return;

    // Show soft prompt after 2s delay
    setTimeout(showPromptBanner, 2000);

    function showPromptBanner() {
        const banner = document.createElement('div');
        banner.className = 'push-prompt';
        banner.innerHTML = `
            <div class="push-prompt__content">
                <span class="material-symbols-outlined push-prompt__icon">notifications_active</span>
                <div class="push-prompt__text">
                    <strong>Enable notifications</strong>
                    <span>Get alerted when your schedule changes</span>
                </div>
            </div>
            <div class="push-prompt__actions">
                <button class="push-prompt__btn push-prompt__btn--enable" id="pushEnable">Enable</button>
                <button class="push-prompt__btn push-prompt__btn--dismiss" id="pushDismiss">Not now</button>
            </div>
        `;

        // Inject styles
        const style = document.createElement('style');
        style.textContent = `
            .push-prompt {
                position: fixed;
                bottom: calc(68px + env(safe-area-inset-bottom, 0px));
                left: 50%;
                transform: translateX(-50%);
                width: calc(100% - 32px);
                max-width: 420px;
                background: #fff;
                border: 1px solid var(--color-neutral-200, #e5e7eb);
                border-radius: 12px;
                padding: 14px 16px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.12);
                z-index: 1000;
                animation: pushPromptSlideUp 0.3s ease-out;
            }
            @keyframes pushPromptSlideUp {
                from { transform: translateX(-50%) translateY(20px); opacity: 0; }
                to { transform: translateX(-50%) translateY(0); opacity: 1; }
            }
            .push-prompt__content {
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 12px;
            }
            .push-prompt__icon {
                font-size: 28px;
                color: #2E4C73;
            }
            .push-prompt__text {
                display: flex;
                flex-direction: column;
                gap: 2px;
            }
            .push-prompt__text strong {
                font-size: 14px;
                color: #1f2937;
            }
            .push-prompt__text span {
                font-size: 12px;
                color: #6b7280;
            }
            .push-prompt__actions {
                display: flex;
                gap: 8px;
                justify-content: flex-end;
            }
            .push-prompt__btn {
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 600;
                cursor: pointer;
                font-family: inherit;
            }
            .push-prompt__btn--enable {
                background: #2E4C73;
                color: #fff;
            }
            .push-prompt__btn--dismiss {
                background: transparent;
                color: #6b7280;
            }
        `;
        document.head.appendChild(style);
        document.body.appendChild(banner);

        document.getElementById('pushEnable').addEventListener('click', async () => {
            banner.remove();
            const permission = await Notification.requestPermission();
            if (permission === 'granted') {
                await ensureSubscription();
            }
            localStorage.setItem('push_prompt_dismissed', 'true');
        });

        document.getElementById('pushDismiss').addEventListener('click', () => {
            banner.remove();
            localStorage.setItem('push_prompt_dismissed', 'true');
        });
    }

    async function ensureSubscription() {
        try {
            const reg = await navigator.serviceWorker.ready;

            // Get VAPID public key
            const keyResp = await fetch('/api/push/vapid-public-key');
            if (!keyResp.ok) return;
            const { public_key } = await keyResp.json();
            if (!public_key) return;

            const sub = await reg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(public_key),
            });

            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
            await fetch('/api/push/subscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
                },
                body: JSON.stringify(sub.toJSON()),
            });
        } catch (e) {
            console.warn('[PushPrompt] Subscription failed:', e);
        }
    }

    function urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
        const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
        const rawData = atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }
})();
