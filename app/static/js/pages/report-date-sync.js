/**
 * Report Date Range Sync
 * Keeps From/To date pickers constrained so the user can't pick
 * an end date before the start date or a start date after the end date.
 */
(function () {
    'use strict';
    var startInput = document.getElementById('start_date');
    var endInput = document.getElementById('end_date');
    if (!startInput || !endInput) return;

    startInput.addEventListener('change', function () {
        if (endInput.value && startInput.value > endInput.value) {
            endInput.value = startInput.value;
        }
        endInput.min = startInput.value;
    });

    endInput.addEventListener('change', function () {
        if (startInput.value && endInput.value < startInput.value) {
            startInput.value = endInput.value;
        }
        startInput.max = endInput.value;
    });

    // Set initial constraints
    if (startInput.value) endInput.min = startInput.value;
    if (endInput.value) startInput.max = endInput.value;
})();
