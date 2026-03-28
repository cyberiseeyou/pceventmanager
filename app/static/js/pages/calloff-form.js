/**
 * Calloff Form — Employee PWA form for reporting same-day/next-day calloffs.
 */
(function () {
    'use strict';

    const form = document.getElementById('calloffForm');
    const dateInput = document.getElementById('calloffDate');
    const reasonSelect = document.getElementById('calloffReason');
    const doctorWarning = document.getElementById('doctorNoteWarning');
    const affectedEventsEl = document.getElementById('affectedEvents');
    const submitBtn = document.getElementById('submitBtn');
    const messageEl = document.getElementById('formMessage');
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content
                   || document.querySelector('[name="csrf_token"]')?.value;

    // Date helpers
    function formatDate(d) {
        return d.toISOString().split('T')[0];
    }

    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    const dates = {
        today: formatDate(today),
        tomorrow: formatDate(tomorrow),
    };

    // Initialize with today selected
    dateInput.value = dates.today;
    document.getElementById('dateToday').textContent = `Today \u2014 ${today.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}`;
    document.getElementById('dateTomorrow').textContent = `Tomorrow`;

    // ── Date toggle ────────────────────────────────────────────

    document.querySelectorAll('.calloff-form__date-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.calloff-form__date-btn').forEach(function (b) { b.classList.remove('active'); });
            btn.classList.add('active');
            dateInput.value = dates[btn.dataset.date];
            fetchAffectedEvents();
        });
    });

    // ── Reason change → doctor's note warning ──────────────────

    reasonSelect.addEventListener('change', function () {
        doctorWarning.hidden = reasonSelect.value !== 'sick';
    });

    // ── Affected events preview ────────────────────────────────

    function fetchAffectedEvents() {
        if (!dateInput.value) return;

        affectedEventsEl.innerHTML = '<div class="calloff-form__events-loading"><span class="material-symbols-outlined">hourglass_empty</span> Checking schedule...</div>';

        fetch('/api/calloffs/affected-events?date=' + dateInput.value)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.events || data.events.length === 0) {
                    affectedEventsEl.innerHTML = '<div class="calloff-form__events-empty"><span class="material-symbols-outlined">event_available</span> No events scheduled for this day.</div>';
                    return;
                }

                var html = '<div class="calloff-form__events-list">';
                data.events.forEach(function (evt) {
                    html += '<div class="calloff-form__event-item">' +
                        '<div class="calloff-form__event-info">' +
                            '<div class="calloff-form__event-name">' + escapeHtml(evt.event_name) + '</div>' +
                            '<div class="calloff-form__event-time">' + escapeHtml(evt.time) + ' \u2014 ' + escapeHtml(evt.event_type) + '</div>' +
                        '</div>' +
                        '<span class="calloff-form__event-badge">Will be affected</span>' +
                    '</div>';
                });
                html += '</div>';
                html += '<p class="calloff-form__events-note">Your supervisor will be notified and can reassign these events.</p>';
                affectedEventsEl.innerHTML = html;
            })
            .catch(function () {
                affectedEventsEl.innerHTML = '<div class="calloff-form__events-empty">Unable to check schedule.</div>';
            });
    }

    // Initial load
    fetchAffectedEvents();

    // ── Form submission ────────────────────────────────────────

    form.addEventListener('submit', function (e) {
        e.preventDefault();

        if (!reasonSelect.value) {
            showMessage('Please select a reason.', 'error');
            return;
        }

        submitBtn.disabled = true;
        submitBtn.textContent = 'Submitting...';

        var body = {
            calloff_date: dateInput.value,
            reason: reasonSelect.value,
            notes: document.getElementById('calloffNotes').value.trim() || null,
        };

        fetch('/api/calloffs', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrfToken || '',
            },
            body: JSON.stringify(body),
        })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
        .then(function (result) {
            if (result.ok) {
                showMessage('Calloff submitted successfully. Your supervisor has been notified.', 'success');
                submitBtn.textContent = 'Submitted';
                // Redirect after short delay
                setTimeout(function () {
                    window.location.href = '/my-dashboard';
                }, 2000);
            } else {
                showMessage(result.data.error || 'Failed to submit calloff.', 'error');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Submit Calloff';
            }
        })
        .catch(function () {
            showMessage('Network error. Please try again.', 'error');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Submit Calloff';
        });
    });

    // ── Helpers ─────────────────────────────────────────────────

    function showMessage(text, type) {
        messageEl.textContent = text;
        messageEl.className = 'calloff-form__message calloff-form__message--' + type;
        messageEl.hidden = false;
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
})();
