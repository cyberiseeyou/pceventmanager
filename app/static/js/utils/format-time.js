/**
 * Time Formatting Utility
 *
 * Shared utility for converting between 12-hour and 24-hour time formats.
 *
 * @module utils/format-time
 */

/**
 * Convert 24-hour time to 12-hour format for display
 *
 * @param {string} time24 - Time in 24-hour format (HH:MM)
 * @returns {string} Time in 12-hour format (e.g., "2:30 PM")
 *
 * @example
 * formatTime('14:30'); // "2:30 PM"
 * formatTime('00:00'); // "12:00 AM"
 * formatTime('12:00'); // "12:00 PM"
 */
export function formatTime(time24) {
    const [hours, minutes] = time24.split(':');
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
    return `${displayHour}:${minutes} ${ampm}`;
}

// Make available globally for non-module scripts
if (typeof window !== 'undefined') {
    window.formatTime = formatTime;
}
