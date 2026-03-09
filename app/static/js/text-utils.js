/**
 * Shared text utility functions loaded globally via base.html.
 */

/**
 * Convert a string to Title Case for consistent name display.
 * @param {string|null|undefined} text - Raw text to convert
 * @returns {string} Title-cased string, or empty string if input is null/undefined
 */
function toTitleCase(text) {
    if (text == null) return '';
    return String(text).toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
}

/**
 * Escape HTML special characters to prevent XSS.
 * @param {string|null|undefined} text - Raw text to escape
 * @returns {string} HTML-safe string, or empty string if input is null/undefined
 */
function escapeHtml(text) {
    if (text == null) return '';
    return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}
