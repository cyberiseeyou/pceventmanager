/**
 * Calloff Management — Supervisor dashboard for reviewing calloffs.
 */
(function () {
    'use strict';

    var csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
    var activeTab = 'pending';
    var currentUploadCalloffId = null;
    var currentCommentCalloffId = null;

    // ── Tab switching ──────────────────────────────────────────

    document.querySelectorAll('.calloff-mgmt__tab').forEach(function (tab) {
        tab.addEventListener('click', function () {
            document.querySelectorAll('.calloff-mgmt__tab').forEach(function (t) {
                t.classList.remove('active');
                t.setAttribute('aria-selected', 'false');
            });
            tab.classList.add('active');
            tab.setAttribute('aria-selected', 'true');

            activeTab = tab.dataset.tab;
            document.querySelectorAll('.calloff-mgmt__panel').forEach(function (p) { p.hidden = true; });
            document.getElementById('panel-' + activeTab).hidden = false;

            if (activeTab === 'pending') loadPending();
            else if (activeTab === 'all') loadAll();
            else if (activeTab === 'patterns') loadPatterns();
        });
    });

    // ── Load data ──────────────────────────────────────────────

    function loadPending() {
        fetch('/api/calloffs?status=pending')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var list = document.getElementById('pendingList');
                var calloffs = data.calloffs || [];

                var badge = document.getElementById('pendingBadge');
                badge.textContent = calloffs.length;
                badge.hidden = calloffs.length === 0;

                if (calloffs.length === 0) {
                    list.innerHTML = '<div class="calloff-mgmt__empty"><span class="material-symbols-outlined">check_circle</span> No pending calloffs.</div>';
                    return;
                }

                list.innerHTML = calloffs.map(function (c) { return renderCalloffCard(c, true); }).join('');
                attachCardActions(list);
            })
            .catch(function () {
                document.getElementById('pendingList').innerHTML = '<div class="calloff-mgmt__empty">Failed to load calloffs.</div>';
            });
    }

    function loadAll() {
        var params = new URLSearchParams();
        var empFilter = document.getElementById('filterEmployee').value;
        if (empFilter) params.set('employee_id', empFilter);
        var statusFilter = document.getElementById('filterStatus').value;
        if (statusFilter) params.set('status', statusFilter);
        var reasonFilter = document.getElementById('filterReason').value;
        if (reasonFilter) params.set('reason', reasonFilter);

        fetch('/api/calloffs?' + params.toString())
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var list = document.getElementById('allList');
                var calloffs = data.calloffs || [];
                if (calloffs.length === 0) {
                    list.innerHTML = '<div class="calloff-mgmt__empty">No calloffs found.</div>';
                    return;
                }
                list.innerHTML = calloffs.map(function (c) { return renderCalloffCard(c, false); }).join('');
                attachCardActions(list);
            });
    }

    function loadPatterns() {
        var days = document.getElementById('filterDays').value || 30;
        fetch('/api/calloffs/patterns?days=' + days)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var container = document.getElementById('patternsContent');
                var employees = data.employees || [];
                if (employees.length === 0) {
                    container.innerHTML = '<div class="calloff-mgmt__empty">No calloffs in this period.</div>';
                    return;
                }

                var html = employees.map(function (emp) {
                    var alertClass = emp.alert ? 'calloff-pattern--alert' : '';
                    var countColor = emp.alert ? 'color:#dc2626;font-weight:600' : 'color:#16a34a';
                    var daysHtml = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'].map(function (d) {
                        var count = emp.by_day_of_week[d] || 0;
                        var opacity = count > 0 ? Math.min(0.3 + count * 0.25, 1) : 0.08;
                        return '<div class="calloff-pattern__day" style="opacity:' + opacity + '" title="' + d + ': ' + count + '">' + d.charAt(0) + '</div>';
                    }).join('');

                    return '<div class="calloff-pattern ' + alertClass + '">' +
                        '<div class="calloff-pattern__header">' +
                            '<strong>' + escapeHtml(emp.name) + '</strong>' +
                            '<span style="' + countColor + '">' + emp.total_calloffs + ' calloff' + (emp.total_calloffs !== 1 ? 's' : '') + '</span>' +
                        '</div>' +
                        '<div class="calloff-pattern__details">' +
                            '<div class="calloff-pattern__reasons">' + Object.entries(emp.by_reason).map(function (e) {
                                return '<span class="calloff-pattern__reason-tag">' + escapeHtml(reasonLabel(e[0])) + ': ' + e[1] + '</span>';
                            }).join(' ') + '</div>' +
                            '<div class="calloff-pattern__days">' + daysHtml + '</div>' +
                        '</div>' +
                        (emp.alert ? '<div class="calloff-pattern__alert-banner">\u26a0\ufe0f ' + escapeHtml(emp.alert_reason) + '</div>' : '') +
                    '</div>';
                }).join('');

                container.innerHTML = html;
            });
    }

    // ── Card rendering ─────────────────────────────────────────

    var REASON_LABELS = { sick: 'Sick / Illness', family_emergency: 'Family Emergency', personal: 'Personal', other: 'Other' };
    function reasonLabel(r) { return REASON_LABELS[r] || r; }

    var STATUS_BADGES = {
        pending: '<span class="calloff-status calloff-status--pending">\u23f3 Pending</span>',
        excused: '<span class="calloff-status calloff-status--excused">\u2713 Excused</span>',
        unexcused: '<span class="calloff-status calloff-status--unexcused">\u2717 Unexcused</span>',
    };

    function renderCalloffCard(c, showActions) {
        var isNew = c.created_at && (Date.now() - new Date(c.created_at).getTime()) < 3600000;
        var countStyle = c.pattern_alert ? 'color:#dc2626;font-weight:600' : 'color:#16a34a';

        var eventsHtml = '';
        if (c.affected_events && c.affected_events.length > 0) {
            eventsHtml = '<div class="calloff-card__events">' +
                '<div class="calloff-card__events-label">Affected Events (' + c.affected_events.length + ')</div>' +
                c.affected_events.map(function (e) {
                    return '<span class="calloff-card__event-tag">' + escapeHtml(e.event_type) + ' \u2014 ' + escapeHtml(e.time) + '</span>';
                }).join(' ') +
            '</div>';
        }

        var attachmentsHtml = '';
        if (c.attachments && c.attachments.length > 0) {
            attachmentsHtml = '<div class="calloff-card__attachments">' +
                '<div class="calloff-card__events-label">\ud83d\udcce Attachments</div>' +
                c.attachments.map(function (a) {
                    return '<a href="/api/calloffs/' + c.id + '/attachments/' + a.id + '/download" class="calloff-card__attachment-link">' + escapeHtml(a.filename) + '</a>';
                }).join(' ') +
            '</div>';
        }

        var actionsHtml = '';
        if (showActions && c.status === 'pending') {
            actionsHtml = '<div class="calloff-card__actions">' +
                '<button class="calloff-card__btn calloff-card__btn--excused" data-action="review" data-id="' + c.id + '" data-status="excused">\u2713 Mark Excused</button>' +
                '<button class="calloff-card__btn calloff-card__btn--unexcused" data-action="review" data-id="' + c.id + '" data-status="unexcused">\u2717 Mark Unexcused</button>' +
                '<button class="calloff-card__btn calloff-card__btn--secondary" data-action="upload" data-id="' + c.id + '">\ud83d\udcce Upload</button>' +
                '<button class="calloff-card__btn calloff-card__btn--secondary" data-action="comment" data-id="' + c.id + '">\ud83d\udcac Comment</button>' +
                (eventsHtml ? '<button class="calloff-card__btn calloff-card__btn--resolve" data-action="resolve" data-id="' + c.id + '">Unschedule Events</button>' : '') +
            '</div>';
        }

        var sickWarning = c.reason === 'sick' ? '<div class="calloff-card__sick-warning">\ud83d\udccb Doctor\'s note required upon return</div>' : '';

        return '<div class="calloff-card' + (c.status === 'pending' ? ' calloff-card--pending' : '') + '">' +
            '<div class="calloff-card__header">' +
                '<div class="calloff-card__employee">' +
                    '<div class="calloff-card__avatar">' + initials(c.employee_name) + '</div>' +
                    '<div>' +
                        '<div class="calloff-card__name">' + escapeHtml(c.employee_name || 'Unknown') + '</div>' +
                        '<div class="calloff-card__meta">Submitted ' + formatTimestamp(c.created_at) + '</div>' +
                    '</div>' +
                '</div>' +
                '<div class="calloff-card__badges">' +
                    (STATUS_BADGES[c.status] || '') +
                    (isNew ? '<span class="calloff-status calloff-status--new">NEW</span>' : '') +
                '</div>' +
            '</div>' +
            '<div class="calloff-card__body">' +
                '<div class="calloff-card__grid">' +
                    '<div><div class="calloff-card__label">Date</div><div class="calloff-card__value">' + escapeHtml(c.calloff_date) + '</div></div>' +
                    '<div><div class="calloff-card__label">Reason</div><div class="calloff-card__value">' + escapeHtml(c.reason_label || reasonLabel(c.reason)) + '</div></div>' +
                    '<div><div class="calloff-card__label">30-Day Count</div><div class="calloff-card__value" style="' + countStyle + '">' + (c.calloff_count_30d || 0) + ' calloff' + ((c.calloff_count_30d || 0) !== 1 ? 's' : '') + (c.pattern_alert ? ' \u26a0\ufe0f' : '') + '</div></div>' +
                '</div>' +
                (c.notes ? '<div class="calloff-card__notes"><div class="calloff-card__label">Employee Notes</div><div class="calloff-card__notes-text">' + escapeHtml(c.notes) + '</div></div>' : '') +
                (c.supervisor_comments ? '<div class="calloff-card__notes"><div class="calloff-card__label">Supervisor Comments</div><div class="calloff-card__notes-text">' + escapeHtml(c.supervisor_comments) + '</div></div>' : '') +
                sickWarning +
                eventsHtml +
                attachmentsHtml +
            '</div>' +
            actionsHtml +
        '</div>';
    }

    // ── Card actions ───────────────────────────────────────────

    function attachCardActions(container) {
        container.querySelectorAll('[data-action="review"]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                reviewCalloff(btn.dataset.id, btn.dataset.status);
            });
        });
        container.querySelectorAll('[data-action="upload"]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                currentUploadCalloffId = btn.dataset.id;
                document.getElementById('uploadFile').value = '';
                document.getElementById('uploadModal').hidden = false;
            });
        });
        container.querySelectorAll('[data-action="comment"]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                currentCommentCalloffId = btn.dataset.id;
                document.getElementById('commentText').value = '';
                document.getElementById('commentModal').hidden = false;
            });
        });
        container.querySelectorAll('[data-action="resolve"]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                resolveCalloff(btn.dataset.id);
            });
        });
    }

    function reviewCalloff(id, status) {
        if (!confirm('Mark this calloff as ' + status + '?')) return;

        fetch('/api/calloffs/' + id + '/review', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
            body: JSON.stringify({ status: status }),
        })
        .then(function (r) { return r.json(); })
        .then(function () { loadPending(); })
        .catch(function (e) { alert('Review failed: ' + e.message); });
    }

    function resolveCalloff(id) {
        if (!confirm('Unschedule all affected events for this calloff?')) return;

        fetch('/api/calloffs/' + id + '/resolve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
            body: JSON.stringify({ action: 'unschedule_all' }),
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            alert('Unscheduled ' + (data.unscheduled_count || 0) + ' event(s).');
            loadPending();
        })
        .catch(function (e) { alert('Resolve failed: ' + e.message); });
    }

    // ── Upload modal ───────────────────────────────────────────

    document.getElementById('uploadSubmit').addEventListener('click', function () {
        var file = document.getElementById('uploadFile').files[0];
        if (!file) { alert('Please select a file.'); return; }

        var formData = new FormData();
        formData.append('file', file);

        fetch('/api/calloffs/' + currentUploadCalloffId + '/attachments', {
            method: 'POST',
            headers: { 'X-CSRF-Token': csrfToken },
            body: formData,
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.status === 'success') {
                document.getElementById('uploadModal').hidden = true;
                loadPending();
            } else {
                alert(data.error || 'Upload failed');
            }
        })
        .catch(function () { alert('Upload failed.'); });
    });

    // ── Comment modal ──────────────────────────────────────────

    document.getElementById('commentSubmit').addEventListener('click', function () {
        var text = document.getElementById('commentText').value.trim();
        if (!text) { alert('Please enter a comment.'); return; }

        fetch('/api/calloffs/' + currentCommentCalloffId + '/review', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
            body: JSON.stringify({ status: 'pending', supervisor_comments: text }),
        })
        .then(function () {
            document.getElementById('commentModal').hidden = true;
            loadPending();
        })
        .catch(function () { alert('Failed to save comment.'); });
    });

    // ── Modal close ────────────────────────────────────────────

    document.querySelectorAll('[data-action="close-modal"]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.getElementById('uploadModal').hidden = true;
            document.getElementById('commentModal').hidden = true;
        });
    });

    // ── Filter changes ─────────────────────────────────────────

    document.getElementById('filterStatus')?.addEventListener('change', function () { if (activeTab === 'all') loadAll(); });
    document.getElementById('filterReason')?.addEventListener('change', function () { if (activeTab === 'all') loadAll(); });
    document.getElementById('filterDays')?.addEventListener('change', function () { if (activeTab === 'patterns') loadPatterns(); });
    document.getElementById('filterEmployee')?.addEventListener('change', function () {
        if (activeTab === 'all') loadAll();
    });

    // ── Load employee filter options ───────────────────────────

    fetch('/api/employees')
        .then(function (r) { return r.json(); })
        .then(function (data) {
            var select = document.getElementById('filterEmployee');
            var employees = data.employees || data.data || [];
            employees.forEach(function (emp) {
                var opt = document.createElement('option');
                opt.value = emp.id;
                opt.textContent = emp.name;
                select.appendChild(opt);
            });
        })
        .catch(function () {});

    // ── Helpers ─────────────────────────────────────────────────

    function initials(name) {
        if (!name) return '?';
        return name.split(' ').map(function (w) { return w[0]; }).join('').toUpperCase().slice(0, 2);
    }

    function formatTimestamp(ts) {
        if (!ts) return '';
        var d = new Date(ts);
        return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    }

    function escapeHtml(str) {
        if (!str) return '';
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // ── Initial load ───────────────────────────────────────────
    loadPending();
})();
