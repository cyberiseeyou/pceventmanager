/**
 * Note Notification System
 *
 * Polls for due notes every 60 seconds and shows a blocking slide-in
 * modal for each. User must dismiss or snooze each note.
 *
 * Depends on: #noteNotificationOverlay (from note_notification_modal.html)
 * API: GET /api/notes/notifications/pending
 *       POST /api/notes/<id>/notification-sent
 *       POST /api/notes/<id>/snooze
 */
(function () {
    'use strict';

    const POLL_INTERVAL_MS = 60000; // 1 minute
    const PRIORITY_LABELS = {
        urgent: { text: 'Urgent', bg: '#FEE2E2', color: '#DC2626' },
        high:   { text: 'High',   bg: '#FEF3C7', color: '#D97706' },
        normal: { text: 'Normal', bg: '#DBEAFE', color: '#1E40AF' },
        low:    { text: 'Low',    bg: '#F3F4F6', color: '#6B7280' }
    };

    let overlay, panel, titleEl, descEl, dueTimeEl, metaEl, queueEl, dismissBtn;
    let queue = [];
    let currentNote = null;
    let pollTimer = null;
    let dismissedThisSession = new Set();

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function isAuthenticated() {
        // If no CSRF meta tag, we're on an unauthenticated page
        return !!document.querySelector('meta[name="csrf-token"]');
    }

    // ---- Polling ----

    function startPolling() {
        if (!isAuthenticated()) return;
        poll(); // immediate first check
        pollTimer = setInterval(poll, POLL_INTERVAL_MS);
    }

    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    async function poll() {
        try {
            const response = await fetch('/api/notes/notifications/pending');

            if (response.status === 401 || response.status === 403) {
                stopPolling();
                return;
            }

            if (!response.ok) return;

            const data = await response.json();
            if (!data.success || !data.notifications || data.notifications.length === 0) return;

            // Add new notes to queue (dedup by ID and skip dismissed this session)
            const currentIds = new Set(queue.map(n => n.id));
            if (currentNote) currentIds.add(currentNote.id);

            data.notifications.forEach(function (note) {
                if (!currentIds.has(note.id) && !dismissedThisSession.has(note.id)) {
                    queue.push(note);
                }
            });

            // Show modal if not already showing
            if (!currentNote && queue.length > 0) {
                showNext();
            } else if (currentNote) {
                updateQueueIndicator();
            }
        } catch (err) {
            console.error('[NoteNotif] Poll error:', err);
        }
    }

    // ---- Modal display ----

    function showNext() {
        if (queue.length === 0) {
            hideModal();
            currentNote = null;
            return;
        }

        currentNote = queue.shift();
        renderNote(currentNote);
        showModal();
    }

    function renderNote(note) {
        if (!titleEl) return;

        titleEl.textContent = note.title || 'Note Reminder';
        descEl.textContent = note.content || '';
        descEl.style.display = note.content ? '' : 'none';

        // Due time display
        if (note.is_overdue) {
            dueTimeEl.textContent = 'Overdue — ' + (note.due_date || '');
            dueTimeEl.style.color = '#DC2626';
        } else if (note.due_time) {
            dueTimeEl.textContent = 'Due now — ' + formatTime(note.due_time);
            dueTimeEl.style.color = '#6B7280';
        } else {
            dueTimeEl.textContent = 'Due today';
            dueTimeEl.style.color = '#6B7280';
        }

        // Meta badges
        var metaHtml = '';
        var p = PRIORITY_LABELS[note.priority] || PRIORITY_LABELS.normal;
        metaHtml += '<span style="background:' + p.bg + '; color:' + p.color +
            '; font-size:11px; padding:2px 8px; border-radius:4px; font-weight:600;">' +
            p.text + '</span>';

        if (note.linked_event_ref_num) {
            metaHtml += '<span style="background:#DBEAFE; color:#1E40AF; font-size:11px; padding:2px 8px; border-radius:4px;">' +
                '📋 Event #' + note.linked_event_ref_num + '</span>';
        }
        if (note.linked_employee_id) {
            metaHtml += '<span style="background:#D1FAE5; color:#065F46; font-size:11px; padding:2px 8px; border-radius:4px;">' +
                '👤 ' + note.linked_employee_id + '</span>';
        }
        if (note.display_type) {
            metaHtml += '<span style="color:#9CA3AF; font-size:11px; padding:2px 0;">' +
                note.display_type + '</span>';
        }
        metaEl.innerHTML = metaHtml;

        updateQueueIndicator();
    }

    function updateQueueIndicator() {
        if (!queueEl) return;
        if (queue.length > 0) {
            queueEl.textContent = (queue.length + 1) + ' reminders — showing 1 of ' + (queue.length + 1);
            queueEl.style.display = '';
        } else {
            queueEl.style.display = 'none';
        }
    }

    function formatTime(timeStr) {
        if (!timeStr) return '';
        var parts = timeStr.split(':');
        var h = parseInt(parts[0], 10);
        var m = parts[1];
        var ampm = h >= 12 ? 'PM' : 'AM';
        h = h % 12 || 12;
        return h + ':' + m + ' ' + ampm;
    }

    function showModal() {
        if (!overlay) return;
        overlay.style.display = '';
        // Force reflow before adding class for transition
        overlay.offsetHeight;
        overlay.classList.add('visible');
    }

    function hideModal() {
        if (!overlay) return;
        overlay.classList.remove('visible');
        setTimeout(function () {
            overlay.style.display = 'none';
        }, 300);
    }

    // ---- Actions ----

    async function dismiss() {
        if (!currentNote) return;
        var noteId = currentNote.id;
        dismissedThisSession.add(noteId);

        try {
            await fetch('/api/notes/' + noteId + '/notification-sent', {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken() }
            });
        } catch (err) {
            console.error('[NoteNotif] Dismiss error:', err);
        }

        showNext();
    }

    async function snooze(duration) {
        if (!currentNote) return;
        var noteId = currentNote.id;
        dismissedThisSession.add(noteId); // Don't re-show this session

        try {
            await fetch('/api/notes/' + noteId + '/snooze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({ duration: duration })
            });
        } catch (err) {
            console.error('[NoteNotif] Snooze error:', err);
        }

        showNext();
    }

    // ---- Init ----

    document.addEventListener('DOMContentLoaded', function () {
        overlay = document.getElementById('noteNotificationOverlay');
        if (!overlay) return;

        panel = document.getElementById('noteNotificationPanel');
        titleEl = document.getElementById('noteNotifTitle');
        descEl = document.getElementById('noteNotifDesc');
        dueTimeEl = document.getElementById('noteNotifDueTime');
        metaEl = document.getElementById('noteNotifMeta');
        queueEl = document.getElementById('noteNotifQueue');
        dismissBtn = document.getElementById('noteNotifDismissBtn');

        // Dismiss button
        if (dismissBtn) {
            dismissBtn.addEventListener('click', dismiss);
        }

        // Snooze buttons
        document.querySelectorAll('.snooze-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var duration = parseInt(this.getAttribute('data-duration'), 10);
                snooze(duration);
            });
        });

        startPolling();
    });
})();
