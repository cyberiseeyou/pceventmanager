/**
 * Fix Wizard - Interactive schedule issue resolver
 *
 * Walks through validation issues one-by-one, presenting numbered fix options.
 * AI Assist mode pre-selects the highest-confidence option.
 *
 * Follows project patterns: data-action delegation, fetch() for API,
 * escapeHtml() for XSS protection.
 */
(function () {
    'use strict';

    function escapeHtml(text) {
        if (text == null) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    var state = {
        issues: [],
        currentIndex: 0,
        selectedOption: null,
        appliedFixes: [],
        skippedCount: 0,
        aiAssistEnabled: true
    };

    var root = document.getElementById('wizard-root');
    var config = window.WIZARD_CONFIG || {};

    function showError(message) {
        var el = document.getElementById('wizard-error');
        if (!el) {
            el = document.createElement('div');
            el.id = 'wizard-error';
            el.className = 'alert alert-danger mt-2';
            el.setAttribute('role', 'alert');
            root.prepend(el);
        }
        el.textContent = message;
        el.style.display = 'block';
        setTimeout(function () { el.style.display = 'none'; }, 8000);
    }

    var ACTION_ICONS = {
        reassign: 'fa-user-edit',
        unschedule: 'fa-times-circle',
        reschedule: 'fa-clock',
        assign_supervisor: 'fa-user-tie',
        ignore: 'fa-eye-slash',
        trade: 'fa-exchange-alt'
    };

    function init() {
        fetchIssues();
    }

    function fetchIssues() {
        var url = config.issuesUrl + '?start_date=' + encodeURIComponent(config.startDate);
        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.status === 'success') {
                    state.issues = data.issues || [];
                    state.currentIndex = 0;
                    state.selectedOption = null;
                    if (state.issues.length === 0) {
                        showEmpty();
                    } else {
                        renderCurrentIssue();
                    }
                } else {
                    showFatalError(data.error || 'Failed to load issues');
                }
            })
            .catch(function (err) {
                showFatalError('Network error: ' + err.message);
            });
    }

    function renderCurrentIssue() {
        var issue = state.issues[state.currentIndex];
        if (!issue) {
            showSummary();
            return;
        }

        state.selectedOption = null;
        var total = state.issues.length;
        var current = state.currentIndex + 1;
        var pct = Math.round((state.currentIndex / total) * 100);

        var html = '';

        // Progress section
        html += '<div class="progress-section">';
        html += '  <span class="progress-text">Issue ' + current + ' of ' + total + '</span>';
        html += '  <div class="progress-bar-container">';
        html += '    <div class="progress-bar-fill" style="width:' + pct + '%"></div>';
        html += '  </div>';
        html += '  <div class="ai-toggle">';
        html += '    <input type="checkbox" id="ai-assist-toggle" ' + (state.aiAssistEnabled ? 'checked' : '') + ' data-action="toggle-ai">';
        html += '    <label for="ai-assist-toggle">AI Assist</label>';
        html += '  </div>';
        html += '</div>';

        // Issue card
        var iss = issue.issue;
        var severity = escapeHtml(iss.severity);
        var ruleName = escapeHtml(iss.rule_name);
        var message = escapeHtml(iss.message);
        var dateStr = issue.date ? escapeHtml(issue.date) : 'Weekly';

        html += '<div class="issue-card">';
        html += '  <div class="issue-card-header">';
        html += '    <span class="severity-badge ' + severity + '">' + severity + '</span>';
        html += '    <span class="issue-rule">' + ruleName + '</span>';
        html += '    <span class="issue-date"><i class="fas fa-calendar"></i> ' + dateStr + '</span>';
        html += '  </div>';
        html += '  <div class="issue-card-body">';
        html += '    <div class="issue-message">' + message + '</div>';

        // Details
        var details = iss.details || {};
        html += '    <div class="issue-details">';
        if (details.employee_name) {
            html += '      <span><i class="fas fa-user"></i> ' + escapeHtml(details.employee_name) + '</span>';
        }
        if (details.event_name) {
            html += '      <span><i class="fas fa-calendar-check"></i> ' + escapeHtml(details.event_name) + '</span>';
        }
        html += '    </div>';

        // Options
        html += renderFixOptions(issue.options);

        html += '  </div>';

        // Action buttons
        html += '  <div class="action-btns">';
        html += '    <button class="btn-apply" id="btn-apply" data-action="wizard-apply" disabled>';
        html += '      <i class="fas fa-check"></i> Apply Fix';
        html += '    </button>';
        html += '    <button class="btn-skip" data-action="wizard-skip">';
        html += '      <i class="fas fa-forward"></i> Skip';
        html += '    </button>';
        html += '  </div>';
        html += '</div>';

        // Keyboard hints
        html += '<div class="keyboard-hint">';
        html += '  <kbd>1</kbd>-<kbd>9</kbd> select option &middot; <kbd>Enter</kbd> apply &middot; <kbd>Esc</kbd> skip';
        html += '</div>';

        root.innerHTML = html;

        // AI assist: auto-select recommended
        if (state.aiAssistEnabled) {
            var recIdx = -1;
            for (var i = 0; i < issue.options.length; i++) {
                if (issue.options[i].is_recommended) {
                    recIdx = i;
                    break;
                }
            }
            if (recIdx >= 0) {
                selectOption(recIdx);
            }
        }
    }

    function renderFixOptions(options) {
        if (!options || options.length === 0) return '';

        var html = '<div class="options-header">Fix Options</div>';
        html += '<div class="option-cards">';

        for (var i = 0; i < options.length; i++) {
            var opt = options[i];
            var icon = ACTION_ICONS[opt.action_type] || 'fa-wrench';
            var isRecommended = opt.is_recommended;
            var classes = 'option-card';
            if (isRecommended) classes += ' recommended';

            var confLevel = opt.confidence >= 60 ? 'high' : (opt.confidence >= 30 ? 'medium' : 'low');

            html += '<div class="' + classes + '" data-action="select-option" data-option-index="' + i + '">';
            html += '  <span class="option-num">' + (i + 1) + '</span>';
            html += '  <i class="fas ' + escapeHtml(icon) + ' option-icon"></i>';
            html += '  <div class="option-body">';
            html += '    <div class="option-desc">' + escapeHtml(opt.description) + '</div>';
            if (isRecommended) {
                html += '    <div class="option-badges"><span class="recommended-badge"><i class="fas fa-robot"></i> AI Recommended</span></div>';
            }
            html += '  </div>';
            html += '  <div class="confidence-bar"><div class="confidence-fill ' + confLevel + '" style="width:' + opt.confidence + '%"></div></div>';
            html += '  <span class="confidence-text">' + opt.confidence + '</span>';
            html += '</div>';
        }

        html += '</div>';
        return html;
    }

    function selectOption(index) {
        state.selectedOption = index;

        // Update visual selection
        var cards = root.querySelectorAll('.option-card');
        for (var i = 0; i < cards.length; i++) {
            cards[i].classList.remove('selected');
        }
        if (cards[index]) {
            cards[index].classList.add('selected');
        }

        // Enable apply button
        var applyBtn = document.getElementById('btn-apply');
        if (applyBtn) {
            applyBtn.disabled = false;
        }
    }

    function applyFix() {
        if (state.selectedOption === null) return;

        var issue = state.issues[state.currentIndex];
        var option = issue.options[state.selectedOption];

        var applyBtn = document.getElementById('btn-apply');
        if (applyBtn) {
            applyBtn.disabled = true;
            applyBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Applying...';
        }

        fetch(config.applyUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.content || ''
            },
            body: JSON.stringify({
                action_type: option.action_type,
                target: option.target
            })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.status === 'success') {
                    state.appliedFixes.push({
                        issue: issue,
                        option: option,
                        result: data
                    });
                    advanceToNext();
                } else {
                    showError('Fix failed: ' + escapeHtml(data.error || 'Unknown error'));
                    if (applyBtn) {
                        applyBtn.disabled = false;
                        applyBtn.innerHTML = '<i class="fas fa-check"></i> Apply Fix';
                    }
                }
            })
            .catch(function (err) {
                showError('Network error: ' + escapeHtml(err.message));
                if (applyBtn) {
                    applyBtn.disabled = false;
                    applyBtn.innerHTML = '<i class="fas fa-check"></i> Apply Fix';
                }
            });
    }

    function skipIssue() {
        var issue = state.issues[state.currentIndex];

        fetch(config.skipUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.content || ''
            },
            body: JSON.stringify({
                rule_name: issue.issue.rule_name,
                details: issue.issue.details,
                date: issue.date,
                message: issue.issue.message,
                severity: issue.issue.severity
            })
        })
            .then(function (r) { return r.json(); })
            .then(function () {
                state.skippedCount++;
                advanceToNext();
            })
            .catch(function () {
                // Skip anyway on network error
                state.skippedCount++;
                advanceToNext();
            });
    }

    function advanceToNext() {
        state.currentIndex++;
        state.selectedOption = null;
        if (state.currentIndex >= state.issues.length) {
            showSummary();
        } else {
            renderCurrentIssue();
        }
    }

    function showEmpty() {
        root.innerHTML =
            '<div class="wizard-empty">' +
            '  <i class="fas fa-check-circle"></i>' +
            '  <h2>All Clear!</h2>' +
            '  <p>No fixable issues found for this week. Great job!</p>' +
            '</div>';
    }

    function showFatalError(msg) {
        root.innerHTML =
            '<div class="wizard-empty">' +
            '  <i class="fas fa-exclamation-triangle" style="color:#dc2626"></i>' +
            '  <h2>Error</h2>' +
            '  <p>' + escapeHtml(msg) + '</p>' +
            '</div>';
    }

    function showSummary() {
        var fixedCount = state.appliedFixes.length;
        var html = '<div class="wizard-summary">';
        html += '  <i class="fas fa-flag-checkered summary-icon"></i>';
        html += '  <h2>Wizard Complete</h2>';
        html += '  <p class="summary-subtitle">Reviewed all ' + state.issues.length + ' issues</p>';

        html += '  <div class="summary-stats">';
        html += '    <div class="summary-stat fixed"><div class="count">' + fixedCount + '</div><div class="label">Fixed</div></div>';
        html += '    <div class="summary-stat skipped"><div class="count">' + state.skippedCount + '</div><div class="label">Skipped</div></div>';
        html += '  </div>';

        if (fixedCount > 0) {
            html += '  <div class="summary-fixes">';
            html += '    <h3>Applied Fixes</h3>';
            for (var i = 0; i < state.appliedFixes.length; i++) {
                var f = state.appliedFixes[i];
                html += '    <div class="summary-fix-item">';
                html += '      <i class="fas fa-check-circle"></i>';
                html += '      <span>' + escapeHtml(f.option.description) + '</span>';
                html += '    </div>';
            }
            html += '  </div>';
        }

        html += '</div>';
        root.innerHTML = html;
    }

    // Event delegation
    document.addEventListener('click', function (e) {
        var el = e.target.closest('[data-action]');
        if (!el) return;

        var action = el.getAttribute('data-action');

        if (action === 'wizard-apply') {
            applyFix();
        } else if (action === 'wizard-skip') {
            skipIssue();
        } else if (action === 'select-option') {
            var idx = parseInt(el.getAttribute('data-option-index'), 10);
            if (!isNaN(idx)) selectOption(idx);
        } else if (action === 'toggle-ai') {
            state.aiAssistEnabled = el.checked;
        }
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', function (e) {
        // Don't capture if typing in an input
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        var issue = state.issues[state.currentIndex];
        if (!issue) return;

        // Number keys 1-9 select options
        var num = parseInt(e.key, 10);
        if (num >= 1 && num <= 9 && issue.options && num <= issue.options.length) {
            e.preventDefault();
            selectOption(num - 1);
            return;
        }

        // Enter applies
        if (e.key === 'Enter' && state.selectedOption !== null) {
            e.preventDefault();
            applyFix();
            return;
        }

        // Escape skips
        if (e.key === 'Escape') {
            e.preventDefault();
            skipIssue();
        }
    });

    // Start
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
